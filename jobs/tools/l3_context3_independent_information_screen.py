#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Screen nonlinear, antisymmetric CTX3 directions on the immutable CTX2 corpus.

The screen is deliberately upstream of target construction.  It compares one
streaming linear ridge mapper on raw CTX2 with three preregistered expansions:
odd curvature, tactical magnitude gates, and their union.  Candidate selection
uses train OOF rows only.  The selected bank is then checked on the disjoint
holdout and against a fold/cohort/phase/material-preserving feature shuffle.

No PatternEval model, self-play, force game, frozen cohort, or promotion is
involved.  A PASS only authorizes an exact tanh-mapper aligned/shuffled screen.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:
    from l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _game_equal_weights,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        _splitmix64,
        game_folds,
        tempo_phase_from_records,
    )
except ModuleNotFoundError:
    from jobs.tools.l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _game_equal_weights,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        _splitmix64,
        game_folds,
        tempo_phase_from_records,
    )


GATE_PAIRS = (
    ("legal_move_count_delta", "forced_move_delta"),
    ("legal_capture_option_delta", "max_capture_length_delta"),
    ("max_capture_length_delta", "legal_capture_option_delta"),
    ("promotion_pressure_delta", "blocked_man_delta"),
    ("blocked_man_delta", "promotion_pressure_delta"),
    ("king_safe_mobility_delta", "extra_king_delta"),
    ("king_denied_delta", "king_proximity_delta"),
    ("king_centrality_delta", "king_proximity_delta"),
    ("center_presence_delta", "men_delta"),
    ("wing_skew_abs_delta", "men_delta"),
)
BASE_WIDTH = len(CTX2_CONTEXT_COMPONENTS)
CURVATURE_WIDTH = 2 * len(CTX2_BASE_COMPONENTS)
GATE_WIDTH = 2 * len(GATE_PAIRS)
FULL_WIDTH = BASE_WIDTH + CURVATURE_WIDTH + GATE_WIDTH
CANDIDATE_COLUMNS = {
    "odd_curvature": np.arange(BASE_WIDTH + CURVATURE_WIDTH, dtype=np.int64),
    "tactical_magnitude_gates": np.concatenate((
        np.arange(BASE_WIDTH, dtype=np.int64),
        np.arange(BASE_WIDTH + CURVATURE_WIDTH, FULL_WIDTH, dtype=np.int64),
    )),
    "combined": np.arange(FULL_WIDTH, dtype=np.int64),
}


def component_names() -> tuple[str, ...]:
    curvature = tuple(
        f"{phase}_signed_square_{name}"
        for phase in ("tempo_mid", "tempo_end")
        for name in CTX2_BASE_COMPONENTS
    )
    gates = tuple(
        f"{phase}_{left}_x_abs_{right}"
        for phase in ("tempo_mid", "tempo_end")
        for left, right in GATE_PAIRS
    )
    return CTX2_CONTEXT_COMPONENTS + curvature + gates


def feature_bank(raw: np.ndarray, tempo: np.ndarray) -> np.ndarray:
    """Return the fixed 80D bank; every new column is colour-antisymmetric."""
    x = np.asarray(raw, dtype=np.float64)
    phase = np.asarray(tempo, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != BASE_WIDTH or phase.shape != (len(x),):
        raise ValueError("CTX3 feature inputs are not aligned 30D CTX2 rows")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(phase)):
        raise ValueError("CTX3 feature inputs must be finite")
    base = x[:, :15] + x[:, 15:]
    mid = phase[:, None]
    end = 1.0 - mid
    signed_square = base * np.abs(base)
    base_index = {name: index for index, name in enumerate(CTX2_BASE_COMPONENTS)}
    gated = np.column_stack([
        base[:, base_index[left]] * np.abs(base[:, base_index[right]])
        for left, right in GATE_PAIRS
    ])
    result = np.concatenate(
        (x, mid * signed_square, end * signed_square, mid * gated, end * gated),
        axis=1,
    )
    if result.shape != (len(x), FULL_WIDTH) or not np.all(np.isfinite(result)):
        raise RuntimeError("CTX3 feature-bank construction drift")
    return result


@dataclass
class SufficientStats:
    weight: float
    sum_x: np.ndarray
    sum_x2: np.ndarray
    xtx: np.ndarray
    xty: np.ndarray


