#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evaluate the four replay-DOE models on separate OLD and NEW holdouts.

Positive contrast effects mean that the candidate has lower native-WDL
log-loss than the baseline.  Bootstrap resampling is clustered by opening_id.
The balanced diagnostic gives OLD and NEW equal 50% cohort mass regardless of
holdout row counts.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs" / "tools"))
import jass_megacorpus_static_readout as base  # noqa: E402


def _assignment(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    name, path = raw.split("=", 1)
    if not name or not path:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    return name, path


def _wdl_targets(records: np.memmap) -> np.ndarray:
    wdl = np.asarray(records["wdl"], dtype=np.float64)
    stm = np.asarray(records["stm"])
    if not bool(np.all(np.isin(wdl, (-1.0, 0.0, 1.0)))):
        raise ValueError("holdout contains invalid WDL")
    if not bool(np.all(np.isin(stm, (0, 1)))):
        raise ValueError("holdout contains invalid side-to-move")
    return (np.where(stm == 1, wdl, -wdl) + 1.0) * 0.5


def _cluster_arrays(effect: np.ndarray, clusters: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    _, inverse = np.unique(clusters, return_inverse=True)
    sums = np.bincount(inverse, weights=effect).astype(np.float64)
    counts = np.bincount(inverse).astype(np.float64)
    if len(sums) == 0 or bool(np.any(counts <= 0)):
        raise ValueError("empty/invalid opening clusters")
    return sums, counts


def _balanced_cluster_bootstrap(
    old_effect: np.ndarray,
    old_clusters: np.ndarray,
    new_effect: np.ndarray,
    new_clusters: np.ndarray,
    *,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    old_sums, old_counts = _cluster_arrays(old_effect, old_clusters)
    new_sums, new_counts = _cluster_arrays(new_effect, new_clusters)
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    batch = max(1, min(1024, 2_000_000 // max(len(old_sums), len(new_sums))))
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        oi = rng.integers(0, len(old_sums), size=(stop - start, len(old_sums)))
        ni = rng.integers(0, len(new_sums), size=(stop - start, len(new_sums)))
        old_draw = old_sums[oi].sum(axis=1) / old_counts[oi].sum(axis=1)
        new_draw = new_sums[ni].sum(axis=1) / new_counts[ni].sum(axis=1)
        draws[start:stop] = 0.5 * (old_draw + new_draw)
    point = 0.5 * (float(old_effect.mean()) + float(new_effect.mean()))
    low, high = np.quantile(draws, (0.025, 0.975))
    return {
        "effect": point,
        "ci_low": float(low),
        "ci_high": float(high),
        "probability_positive": float(np.mean(draws > 0.0)),
        "bootstrap_samples": samples,
        "seed": seed,
        "cohort_mass": {"OLD": 0.5, "NEW": 0.5},
        "OLD_opening_clusters": int(len(old_sums)),
        "NEW_opening_clusters": int(len(new_sums)),
    }


def _load_cohort(
    *, data: str, meta: str, feat: str, model_paths: dict[str, str], chunk: int
) -> dict[str, Any]:
    records, count = base.open_counted(data, {b"JNNW": base.JNNW_DTYPE})
    metadata, meta_count = base.open_counted(
        meta, {b"JSM1": base.JSM1_DTYPE, b"JSM2": base.JSM2_DTYPE}
    )
    features = base.open_feat(feat, count)
    if meta_count != count or count <= 0:
        raise ValueError("holdout data/meta alignment drift")
    targets = _wdl_targets(records)
    openings = np.asarray(metadata["opening_id"], dtype=np.uint64)
    logits = {
        name: base.score_model(path, records, features, 0, chunk)
        for name, path in model_paths.items()
    }
    return {
        "records": records,
        "targets": targets,
        "openings": openings,
        "logits": logits,
        "report": {
            "records": int(count),
            "unique_openings": int(len(np.unique(openings))),
            "target": "native_JNNW_WDL_black_POV_probability",
            "models": {name: base.metrics(values, targets) for name, values in logits.items()},
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("old", "new"):
        parser.add_argument(f"--{label}-data", required=True)
        parser.add_argument(f"--{label}-meta", required=True)
        parser.add_argument(f"--{label}-feat", required=True)
    parser.add_argument("--model", action="append", type=_assignment, required=True)
    parser.add_argument("--contrast", action="append", required=True,
                        help="CANDIDATE:BASELINE")
    parser.add_argument("--chunk", type=int, default=20000)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=2026082109)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    model_paths = dict(args.model)
    if len(model_paths) != len(args.model) or set(model_paths) != {"A", "B", "C", "D"}:
        raise SystemExit("models must be exactly A/B/C/D with no duplicates")
    old = _load_cohort(
        data=args.old_data, meta=args.old_meta, feat=args.old_feat,
        model_paths=model_paths, chunk=args.chunk,
    )
    new = _load_cohort(
        data=args.new_data, meta=args.new_meta, feat=args.new_feat,
        model_paths=model_paths, chunk=args.chunk,
    )

    contrasts: dict[str, Any] = {}
    for index, raw in enumerate(args.contrast):
        if ":" not in raw:
            raise SystemExit(f"invalid contrast: {raw}")
        candidate, baseline = raw.split(":", 1)
        if candidate not in model_paths or baseline not in model_paths:
            raise SystemExit(f"unknown model in contrast: {raw}")
        old_effect = base.loss_vector(old["logits"][baseline], old["targets"]) - base.loss_vector(
            old["logits"][candidate], old["targets"]
        )
        new_effect = base.loss_vector(new["logits"][baseline], new["targets"]) - base.loss_vector(
            new["logits"][candidate], new["targets"]
        )
        seed = args.bootstrap_seed + index * 100
        contrasts[raw] = {
            "positive_means": f"{candidate}_lower_logloss_than_{baseline}",
            "OLD": base.cluster_bootstrap_effect(
                old_effect, old["openings"], samples=args.bootstrap_samples, seed=seed
            ),
            "NEW": base.cluster_bootstrap_effect(
                new_effect, new["openings"], samples=args.bootstrap_samples, seed=seed + 1
            ),
            "BALANCED_OLD_NEW": _balanced_cluster_bootstrap(
                old_effect, old["openings"], new_effect, new["openings"],
                samples=args.bootstrap_samples, seed=seed + 2,
            ),
        }

    balanced_models = {}
    for name in model_paths:
        om = old["report"]["models"][name]
        nm = new["report"]["models"][name]
        balanced_models[name] = {
            "logloss": 0.5 * (om["logloss"] + nm["logloss"]),
            "brier": 0.5 * (om["brier"] + nm["brier"]),
            "mae_probability": 0.5 * (om["mae_probability"] + nm["mae_probability"]),
            "cohort_mass": {"OLD": 0.5, "NEW": 0.5},
        }

    payload = {
        "schema": "jass.l3_exploratory_replay_doe_static_readout.v1",
        "target": "native_JNNW_WDL",
        "holdout_training_leakage": 0,
        "cohorts": {"OLD": old["report"], "NEW": new["report"]},
        "balanced_models": balanced_models,
        "contrasts": contrasts,
        "primary_contrast": "B:A",
        "secondary_contrasts": ["B:C", "C:D"],
        "selection_role": "diagnostic_only_native_force_is_primary",
        "promotion_authorized": False,
    }
    out = Path(args.out)
    if out.exists():
        raise ValueError(f"refusing to overwrite {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
