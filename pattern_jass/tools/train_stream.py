#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Disk-streaming logistic-regression trainer for the Scan-style pattern eval
(PJTW v3). The "Tier 2" fit: scales to tens-to-hundreds of millions of self-play
positions WITHOUT loading them into RAM.

Where the in-RAM trainers cap out:
  * train.py --lowmem    keeps the whole pattern sparse + raw extras in RAM  (~2.4M)
  * train.py --minibatch keeps the per-row data arrays (cols, extras) in RAM (~10-15M)
Both hold O(N) design data in memory. This trainer keeps in RAM ONLY tiny
per-row arrays (wdl/stm/phase, a few bytes each) plus a 68MB prune remap, and
RE-READS the bitboards + extras FROM DISK in `--chunk`-row blocks each L-BFGS
iteration. So peak RAM is ~O(chunk), independent of N; the cost is ~max_iter
full disk passes over --data + --feat.

It REUSES train.py's exact builders / fold logic / chunked-L-BFGS / expand /
writer, so the output .pjtw is byte-identical in layout to train.py's
`--scan-eval` output and the C++ ScanEvalNetwork loader accepts it unchanged.

JNNW record  : 38B = 4×uint64 (wm,wk,bm,bk) + uint8 stm + int32 score + int8 wdl
FEAT (extras): magic 'FEAT', uint32 cnt, uint32 k(=NUM_EXTRAS), float32[cnt*k]
"""

import argparse
import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

# Same sys.path dance as train.py: tools dir for master_loader/patterns/symmetry,
# plus the reset-proof external geometry dir if pinned.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_pgd = os.environ.get("JASS_PATTERNS_DIR")
if _pgd:
    sys.path.insert(0, _pgd)
import patterns                                    # noqa: E402
import train                                       # noqa: E402  (reuse builders/expand/writer)
import eval_phase                                  # noqa: E402  (shared fit/report phase path)
from train import (                                # noqa: E402
    CF_BUCKETS, colorfold_maps,
    build_sparse_X_phased, build_extras_phased,
    train_lbfgs_chunked, write_weights_v3,
    load_v3_weights_float,
    phase_wmg,
)

# JNNW / FEAT on-disk geometry.
JNNW_MAGIC = b'JNNW'
JNNW_HEADER_SIZE = 8
JNNW_RECORD_SIZE = 38
# np structured dtype matching the 38B record (little-endian, packed).
_JNNW_DTYPE = np.dtype([
    ('wm', '<u8'), ('wk', '<u8'), ('bm', '<u8'), ('bk', '<u8'),
    ('stm', 'u1'), ('score', '<i4'), ('wdl', 'i1'),
])
assert _JNNW_DTYPE.itemsize == JNNW_RECORD_SIZE

FEAT_MAGIC = b'FEAT'
FEAT_HEADER_SIZE = 12


# --------------------------------------------------------------------------- #
#  On-disk readers : seek + read a contiguous [i:i+n) row range, never the whole
#  file. memmap gives us cheap random-access slices without a full read.
# --------------------------------------------------------------------------- #
def open_jnnw(path: str):
    """Validate the JNNW header and return (memmap_of_records, n_records).
    The memmap is over the record body only; slicing it reads just those rows."""
    with open(path, 'rb') as f:
        head = f.read(JNNW_HEADER_SIZE)
    if head[:4] != JNNW_MAGIC:
        raise SystemExit(f'{path}: not a JNNW file (magic {head[:4]!r})')
    count = struct.unpack_from('<I', head, 4)[0]
    fsize = os.path.getsize(path)
    body = fsize - JNNW_HEADER_SIZE
    if body % JNNW_RECORD_SIZE != 0:
        raise SystemExit(f'{path}: body {body} not a multiple of {JNNW_RECORD_SIZE}')
    derived = body // JNNW_RECORD_SIZE
    if count != derived:
        raise SystemExit(f'{path}: header count {count} != file-derived {derived}')
    mm = np.memmap(path, dtype=_JNNW_DTYPE, mode='r',
                   offset=JNNW_HEADER_SIZE, shape=(count,))
    return mm, count


def open_feat(path: str, n_expected: int):
    """Validate the FEAT header (and alignment to --data) and return
    (memmap (n,k) float32, k). Values stay RAW (the playable-eval convention)."""
    with open(path, 'rb') as f:
        head = f.read(FEAT_HEADER_SIZE)
    if head[:4] != FEAT_MAGIC:
        raise SystemExit(f'{path}: not a FEAT file (magic {head[:4]!r})')
    cnt, k = struct.unpack_from('<II', head, 4)
    if cnt != n_expected:
        raise SystemExit(f'{path}: feature count {cnt} != data {n_expected}')
    fsize = os.path.getsize(path)
    need = FEAT_HEADER_SIZE + cnt * k * 4
    if fsize < need:
        raise SystemExit(f'{path}: file {fsize}B < expected {need}B (cnt={cnt} k={k})')
    mm = np.memmap(path, dtype='<f4', mode='r',
                   offset=FEAT_HEADER_SIZE, shape=(cnt, k))
    return mm, int(k)


# --------------------------------------------------------------------------- #
#  Optional per-row sample weights.  The contract is deliberately strict:
#  a NumPy vector aligned 1:1 with JNNW, validated but never clipped,
#  normalised on TRAIN rows only, and never applied to the holdout.
# --------------------------------------------------------------------------- #
_WEIGHT_QUANTILES = (
    ("p00", 0.00), ("p01", 0.01), ("p05", 0.05), ("p25", 0.25),
    ("p50", 0.50), ("p75", 0.75), ("p95", 0.95), ("p99", 0.99),
    ("p100", 1.00),
)


def _sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write_json(path: str | Path, payload: dict) -> None:
    target = Path(path)
    if target.exists():
        raise SystemExit(f"{target}: weights report already exists (no-clobber)")
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(
        f".{target.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        # os.replace would silently clobber a target created after the check
        # above. A same-directory hard-link publishes the complete temporary
        # inode atomically and fails if the target appeared concurrently.
        os.link(temporary, target)
    except FileExistsError as exc:
        if target.exists():
            raise SystemExit(
                f"{target}: weights report already exists (no-clobber)"
            ) from exc
        raise SystemExit(
            f"{target}: cannot create atomic weights-report temporary"
        ) from exc
    except OSError as exc:
        raise SystemExit(
            f"{target}: cannot atomically publish weights report: {exc}"
        ) from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


ERROR_REGION_SCHEMA = "jass.l3_curriculum_error_region.v1"


def _prepare_trainable_region(
    args,
    folder,
    remap: np.ndarray | None,
    pat_n: int,
    extras_n: int,
) -> tuple[np.ndarray | None, dict | None]:
    """Map an audited full-table error region into the current pruned layout.

    The region deliberately names *unfolded* full pattern columns.  This keeps
    the scientific artefact independent of the trainer's visit-order remap.
    Under exact fold both members of a true rot180+colour-swap orbit resolve to
    the same trainable coordinate.
    """
    region_path = getattr(args, "trainable_region", None)
    report_path = getattr(args, "trainable_region_report", None)
    if region_path is None:
        if report_path is not None:
            raise SystemExit("--trainable-region-report requires --trainable-region")
        return None, None
    if report_path is None:
        raise SystemExit("--trainable-region requires --trainable-region-report")
    if not getattr(args, "prior_mean", None):
        raise SystemExit("--trainable-region requires --prior-mean as the frozen champion")
    if folder.mode != "exact":
        raise SystemExit("--trainable-region v1 requires --exact-fold")
    if remap is None:
        raise SystemExit("--trainable-region requires the default lossless --prune path")
    if int(getattr(args, "prune_min_visits", 1)) != 1:
        raise SystemExit("--trainable-region requires --prune-min-visits 1")

    source = Path(region_path)
    try:
        region = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"{source}: cannot read trainable region: {exc}") from exc
    if not isinstance(region, dict) or region.get("schema") != ERROR_REGION_SCHEMA:
        raise SystemExit(f"{source}: expected schema {ERROR_REGION_SCHEMA}")
    if region.get("fold") != "exact_rot180_colour_swap":
        raise SystemExit(f"{source}: error region fold is not exact")
    if region.get("fit_authorized") is not True:
        raise SystemExit(f"{source}: error region did not authorize a fit")
    if region.get("promotion_authorized") is not False:
        raise SystemExit(f"{source}: error region promotion guard is not false")
    champion_sha256 = region.get("champion_sha256")
    if not isinstance(champion_sha256, str) or len(champion_sha256) != 64:
        raise SystemExit(f"{source}: missing authenticated champion_sha256")
    actual_champion_sha256 = _sha256_file(args.prior_mean)
    if champion_sha256 != actual_champion_sha256:
        raise SystemExit(
            f"{source}: champion hash mismatch: region={champion_sha256} "
            f"prior={actual_champion_sha256}"
        )
    contract = region.get("strict_fit_contract")
    if (
        not isinstance(contract, dict)
        or contract.get("freeze_everything_else_at_champion") is not True
    ):
        raise SystemExit(f"{source}: strict frozen-region contract is absent")
    if contract.get("train_dense_extras") is not False:
        raise SystemExit(f"{source}: v1 requires all dense extras to remain frozen")

    full_tb = patterns.TOTAL_BUCKETS
    raw_columns = region.get("pattern_columns_full")
    if (
        not isinstance(raw_columns, list)
        or not raw_columns
        or any(type(value) is not int for value in raw_columns)
    ):
        raise SystemExit(f"{source}: pattern_columns_full must be a non-empty int list")
    if len(raw_columns) != len(set(raw_columns)):
        raise SystemExit(f"{source}: duplicate full pattern column")
    confirmation = region.get("confirmation")
    if not isinstance(confirmation, list) or any(
        not isinstance(item, dict) or type(item.get("full_pattern_column")) is not int
        for item in confirmation
    ):
        raise SystemExit(f"{source}: malformed bucket confirmation evidence")
    confirmed = {int(item["full_pattern_column"]) for item in confirmation}
    if confirmed != set(raw_columns):
        raise SystemExit(f"{source}: selected buckets differ from confirmation evidence")
    raw = np.asarray(raw_columns, dtype=np.int64)
    if int(raw.min()) < 0 or int(raw.max()) >= full_tb:
        raise SystemExit(f"{source}: full pattern column outside [0,{full_tb})")
    pattern_id = raw // patterns.BUCKETS_PER_PATTERN
    bucket_id = raw % patterns.BUCKETS_PER_PATTERN
    canonical = folder.rf_canon[pattern_id, bucket_id].astype(np.int64)
    canonical = np.unique(canonical)
    dense = remap[canonical]
    missing = canonical[dense == 0]
    if len(missing):
        raise SystemExit(
            f"{source}: {len(missing)} confirmed canonical buckets are absent "
            "from the fit corpus; the error repair corpus is incomplete"
        )
    dense = np.unique(dense.astype(np.int64))
    if bool(np.any(dense <= 0)) or bool(np.any(dense >= pat_n)):
        raise SystemExit(f"{source}: internal dense bucket mapping failure")

    extras = region.get("extras", [])
    if not isinstance(extras, list) or any(type(value) is not int for value in extras):
        raise SystemExit(f"{source}: extras must be an integer list")
    if extras:
        raise SystemExit(f"{source}: v1 freezes all extras; extras must be empty")
    if len(extras) != len(set(extras)):
        raise SystemExit(f"{source}: duplicate extra coordinate")
    if extras and (min(extras) < 0 or max(extras) >= extras_n):
        raise SystemExit(f"{source}: extra coordinate outside [0,{extras_n})")

    mask = np.zeros(2 * pat_n + 2 * extras_n, dtype=bool)
    mask[dense] = True
    mask[pat_n + dense] = True
    if extras:
        ext = np.asarray(extras, dtype=np.int64)
        mask[2 * pat_n + ext] = True
        mask[2 * pat_n + extras_n + ext] = True
    prepared = {
        "schema": "jass.train_stream_trainable_region.v1",
        "source": {
            "path": str(source),
            "sha256": _sha256_file(source),
            "schema": ERROR_REGION_SCHEMA,
            "champion_sha256": champion_sha256,
        },
        "fold": folder.mode,
        "full_pattern_columns": len(raw_columns),
        "canonical_pattern_buckets": int(len(canonical)),
        "dense_pattern_slots": int(len(dense)),
        "extra_coordinates": len(extras),
        "trainable_coordinates": int(np.count_nonzero(mask)),
        "frozen_coordinates": int(len(mask) - np.count_nonzero(mask)),
        "canonical_pattern_buckets_list": [int(value) for value in canonical],
        "extra_coordinates_list": list(extras),
        "outside_region_contract": "byte_identical_to_prior_mean_after_serialization",
    }
    target = Path(report_path)
    protected = [source, Path(args.data), Path(args.feat), Path(args.out), Path(args.prior_mean)]
    if target.resolve(strict=False) in {
        path.resolve(strict=False) for path in protected
    }:
        raise SystemExit("--trainable-region-report must be distinct from every input/output")
    if target.exists():
        raise SystemExit(f"{target}: trainable region report already exists (no-clobber)")
    return mask, prepared


def _audit_frozen_region(
    args,
    folder,
    prepared: dict,
) -> dict:
    """Prove that serialization changed no coefficient outside the region."""
    parent, parent_scale, parent_pat_n, parent_ext_n = load_v3_weights_float(
        args.prior_mean
    )
    output, output_scale, output_pat_n, output_ext_n = load_v3_weights_float(args.out)
    if (parent_scale, parent_pat_n, parent_ext_n) != (
        output_scale,
        output_pat_n,
        output_ext_n,
    ):
        raise SystemExit("local refit output geometry/scale differs from frozen champion")
    canonical_active = np.zeros(patterns.TOTAL_BUCKETS, dtype=bool)
    canonical_active[np.asarray(
        prepared["canonical_pattern_buckets_list"], dtype=np.int64
    )] = True
    full_active = canonical_active[folder.rf_canon.ravel()]
    extra_active = np.zeros(parent_ext_n, dtype=bool)
    extra_active[np.asarray(prepared["extra_coordinates_list"], dtype=np.int64)] = True
    allowed = np.concatenate([full_active, full_active, extra_active, extra_active])
    changed = parent != output
    changed_outside = int(np.count_nonzero(changed & ~allowed))
    changed_inside = int(np.count_nonzero(changed & allowed))
    if changed_outside:
        raise SystemExit(
            f"strict local refit violated frozen region: {changed_outside} coefficients drifted"
        )
    return {
        **prepared,
        "parent": {"path": str(args.prior_mean), "sha256": _sha256_file(args.prior_mean)},
        "output": {"path": str(args.out), "sha256": _sha256_file(args.out)},
        "changed_inside_region": changed_inside,
        "changed_outside_region": changed_outside,
        "frozen_region_exact": True,
    }


def _validate_weights_report_target(args, weights_path: Path, report_path: str) -> Path:
    target = Path(report_path)
    target_resolved = target.resolve(strict=False)
    protected = (
        ("--sample-weights", weights_path),
        ("--data", getattr(args, "data", None)),
        ("--feat", getattr(args, "feat", None)),
        ("--out", getattr(args, "out", None)),
    )
    for flag, protected_path in protected:
        if protected_path is None:
            continue
        if target_resolved == Path(protected_path).resolve(strict=False):
            raise SystemExit(
                f"--weights-report must be distinct from {flag}: {target}"
            )
    if target.exists():
        raise SystemExit(f"{target}: weights report already exists (no-clobber)")
    return target


def _weight_stats(values: np.ndarray) -> dict:
    numeric = np.asarray(values, dtype=np.float64)
    if numeric.ndim != 1 or len(numeric) == 0:
        raise ValueError("weight statistics require a non-empty 1-D array")
    total = float(np.sum(numeric, dtype=np.float64))
    sum_squares = float(np.dot(numeric, numeric))
    quantile_values = np.quantile(
        numeric,
        [probability for _, probability in _WEIGHT_QUANTILES],
        method="linear",
    )
    return {
        "count": int(len(numeric)),
        "sum": total,
        "sum_squares": sum_squares,
        "mean": total / len(numeric),
        "min": float(np.min(numeric)),
        "max": float(np.max(numeric)),
        "quantiles": {
            name: float(value)
            for (name, _), value in zip(_WEIGHT_QUANTILES, quantile_values)
        },
    }


def _resolve_holdout(args, n_records: int) -> tuple[int, int]:
    hold_frac = float(getattr(args, "holdout_frac", 0.0) or 0.0)
    hold_count = int(getattr(args, "holdout_count", 0) or 0)
    if not np.isfinite(hold_frac) or hold_frac < 0.0 or hold_frac >= 1.0:
        raise SystemExit(
            f"--holdout-frac must be finite and in [0,1), got {hold_frac}"
        )
    if hold_count < 0 or hold_count >= n_records:
        raise SystemExit(
            f"--holdout-count must be in [0,{max(0, n_records - 1)}], "
            f"got {hold_count}"
        )
    if hold_count and hold_frac:
        raise SystemExit("--holdout-count and --holdout-frac are mutually exclusive")
    if hold_count:
        train_n = n_records - hold_count
        print(
            f"holdout : exact tail count={hold_count:,} "
            f"-> fit on {train_n:,} rows"
        )
    else:
        train_n = (
            int(round(n_records * (1.0 - hold_frac)))
            if hold_frac > 0.0
            else n_records
        )
        hold_count = n_records - train_n
        if hold_frac > 0.0:
            print(
                f"holdout : frac={hold_frac} -> fit on {train_n:,} rows, "
                f"val on {hold_count:,} rows"
            )
    if train_n <= 0:
        raise SystemExit("holdout leaves an empty train split")
    return train_n, hold_count


def _load_sample_weights(
    args,
    n_records: int,
    train_n: int,
    hold_count: int,
) -> tuple[np.ndarray | None, dict | None]:
    weights_path = getattr(args, "sample_weights", None)
    report_path = getattr(args, "weights_report", None)
    weight_min = getattr(args, "weight_min", None)
    weight_max = getattr(args, "weight_max", None)
    normalization = getattr(args, "weight_normalization", "mean-train-1")

    if not weights_path:
        if report_path is not None or weight_min is not None or weight_max is not None:
            raise SystemExit(
                "--weight-min/--weight-max/--weights-report require "
                "--sample-weights"
            )
        return None, None

    missing = [
        flag
        for flag, value in (
            ("--weight-min", weight_min),
            ("--weight-max", weight_max),
            ("--weights-report", report_path),
        )
        if value is None
    ]
    if missing:
        raise SystemExit("--sample-weights requires " + ", ".join(missing))
    if normalization != "mean-train-1":
        raise SystemExit(
            "--weight-normalization must be mean-train-1 when sample weights are used"
        )

    weight_min = float(weight_min)
    weight_max = float(weight_max)
    if (
        not np.isfinite(weight_min)
        or not np.isfinite(weight_max)
        or weight_min <= 0.0
        or weight_max < weight_min
    ):
        raise SystemExit(
            "--weight-min/--weight-max must be finite with "
            f"0 < min <= max, got {weight_min}/{weight_max}"
        )
    # Bounds describe float32 inputs.  Compare at that precision so a requested
    # decimal such as 0.1 accepts its exact float32 representation.
    bound_min32 = np.float32(weight_min)
    bound_max32 = np.float32(weight_max)
    if (
        not np.isfinite(bound_min32)
        or not np.isfinite(bound_max32)
        or bound_min32 <= 0.0
        or bound_max32 < bound_min32
    ):
        raise SystemExit("--weight-min/--weight-max are invalid at float32 precision")

    path = Path(weights_path)
    report_target = _validate_weights_report_target(args, path, report_path)
    try:
        raw = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise SystemExit(f"{path}: cannot load sample weights: {exc}") from exc
    if not isinstance(raw, np.ndarray) or raw.ndim != 1:
        raise SystemExit(
            f"{path}: sample weights must be a 1-D NumPy array, "
            f"got shape={getattr(raw, 'shape', None)}"
        )
    if raw.dtype != np.dtype(np.float32):
        raise SystemExit(
            f"{path}: sample weights dtype must be float32 exactly, got {raw.dtype}"
        )
    if raw.shape != (n_records,):
        raise SystemExit(
            f"{path}: sample weights length {len(raw)} != data records {n_records}"
        )
    if not bool(np.all(np.isfinite(raw))):
        raise SystemExit(f"{path}: sample weights contain NaN or infinity")
    if not bool(np.all(raw > 0.0)):
        raise SystemExit(f"{path}: sample weights must all be strictly positive")

    observed_min = float(np.min(raw))
    observed_max = float(np.max(raw))
    if observed_min < float(bound_min32) or observed_max > float(bound_max32):
        raise SystemExit(
            f"{path}: observed weight range [{observed_min}, {observed_max}] "
            f"outside validation bounds [{float(bound_min32)}, "
            f"{float(bound_max32)}]; weights are never clipped"
        )

    raw_train = np.asarray(raw[:train_n], dtype=np.float64)
    raw_train_mean = float(np.sum(raw_train, dtype=np.float64)) / train_n
    if not np.isfinite(raw_train_mean) or raw_train_mean <= 0.0:
        raise SystemExit(f"{path}: invalid mean over train sample weights")
    normalization_factor = 1.0 / raw_train_mean
    normalized_train = raw_train * normalization_factor
    normalized_mean = float(np.sum(normalized_train, dtype=np.float64)) / train_n
    if not np.isfinite(normalized_mean) or not np.isclose(
        normalized_mean, 1.0, rtol=0.0, atol=1e-12
    ):
        raise SystemExit(
            f"{path}: train-only normalization failed, mean={normalized_mean}"
        )

    # A constant positive vector becomes exactly the historical unweighted
    # objective after normalisation.  Keep sw_all=None so even floating-point
    # summation order remains byte-compatible with legacy fits.
    uniform_after_normalization = bool(
        float(np.min(raw_train)) == float(np.max(raw_train))
    )
    optimizer_sw_all = None
    if not uniform_after_normalization:
        optimizer_sw_all = np.asarray(raw, dtype=np.float64) * normalization_factor

    normalized_stats = _weight_stats(normalized_train)
    sum_weights = normalized_stats["sum"]
    sum_squares = normalized_stats["sum_squares"]
    ess = (sum_weights * sum_weights / sum_squares) if sum_squares > 0.0 else 0.0
    report = {
        "schema": 1,
        "operation": "train_stream_sample_weights",
        "source": {
            "path": str(path),
            "sha256": _sha256_file(path),
            "dtype": str(raw.dtype),
            "shape": [int(value) for value in raw.shape],
        },
        "aligned_inputs": {
            "data_path": str(args.data),
            "data_sha256": _sha256_file(args.data),
            "feat_path": str(args.feat),
            "feat_sha256": _sha256_file(args.feat),
        },
        "split": {
            "records": int(n_records),
            "train_records": int(train_n),
            "holdout_records": int(hold_count),
            "normalization_scope": "train_only",
            "holdout_weighted": False,
        },
        "validation": {
            "strictly_positive": True,
            "bounds_scope": "all_rows",
            "clipping_applied": False,
            "requested_min": weight_min,
            "requested_max": weight_max,
            "float32_min": float(bound_min32),
            "float32_max": float(bound_max32),
            "observed_all_rows_min": observed_min,
            "observed_all_rows_max": observed_max,
        },
        "normalization": {
            "method": normalization,
            "raw_train_mean": raw_train_mean,
            "factor": normalization_factor,
            "normalized_train_mean": normalized_mean,
        },
        "raw_train": _weight_stats(raw_train),
        "normalized_train": normalized_stats,
        "effective_sample_size": {
            "kind": "kish_row_level",
            "ess": ess,
            "ess_fraction": ess / train_n,
            "design_effect": train_n / ess if ess > 0.0 else None,
        },
        "optimizer": {
            "sw_all_used": optimizer_sw_all is not None,
            "uniform_after_normalization": uniform_after_normalization,
        },
    }
    _atomic_write_json(report_target, report)
    print(
        "SAMPLE_WEIGHTS "
        + json.dumps(
            {
                "ess": ess,
                "ess_fraction": ess / train_n,
                "holdout_weighted": False,
                "normalization": normalization,
                "report": str(report_target),
                "sha256": report["source"]["sha256"],
                "uniform": uniform_after_normalization,
            },
            sort_keys=True,
        )
    )
    return optimizer_sw_all, report


def _validate_targets_report_target(args, targets_path: Path, report_path: str) -> Path:
    target = Path(report_path)
    target_resolved = target.resolve(strict=False)
    protected = (
        ("--target-values", targets_path),
        ("--sample-weights", getattr(args, "sample_weights", None)),
        ("--weights-report", getattr(args, "weights_report", None)),
        ("--optimizer-report", getattr(args, "optimizer_report", None)),
        ("--data", getattr(args, "data", None)),
        ("--feat", getattr(args, "feat", None)),
        ("--out", getattr(args, "out", None)),
    )
    for flag, protected_path in protected:
        if protected_path is None:
            continue
        if target_resolved == Path(protected_path).resolve(strict=False):
            raise SystemExit(
                f"--targets-report must be distinct from {flag}: {target}"
            )
    if target.exists():
        raise SystemExit(f"{target}: targets report already exists (no-clobber)")
    return target


def _atomic_write_targets_report(path: Path, payload: dict) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}"
    )
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        # Publish without a race that could overwrite a target created after
        # validation. Same-directory hard-linking is atomic and no-clobber.
        os.link(temporary, path)
    except FileExistsError as exc:
        if path.exists():
            raise SystemExit(
                f"{path}: targets report already exists (no-clobber)"
            ) from exc
        raise SystemExit(
            f"{path}: cannot create atomic targets-report temporary"
        ) from exc
    except OSError as exc:
        raise SystemExit(
            f"{path}: cannot atomically publish targets report: {exc}"
        ) from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _load_target_values(
    args,
    n_records: int,
    train_n: int,
    hold_count: int,
) -> tuple[np.ndarray | None, dict | None]:
    """Load an immutable black-POV probability target sidecar.

    The opt-in path is deliberately separate from ``wdl`` and ``value`` so an
    omitted or misspelled flag can never silently change the historical fit.
    Values are validated but never clipped or normalised; the holdout tail uses
    the aligned sidecar labels for the same objective as the train prefix.
    """
    values_path = getattr(args, "target_values", None)
    report_path = getattr(args, "targets_report", None)
    if getattr(args, "target", "wdl") != "external":
        if values_path is not None or report_path is not None:
            raise SystemExit(
                "--target-values/--targets-report require --target external"
            )
        return None, None
    if values_path is None or report_path is None:
        raise SystemExit(
            "--target external requires --target-values and --targets-report"
        )

    path = Path(values_path)
    report_target = _validate_targets_report_target(args, path, report_path)
    try:
        raw = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise SystemExit(f"{path}: cannot load target values: {exc}") from exc
    if not isinstance(raw, np.ndarray) or raw.ndim != 1:
        raise SystemExit(
            f"{path}: target values must be a 1-D NumPy array, "
            f"got shape={getattr(raw, 'shape', None)}"
        )
    if raw.dtype != np.dtype(np.float32):
        raise SystemExit(
            f"{path}: target values dtype must be float32 exactly, got {raw.dtype}"
        )
    if raw.shape != (n_records,):
        raise SystemExit(
            f"{path}: target values length {len(raw)} != data records {n_records}"
        )
    if not bool(np.all(np.isfinite(raw))):
        raise SystemExit(f"{path}: target values contain NaN or infinity")
    observed_min = float(np.min(raw))
    observed_max = float(np.max(raw))
    if observed_min < 0.0 or observed_max > 1.0:
        raise SystemExit(
            f"{path}: target values range [{observed_min}, {observed_max}] "
            "outside black-POV probability interval [0,1]; values are never clipped"
        )

    report = {
        "schema": 1,
        "operation": "train_stream_external_targets",
        "source": {
            "path": str(path),
            "sha256": _sha256_file(path),
            "dtype": str(raw.dtype),
            "shape": [int(value) for value in raw.shape],
            "pov": "black",
            "range": "win_probability_[0,1]",
        },
        "aligned_inputs": {
            "data_path": str(args.data),
            "data_sha256": _sha256_file(args.data),
            "feat_path": str(args.feat),
            "feat_sha256": _sha256_file(args.feat),
        },
        "split": {
            "records": int(n_records),
            "train_records": int(train_n),
            "holdout_records": int(hold_count),
            "holdout_uses_external_targets": bool(hold_count),
        },
        "validation": {
            "finite": True,
            "clipping_applied": False,
            "observed_min": observed_min,
            "observed_max": observed_max,
        },
        "train": {
            "mean": float(np.mean(raw[:train_n], dtype=np.float64)),
            "standard_deviation": float(np.std(raw[:train_n], dtype=np.float64)),
        },
    }
    _atomic_write_targets_report(report_target, report)
    print(
        "EXTERNAL_TARGETS "
        + json.dumps(
            {
                "report": str(report_target),
                "sha256": report["source"]["sha256"],
                "min": observed_min,
                "max": observed_max,
                "holdout_uses_external_targets": bool(hold_count),
            },
            sort_keys=True,
        )
    )
    return raw, report


def _holdout_logloss(build_fn, y_all, model_weights, train_n, n_records, chunk):
    """Unweighted tail cross-entropy; sample weights deliberately cannot enter."""
    eps = 1e-12
    total_loss = 0.0
    total_rows = 0
    for index in range(train_n, n_records, chunk):
        selected = np.arange(index, min(index + chunk, n_records), dtype=np.int64)
        logits = build_fn(selected) @ model_weights
        probabilities = 0.5 * (np.tanh(0.5 * logits) + 1.0)
        targets = y_all[selected]
        total_loss += float(
            -np.sum(
                targets * np.log(probabilities + eps)
                + (1.0 - targets) * np.log(1.0 - probabilities + eps)
            )
        )
        total_rows += len(selected)
    return total_loss / max(total_rows, 1), total_rows


# --------------------------------------------------------------------------- #
#  Per-chunk adapters to the shared phase helpers.  These retain the historical
#  train_stream surface for rank/wdl finetune callers without duplicating math.
# --------------------------------------------------------------------------- #
def _piece_count_bb(wm, wk, bm, bk):
    """Total pieces (men+kings, both sides) per row : popcount(OR of 4 boards)."""
    return eval_phase.piece_count_bb(wm, wk, bm, bk)


def _tempo_wmg_bb(wm, bm):
    """Scan tempo midgame weight = clip(tempo/300), men only. Matches train.py."""
    return eval_phase.tempo_wmg_bb(wm, bm)


# --------------------------------------------------------------------------- #
#  Fold (cols/signs) for one chunk's bitboards. Replicates train.py's cols/signs
#  logic for the chosen fold (--full-fold vs --color-fold vs none).
# --------------------------------------------------------------------------- #
class Folder:
    """Maps a chunk's (black_men, white_men) -> (cols, signs) in the TRAINING
    layout (PAT_BUCKETS buckets/pattern), and carries the fold maps needed to
    EXPAND the trained canonical block back to the full 17M v3 table."""

    def __init__(self, mode: str):
        self.mode = mode
        NP = patterns.NUM_PATTERNS
        self.cf_U2C = self.cf_U2S = None        # --color-fold expand maps
        self.rf_canon = self.rf_sign = None     # --full-fold expand maps
        if mode == 'full':
            import symmetry
            # FULL stack : colour + rot180 + translation + reflection (train.py).
            self.rf_canon, self.rf_sign = symmetry.build_canon(translate=True,
                                                               reflect=True)
            self.PAT_BUCKETS = patterns.BUCKETS_PER_PATTERN   # canonical = 17M index space
        elif mode == 'exact':
            import symmetry
            # SEULE la symétrie vraie du damier : rot180∘colour-swap. Voir
            # symmetry.build_exact_canon pour pourquoi ce n'est ni build_canon
            # ni une variante avec LR.
            self.rf_canon, self.rf_sign = symmetry.build_exact_canon()
            self.PAT_BUCKETS = patterns.BUCKETS_PER_PATTERN   # espace 17M, comprimé par --prune
        elif mode == 'color':
            self.cf_U2C, self.cf_U2S = colorfold_maps()
            self.PAT_BUCKETS = CF_BUCKETS
        elif mode == 'none':
            self.PAT_BUCKETS = patterns.BUCKETS_PER_PATTERN
        else:
            raise SystemExit(f'unknown fold {mode!r}')
        self.NP = NP
        self.TB = self.PAT_BUCKETS * NP

    def cols_signs(self, black_men, white_men):
        """(n,NP) int64 columns in [0,TB) and (n,NP) float32 signs (or None)."""
        idx = patterns.extract_indices(black_men, white_men)
        NP = self.NP
        if self.rf_canon is not None:      # 'full' comme 'exact'
            cols = self.rf_canon[np.arange(NP)[None, :], idx]          # canonical 17M-space col
            signs = self.rf_sign[np.arange(NP)[None, :], idx].astype(np.float32)
        elif self.mode == 'color':
            canon = self.cf_U2C[idx]                                   # [0,CF_HALF]
            signs = self.cf_U2S[idx].astype(np.float32)               # ±1
            cols = canon + (np.arange(NP, dtype=np.int64) * self.PAT_BUCKETS)[None, :]
        else:
            cols = patterns.flat_feature_columns(idx)
            signs = None
        return cols, signs


def expand_pat(folder: Folder, canon_mg, canon_eg, scale):
    """EXPAND the trained canonical pattern block (TB-sized, possibly un-pruned)
    back to the standard full 17M v3 table, quantised to int32. Copies train.py's
    train_scan_eval expand logic exactly (color-fold / full-fold / none)."""
    def quant(block):
        q = np.round(block * scale).astype(np.int64)
        return np.clip(q, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)

    if folder.rf_canon is not None:
        # --full-fold (rot/trans/refl) : full[p*NB+c] = sign[p][c]·w_canon[canon_col[p][c]].
        rf_canon = folder.rf_canon
        rf_sign = folder.rf_sign
        full_mg = (rf_sign.ravel().astype(canon_mg.dtype) * canon_mg[rf_canon.ravel()])
        full_eg = (rf_sign.ravel().astype(canon_eg.dtype) * canon_eg[rf_canon.ravel()])
        return quant(full_mg), quant(full_eg)
    if folder.cf_U2C is not None:
        # --color-fold : W_full[u] = sign(u)·w_canon[|signed(u)|], per pattern.
        NB = patterns.BUCKETS_PER_PATTERN                  # 531441
        NP = patterns.NUM_PATTERNS
        TBfull = NB * NP
        cf_U2C, cf_U2S = folder.cf_U2C, folder.cf_U2S
        # canonical bucket 0 (all-empty, colour-swap fixpoint) -> antisymmetric weight 0.
        canon_mg = canon_mg.copy(); canon_eg = canon_eg.copy()
        canon_mg[np.arange(NP) * CF_BUCKETS] = 0
        canon_eg[np.arange(NP) * CF_BUCKETS] = 0
        full_mg = np.empty(TBfull, dtype=canon_mg.dtype)
        full_eg = np.empty(TBfull, dtype=canon_eg.dtype)
        for p in range(NP):
            cb_mg = canon_mg[p * CF_BUCKETS:(p + 1) * CF_BUCKETS]
            cb_eg = canon_eg[p * CF_BUCKETS:(p + 1) * CF_BUCKETS]
            full_mg[p * NB:(p + 1) * NB] = cf_U2S * cb_mg[cf_U2C]
            full_eg[p * NB:(p + 1) * NB] = cf_U2S * cb_eg[cf_U2C]
        return quant(full_mg), quant(full_eg)
    # no fold : the canonical block IS the 17M table.
    return quant(canon_mg), quant(canon_eg)


# --------------------------------------------------------------------------- #
#  Champion projection shared by two deliberately different continuation modes:
#    * --prior-mean : Gaussian ridge toward the previous champion;
#    * --warm-start : optimiser initialisation only, ordinary L2 remains centred 0.
#  Both fold a standard full-table PJTW back into the CURRENT pruned layout.
# --------------------------------------------------------------------------- #
def project_champion_mean(path, folder, keep, PAT_N, E):
    w_champ, scale_c, n_pat_c, n_ext_c = load_v3_weights_float(path)
    if n_ext_c != E:
        raise SystemExit(f'champion n_ext {n_ext_c} != current extras {E} '
                         '(champion built with different feature flags)')
    NP = patterns.NUM_PATTERNS
    NB = patterns.BUCKETS_PER_PATTERN
    if n_pat_c != NP * NB:
        raise SystemExit(f'champion n_pat {n_pat_c} != {NP * NB} (full table v3 expected)')
    cm_full = w_champ[0:n_pat_c]
    ce_full = w_champ[n_pat_c:2 * n_pat_c]
    ext_mg_c = w_champ[2 * n_pat_c:2 * n_pat_c + n_ext_c]
    ext_eg_c = w_champ[2 * n_pat_c + n_ext_c:2 * n_pat_c + 2 * n_ext_c]
    # --- fold-back full -> canonical training block (p*PAT_BUCKETS + cc) ---
    if folder.mode == 'color':
        U2C, U2S = colorfold_maps()
        rep_b = np.empty(CF_BUCKETS, dtype=np.int64)
        rep_b[U2C] = np.arange(NB, dtype=np.int64)          # any representative per canonical
        srb = U2S[rep_b].astype(np.float64)
        canon_mg = (cm_full.reshape(NP, NB)[:, rep_b] * srb[None, :]).reshape(NP * CF_BUCKETS)
        canon_eg = (ce_full.reshape(NP, NB)[:, rep_b] * srb[None, :]).reshape(NP * CF_BUCKETS)
    elif folder.mode == 'exact':
        # Le champion précédent a été ajusté SANS cette contrainte : ses deux
        # membres d'orbite ne coïncident pas. Prendre un représentant (comme le
        # fait la branche 'color', légitime là où la contrainte est déjà
        # satisfaite exactement) reviendrait à choisir arbitrairement une moitié
        # et à jeter l'autre. On MOYENNE — c'est la projection orthogonale sur le
        # sous-espace contraint, donc le point admissible le plus proche du
        # champion, ce que « continuer depuis le champion » doit vouloir dire.
        cc = folder.rf_canon.ravel()
        sg = folder.rf_sign.ravel().astype(np.float64)
        TBfull = NP * NB
        cnt = np.bincount(cc, minlength=TBfull).astype(np.float64)
        cnt[cnt == 0.0] = 1.0                               # colonnes non canoniques
        canon_mg = np.bincount(cc, weights=sg * cm_full, minlength=TBfull) / cnt
        canon_eg = np.bincount(cc, weights=sg * ce_full, minlength=TBfull) / cnt
    elif folder.mode == 'none':
        canon_mg, canon_eg = cm_full, ce_full               # canonical == full
    else:
        raise SystemExit(f'champion continuation unsupported for fold={folder.mode!r} '
                         '(color/exact/none only)')
    # --- prune-align : dense slot s(1..K) -> canonical bucket keep[s-1] ; slot0=fallback(0) ---
    mu_pat_mg = np.zeros(PAT_N, dtype=np.float64)
    mu_pat_eg = np.zeros(PAT_N, dtype=np.float64)
    mu_pat_mg[1:] = canon_mg[keep]
    mu_pat_eg[1:] = canon_eg[keep]
    mu = np.concatenate([mu_pat_mg, mu_pat_eg, ext_mg_c, ext_eg_c])
    return mu, scale_c


# --------------------------------------------------------------------------- #
#  Sequential-Bayesian prior : project the previous champion as a Gaussian
#  prior.  This is stronger than --warm-start because it changes the objective.
# --------------------------------------------------------------------------- #
# Valeur par defaut de --prior-decay. Nommee pour que la garde de
# --prior-alpha-cap puisse distinguer « laisse au defaut » de « passe
# explicitement ». Passer --prior-decay 1.0 a la main est indiscernable du
# defaut, et c'est acceptable : c'est la valeur qui ne change rien.
PRIOR_DECAY_DEFAULT = 1.0


def build_sequential_prior(args, folder, keep, kept_counts, PAT_N, E, N, l2):
    mu, scale_c = project_champion_mean(
        args.prior_mean, folder, keep, PAT_N, E)
    lam = float(args.prior_visit_scale); dec = float(args.prior_decay)
    # The extras are charged visits/N = 1, so a shared decay hits them ~9850x
    # harder than the mean pattern bucket. Keeping them on the same knob would
    # confound visit-adaptive pattern shrinkage with pinning the extras to the
    # parent; defaulting to `dec` keeps every historical run byte-identical.
    dec_ext = dec if args.prior_decay_ext is None else float(args.prior_decay_ext)
    visits = kept_counts.astype(np.float64) / max(N, 1)
    prec_pat = np.full(PAT_N, l2, dtype=np.float64)
    if args.prior_alpha_cap is None:
        prec_pat[1:] = l2 + dec * lam * visits
        prec_ext_val = l2 + dec_ext * lam                    # extras active every row (visits/N=1)
    else:
        # BOUNDED-INFLUENCE prior : cap the parent's SHARE of each bucket.
        # The posterior mean is a convex blend  w = a*mu + (1-a)*w_data  with
        #     a_j = prec_j / (prec_j + lam*visits_j/N)
        # because lam*visits/N is the logistic data-Fisher scale — that is
        # exactly what --prior-visit-scale documents. At a CONSTANT prec = l2,
        # `a` tends to 1 on thin buckets: the champion carries buckets that are
        # ~100 % parent, and nothing bounds it. Solving a_j <= cap gives
        #     prec_j <= cap/(1-cap) * lam * visits_j/N
        # keeping l2 as the ceiling, so the cap can only ever RELAX the pull.
        # This interpolates continuously between the two poles: cap -> 1
        # restores the constant-l2 champion, cap -> 0 approaches a scratch fit.
        # NB the extras carry visits/N = 1, so their cap term is cap/(1-cap)*lam
        # — far above l2 at any sane cap — hence they simply stay at l2. The cap
        # does NOT reintroduce the extras asymmetry.
        # NB slot 0 is the un-pruned fallback, not a visited bucket: left at l2.
        k = args.prior_alpha_cap / (1.0 - args.prior_alpha_cap)
        prec_pat[1:] = np.minimum(l2, k * lam * visits)
        prec_ext_val = min(l2, k * lam)
    prec = np.concatenate([prec_pat, prec_pat,
                           np.full(E, prec_ext_val), np.full(E, prec_ext_val)])
    if args.prior_alpha_cap is None:
        mode = f'decay={dec} decay_ext={dec_ext}'
    else:
        # Realised share, not the requested cap: buckets sitting at the l2
        # ceiling are BELOW the cap, so the max is the number that matters.
        a = prec_pat[1:] / (prec_pat[1:] + lam * visits)
        mode = (f'alpha_cap={args.prior_alpha_cap} '
                f'alpha med={np.median(a):.3f} max={a.max():.3f} '
                f'at_l2_ceiling={100.0 * np.mean(prec_pat[1:] >= l2):.1f}%')
    print(f'prior : champion={args.prior_mean} (scale={scale_c})  λ={lam} {mode}  '
          f'prec[pat] med={np.median(prec_pat[1:]):.3e} max={prec_pat[1:].max():.3e} '
          f'prec[ext]={prec_ext_val:.3e}  warm-start at μ')
    return mu, prec


# --------------------------------------------------------------------------- #
#  The streaming trainer.
# --------------------------------------------------------------------------- #
def train_stream(args):
    t_start = time.time()
    fold_mode = ('full' if args.full_fold else
                 'exact' if args.exact_fold else
                 'color' if args.color_fold else 'none')
    folder = Folder(fold_mode)

    mm, N = open_jnnw(args.data)
    feat, K = open_feat(args.feat, N)
    EVAL_NUM_EXTRAS = K
    print(f'JNNW {args.data} : {N:,} records')
    print(f'FEAT {args.feat} : k={K} extras')
    print(f'fold : {fold_mode}  ({folder.PAT_BUCKETS:,} buckets/pattern, '
          f'TB={folder.TB:,})')
    print(f'occupancy : {"men|kings (king-aware, Scan-style)" if args.king_patterns else "men only"}')

    chunk = int(args.chunk)
    TB = folder.TB
    train_N, hold_count = _resolve_holdout(args, N)
    sample_weights, _weights_report = _load_sample_weights(
        args, N, train_N, hold_count
    )
    external_targets, _targets_report = _load_target_values(
        args, N, train_N, hold_count
    )

    # --- Pass A : stream once to build the tiny per-row arrays (wdl/stm/phase) and
    #     the prune visit-count remap. Bitboards + extras are NOT kept; only O(N)
    #     bytes of wdl/stm/phase + the O(TB) int counts survive this pass. ------- #
    print(f'pass A (phase + prune scan, chunk={chunk:,}) ...')
    tA = time.time()
    y_all = np.empty(N, dtype=np.float64)        # black-POV win-prob target {0,.5,1}
    wmg_all = np.empty(N, dtype=np.float32)
    weg_all = np.empty(N, dtype=np.float32)
    do_prune = bool(args.prune)
    ccounts = np.zeros(TB, dtype=np.int64) if do_prune else None
    n_win = n_draw = n_loss = 0
    for i in range(0, N, chunk):
        j = min(i + chunk, N)
        rec = mm[i:j]
        wm = np.ascontiguousarray(rec['wm']); wk = np.ascontiguousarray(rec['wk'])
        bm = np.ascontiguousarray(rec['bm']); bk = np.ascontiguousarray(rec['bk'])
        stm = np.ascontiguousarray(rec['stm'])
        wdl = np.ascontiguousarray(rec['wdl']).astype(np.float64)
        if args.target == 'external':
            y_all[i:j] = np.asarray(external_targets[i:j], dtype=np.float64)
        elif args.target == 'value':
            # Independent value-target distillation (option B) : regress on the
            # DEEP-search value stored in `score` (STM-POV), mapped to a black-POV
            # win-prob via a sigmoid so it stays in the same [0,1] regime as the
            # WDL-logistic champions. score_black = score if stm==1 else -score.
            score = np.ascontiguousarray(rec['score']).astype(np.float64)
            score_black = np.where(stm == 1, score, -score)
            y_all[i:j] = 1.0 / (1.0 + np.exp(-score_black / float(args.value_scale)))
        else:
            # black-POV WDL target y = (wdl_black+1)/2, wdl_black = wdl if stm==1 else -wdl.
            wdl_black = np.where(stm == 1, wdl, -wdl)
            y_all[i:j] = (wdl_black + 1.0) * 0.5
        n_win += int((wdl > 0).sum()); n_loss += int((wdl < 0).sum())
        n_draw += int((wdl == 0).sum())
        # phase weights (same as train.py : tempo-stage or piece-count ramp).
        if args.tempo_stage:
            wmg = _tempo_wmg_bb(wm, bm)
        else:
            pc = np.minimum(_piece_count_bb(wm, wk, bm, bk), 40).astype(np.float64)
            wmg = phase_wmg(pc, args.phase_lo, args.phase_hi)
        wmg_all[i:j] = wmg.astype(np.float32)
        weg_all[i:j] = (1.0 - wmg).astype(np.float32)
        if do_prune:
            pb = (bm | bk) if args.king_patterns else bm
            pw = (wm | wk) if args.king_patterns else wm
            cols, _ = folder.cols_signs(pb, pw)
            ccounts += np.bincount(cols.ravel(), minlength=TB)
    if args.target == 'external':
        print(f'  target=EXTERNAL (black-POV probability sidecar)  '
              f'y mean={y_all.mean():.3f} std={y_all.std():.3f}  ({time.time()-tA:.1f}s)')
    elif args.target == 'value':
        print(f'  target=VALUE (deep-search score, scale={args.value_scale})  '
              f'y mean={y_all.mean():.3f} std={y_all.std():.3f}  ({time.time()-tA:.1f}s)')
    else:
        print(f'  target=WDL  win={n_win} draw={n_draw} loss={n_loss} '
              f'({100*n_draw/max(N,1):.1f}% draws)  ({time.time()-tA:.1f}s)')

    # --- Prune remap : bucket(0..TB) -> dense slot. Lossless at min-visits=1 (every
    #     visited bucket gets a slot 1..K; slot 0 = unseen fallback, stays 0). ----- #
    remap = None
    PAT_N = TB
    if do_prune:
        keep = np.flatnonzero(ccounts >= args.prune_min_visits)
        keep = keep[np.argsort(ccounts[keep])[::-1]]     # common buckets -> low slots
        K = len(keep)
        # int32 remap : TB=17M < 2^31 so slots fit; 17M*4 = 68MB (vs 136MB int64).
        remap = np.zeros(TB, dtype=np.int32)             # 0 = fallback/unseen
        remap[keep] = np.arange(1, K + 1, dtype=np.int32)
        PAT_N = K + 1
        kept_counts = ccounts[keep].copy() if args.prior_mean else None  # per-slot visits for prior
        print(f'prune : keep {K:,} buckets (>= {args.prune_min_visits} visits) '
              f'-> {2*PAT_N:,} pattern cols vs {2*TB:,}  ({TB/max(PAT_N,1):.1f}x fewer); '
              f'remap RAM={remap.nbytes/1e6:.0f}MB')
        if args.prune_min_visits > 1:
            print('  WARNING: --prune-min-visits>1 pools low-count buckets into the '
                  'fallback slot 0, which is DROPPED at deploy -> the played eval '
                  'differs slightly from the trained model. Use 1 for a lossless prune.',
                  file=sys.stderr)
        del ccounts
    if (args.prior_mean or args.warm_start or args.init_file) and not do_prune:
        raise SystemExit('--prior-mean/--warm-start/--init-file require --prune '
                         '(champion must be aligned to the visited dense slots)')

    n_cols = 2 * PAT_N + 2 * EVAL_NUM_EXTRAS
    print(f'design : {n_cols:,} columns (2x{PAT_N:,} pat + 2x{EVAL_NUM_EXTRAS} ext)')
    trainable_mask, trainable_region = _prepare_trainable_region(
        args, folder, remap, PAT_N, EVAL_NUM_EXTRAS
    )
    if trainable_region is not None:
        print(
            "trainable-region : "
            f"{trainable_region['dense_pattern_slots']:,} pattern slots + "
            f"{trainable_region['extra_coordinates']} extras; "
            f"{trainable_region['frozen_coordinates']:,} coordinates strictly frozen"
        )

    # --- Disk-backed build_fn : sel is a CONTIGUOUS row range produced by
    #     train_lbfgs_chunked's tr_idx[i:i+batch]. We require contiguity so we can
    #     seek the memmaps; assert it to fail loud if that ever changes. --------- #
    logistic = (args.loss == 'logistic')

    def build_fn(sel):
        lo = int(sel[0]); hi = int(sel[-1]) + 1
        # tr_idx = arange(N) so a chunk slice is contiguous & sorted.
        assert hi - lo == len(sel) and sel[0] == lo and sel[-1] == hi - 1, \
            'build_fn expects a contiguous row range (tr_idx must be arange(N))'
        rec = mm[lo:hi]
        wm = np.ascontiguousarray(rec['wm']); bm = np.ascontiguousarray(rec['bm'])
        if args.king_patterns:
            wk = np.ascontiguousarray(rec['wk']); bk = np.ascontiguousarray(rec['bk'])
            pb = bm | bk; pw = wm | wk
        else:
            pb = bm; pw = wm
        cols, signs = folder.cols_signs(pb, pw)
        if remap is not None:
            cols = remap[cols]                            # (n,NP) in [0,K]
        wmg = wmg_all[lo:hi].astype(np.float64)
        weg = weg_all[lo:hi].astype(np.float64)
        Xpat = build_sparse_X_phased(cols, wmg, weg, PAT_N, signs)
        extras = np.ascontiguousarray(feat[lo:hi]).astype(np.float64)
        Xext = build_extras_phased(extras, wmg, weg)
        return sp.hstack([Xpat, Xext], format='csr')      # [pat_mg|pat_eg|ext_mg|ext_eg]

    # --- L-BFGS over the TRAIN prefix, streamed from disk each iteration. tr_idx is
    #     arange(train_N) so train_lbfgs_chunked re-reads every chunk per gradient
    #     eval (~max_iter disk passes). The accumulated gradient is the EXACT
    #     full-batch gradient (only the assembly is streamed). ------------------ #
    print(f'L-BFGS  loss={args.loss}  l2={args.l2}  max_iter={args.max_iter}  '
          f'chunk={chunk:,}  (~{args.max_iter} disk passes over data+feat)')
    # The held-out tail is never passed to the optimiser. Prune/remap deliberately
    # retain the historical full-N visit scan; only weights and normalisation are
    # train-only. This preserves the legacy model path when weights are absent.
    tr_idx = np.arange(train_N, dtype=np.int64)
    # Hierarchical-shrinkage grouping : slot -> parent pattern id (-1 = unseen fallback).
    slot_pattern = None
    if args.hier_l2 > 0.0:
        PB = folder.PAT_BUCKETS
        if remap is None:                               # no prune : PAT_N == TB, dense grid
            slot_pattern = (np.arange(PAT_N, dtype=np.int64) // PB).astype(np.int32)
        else:                                           # pruned : slot 0 = fallback, 1..K = keep
            slot_pattern = np.full(PAT_N, -1, dtype=np.int32)
            slot_pattern[1:K + 1] = (keep // PB).astype(np.int32)
        print(f'hier-l2 : {args.hier_l2}  (backoff vers la moyenne du pattern parent, '
              f'{patterns.NUM_PATTERNS} patterns)')
    # Sequential-Bayesian prior (opt-in) : project the previous champion into the
    # training layout as a per-weight precision-weighted Gaussian prior. OFF
    # (--prior-mean unset) => exact plain-L2 behaviour, byte-identical output.
    prior_mean = prior_prec = initial_mean = None
    if args.prior_mean:
        prior_mean, prior_prec = build_sequential_prior(
            args, folder, keep, kept_counts, PAT_N, EVAL_NUM_EXTRAS, N, args.l2)
    if args.warm_start:
        initial_mean, scale_c = project_champion_mean(
            args.warm_start, folder, keep, PAT_N, EVAL_NUM_EXTRAS)
        print(f'warm-start : champion={args.warm_start} (scale={scale_c}) ; '
              'initialisation only, objective keeps ordinary zero-centred L2')
    elif args.init_mode == 'zero':
        initial_mean = np.zeros(n_cols, dtype=np.float64)
        print('initialization : explicit ZERO (independent of L2 centre)')
    elif args.init_mode == 'file':
        initial_mean, scale_c = project_champion_mean(
            args.init_file, folder, keep, PAT_N, EVAL_NUM_EXTRAS)
        print(f'initialization : FILE={args.init_file} (scale={scale_c}) '
              '(independent of L2 centre)')
    t0 = time.time()
    optimizer_diagnostics = {}
    w_float, train_loss, n_iter = train_lbfgs_chunked(
        build_fn, tr_idx, y_all, args.l2, args.max_iter,
        logistic, n_cols, chunk, sw_all=sample_weights,
        hier_l2=args.hier_l2, slot_pattern=slot_pattern,
        pat_n=PAT_N, n_patterns=patterns.NUM_PATTERNS,
        prior_mean=prior_mean, prior_prec=prior_prec, initial_mean=initial_mean,
        optimizer_diagnostics=optimizer_diagnostics, maxcor=args.lbfgs_maxcor,
        gtol=args.lbfgs_gtol, trainable_mask=trainable_mask)
    print(f'  train_loss={train_loss:.6f}  iters={n_iter}  ({time.time()-t0:.1f}s)')
    print('OPTIMIZER ' + json.dumps(optimizer_diagnostics, sort_keys=True))
    if args.optimizer_report:
        Path(args.optimizer_report).write_text(
            json.dumps(optimizer_diagnostics, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )

    # --- HOLDOUT log-loss : same forward pass (build_fn + sigmoid CE) as the fit,
    #     on the held-out tail rows [train_N, N), at the fitted weights. Pure data
    #     cross-entropy (no L2/prior term) => a clean generalisation estimate. ---- #
    if hold_count > 0 and train_N < N:
        _holdout_loss, _nv = _holdout_logloss(
            build_fn, y_all, w_float, train_N, N, chunk
        )
        print(f'HOLDOUT_LOGLOSS {_holdout_loss:.6f}  '
              f'(frac={_nv/max(N,1):.8f} n_val={_nv})')

    # --- Un-prune to the TB-sized training block, then fold-EXPAND to the full 17M
    #     v3 table and write a standard PJTW v3 (byte-compatible with the C++ loader). #
    def quant(block):
        q = np.round(block * args.scale).astype(np.int64)
        return np.clip(q, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)

    E = EVAL_NUM_EXTRAS
    pat_mg_d = w_float[0:PAT_N]
    pat_eg_d = w_float[PAT_N:2 * PAT_N]
    ext_mg = quant(w_float[2 * PAT_N:2 * PAT_N + E])
    ext_eg = quant(w_float[2 * PAT_N + E:2 * PAT_N + 2 * E])
    # (1) un-prune to the TB-sized training-layout block.
    if remap is not None:
        canon_mg = np.zeros(TB, dtype=w_float.dtype)
        canon_eg = np.zeros(TB, dtype=w_float.dtype)
        kept = np.flatnonzero(remap > 0)
        canon_mg[kept] = pat_mg_d[remap[kept]]
        canon_eg[kept] = pat_eg_d[remap[kept]]
    else:
        canon_mg, canon_eg = np.asarray(pat_mg_d), np.asarray(pat_eg_d)
    # (2) fold-expand to the standard 17M men-only layout (quantised int32).
    pat_mg, pat_eg = expand_pat(folder, canon_mg, canon_eg, args.scale)
    print(f'quant : scale={args.scale}  '
          f'pat range=[{int(pat_mg.min())},{int(pat_mg.max())}] '
          f'ext_mg range=[{int(ext_mg.min())},{int(ext_mg.max())}]')

    write_weights_v3(Path(args.out), pat_mg, pat_eg, ext_mg, ext_eg, args.scale,
                     king=args.king_patterns)
    if trainable_region is not None:
        frozen_audit = _audit_frozen_region(args, folder, trainable_region)
        _atomic_write_json(args.trainable_region_report, frozen_audit)
        print(
            "TRAINABLE_REGION "
            + json.dumps(
                {
                    "changed_inside_region": frozen_audit["changed_inside_region"],
                    "changed_outside_region": 0,
                    "frozen_region_exact": True,
                    "report": str(args.trainable_region_report),
                    "source_sha256": trainable_region["source"]["sha256"],
                },
                sort_keys=True,
            )
        )
    total = 2 * (len(pat_mg) + E)
    print(f'wrote {args.out}  (v3, {total:,} weights, {20 + 4 * total:,} bytes)  '
          f'[total {time.time()-t_start:.1f}s]')
    return 0


def validate_prior_alpha_cap(args):
    """Refuse toute combinaison ambigue AVANT de toucher au corpus.

    Placee au parse et non dans `train_stream` : les gardes tardives ne
    tiraient qu'apres la passe de prune, donc un job mal configure brulait un
    scan complet du corpus avant de mourir.
    """
    if args.prior_alpha_cap is None:
        return
    if not args.prior_mean:
        raise SystemExit('--prior-alpha-cap requires --prior-mean (it bounds the parent '
                         'share; without a parent there is nothing to bound)')
    if not 0.0 < args.prior_alpha_cap < 1.0:
        raise SystemExit(f'--prior-alpha-cap must lie strictly in (0,1), got '
                         f'{args.prior_alpha_cap} (0 = no parent, so pass no --prior-mean ; '
                         f'1 = unbounded, that is the plain --prior-decay 0 recipe)')
    # The cap REPLACES the decay formula: honouring both would silently drop one.
    for flag, val in (('--prior-decay', args.prior_decay),
                      ('--prior-decay-ext', args.prior_decay_ext)):
        if val not in (None, PRIOR_DECAY_DEFAULT):
            raise SystemExit(f'--prior-alpha-cap replaces the decay formula and cannot be '
                             f'combined with an explicit {flag}={val}')


def validate_initialization_args(args):
    """Validate the backward-compatible independent initialization interface."""
    mode = args.init_mode
    if args.warm_start:
        if mode != 'legacy' or args.init_file:
            raise SystemExit('--warm-start is the legacy file-initialization alias and cannot '
                             'be combined with --init-mode/--init-file')
        return
    if mode == 'file' and not args.init_file:
        raise SystemExit('--init-mode file requires --init-file')
    if mode != 'file' and args.init_file:
        raise SystemExit('--init-file requires --init-mode file')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', required=True, help='JNNW master dataset on disk (can be huge)')
    ap.add_argument('--feat', required=True,
                    help='FEAT file of raw extras aligned 1:1 to --data, on disk')
    ap.add_argument('--out', required=True, help='output PJTW v3 weights path')
    ap.add_argument('--loss', choices=['logistic', 'ls'], default='logistic',
                    help="logistic regression on WDL outcomes (Scan's objective, "
                         "default) or least-squares on the WDL target.")
    ap.add_argument('--target', choices=['wdl', 'value', 'external'], default='wdl',
                    help="wdl (default) = train on the game/egdb outcome label. "
                         "value = independent value-target distillation : train on the "
                         "DEEP-search value in the `score` field (via --deep-relabel), "
                         "mapped to a win-prob with --value-scale. external = aligned "
                         "black-POV probability labels from --target-values.")
    ap.add_argument('--target-values', type=str, default=None,
                    help='with --target external: aligned float32 .npy vector in [0,1]')
    ap.add_argument('--targets-report', type=str, default=None,
                    help='with --target external: atomic JSON provenance report')
    ap.add_argument('--value-scale', type=float, default=200.0,
                    help="sigmoid scale (eval units) mapping deep-search score → win-prob "
                         "when --target value. Larger = softer targets. Default 200.")
    fold = ap.add_mutually_exclusive_group()
    fold.add_argument('--full-fold', action='store_true',
                      help='FULL symmetry fold (colour+rot180+translation+reflection); '
                           'expanded back to the standard 17M v3 .pjtw.')
    fold.add_argument('--exact-fold', action='store_true',
                      help="EXACT-only fold : groupe {id, rot180∘colour-swap}, la seule "
                           "symétrie que les règles garantissent. 8cf -> 2 125 764 poids, "
                           "le compte de Scan. N'impose PAS cs seule ni rot seule, que le "
                           "module symmetry qualifie lui-même d'approximatives.")
    fold.add_argument('--color-fold', action='store_true',
                      help='colour-antisymmetry fold (17M->8.5M); expanded to 17M v3 .pjtw.')
    ap.add_argument('--tempo-stage', action='store_true',
                    help="Scan tempo (men-advancement) phase blend instead of the "
                         "piece-count ramp. MUST pair with the C++ -DJASS_TEMPO_STAGE.")
    ap.add_argument('--phase-lo', type=float, default=0.0,
                    help='phase ramp low (pieces); wmg=0 at/below. MUST match C++ '
                         '-DJASS_PHASE_LO. Ignored under --tempo-stage.')
    ap.add_argument('--phase-hi', type=float, default=40.0,
                    help='phase ramp high (pieces); wmg=1 at/above. MUST match C++ '
                         '-DJASS_PHASE_HI. Ignored under --tempo-stage.')
    ap.add_argument('--l2', type=float, default=1e-4)
    ap.add_argument('--hier-l2', type=float, default=0.0,
                    help='Hierarchical shrinkage (backoff) : ADD λ·Σ(w_b−μ_p)² toward the PARENT '
                         'pattern mean on top of the ordinary ridge/prior term. 0 = off (legacy '
                         'objective). Pairs with a small --l2.')
    continuation = ap.add_mutually_exclusive_group()
    continuation.add_argument('--prior-mean', type=str, default=None,
                    help='SEQUENTIAL-BAYESIAN prior : PJTW v3 of the PREVIOUS champion. When set, the '
                         'ridge toward 0 is replaced by a Gaussian prior toward this champion, with '
                         'per-weight precision = l2 + decay·λ·(visits/N) (extras: visits=N), warm-started '
                         'at μ. Carries acquired knowledge across generations (anti-forgetting of rare '
                         'buckets). OFF (default) = plain L2, byte-identical. Requires --prune ; '
                         '--color-fold, --exact-fold or none.')
    continuation.add_argument('--warm-start', type=str, default=None,
                    help='PJTW v3 of the previous student used ONLY as the L-BFGS starting point. '
                         'Unlike --prior-mean, this does not anchor the objective to the parent: '
                         'the ordinary --l2 penalty remains centred on zero. Requires --prune and '
                         '--color-fold, --exact-fold or no fold.')
    ap.add_argument('--init-mode', choices=['legacy', 'zero', 'file'], default='legacy',
                    help='optimizer initialization independent of the L2 centre. legacy preserves '
                         'historical behavior (prior mean when --prior-mean is set, otherwise zero); '
                         'zero starts at zero; file requires --init-file. --warm-start remains the '
                         'backward-compatible zero-centred file-initialization alias.')
    ap.add_argument('--init-file', type=str, default=None,
                    help='PJTW v3 optimizer starting point for --init-mode file; may be combined '
                         'with --prior-mean because it does not change the L2 centre')
    ap.add_argument('--prior-visit-scale', type=float, default=0.25,
                    help='λ : prior evidence per accumulated visit (dimensionless ; ~0.25 balances the '
                         'prior against the logistic data-Fisher). Only with --prior-mean.')
    ap.add_argument('--prior-decay', type=float, default=PRIOR_DECAY_DEFAULT,
                    help='discount on the prior precision (0..1). 1 = full visit-weighting ; 0 = plain '
                         'ridge toward the champion (uniform l2, μ=champion). Only with --prior-mean.')
    ap.add_argument('--prior-decay-ext', type=float, default=None,
                    help='separate discount for the EXTRAS block. Defaults to --prior-decay, which '
                         'reproduces the historical behaviour byte-identically. Split it out because '
                         'the extras are charged visits/N=1 by construction, so at a shared decay '
                         'their prior precision is l2+decay·λ — ~9850x that of the mean pattern '
                         'bucket on a 2M corpus (123 visits/bucket). A single knob confounds visit-adaptive '
                         'pattern shrinkage with pinning the extras to the parent. Only with '
                         '--prior-mean.')
    ap.add_argument('--prior-alpha-cap', type=float, default=None,
                    help='BOUNDED-INFLUENCE prior: cap the parent share a_j = prec/(prec + '
                         'λ·visits/N) of EVERY pattern bucket at this value, in (0,1). Sets '
                         'prec_j = min(l2, cap/(1-cap)·λ·visits_j/N), so the parent can only be '
                         'RELAXED, never strengthened. At a constant prec=l2 the share tends to 1 '
                         'on thin buckets — the model carries buckets that are ~100%% parent with '
                         'nothing bounding it. Interpolates continuously between the poles: '
                         'cap->1 is the constant-l2 recipe, cap->0 approaches a scratch fit. '
                         'Mutually exclusive with --prior-decay/--prior-decay-ext. Only with '
                         '--prior-mean.')
    ap.add_argument('--max-iter', type=int, default=25,
                    help='L-BFGS iters; EACH is ~one disk pass over data+feat. Keep small.')
    ap.add_argument('--optimizer-report', type=str, default=None,
                    help='optional JSON report with SciPy success/status/message and gradient norm')
    ap.add_argument('--lbfgs-maxcor', type=int, default=5,
                    help='L-BFGS correction history size; larger values use more RAM but improve curvature')
    ap.add_argument('--lbfgs-gtol', type=float, default=None,
                    help='optional projected-gradient convergence threshold; SciPy default when omitted')
    ap.add_argument('--scale', type=int, default=1000, help='quantisation factor')
    holdout = ap.add_mutually_exclusive_group()
    holdout.add_argument('--holdout-frac', type=float, default=0.0,
                    help='fraction (0..1) of the tail rows held out from the fit to report a '
                         'HOLDOUT_LOGLOSS generalisation estimate. 0 = off (byte-identical). '
                         'Data must be pre-shuffled for the split to be representative.')
    holdout.add_argument('--holdout-count', type=int, default=0,
                    help='exact number of tail rows held out. Intended for a game/opening-level '
                         'split assembled by tools/selfplay_frontier.py; avoids fractional rounding.')
    ap.add_argument('--sample-weights', type=str, default=None,
                    help='optional float32 .npy vector aligned 1:1 with --data rows')
    ap.add_argument('--weight-normalization', choices=['mean-train-1'],
                    default='mean-train-1',
                    help='sample-weight normalisation, computed on train rows only')
    ap.add_argument('--weight-min', type=float, default=None,
                    help='required with --sample-weights: inclusive lower validation bound')
    ap.add_argument('--weight-max', type=float, default=None,
                    help='required with --sample-weights: inclusive upper validation bound')
    ap.add_argument('--weights-report', type=str, default=None,
                    help='required with --sample-weights: atomic JSON provenance/statistics report')
    ap.add_argument('--trainable-region', type=str, default=None,
                    help='audited jass.l3_curriculum_error_region.v1 JSON; with --exact-fold '
                         'and --prior-mean, optimise only its confirmed buckets and freeze every '
                         'other coefficient exactly at the champion')
    ap.add_argument('--trainable-region-report', type=str, default=None,
                    help='required with --trainable-region: atomic post-serialization proof that '
                         'no coefficient outside the region changed')
    ap.add_argument('--chunk', type=int, default=500000,
                    help='rows/chunk read from disk per gradient sub-step.')
    ap.add_argument('--prune', dest='prune', action='store_true', default=True,
                    help='(default on) train over a collision-free dense remap of '
                         'the pattern table; scatter back to a standard 17M .pjtw.')
    ap.add_argument('--no-prune', dest='prune', action='store_false',
                    help='disable pruning (train the full TB-sized pattern table).')
    ap.add_argument('--prune-min-visits', type=int, default=1,
                    help='with --prune : keep a bucket only if visited >= this many '
                         'times (1 = lossless).')
    ap.add_argument('--king-patterns', action='store_true',
                    help='PIECE-PRESENCE occupancy includes kings (men|kings, '
                         'Scan-style) for the pattern buckets, exactly like '
                         'train.py --king-patterns and a -DJASS_KING_PATTERNS build. '
                         'Records king=True in the PJTW v3 marker (rejected by a '
                         'men-only binary). Default OFF = men-only occupancy.')
    args = ap.parse_args(argv)
    validate_prior_alpha_cap(args)
    validate_initialization_args(args)
    return train_stream(args)


if __name__ == '__main__':
    raise SystemExit(main())