def empty_stats(width: int) -> SufficientStats:
    return SufficientStats(
        0.0,
        np.zeros(width, dtype=np.float64),
        np.zeros(width, dtype=np.float64),
        np.zeros((width, width), dtype=np.float64),
        np.zeros(width, dtype=np.float64),
    )


def add_stats(target: SufficientStats, x: np.ndarray, y: np.ndarray, w: np.ndarray) -> None:
    target.weight += float(w.sum())
    target.sum_x += x.T @ w
    target.sum_x2 += (x * x).T @ w
    target.xtx += x.T @ (x * w[:, None])
    target.xty += x.T @ (y * w)


def subtract_stats(total: SufficientStats, heldout: SufficientStats) -> SufficientStats:
    return SufficientStats(
        total.weight - heldout.weight,
        total.sum_x - heldout.sum_x,
        total.sum_x2 - heldout.sum_x2,
        total.xtx - heldout.xtx,
        total.xty - heldout.xty,
    )


def fit_from_stats(
    stats: SufficientStats, columns: np.ndarray, ridge: float
) -> tuple[np.ndarray, np.ndarray]:
    if stats.weight <= 0:
        raise ValueError("cannot fit from zero-weight statistics")
    cols = np.asarray(columns, dtype=np.int64)
    rms = np.sqrt(np.maximum(stats.sum_x2[cols] / stats.weight, 1e-18))
    gram = stats.xtx[np.ix_(cols, cols)] / np.outer(rms, rms) / stats.weight
    rhs = stats.xty[cols] / rms / stats.weight
    theta_scaled = np.linalg.solve(gram + ridge * np.eye(len(cols)), rhs)
    return theta_scaled / rms, rms


def predict(x: np.ndarray, columns: np.ndarray, theta_raw: np.ndarray) -> np.ndarray:
    return np.clip(x[:, columns] @ theta_raw, -1.0, 1.0)


def covariance_novelty(stats: SufficientStats, columns: np.ndarray) -> dict[str, Any]:
    if stats.weight <= 0:
        raise ValueError("zero-weight covariance")
    cols = np.asarray(columns, dtype=np.int64)
    mean = stats.sum_x / stats.weight
    covariance = stats.xtx / stats.weight - np.outer(mean, mean)
    covariance = 0.5 * (covariance + covariance.T)
    base = np.arange(BASE_WIDTH, dtype=np.int64)
    augmentation = np.setdiff1d(cols, base, assume_unique=True)
    cbb = covariance[np.ix_(base, base)]
    caa = covariance[np.ix_(augmentation, augmentation)]
    cba = covariance[np.ix_(base, augmentation)]
    residual = caa - cba.T @ np.linalg.pinv(cbb + 1e-8 * np.eye(BASE_WIDTH)) @ cba
    residual = 0.5 * (residual + residual.T)
    residual_variance = np.maximum(np.diag(residual), 0.0)
    original_variance = np.maximum(np.diag(caa), 1e-18)
    fractions = np.clip(residual_variance / original_variance, 0.0, 1.0)
    scale = np.sqrt(np.maximum(residual_variance, 1e-18))
    correlation = residual / np.outer(scale, scale)
    correlation = np.clip(0.5 * (correlation + correlation.T), -1.0, 1.0)
    np.fill_diagonal(correlation, np.where(residual_variance > 1e-14, 1.0, 0.0))
    eigenvalues = np.maximum(np.linalg.eigvalsh(correlation), 0.0)
    positive = eigenvalues[eigenvalues > max(float(eigenvalues.max()) * 1e-6, 1e-10)]
    effective = (
        float(eigenvalues.sum() ** 2 / np.sum(eigenvalues * eigenvalues))
        if np.any(eigenvalues > 0)
        else 0.0
    )
    off = correlation - np.diag(np.diag(correlation))
    return {
        "augmentation_width": int(len(augmentation)),
        "residual_effective_dimension": effective,
        "residual_numeric_rank": int(len(positive)),
        "median_residual_variance_fraction": float(np.median(fractions)),
        "minimum_residual_variance_fraction": float(np.min(fractions)),
        "maximum_absolute_residual_correlation": float(np.max(np.abs(off))),
        "residual_variance_fractions": [float(value) for value in fractions],
    }


