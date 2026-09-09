#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-Francois Collin
"""Build the R1 external training target (preregistration
``docs/experiments/L3_R1_ADJUDICATED_RELABEL_V1_20260909.md`` §3.3, guard §4.2).

Inputs
------
* the original JNNW corpus (terminal self-play WDL);
* the SAME corpus after ``jass --deep-relabel`` (adjudicated WDL in the
  ``wdl`` byte, raw search/EGDB score in the ``score`` field, both records
  otherwise byte-identical to the original — same bitboards, same ``stm``);
* the 1-byte-per-record source-tags sidecar written alongside the relabel
  pass (``0`` = SEARCH, ``1`` = TB, ``2`` = TERMINAL, per record, in order).

JNNW format (unchanged across both files): 8-byte header (``b"JNNW"`` +
uint32 little-endian record count) followed by ``N`` little-endian 38-byte
records: 4x uint64 bitboards (white_men, white_kings, black_men, black_kings),
uint8 ``stm`` (1 = black to move), int32 ``score`` (STM POV), int8 ``wdl``
(STM POV, one of {-1, 0, +1}). Same layout as
``pattern_jass/tools/jnnw_stats.py:36-48``, ``jobs/tools/l3_conditional_targets.py:30-56``
and the raw-offset variant in ``jobs/tools/assert_corpus_wdl.py:36-39``.

External-target contract (consumed by ``train_stream --target external``,
``pattern_jass/tools/train_stream.py:690-793``): a 1-D ``.npy``, dtype
float32 exactly, length == n_records, all finite, values in [0, 1], BLACK-POV
win probability. Black-POV conversion follows the CONTEXT_30 template
(``jobs/tools/l3_replay_context30_targets.py:176-189``):
``wdl_black = where(stm == 1, wdl, -wdl)``, ``p = (wdl_black + 1) / 2``.

R1 target (prereg §3.3):
    p_term = (wdl_black_original    + 1) / 2
    p_adj  = (wdl_black_relabelled  + 1) / 2
    y_R1   = alpha * p_term + (1 - alpha) * p_adj      (alpha default 0.5)
    y_ADJ  = p_adj                                       (diagnostic sidecar)

Phase bins replicate ``phase_index_of`` / ``NUM_PHASES`` / ``PHASE_NAMES``
from ``src/main.cpp:245-255`` EXACTLY (popcount of all four bitboards, i.e.
total pieces on board):
    pieces >= 30 -> 0 "opening"
    pieces >= 22 -> 1 "midgame"
    pieces >= 15 -> 2 "late-mid"
    pieces >= 8  -> 3 "endgame"
    else         -> 4 "deep-eg"
Cite the lines above so drift against ``src/main.cpp`` is auditable; if that
function's thresholds ever change, this module's ``PHASE_THRESHOLDS`` must be
updated to match, not the other way around.

Label guard (prereg §4.2, same bands as ``assert_corpus_wdl.py``): the
ADJUDICATED WDL distribution (STM POV, exactly as read from the relabelled
file's ``wdl`` byte — no black-POV conversion) must have draw share in
[min_draw_share, max_draw_share] and |win_share - loss_share| <=
max_side_skew. On failure the report is still written, with
``guard.status == "R1_LABEL_GUARD_FAILED"``, and the process exits 6 WITHOUT
writing either npy output. On success ``guard.status ==
"R1_LABEL_GUARD_PASS"``.

Exit codes
----------
0  success, both npy outputs and the report written, guard passed.
2  usage/contract violation: mismatched record counts, mismatched bitboards
   or stm between the two JNNW files, malformed/mis-sized/out-of-range
   source-tags file, malformed --context30 sidecar, or an output path that
   already exists / aliases an input (no-clobber).
6  label guard failed (report written, npy outputs NOT written).

Deterministic; no randomness; numpy only (no scipy).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

_HERE = Path(__file__).resolve().parent
_CONDITIONAL_TARGETS_SPEC = importlib.util.spec_from_file_location(
    "l3_conditional_targets", _HERE / "l3_conditional_targets.py"
)
assert _CONDITIONAL_TARGETS_SPEC is not None and _CONDITIONAL_TARGETS_SPEC.loader is not None
_conditional_targets = importlib.util.module_from_spec(_CONDITIONAL_TARGETS_SPEC)
_CONDITIONAL_TARGETS_SPEC.loader.exec_module(_conditional_targets)

_atomic_save_npy = _conditional_targets._atomic_save_npy
_atomic_write_json = _conditional_targets._atomic_write_json

JNNW_MAGIC = b"JNNW"
JNNW_HEADER_SIZE = 8
JNNW_RECORD_SIZE = 38
# First 33 bytes of a record = 4x uint64 bitboards (32 bytes) + uint8 stm.
# These must be byte-identical between the original and relabelled corpus;
# only the trailing score (int32) and wdl (int8) bytes may differ.
JNNW_POSITION_PREFIX_SIZE = 33

JNNW_DTYPE = np.dtype([
    ("wm", "<u8"),
    ("wk", "<u8"),
    ("bm", "<u8"),
    ("bk", "<u8"),
    ("stm", "u1"),
    ("score", "<i4"),
    ("wdl", "i1"),
])
assert JNNW_DTYPE.itemsize == JNNW_RECORD_SIZE

# src/main.cpp:245-255 (phase_index_of / NUM_PHASES / PHASE_NAMES).
NUM_PHASES = 5
PHASE_NAMES = ("opening", "midgame", "late-mid", "endgame", "deep-eg")
# Thresholds paired with PHASE_NAMES: pieces >= threshold[i] -> phase i,
# evaluated in this order (matches the C++ if/else-if chain exactly).
PHASE_THRESHOLDS = (30, 22, 15, 8, 0)

DEFAULT_ALPHA = 0.5
DEFAULT_MIN_DRAW_SHARE = 0.10
DEFAULT_MAX_DRAW_SHARE = 0.60
DEFAULT_MAX_SIDE_SKEW = 0.10

SOURCE_TAG_NAMES = {0: "search", 1: "tb", 2: "terminal"}

SCHEMA = "jass.l3.r1_adjudicated_target.v1"


class R1TargetError(SystemExit):
    """SystemExit carrying a fail-closed exit code (2 = contract violation).

    The message is printed to stderr immediately so it is visible even
    though ``SystemExit``'s own payload becomes the process exit code.
    """

    def __init__(self, message: str, code: int = 2) -> None:
        print(f"error: {message}", file=sys.stderr)
        super().__init__(code)
        self.message = message


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _open_jnnw(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) < JNNW_HEADER_SIZE:
        raise R1TargetError(f"{path}: file smaller than JNNW header")
    if raw[:4] != JNNW_MAGIC:
        raise R1TargetError(f"{path}: bad JNNW magic")
    count = int(np.frombuffer(raw, dtype="<u4", count=1, offset=4)[0])
    expected = JNNW_HEADER_SIZE + count * JNNW_RECORD_SIZE
    if len(raw) != expected:
        raise R1TargetError(
            f"{path}: size {len(raw)} bytes inconsistent with header count "
            f"{count} (expected {expected} bytes)"
        )
    records = np.frombuffer(raw, dtype=JNNW_DTYPE, count=count, offset=JNNW_HEADER_SIZE)
    return records


def _position_prefix_bytes(path: Path, count: int) -> np.ndarray:
    """Return the first 33 bytes of every record, as a (count, 33) uint8 view."""
    raw = np.fromfile(path, dtype=np.uint8, offset=JNNW_HEADER_SIZE)
    raw = raw[: count * JNNW_RECORD_SIZE]
    return raw.reshape(count, JNNW_RECORD_SIZE)[:, :JNNW_POSITION_PREFIX_SIZE]


def _check_positions_identical(orig_path: Path, relab_path: Path, count: int) -> None:
    orig_prefix = _position_prefix_bytes(orig_path, count)
    relab_prefix = _position_prefix_bytes(relab_path, count)
    mismatched = np.any(orig_prefix != relab_prefix, axis=1)
    if bool(np.any(mismatched)):
        first = int(np.argmax(mismatched))
        raise R1TargetError(
            f"bitboards/stm mismatch between original and relabelled corpus "
            f"at record index {first} (first offending index)"
        )


def _load_source_tags(path: Path, count: int) -> np.ndarray:
    raw = np.fromfile(path, dtype=np.uint8)
    if raw.shape[0] != count:
        raise R1TargetError(
            f"{path}: source-tags size {raw.shape[0]} != record count {count}"
        )
    valid = np.array([0, 1, 2], dtype=np.uint8)
    if not bool(np.all(np.isin(raw, valid))):
        bad = int(raw[~np.isin(raw, valid)][0])
        raise R1TargetError(f"{path}: invalid source-tag byte value {bad} (expected 0/1/2)")
    return raw


def _phase_index(pieces: np.ndarray) -> np.ndarray:
    out = np.full(pieces.shape, NUM_PHASES - 1, dtype=np.int64)
    # Evaluate thresholds in the SAME order as the C++ if/else-if chain so a
    # position satisfying multiple thresholds gets the first (highest) one.
    assigned = np.zeros(pieces.shape, dtype=bool)
    for idx, threshold in enumerate(PHASE_THRESHOLDS[:-1]):
        hit = (~assigned) & (pieces >= threshold)
        out[hit] = idx
        assigned |= hit
    out[~assigned] = NUM_PHASES - 1
    return out


def _black_pov_prob(stm: np.ndarray, wdl: np.ndarray) -> np.ndarray:
    wdl_black = np.where(stm == 1, wdl, -wdl).astype(np.float64)
    return (wdl_black + 1.0) / 2.0


def _confusion_matrix(term_wdl: np.ndarray, adj_wdl: np.ndarray) -> list[list[int]]:
    order = (-1, 0, 1)
    matrix = [[0, 0, 0] for _ in order]
    for i, tv in enumerate(order):
        term_mask = term_wdl == tv
        for j, av in enumerate(order):
            matrix[i][j] = int(np.count_nonzero(term_mask & (adj_wdl == av)))
    return matrix


def _reversal_stats(term_wdl: np.ndarray, adj_wdl: np.ndarray, phases: np.ndarray) -> dict[str, Any]:
    reversed_mask = term_wdl != adj_wdl
    n = term_wdl.shape[0]
    global_rate = float(np.count_nonzero(reversed_mask)) / n if n else 0.0
    per_phase: dict[str, Any] = {}
    for idx, name in enumerate(PHASE_NAMES):
        phase_mask = phases == idx
        phase_n = int(np.count_nonzero(phase_mask))
        phase_rev = int(np.count_nonzero(reversed_mask & phase_mask))
        per_phase[name] = {
            "n": phase_n,
            "reversal_rate": (phase_rev / phase_n) if phase_n else None,
        }
    return {"global": global_rate, "by_phase": per_phase}


def _wdl_shares(wdl: np.ndarray) -> dict[str, float]:
    n = wdl.shape[0]
    return {
        "loss": float(np.count_nonzero(wdl == -1)) / n if n else 0.0,
        "draw": float(np.count_nonzero(wdl == 0)) / n if n else 0.0,
        "win": float(np.count_nonzero(wdl == 1)) / n if n else 0.0,
    }


def _evaluate_guard(
    adj_wdl_stm: np.ndarray,
    min_draw_share: float,
    max_draw_share: float,
    max_side_skew: float,
) -> dict[str, Any]:
    n = int(adj_wdl_stm.shape[0])
    if n == 0:
        raise R1TargetError("zero records — failure, not a neutral empty corpus")
    shares = _wdl_shares(adj_wdl_stm)
    skew = abs(shares["win"] - shares["loss"])
    problems = []
    if shares["draw"] < min_draw_share:
        problems.append(f"draw_share {shares['draw']:.4f} < min {min_draw_share}")
    if shares["draw"] > max_draw_share:
        problems.append(f"draw_share {shares['draw']:.4f} > max {max_draw_share}")
    if skew > max_side_skew:
        problems.append(f"|win-loss| skew {skew:.4f} > max {max_side_skew}")
    status = "R1_LABEL_GUARD_PASS" if not problems else "R1_LABEL_GUARD_FAILED"
    return {
        "status": status,
        "n": n,
        "shares_stm_pov": shares,
        "side_skew": skew,
        "min_draw_share": min_draw_share,
        "max_draw_share": max_draw_share,
        "max_side_skew": max_side_skew,
        "problems": problems,
    }


def _quantile_stats(values: np.ndarray) -> dict[str, float]:
    quantile_points = (0, 5, 25, 50, 75, 95, 100)
    quantiles = np.percentile(values, quantile_points)
    stats = {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
    }
    for point, value in zip(quantile_points, quantiles):
        stats[f"q{point}"] = float(value)
    return stats


def build_report(
    original_path: Path,
    relabelled_path: Path,
    tags_path: Path,
    out_r1_path: Path,
    out_adj_path: Path,
    alpha: float,
    min_draw_share: float,
    max_draw_share: float,
    max_side_skew: float,
    context30_path: Path | None,
) -> tuple[dict[str, Any], np.ndarray | None, np.ndarray | None]:
    orig = _open_jnnw(original_path)
    relab = _open_jnnw(relabelled_path)
    if orig.shape[0] != relab.shape[0]:
        raise R1TargetError(
            f"record count mismatch: original={orig.shape[0]} relabelled={relab.shape[0]}"
        )
    n = int(orig.shape[0])
    _check_positions_identical(original_path, relabelled_path, n)
    tags = _load_source_tags(tags_path, n)

    term_wdl_stm = orig["wdl"].astype(np.int64)
    adj_wdl_stm = relab["wdl"].astype(np.int64)
    if not bool(np.all(np.isin(term_wdl_stm, (-1, 0, 1)))):
        raise R1TargetError("original corpus contains a WDL byte outside {-1,0,1}")
    if not bool(np.all(np.isin(adj_wdl_stm, (-1, 0, 1)))):
        raise R1TargetError("relabelled corpus contains a WDL byte outside {-1,0,1}")

    stm = orig["stm"].astype(np.int64)
    p_term = _black_pov_prob(stm, term_wdl_stm)
    p_adj = _black_pov_prob(stm, adj_wdl_stm)

    y_r1 = np.asarray(alpha * p_term + (1.0 - alpha) * p_adj, dtype=np.float32)
    y_adj = np.asarray(p_adj, dtype=np.float32)
    if not bool(np.all(np.isfinite(y_r1))) or not bool(np.all(np.isfinite(y_adj))):
        raise R1TargetError("target computation produced non-finite values")
    if float(y_r1.min()) < 0.0 or float(y_r1.max()) > 1.0:
        raise R1TargetError("y_r1 left probability range [0,1]")
    if float(y_adj.min()) < 0.0 or float(y_adj.max()) > 1.0:
        raise R1TargetError("y_adj left probability range [0,1]")

    # popcount via numpy: sum of per-byte popcounts of the four bitboards.
    def _popcount64(values: np.ndarray) -> np.ndarray:
        byte_view = values.astype(">u8").view(np.uint8).reshape(values.shape[0], 8)
        table = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint32)
        return table[byte_view].sum(axis=1).astype(np.int64)

    total_pieces = (
        _popcount64(orig["wm"])
        + _popcount64(orig["wk"])
        + _popcount64(orig["bm"])
        + _popcount64(orig["bk"])
    )
    phases = _phase_index(total_pieces)

    guard = _evaluate_guard(adj_wdl_stm, min_draw_share, max_draw_share, max_side_skew)

    tag_counts = {
        SOURCE_TAG_NAMES[value]: int(np.count_nonzero(tags == value))
        for value in (0, 1, 2)
    }

    confusion = _confusion_matrix(term_wdl_stm, adj_wdl_stm)
    reversal = _reversal_stats(term_wdl_stm, adj_wdl_stm, phases)
    adj_shares = _wdl_shares(adj_wdl_stm)
    term_shares = _wdl_shares(term_wdl_stm)

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "n_records": n,
        "alpha": alpha,
        "inputs": {
            "original": {"path": str(original_path), "sha256": _sha256(original_path)},
            "relabelled": {"path": str(relabelled_path), "sha256": _sha256(relabelled_path)},
            "source_tags": {"path": str(tags_path), "sha256": _sha256(tags_path)},
        },
        "source_tag_counts": tag_counts,
        "confusion_matrix_terminal_x_adjudicated": {
            "order": [-1, 0, 1],
            "pov": "stm",
            "matrix": confusion,
        },
        "reversal_rate": reversal,
        "terminal_wdl_shares_stm_pov": term_shares,
        "adjudicated_wdl_shares_stm_pov": adj_shares,
        "guard": guard,
        "y_r1_stats": _quantile_stats(y_r1),
        "y_adj_stats": _quantile_stats(y_adj),
        "outputs": {
            "out_r1": {"path": str(out_r1_path)},
            "out_adj": {"path": str(out_adj_path)},
        },
    }

    if context30_path is not None:
        ctx = np.load(context30_path)
        if ctx.dtype != np.float32:
            raise R1TargetError(f"{context30_path}: --context30 must be float32")
        if ctx.shape != (n,):
            raise R1TargetError(
                f"{context30_path}: --context30 length {ctx.shape} != n_records {n}"
            )
        if not bool(np.all(np.isfinite(ctx))):
            raise R1TargetError(f"{context30_path}: --context30 contains non-finite values")
        if float(ctx.min()) < 0.0 or float(ctx.max()) > 1.0:
            raise R1TargetError(f"{context30_path}: --context30 left probability range [0,1]")
        mad = float(np.mean(np.abs(y_r1.astype(np.float64) - ctx.astype(np.float64))))
        if np.std(ctx) > 0 and np.std(y_r1) > 0:
            corr = float(np.corrcoef(y_r1.astype(np.float64), ctx.astype(np.float64))[0, 1])
        else:
            corr = None
        report["context30_comparison"] = {
            "path": str(context30_path),
            "sha256": _sha256(context30_path),
            "stats": _quantile_stats(ctx),
            "mean_abs_diff_vs_y_r1": mad,
            "pearson_corr_vs_y_r1": corr,
        }

    if guard["status"] != "R1_LABEL_GUARD_PASS":
        return report, None, None
    return report, y_r1, y_adj


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--relabelled", required=True, type=Path)
    parser.add_argument("--source-tags", required=True, type=Path)
    parser.add_argument("--out-r1", required=True, type=Path)
    parser.add_argument("--out-adj", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--alpha", type=float, default=DEFAULT_ALPHA)
    parser.add_argument("--context30", type=Path, default=None)
    parser.add_argument("--min-draw-share", type=float, default=DEFAULT_MIN_DRAW_SHARE)
    parser.add_argument("--max-draw-share", type=float, default=DEFAULT_MAX_DRAW_SHARE)
    parser.add_argument("--max-side-skew", type=float, default=DEFAULT_MAX_SIDE_SKEW)
    return parser.parse_args(argv)


def _check_no_clobber(paths: dict[str, Path]) -> None:
    resolved = {name: path.resolve(strict=False) for name, path in paths.items()}
    values = list(resolved.values())
    for i, (name_i, path_i) in enumerate(resolved.items()):
        if path_i.exists():
            raise R1TargetError(f"{name_i} output {path_i} already exists (no-clobber)")
        for j, path_j in enumerate(values):
            if i != j and path_i == path_j:
                raise R1TargetError(f"{name_i} output path aliases another output path")


def _check_outputs_not_inputs(outputs: dict[str, Path], inputs: dict[str, Path]) -> None:
    resolved_outputs = {name: path.resolve(strict=False) for name, path in outputs.items()}
    resolved_inputs = {name: path.resolve(strict=False) for name, path in inputs.items()}
    for out_name, out_path in resolved_outputs.items():
        for in_name, in_path in resolved_inputs.items():
            if out_path == in_path:
                raise R1TargetError(f"{out_name} output cannot alias input {in_name}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    inputs = {
        "original": args.original,
        "relabelled": args.relabelled,
        "source_tags": args.source_tags,
    }
    if args.context30 is not None:
        inputs["context30"] = args.context30
    outputs = {
        "out_r1": args.out_r1,
        "out_adj": args.out_adj,
        "report": args.report,
    }
    _check_no_clobber(outputs)
    _check_outputs_not_inputs(outputs, inputs)

    for name, path in inputs.items():
        if not path.exists():
            raise R1TargetError(f"{name} input {path} does not exist")

    report, y_r1, y_adj = build_report(
        original_path=args.original,
        relabelled_path=args.relabelled,
        tags_path=args.source_tags,
        out_r1_path=args.out_r1,
        out_adj_path=args.out_adj,
        alpha=args.alpha,
        min_draw_share=args.min_draw_share,
        max_draw_share=args.max_draw_share,
        max_side_skew=args.max_side_skew,
        context30_path=args.context30,
    )

    if y_r1 is None or y_adj is None:
        # Guard failed: still write the report (so the failure is auditable)
        # but no npy outputs, and record their sha256 as absent.
        _atomic_write_json(args.report, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 6

    _atomic_save_npy(args.out_r1, y_r1)
    _atomic_save_npy(args.out_adj, y_adj)
    report["outputs"]["out_r1"]["sha256"] = _sha256(args.out_r1)
    report["outputs"]["out_adj"]["sha256"] = _sha256(args.out_adj)
    _atomic_write_json(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
