#!/usr/bin/env python3
"""Diagnostic-only post-fit SB1 readout. It never selects a model or emits a strength verdict."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from jobs.tools.sb1_weight_audit import (
    correlation,
    model_blocks,
    open_feat,
    open_jnnw,
    pair_family_stats,
    rms,
    score_components,
    sha256_file,
)


def stable_sigmoid(x: np.ndarray) -> np.ndarray:
    values = np.asarray(x, dtype=np.float64)
    out = np.empty_like(values)
    positive = values >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_value = np.exp(values[~positive])
    out[~positive] = exp_value / (1.0 + exp_value)
    return out


def cross_entropy(logits: np.ndarray, targets: np.ndarray) -> float:
    return float(np.mean(np.logaddexp(0.0, logits) - targets * logits))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--feat", required=True)
    parser.add_argument("--target-values", required=True)
    parser.add_argument("--train-count", type=int, required=True)
    parser.add_argument("--self-basin", required=True)
    parser.add_argument("--scan-basin", required=True)
    parser.add_argument("--chunk", type=int, default=20000)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    records = open_jnnw(args.data)
    if not 0 < args.train_count < len(records):
        raise SystemExit("invalid train count")
    feat = open_feat(args.feat, len(records))
    targets = np.load(args.target_values, allow_pickle=False, mmap_mode="r")
    if targets.dtype != np.float32 or targets.shape != (len(records),):
        raise SystemExit("target sidecar drift")
    holdout_targets = np.asarray(targets[args.train_count:], dtype=np.float64)

    self_model = model_blocks(args.self_basin, feat.shape[1])
    scan_model = model_blocks(args.scan_basin, feat.shape[1])
    self_total, self_pattern, self_dense = score_components(
        self_model, records, feat, args.train_count, args.chunk
    )
    scan_total, scan_pattern, scan_dense = score_components(
        scan_model, records, feat, args.train_count, args.chunk
    )
    self_prob = stable_sigmoid(self_total)
    scan_prob = stable_sigmoid(scan_total)

    report = {
        "schema": "jass.sb1.postfit_readout.v1",
        "role": "diagnostic_only_not_selection_not_strength",
        "models": {
            "SELF_BASIN": {"path": args.self_basin, "sha256": sha256_file(args.self_basin)},
            "SCAN_BASIN": {"path": args.scan_basin, "sha256": sha256_file(args.scan_basin)},
        },
        "parameter_distance": pair_family_stats(self_model, scan_model),
        "prediction_distance": {
            "holdout_n": int(len(holdout_targets)),
            "logit_rms": rms(scan_total - self_total),
            "logit_correlation": correlation(self_total, scan_total),
            "probability_rms": rms(scan_prob - self_prob),
            "probability_correlation": correlation(self_prob, scan_prob),
            "pattern_component_rms": rms(scan_pattern - self_pattern),
            "dense_component_rms": rms(scan_dense - self_dense),
        },
        "holdout": {
            "SELF_BASIN_cross_entropy": cross_entropy(self_total, holdout_targets),
            "SCAN_BASIN_cross_entropy": cross_entropy(scan_total, holdout_targets),
            "target_mean": float(holdout_targets.mean()),
            "SELF_BASIN_prediction_mean": float(self_prob.mean()),
            "SCAN_BASIN_prediction_mean": float(scan_prob.mean()),
        },
        "markers": {
            "SCIENTIFIC_DECISION": False,
            "SELECTION": False,
            "STRENGTH_VERDICT": False,
            "FRESH_FORCE": 0,
            "STRENGTH_GAMES": 0,
        },
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
