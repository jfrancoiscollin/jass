#!/usr/bin/env python3
"""Evaluate A/B/C/D PJTW models on one shared opening-disjoint holdout."""
from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
geometry = os.environ.get("JASS_PATTERNS_DIR")
if geometry:
    sys.path.insert(0, geometry)
sys.path.insert(0, str(TOOLS))
import eval_phase  # noqa: E402
import patterns  # noqa: E402

JNNW_DTYPE = np.dtype([
    ("wm", "<u8"), ("wk", "<u8"), ("bm", "<u8"), ("bk", "<u8"),
    ("stm", "u1"), ("score", "<i4"), ("wdl", "i1"),
])
JSM1_DTYPE = np.dtype([("game_id", "<u8"), ("opening_id", "<u8"), ("seeded", "u1")])
JSM2_DTYPE = np.dtype([
    ("game_id", "<u8"), ("opening_id", "<u8"), ("seeded", "u1"),
    ("ply", "<u2"), ("game_plies", "<u2"), ("last_eps_ply", "<u2"),
    ("game_result", "i1"), ("flags", "u1"),
])


def open_counted(path: str, magics: dict[bytes, np.dtype]) -> tuple[np.memmap, int]:
    with open(path, "rb") as handle:
        header = handle.read(8)
    if len(header) != 8 or header[:4] not in magics:
        raise ValueError(f"{path}: unexpected counted-file magic")
    count = struct.unpack_from("<I", header, 4)[0]
    dtype = magics[header[:4]]
    if Path(path).stat().st_size != 8 + count * dtype.itemsize:
        raise ValueError(f"{path}: size/count mismatch")
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(count,)), count


def open_feat(path: str, expected: int) -> np.memmap:
    with open(path, "rb") as handle:
        header = handle.read(12)
    if len(header) != 12 or header[:4] != b"FEAT":
        raise ValueError(f"{path}: invalid FEAT")
    count, width = struct.unpack_from("<II", header, 4)
    if count != expected or Path(path).stat().st_size != 12 + count * width * 4:
        raise ValueError(f"{path}: FEAT shape drift")
    return np.memmap(path, dtype="<f4", mode="r", offset=12, shape=(count, width))


def open_model(path: str, expected_extras: int) -> tuple[np.memmap, int, int]:
    with open(path, "rb") as handle:
        header = handle.read(20)
    if len(header) != 20:
        raise ValueError(f"{path}: truncated PJTW")
    magic, version, scale, n_pat, n_ext = struct.unpack("<5I", header)
    expected_pat = patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN
    if magic != 0x57544A50 or (version & 0xFF) != 3 or scale <= 0:
        raise ValueError(f"{path}: invalid PJTW header")
    if n_pat != expected_pat or n_ext != expected_extras:
        raise ValueError(f"{path}: PJTW geometry drift")
    total = 2 * (n_pat + n_ext)
    if Path(path).stat().st_size != 20 + total * 4:
        raise ValueError(f"{path}: PJTW size drift")
    return np.memmap(path, dtype="<i4", mode="r", offset=20, shape=(total,)), scale, n_pat


def stable_sigmoid(logits: np.ndarray) -> np.ndarray:
    out = np.empty_like(logits, dtype=np.float64)
    positive = logits >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-logits[positive]))
    exp_value = np.exp(logits[~positive])
    out[~positive] = exp_value / (1.0 + exp_value)
    return out


def score_model(
    path: str,
    records: np.memmap,
    feat: np.memmap,
    start: int,
    chunk: int,
) -> np.ndarray:
    weights, scale, n_pat = open_model(path, feat.shape[1])
    logits = np.empty(len(records) - start, dtype=np.float64)
    offsets = np.arange(patterns.NUM_PATTERNS, dtype=np.int64) * patterns.BUCKETS_PER_PATTERN
    ext_mg = np.asarray(weights[2 * n_pat:2 * n_pat + feat.shape[1]], dtype=np.float64) / scale
    ext_eg = np.asarray(weights[2 * n_pat + feat.shape[1]:], dtype=np.float64) / scale
    for lo in range(start, len(records), chunk):
        hi = min(lo + chunk, len(records))
        rec = records[lo:hi]
        wm = np.ascontiguousarray(rec["wm"])
        bm = np.ascontiguousarray(rec["bm"])
        columns = patterns.extract_indices(bm, wm) + offsets[None, :]
        mg = np.asarray(weights[columns], dtype=np.float64).sum(axis=1) / scale
        eg = np.asarray(weights[n_pat + columns], dtype=np.float64).sum(axis=1) / scale
        extras = np.asarray(feat[lo:hi], dtype=np.float64)
        mg += extras @ ext_mg
        eg += extras @ ext_eg
        wmg = eval_phase.tempo_wmg_bb(wm, bm).astype(np.float64)
        logits[lo - start:hi - start] = wmg * mg + (1.0 - wmg) * eg
    return logits


def loss_vector(logits: np.ndarray, targets: np.ndarray) -> np.ndarray:
    return np.logaddexp(0.0, logits) - targets * logits


