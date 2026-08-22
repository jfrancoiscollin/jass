#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build historical CONTEXT_30 targets for a train-only replay corpus.

The production ``l3_conditional_targets`` builder normally requires a non-empty
holdout because it also publishes predictions for that holdout.  A replay fit,
however, materialises only its training rows.  This adapter preserves the exact
historical train-target recipe by appending one synthetic *holdout-only* row in
memory, then discarding its prediction.  The synthetic row never participates
in an OOF mapper fit, RMS estimate, target blend, PatternEval fit or readout.

The scientific recipe is intentionally not configurable here:

* legacy 120-extra / 11-component context mapper;
* five game-disjoint folds, seed 20260811;
* uniform row weighting, ridge 1e-4;
* 50 Newton iterations, tolerance 1e-8, 20 line-search steps;
* aligned target = 0.70 terminal WDL + 0.30 conditional WDL;
* black POV probability output in [0, 1].

No shuffled control, self-play, oracle, EGDB label or search score is consumed.

This adapter is executed beside the immutable historical builder blob used by
the original CONTEXT_30 experiment.  Its calls therefore deliberately use the
legacy builder ABI (one-argument ``context_matrix`` and only the original
cross-fit keyword arguments).  Newer builder defaults are compatible with that
ABI, which also keeps the adapter testable on the current tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

import l3_conditional_targets as base


CONTEXT_SCHEMA = "ctx1-legacy-120"
FOLD_COUNT = 5
FOLD_SEED = 20260811
RIDGE = 1e-4
MAX_ITERATIONS = 50
TOLERANCE = 1e-8
LINE_SEARCH_STEPS = 20
ALPHA = 0.30


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _unique_sentinel_game_id(game_ids: np.ndarray) -> np.uint64:
    values = np.asarray(game_ids, dtype=np.uint64)
    if values.size == 0:
        raise ValueError("train-only context30 requires at least one row")
    maximum = int(values.max())
    limit = (1 << 64) - 1
    if maximum < limit:
        candidate = np.uint64(maximum + 1)
        if not bool(np.any(values == candidate)):
            return candidate
    used = set(int(value) for value in np.unique(values))
    for candidate in range(1 << 20):
        if candidate not in used:
            return np.uint64(candidate)
    raise ValueError("cannot allocate a unique synthetic holdout game id")


def historical_context_matrix(features: np.ndarray) -> np.ndarray:
    """Build CTX1 through the immutable historical one-argument ABI."""

    return base.context_matrix(features)