def phase_material_strata(records: np.ndarray, tempo: np.ndarray) -> np.ndarray:
    phase = np.minimum(np.floor(np.asarray(tempo) * 4).astype(np.int16), 3)
    pieces = np.asarray(
        [
            int(int(wm).bit_count() + int(wk).bit_count() + int(bm).bit_count() + int(bk).bit_count())
            for wm, wk, bm, bk in zip(
                records["wm"], records["wk"], records["bm"], records["bk"]
            )
        ],
        dtype=np.int16,
    )
    material = np.minimum(pieces // 10, 4)
    return phase * 5 + material


def shuffled_sources(
    folds: np.ndarray,
    strata: np.ndarray,
    train_count: int,
    seed: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    count = len(folds)
    if strata.shape != (count,) or not 0 < train_count < count:
        raise ValueError("shuffle inputs are not aligned")
    sources = np.empty(count, dtype=np.int64)
    row_ids = np.arange(count, dtype=np.uint64)
    fixed = 0
    for start, stop, cohort in ((0, train_count, 0), (train_count, count, 1)):
        cohort_folds: Iterable[int] = np.unique(folds[start:stop])
        for fold in cohort_folds:
            fold_rows = np.flatnonzero(folds[start:stop] == fold) + start
            for stratum in np.unique(strata[fold_rows]):
                members = fold_rows[strata[fold_rows] == stratum]
                if len(members) == 1:
                    sources[members] = members
                    fixed += 1
                    continue
                salt = np.uint64(seed ^ (cohort << 24) ^ (int(fold) << 16) ^ int(stratum))
                keys = _splitmix64(row_ids[members] ^ salt)
                ordered = members[np.argsort(keys, kind="stable")]
                sources[ordered] = np.roll(ordered, 1)
    if not np.array_equal(folds[sources], folds) or not np.array_equal(strata[sources], strata):
        raise RuntimeError("CTX3 shuffle crossed a fold or stratum")
    cohorts = np.arange(count) >= train_count
    if not np.array_equal(cohorts[sources], cohorts):
        raise RuntimeError("CTX3 shuffle crossed train/holdout")
    return sources, {
        "seed": seed,
        "stratification": "cohort_x_fold_x_tempo4_x_material5",
        "fixed_point_count": fixed,
        "permutation_sha256": hashlib.sha256(sources.astype("<i8").tobytes()).hexdigest(),
    }


def cluster_interval(
    improvement: np.ndarray,
    weights: np.ndarray,
    openings: np.ndarray,
    *,
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    values = np.asarray(improvement, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    groups, inverse = np.unique(np.asarray(openings, dtype=np.uint64), return_inverse=True)
    numerator = np.bincount(inverse, weights=values * w)
    denominator = np.bincount(inverse, weights=w)
    estimate = float(numerator.sum() / denominator.sum())
    if replicates <= 0:
        raise ValueError("bootstrap replicate count must be positive")
    rng = np.random.default_rng(seed)
    draws = np.empty(replicates, dtype=np.float64)
    for start in range(0, replicates, 100):
        stop = min(start + 100, replicates)
        sampled = rng.integers(0, len(groups), size=(stop - start, len(groups)))
        draws[start:stop] = numerator[sampled].sum(axis=1) / denominator[sampled].sum(axis=1)
    return {
        "estimate": estimate,
        "ci95": [float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))],
        "probability_positive": float((1 + np.sum(draws > 0.0)) / (replicates + 1)),
        "opening_clusters": int(len(groups)),
        "bootstrap_replicates": replicates,
        "bootstrap_seed": seed,
    }


def _stats_pass(
    *,
    records: np.ndarray,
    metadata: np.ndarray,
    features: np.ndarray,
    tempo: np.ndarray,
    outcomes: np.ndarray,
    weights: np.ndarray,
    folds: np.ndarray,
    train_count: int,
    chunk_size: int,
    donor: np.ndarray | None = None,
    columns: np.ndarray | None = None,
) -> tuple[SufficientStats, list[SufficientStats]]:
    width = FULL_WIDTH if columns is None else len(columns)
    total = empty_stats(width)
    per_fold = [empty_stats(width) for _ in range(5)]
    for start in range(0, train_count, chunk_size):
        stop = min(start + chunk_size, train_count)
        raw = np.asarray(features[start:stop], dtype=np.float64)
        phase = tempo[start:stop]
        bank = feature_bank(raw, phase)
        if donor is not None:
            source = donor[start:stop]
            donor_bank = feature_bank(
                np.asarray(features[source], dtype=np.float64), tempo[source]
            )
            bank[:, BASE_WIDTH:] = donor_bank[:, BASE_WIDTH:]
        if columns is not None:
            bank = bank[:, columns]
        y = outcomes[start:stop]
        w = weights[start:stop]
        add_stats(total, bank, y, w)
        local_folds = folds[start:stop]
        for fold in np.unique(local_folds):
            mask = local_folds == fold
            add_stats(per_fold[int(fold)], bank[mask], y[mask], w[mask])
    return total, per_fold


def _oof_predictions(
    *,
    features: np.ndarray,
    tempo: np.ndarray,
    folds: np.ndarray,
    train_count: int,
    total: SufficientStats,
    per_fold: list[SufficientStats],
    candidates: dict[str, np.ndarray],
    ridge: float,
    chunk_size: int,
    donor: np.ndarray | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, list[float]]]:
    predictions = {
        name: np.empty(train_count, dtype=np.float32) for name in candidates
    }
    fold_thetas: dict[str, list[np.ndarray]] = {name: [] for name in candidates}
    fold_signatures: dict[str, list[float]] = {name: [] for name in candidates}
    for fold in range(5):
        training = subtract_stats(total, per_fold[fold])
        for name, columns in candidates.items():
            theta, _rms = fit_from_stats(training, columns, ridge)
            fold_thetas[name].append(theta)
    for start in range(0, train_count, chunk_size):
        stop = min(start + chunk_size, train_count)
        bank = feature_bank(np.asarray(features[start:stop]), tempo[start:stop])
        if donor is not None:
            source = donor[start:stop]
            donor_bank = feature_bank(np.asarray(features[source]), tempo[source])
            bank[:, BASE_WIDTH:] = donor_bank[:, BASE_WIDTH:]
        local = folds[start:stop]
        for fold in np.unique(local):
            mask = local == fold
            for name, columns in candidates.items():
                predictions[name][start:stop][mask] = predict(
                    bank[mask], columns, fold_thetas[name][int(fold)]
                )
    return predictions, fold_signatures


def _holdout_prediction(
    *,
    features: np.ndarray,
    tempo: np.ndarray,
    train_count: int,
    total: SufficientStats,
    columns: np.ndarray,
    ridge: float,
    chunk_size: int,
    donor: np.ndarray | None = None,
) -> np.ndarray:
    theta, _rms = fit_from_stats(total, columns, ridge)
    result = np.empty(len(features) - train_count, dtype=np.float32)
    for start in range(train_count, len(features), chunk_size):
        stop = min(start + chunk_size, len(features))
        bank = feature_bank(np.asarray(features[start:stop]), tempo[start:stop])
        if donor is not None:
            source = donor[start:stop]
            donor_bank = feature_bank(np.asarray(features[source]), tempo[source])
            bank[:, BASE_WIDTH:] = donor_bank[:, BASE_WIDTH:]
        result[start - train_count : stop - train_count] = predict(bank, columns, theta)
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    paths = {name: Path(getattr(args, name)) for name in ("data", "meta", "features", "report")}
    if paths["report"].exists():
        raise ValueError("report is no-clobber")
    records = _open_counted(paths["data"], b"JNNW", JNNW_DTYPE)
    metadata, schema = _open_meta(paths["meta"], len(records))
    features, width = _open_feat(paths["features"], len(records))
    if schema != "JSM2" or width != BASE_WIDTH:
        raise ValueError("CTX3 requires aligned JSM2 and CTX2-30 inputs")
    train_count = int(args.train_count)
    if not 0 < train_count < len(records):
        raise ValueError("train_count must leave a holdout")
    train_openings = set(map(int, np.unique(metadata["opening_id"][:train_count])))
    holdout_openings = set(map(int, np.unique(metadata["opening_id"][train_count:])))
    if train_openings & holdout_openings:
        raise ValueError("opening_id crossed train/holdout")
    outcomes = np.asarray(
        np.where(records["stm"] == 1, records["wdl"], -records["wdl"]),
        dtype=np.float64,
    )
    if not np.all(np.isin(outcomes, (-1.0, 0.0, 1.0))):
        raise ValueError("WDL outside {-1,0,1}")
    weights = _game_equal_weights(np.asarray(metadata["game_id"], dtype=np.uint64))
    tempo = tempo_phase_from_records(records)
    folds = game_folds(np.asarray(metadata["opening_id"], dtype=np.uint64), 5, args.fold_seed)
    folds[train_count:] = 5

    total, per_fold = _stats_pass(
        records=records, metadata=metadata, features=features, tempo=tempo,
        outcomes=outcomes, weights=weights, folds=folds, train_count=train_count,
        chunk_size=args.chunk_size,
    )
    candidates = {"ctx2_raw": np.arange(BASE_WIDTH, dtype=np.int64), **CANDIDATE_COLUMNS}
    oof, _ = _oof_predictions(
        features=features, tempo=tempo, folds=folds, train_count=train_count,
        total=total, per_fold=per_fold, candidates=candidates, ridge=args.ridge,
        chunk_size=args.chunk_size,
    )
    train_outcomes = outcomes[:train_count]
    train_weights = weights[:train_count]
    train_opening_ids = np.asarray(metadata["opening_id"][:train_count], dtype=np.uint64)
    baseline_error = (oof["ctx2_raw"] - train_outcomes) ** 2
    discovery: dict[str, Any] = {}
    for offset, (name, columns) in enumerate(CANDIDATE_COLUMNS.items()):
        candidate_error = (oof[name] - train_outcomes) ** 2
        interval = cluster_interval(
            baseline_error - candidate_error, train_weights, train_opening_ids,
            replicates=args.bootstrap_replicates, seed=args.bootstrap_seed + offset,
        )
        fold_gain = []
        for fold in range(5):
            mask = folds[:train_count] == fold
            fold_gain.append(float(np.average(
                baseline_error[mask] - candidate_error[mask], weights=train_weights[mask]
            )))
        discovery[name] = {
            "oof_mse_improvement_vs_ctx2": interval,
            "positive_fold_count": int(np.sum(np.asarray(fold_gain) > 0.0)),
            "fold_improvements": fold_gain,
            "novelty": covariance_novelty(total, columns),
        }
    eligible = [
        name for name, row in discovery.items()
        if row["oof_mse_improvement_vs_ctx2"]["ci95"][0] > 0.0
    ]
    selected_name = max(
        eligible or list(discovery),
        key=lambda name: discovery[name]["oof_mse_improvement_vs_ctx2"]["estimate"],
    )
    selected_columns = CANDIDATE_COLUMNS[selected_name]

    baseline_holdout = _holdout_prediction(
        features=features, tempo=tempo, train_count=train_count, total=total,
        columns=candidates["ctx2_raw"], ridge=args.ridge, chunk_size=args.chunk_size,
    )
    selected_holdout = _holdout_prediction(
        features=features, tempo=tempo, train_count=train_count, total=total,
        columns=selected_columns, ridge=args.ridge, chunk_size=args.chunk_size,
    )
    holdout_slice = slice(train_count, len(records))
    holdout_error_baseline = (baseline_holdout - outcomes[holdout_slice]) ** 2
    holdout_error_selected = (selected_holdout - outcomes[holdout_slice]) ** 2
    confirmation = cluster_interval(
        holdout_error_baseline - holdout_error_selected,
        weights[holdout_slice], metadata["opening_id"][holdout_slice],
        replicates=args.bootstrap_replicates, seed=args.bootstrap_seed + 100,
    )

    strata = phase_material_strata(records, tempo)
    donor, shuffle_report = shuffled_sources(folds, strata, train_count, args.shuffle_seed)
    shuffled_total, shuffled_per_fold = _stats_pass(
        records=records, metadata=metadata, features=features, tempo=tempo,
        outcomes=outcomes, weights=weights, folds=folds, train_count=train_count,
        chunk_size=args.chunk_size, donor=donor,
    )
    shuffled_oof, _ = _oof_predictions(
        features=features, tempo=tempo, folds=folds, train_count=train_count,
        total=shuffled_total, per_fold=shuffled_per_fold,
        candidates={selected_name: selected_columns},
        ridge=args.ridge, chunk_size=args.chunk_size, donor=donor,
    )
    shuffled_train_error = (shuffled_oof[selected_name] - train_outcomes) ** 2
    aligned_vs_shuffled_oof = cluster_interval(
        shuffled_train_error - (oof[selected_name] - train_outcomes) ** 2,
        train_weights, train_opening_ids,
        replicates=args.bootstrap_replicates, seed=args.bootstrap_seed + 200,
    )
    shuffled_holdout = _holdout_prediction(
        features=features, tempo=tempo, train_count=train_count, total=shuffled_total,
        columns=selected_columns, ridge=args.ridge,
        chunk_size=args.chunk_size, donor=donor,
    )
    aligned_vs_shuffled_holdout = cluster_interval(
        (shuffled_holdout - outcomes[holdout_slice]) ** 2 - holdout_error_selected,
        weights[holdout_slice], metadata["opening_id"][holdout_slice],
        replicates=args.bootstrap_replicates, seed=args.bootstrap_seed + 300,
    )

    selected = discovery[selected_name]
    novelty = selected["novelty"]
    guards = {
        "selected_by_train_oof_only": True,
        "train_oof_gain_ci95_above_zero": selected["oof_mse_improvement_vs_ctx2"]["ci95"][0] > 0.0,
        "at_least_four_of_five_oof_folds_positive": selected["positive_fold_count"] >= 4,
        "holdout_gain_ci95_above_zero": confirmation["ci95"][0] > 0.0,
        "aligned_beats_shuffled_oof_ci95": aligned_vs_shuffled_oof["ci95"][0] > 0.0,
        "aligned_beats_shuffled_holdout_ci95": aligned_vs_shuffled_holdout["ci95"][0] > 0.0,
        "at_least_two_effective_residual_directions": novelty["residual_effective_dimension"] >= 2.0,
        "residual_variance_not_numerical": novelty["median_residual_variance_fraction"] >= 1e-3,
        "shuffle_fixed_points_zero": shuffle_report["fixed_point_count"] == 0,
    }
    passed = all(guards.values())
    payload = {
        "schema": "jass.l3_context3_independent_information_screen.v1",
        "verdict": (
            "JASS_CONTEXT3_INDEPENDENT_INFORMATION_SCREEN_PASSED"
            if passed else "JASS_CONTEXT3_INDEPENDENT_INFORMATION_SCREEN_FAILED"
        ),
        "screen_passed": passed,
        "protocol": {
            "candidate_selection": "train_oof_only_then_single_holdout_confirmation",
            "candidate_order": list(CANDIDATE_COLUMNS),
            "fold_group": "opening_id",
            "fold_count": 5,
            "fold_seed": args.fold_seed,
            "row_weighting": "game_equal",
            "screen_mapper": "streaming_linear_ridge_clipped_to_wdl_range",
            "ridge": args.ridge,
            "bootstrap_replicates": args.bootstrap_replicates,
            "shuffle": "joint_augmentation_rows_within_cohort_fold_tempo4_material5",
            "selfplay_generated": False,
            "patterneval_fits_run": 0,
            "force_games_played": 0,
            "frozen_read": False,
            "promotion_authorized": False,
        },
        "source": {
            "records": len(records),
            "train_records": train_count,
            "holdout_records": len(records) - train_count,
            "data_sha256": _sha256(paths["data"]),
            "meta_sha256": _sha256(paths["meta"]),
            "features_sha256": _sha256(paths["features"]),
            "train_holdout_opening_overlap": 0,
        },
        "components": list(component_names()),
        "gate_pairs": [list(pair) for pair in GATE_PAIRS],
        "discovery": discovery,
        "selected_candidate": selected_name,
        "holdout_improvement_vs_ctx2": confirmation,
        "aligned_vs_shuffled_oof": aligned_vs_shuffled_oof,
        "aligned_vs_shuffled_holdout": aligned_vs_shuffled_holdout,
        "shuffle_control": shuffle_report,
        "guards": guards,
        "next_stage_authorized": passed,
        "next_required_stage": (
            "fit exact tanh CTX3 mapper aligned and shuffled on the same immutable corpus"
            if passed else "close these nonlinear CTX3 banks and redesign raw context observables"
        ),
    }
    paths["report"].parent.mkdir(parents=True, exist_ok=True)
    paths["report"].write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--train-count", type=int, required=True)
    parser.add_argument("--fold-seed", type=int, default=20260811)
    parser.add_argument("--shuffle-seed", type=int, default=2026081903)
    parser.add_argument("--bootstrap-seed", type=int, default=2026081904)
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--ridge", type=float, default=1e-4)
    parser.add_argument("--chunk-size", type=int, default=50_000)
    args = parser.parse_args(argv)
    payload = run(args)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