def metrics(logits: np.ndarray, targets: np.ndarray) -> dict:
    probabilities = stable_sigmoid(logits)
    informative = targets != 0.5
    return {
        "n": int(len(targets)),
        "logloss": float(loss_vector(logits, targets).mean()),
        "mae_probability": float(np.abs(probabilities - targets).mean()),
        "brier": float(np.square(probabilities - targets).mean()),
        "target_mean": float(targets.mean()),
        "prediction_mean": float(probabilities.mean()),
        "sign_agreement_non_neutral": (
            float(np.mean((probabilities[informative] > 0.5) == (targets[informative] > 0.5)))
            if np.any(informative) else None
        ),
        "non_neutral_n": int(informative.sum()),
    }


def cluster_bootstrap_effect(
    effect: np.ndarray,
    clusters: np.ndarray,
    *,
    samples: int,
    seed: int,
) -> dict:
    unique, inverse = np.unique(clusters, return_inverse=True)
    sums = np.bincount(inverse, weights=effect).astype(np.float64)
    counts = np.bincount(inverse).astype(np.float64)
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    # Bound the temporary integer matrix independently of the number of
    # openings (large self-play corpora can have tens of thousands).
    batch = max(1, min(2048, 2_000_000 // max(1, len(unique))))
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        selected = rng.integers(0, len(unique), size=(stop - start, len(unique)))
        draws[start:stop] = sums[selected].sum(axis=1) / counts[selected].sum(axis=1)
    low, high = np.quantile(draws, [0.025, 0.975])
    return {
        "effect": float(effect.mean()),
        "ci_low": float(low),
        "ci_high": float(high),
        "cluster_unit": "opening_id",
        "clusters": int(len(unique)),
        "bootstrap_samples": samples,
        "seed": seed,
        "positive_cluster_fraction": float(np.mean(sums / counts > 0.0)),
    }


def parse_assignment(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    name, path = value.split("=", 1)
    if not name or not path:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    return name, path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--feat", required=True)
    parser.add_argument("--context-targets", required=True)
    parser.add_argument("--train-count", type=int, required=True)
    parser.add_argument("--model", action="append", type=parse_assignment, required=True)
    parser.add_argument("--contrast", action="append", required=True,
                        help="CANDIDATE:BASELINE; positive effect means lower candidate loss")
    parser.add_argument("--chunk", type=int, default=20000)
    parser.add_argument("--bootstrap-samples", type=int, default=5000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260814)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    records, count = open_counted(args.data, {b"JNNW": JNNW_DTYPE})
    metadata, meta_count = open_counted(args.meta, {b"JSM1": JSM1_DTYPE, b"JSM2": JSM2_DTYPE})
    feat = open_feat(args.feat, count)
    targets = np.load(args.context_targets, mmap_mode="r")
    if meta_count != count or targets.shape != (count,):
        raise SystemExit("data/meta/target alignment drift")
    if not 0 < args.train_count < count:
        raise SystemExit("invalid train count")
    context = np.asarray(targets[args.train_count:], dtype=np.float64)
    rec_holdout = records[args.train_count:]
    wdl = np.asarray(rec_holdout["wdl"], dtype=np.float64)
    stm = np.asarray(rec_holdout["stm"])
    terminal = (np.where(stm == 1, wdl, -wdl) + 1.0) * 0.5
    openings = np.asarray(metadata[args.train_count:]["opening_id"], dtype=np.uint64)

    model_paths = dict(args.model)
    if len(model_paths) != len(args.model):
        raise SystemExit("duplicate model name")
    logits = {
        name: score_model(path, records, feat, args.train_count, args.chunk)
        for name, path in model_paths.items()
    }
    target_sets = {"current_context30": context, "terminal_wdl": terminal}
    report = {
        "schema": "jass.megacorpus.abcd_static_readout.v1",
        "cohort": {
            "records": int(len(context)),
            "opening_disjoint_from_current_train": True,
            "unique_openings": int(len(np.unique(openings))),
            "selection_role": "diagnostic_only_strength_is_primary",
        },
        "models": {
            name: {target_name: metrics(values, target)
                   for target_name, target in target_sets.items()}
            for name, values in logits.items()
        },
        "contrasts": {},
    }
    for contrast_index, raw in enumerate(args.contrast):
        if ":" not in raw:
            raise SystemExit(f"invalid contrast {raw!r}")
        candidate, baseline = raw.split(":", 1)
        if candidate not in logits or baseline not in logits:
            raise SystemExit(f"unknown model in contrast {raw!r}")
        item = {}
        for target_index, (target_name, target) in enumerate(target_sets.items()):
            effect = loss_vector(logits[baseline], target) - loss_vector(logits[candidate], target)
            item[target_name] = cluster_bootstrap_effect(
                effect, openings, samples=args.bootstrap_samples,
                seed=args.bootstrap_seed + 100 * contrast_index + target_index,
            )
        report["contrasts"][raw] = item
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