def train_only_oof_predictions(
    contexts: np.ndarray,
    outcomes: np.ndarray,
    game_ids: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return OOF predictions for every real row using the historical recipe.

    ``base.cross_fitted_predictions`` fits every OOF fold exclusively on the
    prefix ``[:train_count]``.  We append one unique holdout row only to satisfy
    its historical non-empty-holdout contract.  Therefore the first ``n``
    predictions are mathematically identical to those obtained when the same
    train prefix is followed by any legitimate, disjoint holdout.
    """

    x = np.asarray(contexts, dtype=np.float64)
    y = np.asarray(outcomes, dtype=np.float64)
    games = np.asarray(game_ids, dtype=np.uint64)
    if x.ndim != 2 or y.shape != (x.shape[0],) or games.shape != (x.shape[0],):
        raise ValueError("train-only context arrays are not aligned")
    if x.shape[0] < FOLD_COUNT:
        raise ValueError("train-only context corpus is too small for five folds")
    if not bool(np.all(np.isfinite(x))) or not bool(np.all(np.isfinite(y))):
        raise ValueError("train-only context arrays contain non-finite values")
    if not bool(np.all(np.isin(y, (-1.0, 0.0, 1.0)))):
        raise ValueError("terminal outcomes must be in {-1,0,1}")

    sentinel_game = _unique_sentinel_game_id(games)
    # The sentinel feature/outcome is irrelevant to OOF training.  Reusing the
    # first context avoids inventing an out-of-support vector for the unused
    # final-mapper prediction.
    x_ext = np.concatenate((x, x[:1]), axis=0)
    y_ext = np.concatenate((y, np.asarray([0.0], dtype=np.float64)))
    games_ext = np.concatenate((games, np.asarray([sentinel_game], dtype=np.uint64)))

    predictions, _, mapping = base.cross_fitted_predictions(
        x_ext,
        y_ext,
        games_ext,
        x.shape[0],
        fold_count=FOLD_COUNT,
        fold_seed=FOLD_SEED,
        ridge=RIDGE,
        max_iterations=MAX_ITERATIONS,
        tolerance=TOLERANCE,
        line_search_steps=LINE_SEARCH_STEPS,
    )
    real = np.asarray(predictions[: x.shape[0]], dtype=np.float64)
    if real.shape != y.shape or not bool(np.all(np.isfinite(real))):
        raise RuntimeError("train-only OOF predictions are invalid")
    if bool(np.any(np.abs(real) > 1.0)):
        raise RuntimeError("train-only OOF predictions left WDL range")

    mapping = dict(mapping)
    mapping["adapter"] = {
        "mode": "train_only_via_disjoint_synthetic_holdout",
        "real_train_rows": int(x.shape[0]),
        "synthetic_holdout_rows": 1,
        "synthetic_game_id": int(sentinel_game),
        "synthetic_row_used_in_oof_training": False,
        "synthetic_row_included_in_output_targets": False,
        "historical_train_recipe_unchanged": True,
        "historical_builder_abi": "legacy_20260811",
    }
    return real, mapping


def run(args: argparse.Namespace) -> dict[str, Any]:
    data_path = Path(args.data)
    meta_path = Path(args.meta)
    feat_path = Path(args.feat)
    out_path = Path(args.out)
    report_path = Path(args.report)
    if out_path.resolve(strict=False) == report_path.resolve(strict=False):
        raise ValueError("target and report outputs must be distinct")
    inputs = {path.resolve(strict=False) for path in (data_path, meta_path, feat_path)}
    if out_path.resolve(strict=False) in inputs or report_path.resolve(strict=False) in inputs:
        raise ValueError("outputs cannot overwrite inputs")
    if out_path.exists() or report_path.exists():
        raise ValueError("train-only context30 outputs are no-clobber")

    records = base._open_counted(data_path, b"JNNW", base.JNNW_DTYPE)
    metadata, meta_schema = base._open_meta(meta_path, len(records))
    features, width = base._open_feat(feat_path, len(records))
    if len(records) <= 0:
        raise ValueError("empty replay corpus")
    if width != 120:
        raise ValueError(f"historical context30 requires 120 extras, got {width}")

    outcomes = np.asarray(
        np.where(records["stm"] == 1, records["wdl"], -records["wdl"]),
        dtype=np.float64,
    )
    if not bool(np.all(np.isin(outcomes, (-1.0, 0.0, 1.0)))):
        raise ValueError("JNNW contains invalid WDL")
    contexts = historical_context_matrix(features)
    games = np.asarray(metadata["game_id"], dtype=np.uint64)
    predictions, mapping = train_only_oof_predictions(contexts, outcomes, games)

    blended_wdl = (1.0 - ALPHA) * outcomes + ALPHA * predictions
    targets = np.asarray((blended_wdl + 1.0) * 0.5, dtype=np.float32)
    if targets.shape != (len(records),) or not bool(np.all(np.isfinite(targets))):
        raise RuntimeError("context30 target shape/finiteness drift")
    if float(targets.min()) < 0.0 or float(targets.max()) > 1.0:
        raise RuntimeError("context30 targets left probability range")

    base._atomic_save_npy(out_path, targets)
    report = {
        "schema": "jass.l3_replay_context30_targets.v1",
        "operation": "historical_context30_aligned_train_only_oof",
        "records": int(len(records)),
        "train_records": int(len(records)),
        "holdout_records": 0,
        "meta_schema": meta_schema,
        "feature_width": width,
        "context_schema": CONTEXT_SCHEMA,
        "target": {
            "name": "CONTEXT_30_ALIGNED_alpha_0.30",
            "formula": "(1-alpha)*terminal_wdl_black+alpha*conditional_wdl_black",
            "alpha": ALPHA,
            "output_pov": "black",
            "output_range": "win_probability_[0,1]",
            "oracle_or_egdb_signal": False,
            "search_score_signal": False,
            "new_selfplay_generated": False,
        },
        "fixed_recipe": {
            "fold_count": FOLD_COUNT,
            "fold_seed": FOLD_SEED,
            "fold_group": "game_id",
            "row_weighting": "uniform",
            "ridge": RIDGE,
            "max_iterations": MAX_ITERATIONS,
            "tolerance": TOLERANCE,
            "line_search_steps": LINE_SEARCH_STEPS,
        },
        "mapping": mapping,
        "source": {
            "data": str(data_path),
            "data_sha256": _sha256(data_path),
            "meta": str(meta_path),
            "meta_sha256": _sha256(meta_path),
            "feat": str(feat_path),
            "feat_sha256": _sha256(feat_path),
        },
        "output": {
            "targets": str(out_path),
            "targets_sha256": _sha256(out_path),
            "dtype": "float32",
            "shape": [int(len(records))],
        },
        "safety": {
            "synthetic_holdout_rows_persisted": 0,
            "synthetic_holdout_rows_consumed_by_pattern_fit": 0,
            "holdout_leakage": 0,
            "frozen_cohorts_read": 0,
            "promotion_authorized": False,
        },
    }
    base._atomic_write_json(report_path, report)
    replayed = json.loads(report_path.read_text(encoding="utf-8"))
    if replayed.get("output", {}).get("targets_sha256") != report["output"]["targets_sha256"]:
        raise RuntimeError("train-only context30 report round-trip failed")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--feat", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    report = run(args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
