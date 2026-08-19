#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fit and causally screen the exact tanh mapper for the CTX3 bank selected by 1416b.

The immutable CTX2 corpus is used three times with identical train/holdout and
opening folds: raw CTX2, the selected aligned CTX3 bank, and a negative control
where only the CTX3 augmentation rows are permuted inside the preregistered
cohort/fold/phase/material strata.  No PatternEval model is fitted here.
"""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    from l3_conditional_targets import (
        JNNW_DTYPE,
        _game_equal_weights,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        cross_fitted_predictions,
        game_folds,
        tempo_phase_from_records,
    )
    from l3_context3_independent_information_screen import (
        BASE_WIDTH,
        CANDIDATE_COLUMNS,
        cluster_interval,
        component_names,
        feature_bank,
        phase_material_strata,
        shuffled_sources,
    )
except ModuleNotFoundError:
    from jobs.tools.l3_conditional_targets import (
        JNNW_DTYPE,
        _game_equal_weights,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        cross_fitted_predictions,
        game_folds,
        tempo_phase_from_records,
    )
    from jobs.tools.l3_context3_independent_information_screen import (
        BASE_WIDTH,
        CANDIDATE_COLUMNS,
        cluster_interval,
        component_names,
        feature_bank,
        phase_material_strata,
        shuffled_sources,
    )


def _write_matrix(
    path: Path,
    features: np.ndarray,
    tempo: np.ndarray,
    columns: np.ndarray,
    *,
    chunk_size: int,
    donors: np.ndarray | None = None,
) -> np.memmap:
    if path.exists():
        raise ValueError(f"{path}: scratch matrix already exists")
    matrix = np.lib.format.open_memmap(
        path, mode="w+", dtype=np.float32, shape=(len(features), len(columns))
    )
    augmentation = np.flatnonzero(columns >= BASE_WIDTH)
    for start in range(0, len(features), chunk_size):
        stop = min(start + chunk_size, len(features))
        bank = feature_bank(np.asarray(features[start:stop]), tempo[start:stop])
        selected = np.asarray(bank[:, columns], dtype=np.float32)
        if donors is not None and augmentation.size:
            source = donors[start:stop]
            donor_bank = feature_bank(np.asarray(features[source]), tempo[source])
            selected[:, augmentation] = donor_bank[:, columns[augmentation]]
        matrix[start:stop] = selected
    matrix.flush()
    return matrix


def _fit(
    matrix: np.ndarray,
    outcomes: np.ndarray,
    game_ids: np.ndarray,
    opening_ids: np.ndarray,
    train_count: int,
    args: argparse.Namespace,
    components: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    return cross_fitted_predictions(
        matrix,
        outcomes,
        game_ids,
        train_count,
        group_ids=opening_ids,
        group_name="opening_id",
        row_weighting="game_equal",
        components=components,
        require_convergence=True,
        fold_count=5,
        fold_seed=int(args.fold_seed),
        ridge=float(args.ridge),
        max_iterations=int(args.max_iterations),
        tolerance=float(args.tolerance),
        line_search_steps=int(args.line_search_steps),
    )


def _contrast(
    better: np.ndarray,
    worse: np.ndarray,
    outcomes: np.ndarray,
    weights: np.ndarray,
    openings: np.ndarray,
    folds: np.ndarray,
    start: int,
    stop: int,
    *,
    bootstrap_replicates: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    rows = slice(start, stop)
    improvement = (
        (worse[rows] - outcomes[rows]) ** 2
        - (better[rows] - outcomes[rows]) ** 2
    )
    interval = cluster_interval(
        improvement,
        weights[rows],
        openings[rows],
        replicates=bootstrap_replicates,
        seed=bootstrap_seed,
    )
    fold_improvements: list[float] = []
    if start == 0:
        for fold in range(5):
            mask = folds[:stop] == fold
            fold_improvements.append(float(np.average(improvement[mask], weights=weights[:stop][mask])))
    return {
        **interval,
        "fold_improvements": fold_improvements,
        "positive_fold_count": int(np.sum(np.asarray(fold_improvements) > 0.0)),
    }


def evaluate(
    *,
    baseline: np.ndarray,
    aligned: np.ndarray,
    shuffled: np.ndarray,
    outcomes: np.ndarray,
    weights: np.ndarray,
    openings: np.ndarray,
    folds: np.ndarray,
    train_count: int,
    bootstrap_replicates: int,
    bootstrap_seed: int,
) -> tuple[dict[str, Any], dict[str, bool]]:
    count = len(outcomes)
    contrasts = {
        "aligned_vs_ctx2_oof": _contrast(
            aligned, baseline, outcomes, weights, openings, folds, 0, train_count,
            bootstrap_replicates=bootstrap_replicates, bootstrap_seed=bootstrap_seed,
        ),
        "aligned_vs_ctx2_holdout": _contrast(
            aligned, baseline, outcomes, weights, openings, folds, train_count, count,
            bootstrap_replicates=bootstrap_replicates, bootstrap_seed=bootstrap_seed + 1,
        ),
        "aligned_vs_shuffled_oof": _contrast(
            aligned, shuffled, outcomes, weights, openings, folds, 0, train_count,
            bootstrap_replicates=bootstrap_replicates, bootstrap_seed=bootstrap_seed + 2,
        ),
        "aligned_vs_shuffled_holdout": _contrast(
            aligned, shuffled, outcomes, weights, openings, folds, train_count, count,
            bootstrap_replicates=bootstrap_replicates, bootstrap_seed=bootstrap_seed + 3,
        ),
    }
    guards = {
        "aligned_beats_ctx2_oof_ci95": contrasts["aligned_vs_ctx2_oof"]["ci95"][0] > 0.0,
        "aligned_beats_ctx2_holdout_ci95": contrasts["aligned_vs_ctx2_holdout"]["ci95"][0] > 0.0,
        "aligned_beats_shuffled_oof_ci95": contrasts["aligned_vs_shuffled_oof"]["ci95"][0] > 0.0,
        "aligned_beats_shuffled_holdout_ci95": contrasts["aligned_vs_shuffled_holdout"]["ci95"][0] > 0.0,
        "aligned_vs_ctx2_at_least_four_oof_folds_positive": contrasts["aligned_vs_ctx2_oof"]["positive_fold_count"] >= 4,
        "aligned_vs_shuffled_at_least_four_oof_folds_positive": contrasts["aligned_vs_shuffled_oof"]["positive_fold_count"] >= 4,
    }
    return contrasts, guards


def run(args: argparse.Namespace) -> dict[str, Any]:
    data_path, meta_path, feat_path = map(Path, (args.data, args.meta, args.features))
    screen_path, report_path = map(Path, (args.screen, args.report))
    aligned_out, shuffled_out = map(Path, (args.aligned_out, args.feature_shuffled_out))
    scratch = Path(args.scratch)
    if report_path.exists() or aligned_out.exists() or shuffled_out.exists():
        raise ValueError("CTX3 mapper outputs are no-clobber")
    scratch.mkdir(parents=True, exist_ok=True)

    screen = json.loads(screen_path.read_text(encoding="utf-8"))
    if screen.get("schema") != "jass.l3_context3_independent_information_screen.v1":
        raise ValueError("1416b screen schema drift")
    if screen.get("verdict") != "JASS_CONTEXT3_INDEPENDENT_INFORMATION_SCREEN_PASSED":
        raise ValueError("1416b did not authorize exact tanh mapper fits")
    selected = str(screen.get("selected_candidate"))
    if selected not in CANDIDATE_COLUMNS:
        raise ValueError("1416b selected candidate drift")
    columns = CANDIDATE_COLUMNS[selected]

    records = _open_counted(data_path, b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(meta_path, len(records))
    features, width = _open_feat(feat_path, len(records))
    if meta_schema != "JSM2" or width != BASE_WIDTH:
        raise ValueError("CTX3 requires aligned JSM2 and CTX2-30 inputs")
    train_count = int(args.train_count)
    if not 0 < train_count < len(records):
        raise ValueError("train_count must leave a holdout")
    source = screen.get("source") or {}
    expected_hashes = {
        "data_sha256": _sha256(data_path),
        "meta_sha256": _sha256(meta_path),
        "features_sha256": _sha256(feat_path),
    }
    if any(source.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("immutable 1416b source hashes drift")

    outcomes = np.asarray(np.where(records["stm"] == 1, records["wdl"], -records["wdl"]), dtype=np.float64)
    weights = _game_equal_weights(np.asarray(metadata["game_id"], dtype=np.uint64))
    game_ids = np.asarray(metadata["game_id"], dtype=np.uint64)
    opening_ids = np.asarray(metadata["opening_id"], dtype=np.uint64)
    tempo = tempo_phase_from_records(records)
    causal_folds = game_folds(opening_ids, 5, int(args.fold_seed))
    shuffle_folds = causal_folds.copy()
    shuffle_folds[train_count:] = 5
    strata = phase_material_strata(records, tempo)
    donors, shuffle_report = shuffled_sources(
        shuffle_folds, strata, train_count, int(args.shuffle_seed)
    )
    if shuffle_report["fixed_point_count"] != 0:
        raise RuntimeError("exact mapper shuffle retained fixed points")

    base_components = tuple(component_names()[:BASE_WIDTH])
    baseline, folds, baseline_mapping = _fit(
        features, outcomes, game_ids, opening_ids, train_count, args, base_components
    )

    aligned_path = scratch / "ctx3-aligned-matrix.npy"
    aligned_matrix = _write_matrix(
        aligned_path, features, tempo, columns, chunk_size=int(args.chunk_size)
    )
    selected_names = tuple(np.asarray(component_names(), dtype=object)[columns].tolist())
    aligned, aligned_folds, aligned_mapping = _fit(
        aligned_matrix, outcomes, game_ids, opening_ids, train_count, args, selected_names
    )
    if not np.array_equal(folds, aligned_folds):
        raise RuntimeError("aligned mapper fold drift")
    del aligned_matrix
    gc.collect()
    aligned_path.unlink()

    shuffled_path = scratch / "ctx3-feature-shuffled-matrix.npy"
    shuffled_matrix = _write_matrix(
        shuffled_path, features, tempo, columns, chunk_size=int(args.chunk_size), donors=donors
    )
    shuffled, shuffled_folds, shuffled_mapping = _fit(
        shuffled_matrix, outcomes, game_ids, opening_ids, train_count, args, selected_names
    )
    if not np.array_equal(folds, shuffled_folds):
        raise RuntimeError("shuffled mapper fold drift")
    del shuffled_matrix
    gc.collect()
    shuffled_path.unlink()

    contrasts, metric_guards = evaluate(
        baseline=baseline, aligned=aligned, shuffled=shuffled, outcomes=outcomes,
        weights=weights, openings=opening_ids, folds=folds, train_count=train_count,
        bootstrap_replicates=int(args.bootstrap_replicates), bootstrap_seed=int(args.bootstrap_seed),
    )
    fit_guards = {
        "selected_candidate_fixed_by_1416b": True,
        "baseline_all_six_fits_converged": all(row["fit"]["converged"] for row in baseline_mapping["folds"] + [baseline_mapping["final_train_fit"]]),
        "aligned_all_six_fits_converged": all(row["fit"]["converged"] for row in aligned_mapping["folds"] + [aligned_mapping["final_train_fit"]]),
        "shuffled_all_six_fits_converged": all(row["fit"]["converged"] for row in shuffled_mapping["folds"] + [shuffled_mapping["final_train_fit"]]),
        "shuffle_fixed_points_zero": shuffle_report["fixed_point_count"] == 0,
    }
    guards = {**fit_guards, **metric_guards}
    passed = all(guards.values())
    np.save(aligned_out, np.asarray(aligned, dtype=np.float32), allow_pickle=False)
    np.save(shuffled_out, np.asarray(shuffled, dtype=np.float32), allow_pickle=False)
    payload = {
        "schema": "jass.l3_context3_exact_tanh_mapper_screen.v1",
        "verdict": "JASS_CONTEXT3_EXACT_TANH_MAPPER_SCREEN_PASSED" if passed else "JASS_CONTEXT3_EXACT_TANH_MAPPER_SCREEN_FAILED",
        "screen_passed": passed,
        "protocol": {
            "selected_by": "1416b_train_oof_only",
            "selected_candidate": selected,
            "selected_width": int(len(columns)),
            "mapper": "fold_local_rms_tanh_linear",
            "group": "opening_id",
            "row_weighting": "game_equal",
            "shuffle": "augmentation_only_within_cohort_fold_tempo4_material5",
            "fold_seed": int(args.fold_seed),
            "shuffle_seed": int(args.shuffle_seed),
            "bootstrap_replicates": int(args.bootstrap_replicates),
            "bootstrap_seed": int(args.bootstrap_seed),
            "patterneval_fits_run": 0,
            "force_games_played": 0,
            "frozen_read": False,
            "promotion_authorized": False,
        },
        "source": {"records": int(len(records)), "train_records": train_count, "holdout_records": int(len(records) - train_count), **expected_hashes},
        "shuffle_control": shuffle_report,
        "mappings": {"ctx2": baseline_mapping, "aligned_ctx3": aligned_mapping, "feature_shuffled_ctx3": shuffled_mapping},
        "contrasts": contrasts,
        "guards": guards,
        "outputs": {"aligned_prediction_sha256": _sha256(aligned_out), "feature_shuffled_prediction_sha256": _sha256(shuffled_out)},
        "next_stage_authorized": passed,
        "next_required_stage": "construct paired aligned-vs-shuffled CTX3 target sidecars and fit PatternEval" if passed else "close selected CTX3 mapper family",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--screen", required=True)
    parser.add_argument("--train-count", type=int, required=True)
    parser.add_argument("--aligned-out", required=True)
    parser.add_argument("--feature-shuffled-out", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--fold-seed", type=int, default=20260811)
    parser.add_argument("--shuffle-seed", type=int, default=2026081903)
    parser.add_argument("--bootstrap-seed", type=int, default=2026081905)
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--ridge", type=float, default=1e-4)
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--tolerance", type=float, default=1e-8)
    parser.add_argument("--line-search-steps", type=int, default=20)
    parser.add_argument("--chunk-size", type=int, default=50_000)
    args = parser.parse_args(argv)
    print(json.dumps(run(args), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
