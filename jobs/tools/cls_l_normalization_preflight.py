#!/usr/bin/env python3
"""CLS-L source/normalisation preflight over the frozen CURRENT_2M distribution.

No optimiser is invoked.  The stage reconstructs the exact train-time coordinate
system, projects immutable CURRICULUM to that system, and seals the two TRAIN-only
unregularised gradient norms required by the merged CLS-L V1 preregistration.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "pattern_jass" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cls_l_objective as objective  # noqa: E402
import train_stream as stream  # noqa: E402

SCHEMA = "jass.cls_l_source_normalization_preflight.v1"
TERMINAL = "CLS_L_SOURCE_NORMALIZATION_PREFLIGHT_READY_V1"
RECORDS = 2_000_000
TRAIN_RECORDS = 1_800_796
HOLDOUT_RECORDS = 199_204
EXTRAS = 120
CHUNK = 20_000
L2 = 1e-5
FOLD = "exact"
TEMPO_STAGE = True
PRUNE_MIN_VISITS = 1


class PreflightError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    if path.exists():
        raise PreflightError(f"no-clobber:{path}")
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def validate_local_targets(path: Path, records: int) -> np.ndarray:
    try:
        values = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise PreflightError(f"local_target_load:{exc}") from exc
    if not isinstance(values, np.ndarray) or values.shape != (records,):
        raise PreflightError(f"local_target_shape:{getattr(values, 'shape', None)}")
    if values.dtype != np.dtype(np.float32):
        raise PreflightError(f"local_target_dtype:{values.dtype}")
    for start in range(0, records, CHUNK):
        block = np.asarray(values[start:start + CHUNK])
        if not bool(np.all(np.isfinite(block))):
            raise PreflightError("local_target_nonfinite")
        if bool(np.any(block < 0.0)) or bool(np.any(block > 1.0)):
            raise PreflightError("local_target_range")
    return values


def wdl_black_probability(wdl: np.ndarray, stm: np.ndarray) -> np.ndarray:
    w = np.asarray(wdl, dtype=np.float64)
    s = np.asarray(stm)
    if w.shape != s.shape:
        raise PreflightError("wdl_stm_shape")
    black = np.where(s == 1, w, -w)
    return (black + 1.0) * 0.5


def compute(data: Path, feat_path: Path, local_path: Path, parent_path: Path) -> dict:
    mm, records = stream.open_jnnw(str(data))
    feat, extras = stream.open_feat(str(feat_path), records)
    if records != RECORDS:
        raise PreflightError(f"record_count:{records}")
    if extras != EXTRAS:
        raise PreflightError(f"extras:{extras}")
    local = validate_local_targets(local_path, records)

    folder = stream.Folder(FOLD)
    tb = folder.TB
    wdl_targets = np.empty(records, dtype=np.float64)
    wmg_all = np.empty(records, dtype=np.float32)
    weg_all = np.empty(records, dtype=np.float32)
    counts = np.zeros(tb, dtype=np.int64)

    for start in range(0, records, CHUNK):
        stop = min(start + CHUNK, records)
        rec = mm[start:stop]
        wm = np.ascontiguousarray(rec["wm"])
        bm = np.ascontiguousarray(rec["bm"])
        stm = np.ascontiguousarray(rec["stm"])
        wdl = np.ascontiguousarray(rec["wdl"])
        wdl_targets[start:stop] = wdl_black_probability(wdl, stm)
        wmg = stream._tempo_wmg_bb(wm, bm)
        wmg_all[start:stop] = np.asarray(wmg, dtype=np.float32)
        weg_all[start:stop] = np.asarray(1.0 - wmg, dtype=np.float32)
        cols, _signs = folder.cols_signs(bm, wm)
        counts += np.bincount(cols.ravel(), minlength=tb)

    keep = np.flatnonzero(counts >= PRUNE_MIN_VISITS)
    keep = keep[np.argsort(counts[keep])[::-1]]
    remap = np.zeros(tb, dtype=np.int32)
    remap[keep] = np.arange(1, len(keep) + 1, dtype=np.int32)
    pat_n = len(keep) + 1
    n_cols = 2 * pat_n + 2 * EXTRAS

    parent, scale = stream.project_champion_mean(
        str(parent_path), folder, keep, pat_n, EXTRAS
    )
    if parent.shape != (n_cols,):
        raise PreflightError(f"parent_geometry:{parent.shape}:{n_cols}")

    def build_fn(selected: np.ndarray):
        lo = int(selected[0]); hi = int(selected[-1]) + 1
        if hi - lo != len(selected) or int(selected[-1]) != hi - 1:
            raise PreflightError("noncontiguous_train_chunk")
        rec = mm[lo:hi]
        wm = np.ascontiguousarray(rec["wm"])
        bm = np.ascontiguousarray(rec["bm"])
        cols, signs = folder.cols_signs(bm, wm)
        cols = remap[cols]
        wmg = wmg_all[lo:hi].astype(np.float64)
        weg = weg_all[lo:hi].astype(np.float64)
        xpat = stream.build_sparse_X_phased(cols, wmg, weg, pat_n, signs)
        extras_block = np.ascontiguousarray(feat[lo:hi]).astype(np.float64)
        xext = stream.build_extras_phased(extras_block, wmg, weg)
        return stream.sp.hstack([xpat, xext], format="csr")

    train_rows = np.arange(TRAIN_RECORDS, dtype=np.int64)
    norms = objective.frozen_gradient_norms(
        build_fn,
        train_rows,
        local,
        wdl_targets,
        parent,
        batch=CHUNK,
    )

    identity = hashlib.sha256()
    identity.update(np.asarray(keep, dtype="<i8").tobytes())
    identity.update(f"{FOLD}|{pat_n}|{EXTRAS}|{n_cols}|tempo|prune1".encode())

    return {
        "schema": SCHEMA,
        "terminal": TERMINAL,
        "state": "completed",
        "records": RECORDS,
        "train_records": TRAIN_RECORDS,
        "holdout_records": HOLDOUT_RECORDS,
        "normalization_scope": "TRAIN_ONLY",
        "holdout_rows_used_for_normalization": 0,
        "normalization_point": "projected_CURRICULUM_w0",
        "gradient_norms": norms,
        "lambda_normalized_gradient": objective.FROZEN_LAMBDA,
        "common_recipe": {
            "fold": FOLD,
            "tempo_stage": TEMPO_STAGE,
            "extras": EXTRAS,
            "prune_min_visits": PRUNE_MIN_VISITS,
            "l2": L2,
            "chunk": CHUNK,
            "parent_scale": int(scale),
            "pattern_slots": int(pat_n),
            "trainable_coordinates": int(n_cols),
            "coordinate_identity_sha256": identity.hexdigest(),
        },
        "inputs": {
            "data_sha256": sha256(data),
            "feat_sha256": sha256(feat_path),
            "local_targets_sha256": sha256(local_path),
            "parent_sha256": sha256(parent_path),
        },
        "fits": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "confirmation_target_reads": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--feat", required=True, type=Path)
    ap.add_argument("--local-targets", required=True, type=Path)
    ap.add_argument("--parent", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    payload = compute(args.data, args.feat, args.local_targets, args.parent)
    atomic_json(args.out, payload)
    print(json.dumps({"terminal": TERMINAL, "gradient_norms": payload["gradient_norms"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
