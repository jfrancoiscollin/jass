#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build leakage-resistant conditional target sidecars for full-size Jass.

CTX1 reproduces the historical 11-component mapper.  CTX2 consumes a dedicated
30-wide C++ dump: 15 colour-antisymmetric board/tactical signals kept in
separate tempo-midgame and tempo-endgame banks.  Exact legal-move components
come from the production FMJD move generator, not a Python approximation.

Train rows receive out-of-fold predictions; the strict CTX2 protocol groups
paired games by opening, computes scaling on each fold's training rows only,
and gives every game equal total loss weight.  Holdout rows receive a mapper
fitted on the train prefix only.  The shuffled control preserves cohort/fold
and optional WDL/phase marginals while breaking fine state alignment.
No oracle, EGDB label, search score, frozen cohort, or new self-play is read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import time
from typing import Any

import numpy as np

JNNW_DTYPE = np.dtype(
    [
        ("wm", "<u8"),
        ("wk", "<u8"),
        ("bm", "<u8"),
        ("bk", "<u8"),
        ("stm", "u1"),
        ("score", "<i4"),
        ("wdl", "i1"),
    ]
)
JSM1_DTYPE = np.dtype(
    [("game_id", "<u8"), ("opening_id", "<u8"), ("seeded", "u1")]
)
JSM2_DTYPE = np.dtype(
    [
        ("game_id", "<u8"),
        ("opening_id", "<u8"),
        ("seeded", "u1"),
        ("ply", "<u2"),
        ("game_plies", "<u2"),
        ("last_eps_ply", "<u2"),
        ("game_result", "i1"),
        ("flags", "u1"),
    ]
)
assert JNNW_DTYPE.itemsize == 38
assert JSM1_DTYPE.itemsize == 17
assert JSM2_DTYPE.itemsize == 25

CTX1_CONTEXT_COMPONENTS = (
    "men_delta",
    "king_count_delta",
    "mobility_delta",
    "balance_delta",
    "king_centrality_delta",
    "king_proximity_delta",
    "king_safe_mobility_delta",
    "king_denied_delta",
    "men_skew_delta",
    "has_king_delta",
    "extra_king_delta",
)

CTX2_BASE_COMPONENTS = (
    "men_delta",
    "has_king_delta",
    "extra_king_delta",
    "legal_move_count_delta",
    "legal_capture_option_delta",
    "max_capture_length_delta",
    "forced_move_delta",
    "promotion_pressure_delta",
    "blocked_man_delta",
    "center_presence_delta",
    "wing_skew_abs_delta",
    "king_centrality_delta",
    "king_proximity_delta",
    "king_safe_mobility_delta",
    "king_denied_delta",
)
CTX2_CONTEXT_COMPONENTS = tuple(
    f"{phase}_{component}"
    for phase in ("tempo_mid", "tempo_end")
    for component in CTX2_BASE_COMPONENTS
)
CONTEXT_SCHEMAS = {
    "ctx1-legacy-120": CTX1_CONTEXT_COMPONENTS,
    "ctx2-phase-tactical-30": CTX2_CONTEXT_COMPONENTS,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _open_counted(path: Path, magic: bytes, dtype: np.dtype) -> np.memmap:
    with path.open("rb") as handle:
        header = handle.read(8)
    if len(header) != 8 or header[:4] != magic:
        raise ValueError(f"{path}: expected {magic!r} header")
    count = struct.unpack_from("<I", header, 4)[0]
    expected = 8 + count * dtype.itemsize
    if path.stat().st_size != expected:
        raise ValueError(f"{path}: size {path.stat().st_size} != {expected}")
    return np.memmap(path, dtype=dtype, mode="r", offset=8, shape=(count,))


def _open_meta(path: Path, expected_count: int) -> tuple[np.memmap, str]:
    with path.open("rb") as handle:
        magic = handle.read(4)
    if magic == b"JSM1":
        rows = _open_counted(path, magic, JSM1_DTYPE)
    elif magic == b"JSM2":
        rows = _open_counted(path, magic, JSM2_DTYPE)
    else:
        raise ValueError(f"{path}: expected JSM1 or JSM2")
    if len(rows) != expected_count:
        raise ValueError(f"{path}: metadata rows {len(rows)} != data {expected_count}")
    return rows, magic.decode("ascii")


def _open_feat(path: Path, expected_count: int) -> tuple[np.memmap, int]:
    with path.open("rb") as handle:
        header = handle.read(12)
    if len(header) != 12 or header[:4] != b"FEAT":
        raise ValueError(f"{path}: invalid FEAT header")
    count, width = struct.unpack_from("<II", header, 4)
    if count != expected_count:
        raise ValueError(f"{path}: FEAT rows {count} != data {expected_count}")
    expected = 12 + count * width * 4
    if path.stat().st_size != expected:
        raise ValueError(f"{path}: FEAT size {path.stat().st_size} != {expected}")
    return (
        np.memmap(path, dtype="<f4", mode="r", offset=12, shape=(count, width)),
        int(width),
    )


def context_matrix(
    features: np.ndarray,
    schema: str = "ctx1-legacy-120",
) -> np.ndarray:
    """Return the mapper matrix for an explicit, versioned context schema."""
    raw = np.asarray(features)
    if schema == "ctx2-phase-tactical-30":
        if raw.ndim != 2 or raw.shape[1] != len(CTX2_CONTEXT_COMPONENTS):
            raise ValueError(
                "CTX2 requires the dedicated 30-wide phase-tactical dump, "
                f"got {raw.shape}"
            )
        values = np.asarray(raw, dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise ValueError("conditional context contains non-finite values")
        return values
    if schema != "ctx1-legacy-120":
        raise ValueError(f"unknown conditional context schema: {schema}")
    if raw.ndim != 2 or raw.shape[1] != 120:
        raise ValueError(
            f"conditional transfer requires the L2LOW 120-extra architecture, got {raw.shape}"
        )
    values = np.empty((raw.shape[0], len(CTX1_CONTEXT_COMPONENTS)), dtype=np.float64)
    values[:, 0] = raw[:, 100] - raw[:, 101]
    values[:, 1] = raw[:, :50].sum(axis=1) - raw[:, 50:100].sum(axis=1)
    values[:, 2] = raw[:, 102] - raw[:, 103]
    values[:, 3] = raw[:, 104] - raw[:, 105]
    values[:, 4] = raw[:, 106] - raw[:, 107]
    values[:, 5] = raw[:, 108] - raw[:, 109]
    values[:, 6] = raw[:, 110] - raw[:, 111]
    values[:, 7] = raw[:, 112] - raw[:, 113]
    values[:, 8] = raw[:, 114] - raw[:, 115]
    values[:, 9] = raw[:, 116] - raw[:, 117]
    values[:, 10] = raw[:, 118] - raw[:, 119]
    if not np.all(np.isfinite(values)):
        raise ValueError("conditional context contains non-finite values")
    return values


def _splitmix64(values: np.ndarray) -> np.ndarray:
    with np.errstate(over="ignore"):
        z = np.asarray(values, dtype=np.uint64) + np.uint64(0x9E3779B97F4A7C15)
        z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return z ^ (z >> np.uint64(31))


def game_folds(game_ids: np.ndarray, fold_count: int, seed: int) -> np.ndarray:
    if fold_count < 2:
        raise ValueError("fold_count must be >= 2")
    mixed = _splitmix64(np.asarray(game_ids, dtype=np.uint64) ^ np.uint64(seed))
    return np.asarray(mixed % np.uint64(fold_count), dtype=np.int8)


def _game_equal_weights(game_ids: np.ndarray) -> np.ndarray:
    _, inverse, counts = np.unique(
        np.asarray(game_ids, dtype=np.uint64),
        return_inverse=True,
        return_counts=True,
    )
    return 1.0 / counts[inverse].astype(np.float64)


def _weighted_rms(matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
    weight_sum = float(weights.sum())
    rms = np.sqrt((matrix * matrix).T @ weights / weight_sum)
    return np.where(rms > 1e-12, rms, 1.0)


def _matrix_diagnostics(
    matrix: np.ndarray,
    weights: np.ndarray,
    components: tuple[str, ...],
) -> dict[str, Any]:
    weight_sum = float(weights.sum())
    mean = matrix.T @ weights / weight_sum
    second = matrix.T @ (matrix * weights[:, None]) / weight_sum
    covariance = second - np.outer(mean, mean)
    covariance = 0.5 * (covariance + covariance.T)
    variance = np.maximum(np.diag(covariance), 0.0)
    denom = np.sqrt(np.outer(variance, variance))
    correlation = np.divide(
        covariance,
        denom,
        out=np.zeros_like(covariance),
        where=denom > 1e-18,
    )
    np.fill_diagonal(correlation, np.where(variance > 1e-18, 1.0, 0.0))
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0.0)
    largest = float(eigenvalues[-1]) if eigenvalues.size else 0.0
    threshold = max(largest * 1e-10, 1e-14)
    positive = eigenvalues[eigenvalues > threshold]
    high_pairs = []
    for left in range(len(components)):
        for right in range(left + 1, len(components)):
            value = float(correlation[left, right])
            if abs(value) >= 0.98:
                high_pairs.append(
                    {"left": components[left], "right": components[right], "r": value}
                )
    return {
        "weighted_feature_mean": [float(value) for value in mean],
        "weighted_feature_variance": [float(value) for value in variance],
        "correlation": [[float(value) for value in row] for row in correlation],
        "high_absolute_correlation_pairs_ge_0_98": high_pairs,
        "effective_rank": int(positive.size),
        "dimension": int(matrix.shape[1]),
        "covariance_condition_number": (
            float(positive[-1] / positive[0]) if positive.size else None
        ),
    }


def _validated_weights(
    sample_weights: np.ndarray | None,
    count: int,
) -> np.ndarray:
    if sample_weights is None:
        return np.ones(count, dtype=np.float64)
    weights = np.asarray(sample_weights, dtype=np.float64)
    if weights.shape != (count,) or not np.all(np.isfinite(weights)):
        raise ValueError("sample weights must be finite and aligned")
    if np.any(weights <= 0.0) or float(weights.sum()) <= 0.0:
        raise ValueError("sample weights must be strictly positive")
    return weights


def _loss(
    matrix: np.ndarray,
    targets: np.ndarray,
    theta: np.ndarray,
    ridge: float,
    sample_weights: np.ndarray | None = None,
) -> float:
    residual = np.tanh(matrix @ theta) - targets
    weights = _validated_weights(sample_weights, len(targets))
    data_loss = float(np.dot(weights, residual * residual) / weights.sum())
    return 0.5 * data_loss + 0.5 * ridge * float(theta @ theta)


def fit_tanh_linear(
    matrix: np.ndarray,
    targets: np.ndarray,
    *,
    ridge: float,
    max_iterations: int,
    tolerance: float,
    line_search_steps: int,
    sample_weights: np.ndarray | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    x = np.asarray(matrix, dtype=np.float64)
    y = np.asarray(targets, dtype=np.float64)
    if x.ndim != 2 or y.shape != (x.shape[0],) or x.shape[0] == 0:
        raise ValueError("fit requires non-empty aligned matrix and targets")
    weights = _validated_weights(sample_weights, len(y))
    weight_sum = float(weights.sum())
    theta = np.zeros(x.shape[1], dtype=np.float64)
    identity = np.eye(x.shape[1], dtype=np.float64)
    current = _loss(x, y, theta, ridge, weights)
    initial = current
    converged = False
    iterations = 0
    for iteration in range(max_iterations):
        prediction = np.tanh(x @ theta)
        derivative = 1.0 - prediction * prediction
        residual = prediction - y
        gradient = x.T @ (weights * derivative * residual) / weight_sum + ridge * theta
        curvature = weights * derivative * derivative
        hessian = x.T @ (x * curvature[:, None]) / weight_sum \
            + (ridge + 1e-12) * identity
        gradient_inf = float(np.max(np.abs(gradient)))
        if gradient_inf <= tolerance:
            converged = True
            iterations = iteration
            break
        step = np.linalg.solve(hessian, gradient)
        accepted = False
        scale = 1.0
        candidate = theta
        candidate_loss = current
        for _ in range(line_search_steps):
            proposal = theta - scale * step
            proposal_loss = _loss(x, y, proposal, ridge, weights)
            if proposal_loss < current:
                candidate = proposal
                candidate_loss = proposal_loss
                accepted = True
                break
            scale *= 0.5
        iterations = iteration + 1
        if not accepted:
            if gradient_inf <= max(tolerance, 1e-10):
                converged = True
            break
        update = float(np.max(np.abs(candidate - theta)))
        theta = candidate
        current = candidate_loss
        if update <= tolerance:
            converged = True
            break
    if not np.all(np.isfinite(theta)):
        raise RuntimeError("conditional fit produced non-finite coefficients")
    return theta, {
        "row_count": int(len(y)),
        "effective_weight_sum": weight_sum,
        "initial_loss": initial,
        "final_loss": current,
        "iterations": iterations,
        "converged": converged,
    }


def cross_fitted_predictions(
    matrix: np.ndarray,
    outcomes: np.ndarray,
    game_ids: np.ndarray,
    train_count: int,
    *,
    group_ids: np.ndarray | None = None,
    group_name: str = "game_id",
    row_weighting: str = "uniform",
    components: tuple[str, ...] | None = None,
    require_convergence: bool = False,
    fold_count: int,
    fold_seed: int,
    ridge: float,
    max_iterations: int,
    tolerance: float,
    line_search_steps: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    n = len(outcomes)
    games = np.asarray(game_ids, dtype=np.uint64)
    groups = games if group_ids is None else np.asarray(group_ids, dtype=np.uint64)
    if matrix.shape[0] != n or games.shape != (n,) or groups.shape != (n,):
        raise ValueError("conditional arrays are not aligned")
    if components is None:
        components = tuple(f"context_{index}" for index in range(matrix.shape[1]))
    if len(components) != matrix.shape[1]:
        raise ValueError("component names do not match conditional matrix width")
    if not 0 < train_count < n:
        raise ValueError("train_count must leave non-empty train and holdout cohorts")
    train_games = set(int(value) for value in np.unique(games[:train_count]))
    holdout_games = set(int(value) for value in np.unique(games[train_count:]))
    game_overlap = train_games & holdout_games
    if game_overlap:
        raise ValueError(f"{len(game_overlap)} complete games cross train/holdout boundary")
    train_groups = set(int(value) for value in np.unique(groups[:train_count]))
    holdout_groups = set(int(value) for value in np.unique(groups[train_count:]))
    group_overlap = train_groups & holdout_groups
    if group_overlap:
        raise ValueError(
            f"{len(group_overlap)} complete {group_name} groups cross train/holdout boundary"
        )
    if row_weighting == "uniform":
        sample_weights = np.ones(n, dtype=np.float64)
    elif row_weighting == "game_equal":
        sample_weights = _game_equal_weights(games)
    else:
        raise ValueError(f"unknown row weighting: {row_weighting}")

    folds = game_folds(groups, fold_count, fold_seed)
    predictions = np.empty(n, dtype=np.float64)
    blind = np.empty(train_count, dtype=np.float64)
    fold_rows: list[dict[str, Any]] = []
    train_positions = np.arange(train_count, dtype=np.int64)
    for fold in range(fold_count):
        evaluation = train_positions[folds[:train_count] == fold]
        training = train_positions[folds[:train_count] != fold]
        if evaluation.size == 0 or training.size == 0:
            raise ValueError(f"conditional fold {fold} is empty")
        training_games = set(int(value) for value in np.unique(games[training]))
        evaluation_games = set(int(value) for value in np.unique(games[evaluation]))
        training_groups = set(int(value) for value in np.unique(groups[training]))
        evaluation_groups = set(int(value) for value in np.unique(groups[evaluation]))
        if training_games & evaluation_games:
            raise RuntimeError("a complete game crossed an OOF fold")
        if training_groups & evaluation_groups:
            raise RuntimeError(f"a complete {group_name} group crossed an OOF fold")
        fold_weights = sample_weights[training]
        fold_rms = _weighted_rms(matrix[training], fold_weights)
        training_matrix = matrix[training] / fold_rms
        evaluation_matrix = matrix[evaluation] / fold_rms
        theta, fit = fit_tanh_linear(
            training_matrix,
            outcomes[training],
            ridge=ridge,
            max_iterations=max_iterations,
            tolerance=tolerance,
            line_search_steps=line_search_steps,
            sample_weights=fold_weights,
        )
        if require_convergence and not fit["converged"]:
            raise RuntimeError(f"conditional fold {fold} did not converge")
        predictions[evaluation] = np.tanh(evaluation_matrix @ theta)
        blind[evaluation] = float(
            np.average(outcomes[training], weights=fold_weights)
        )
        fold_rows.append(
            {
                "fold": fold,
                "training_rows": int(training.size),
                "evaluation_rows": int(evaluation.size),
                "training_games": len(training_games),
                "evaluation_games": len(evaluation_games),
                "game_disjoint": True,
                "training_groups": len(training_groups),
                "evaluation_groups": len(evaluation_groups),
                "group_disjoint": True,
                "rms_fitted_on_training_rows_only": True,
                "rms_scale": [float(value) for value in fold_rms],
                "theta_scaled": [float(value) for value in theta],
                "theta_raw": [float(value) for value in theta / fold_rms],
                "fit": fit,
            }
        )

    final_weights = sample_weights[:train_count]
    final_rms = _weighted_rms(matrix[:train_count], final_weights)
    final_train_matrix = matrix[:train_count] / final_rms
    final_theta, final_fit = fit_tanh_linear(
        final_train_matrix,
        outcomes[:train_count],
        ridge=ridge,
        max_iterations=max_iterations,
        tolerance=tolerance,
        line_search_steps=line_search_steps,
        sample_weights=final_weights,
    )
    if require_convergence and not final_fit["converged"]:
        raise RuntimeError("final conditional mapper did not converge")
    predictions[train_count:] = np.tanh(
        (matrix[train_count:] / final_rms) @ final_theta
    )
    if not np.all(np.isfinite(predictions)) or np.any(np.abs(predictions) > 1.0):
        raise RuntimeError("conditional predictions left finite WDL range")
    oof_mse = float(np.average(
        (predictions[:train_count] - outcomes[:train_count]) ** 2,
        weights=final_weights,
    ))
    blind_mse = float(np.average(
        (blind - outcomes[:train_count]) ** 2,
        weights=final_weights,
    ))
    return predictions, folds, {
        "components": list(components),
        "train_rms_scale": [float(value) for value in final_rms],
        "fold_local_rms": True,
        "scale_is_positive_only_no_mean_centering": True,
        "fold_count": fold_count,
        "fold_seed": fold_seed,
        "fold_group": group_name,
        "row_weighting": row_weighting,
        "each_game_total_weight_equal": row_weighting == "game_equal",
        "folds": fold_rows,
        "all_games_fold_disjoint": True,
        "all_groups_fold_disjoint": True,
        "train_holdout_game_overlap": 0,
        "train_holdout_group_overlap": 0,
        "train_unique_games": len(train_games),
        "holdout_unique_games": len(holdout_games),
        "train_unique_groups": len(train_groups),
        "holdout_unique_groups": len(holdout_groups),
        "oof_mse_vs_wdl": oof_mse,
        "state_blind_oof_mse_vs_wdl": blind_mse,
        "oof_mse_gain_vs_state_blind": blind_mse - oof_mse,
        "matrix_diagnostics": _matrix_diagnostics(
            matrix[:train_count], final_weights, components
        ),
        "final_train_fit": {
            "theta_scaled": [float(value) for value in final_theta],
            "theta_raw": [float(value) for value in final_theta / final_rms],
            "fit": final_fit,
        },
    }


def shuffled_within_cohort_folds(
    predictions: np.ndarray,
    folds: np.ndarray,
    train_count: int,
    seed: int,
    strata: np.ndarray | None = None,
    strata_name: str = "custom",
) -> tuple[np.ndarray, dict[str, Any]]:
    values = np.asarray(predictions, dtype=np.float64)
    groups = None if strata is None else np.asarray(strata)
    if groups is not None and groups.shape != values.shape:
        raise ValueError("shuffle strata must align one-to-one with predictions")
    shuffled = np.empty_like(values)
    sources = np.empty(len(values), dtype=np.int64)
    row_ids = np.arange(len(values), dtype=np.uint64)
    for start, stop, cohort in (
        (0, train_count, "train"),
        (train_count, len(values), "holdout"),
    ):
        for fold in sorted(int(value) for value in np.unique(folds[start:stop])):
            fold_members = np.flatnonzero(folds[start:stop] == fold) + start
            group_values = (None,) if groups is None else tuple(np.unique(groups[fold_members]))
            for group in group_values:
                members = fold_members if group is None else fold_members[groups[fold_members] == group]
                if members.size < 2:
                    suffix = "" if group is None else f" stratum {group}"
                    raise ValueError(f"{cohort} fold {fold}{suffix} has fewer than two rows")
                group_salt = 0 if group is None else int(group) + 2
                keys = _splitmix64(
                    row_ids[members] ^ np.uint64(seed) ^ np.uint64(fold)
                    ^ (np.uint64(group_salt) << np.uint64(32))
                )
                ordered = members[np.argsort(keys, kind="stable")]
                rotated = np.roll(ordered, 1)
                shuffled[ordered] = values[rotated]
                sources[ordered] = rotated
                if not np.array_equal(np.sort(shuffled[ordered]), np.sort(values[ordered])):
                    raise RuntimeError("shuffle changed a cohort/fold/stratum marginal")
    if np.any(sources == np.arange(len(values), dtype=np.int64)):
        raise RuntimeError("shuffle retained a source row")
    if np.any((sources < train_count) != (np.arange(len(values)) < train_count)):
        raise RuntimeError("shuffle crossed train/holdout cohorts")
    if not np.array_equal(folds[sources], folds):
        raise RuntimeError("shuffle crossed conditional folds")
    if groups is not None and not np.array_equal(groups[sources], groups):
        raise RuntimeError("shuffle crossed causal strata")
    return shuffled, {
        "seed": seed,
        "fixed_point_count": 0,
        "all_sources_within_same_cohort": True,
        "all_sources_within_same_fold": True,
        "stratification": "none" if groups is None else strata_name,
        "all_sources_within_same_stratum": groups is not None,
        "all_cohort_fold_marginals_preserved": True,
        "permutation_hash": hashlib.sha256(sources.tobytes(order="C")).hexdigest(),
    }


def _atomic_save_npy(path: Path, values: np.ndarray) -> None:
    if path.exists():
        raise ValueError(f"{path}: output exists (no-clobber)")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with temporary.open("xb") as handle:
            np.save(handle, values, allow_pickle=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ValueError(f"{path}: output exists (no-clobber)") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"{path}: output exists (no-clobber)")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ValueError(f"{path}: output exists (no-clobber)") from exc
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def tempo_phase_from_records(
    records: np.ndarray,
    *,
    chunk_size: int = 200_000,
) -> np.ndarray:
    """Return Scan tempo wmg without materialising a multi-million-row bit cube."""
    white_weights = np.zeros(64, dtype=np.float64)
    black_weights = np.zeros(64, dtype=np.float64)
    for index in range(64):
        bit = (index // 8) * 8 + (7 - index % 8)
        if bit < 50:
            row = bit // 5
            white_weights[index] = row
            black_weights[index] = 9 - row
    result = np.empty(len(records), dtype=np.float32)
    for start in range(0, len(records), chunk_size):
        stop = min(start + chunk_size, len(records))
        white_men = np.ascontiguousarray(records["wm"][start:stop], dtype="<u8")
        black_men = np.ascontiguousarray(records["bm"][start:stop], dtype="<u8")
        white_bits = np.unpackbits(white_men.view(np.uint8)).reshape(stop - start, 64)
        black_bits = np.unpackbits(black_men.view(np.uint8)).reshape(stop - start, 64)
        tempo = white_bits @ white_weights + black_bits @ black_weights
        result[start:stop] = np.clip(tempo / 300.0, 0.0, 1.0)
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    data_path = Path(args.data)
    meta_path = Path(args.meta)
    feat_path = Path(args.feat)
    aligned_path = Path(args.aligned_out)
    shuffled_path = Path(args.shuffled_out)
    report_path = Path(args.report)
    outputs = {path.resolve(strict=False) for path in (aligned_path, shuffled_path, report_path)}
    inputs = {path.resolve(strict=False) for path in (data_path, meta_path, feat_path)}
    if len(outputs) != 3 or outputs & inputs:
        raise ValueError("outputs must be distinct and cannot alias inputs")
    if any(path.exists() for path in (aligned_path, shuffled_path, report_path)):
        raise ValueError("conditional target outputs are no-clobber")

    records = _open_counted(data_path, b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(meta_path, len(records))
    features, width = _open_feat(feat_path, len(records))
    train_count = int(args.train_count)
    if not 0 < train_count < len(records):
        raise ValueError("--train-count must leave non-empty train and holdout cohorts")
    outcomes = np.asarray(
        np.where(records["stm"] == 1, records["wdl"], -records["wdl"]),
        dtype=np.float64,
    )
    if not np.all(np.isin(outcomes, (-1.0, 0.0, 1.0))):
        raise ValueError("JNNW contains WDL outside {-1,0,1}")
    context_schema = getattr(args, "context_schema", "ctx1-legacy-120")
    if context_schema not in CONTEXT_SCHEMAS:
        raise ValueError(f"unknown conditional context schema: {context_schema}")
    group_by = getattr(args, "group_by", "game_id")
    if group_by not in ("game_id", "opening_id"):
        raise ValueError("--group-by must be game_id or opening_id")
    row_weighting = getattr(args, "row_weighting", "uniform")
    require_convergence = bool(getattr(args, "require_convergence", False))
    phase_bin_count = int(getattr(args, "shuffle_phase_bins", 0))
    stratified_wdl = bool(getattr(args, "shuffle_within_wdl", False))
    if phase_bin_count not in (0,) and phase_bin_count < 2:
        raise ValueError("--shuffle-phase-bins must be 0 or >= 2")
    if context_schema == "ctx2-phase-tactical-30" and (
        group_by != "opening_id"
        or row_weighting != "game_equal"
        or not require_convergence
        or not stratified_wdl
        or phase_bin_count < 2
    ):
        raise ValueError(
            "CTX2 strict protocol requires opening_id folds, game_equal weighting, "
            "convergence enforcement, WDL stratification and >=2 phase bins"
        )
    contexts = context_matrix(features, context_schema)
    game_ids = np.asarray(metadata["game_id"], dtype=np.uint64)
    group_ids = np.asarray(metadata[group_by], dtype=np.uint64)
    predictions, folds, mapping = cross_fitted_predictions(
        contexts,
        outcomes,
        game_ids,
        train_count,
        group_ids=group_ids,
        group_name=group_by,
        row_weighting=row_weighting,
        components=CONTEXT_SCHEMAS[context_schema],
        require_convergence=require_convergence,
        fold_count=int(args.fold_count),
        fold_seed=int(args.fold_seed),
        ridge=float(args.ridge),
        max_iterations=int(args.max_iterations),
        tolerance=float(args.tolerance),
        line_search_steps=int(args.line_search_steps),
    )
    strata = None
    strata_name = "custom"
    phase_bins = None
    if phase_bin_count:
        phase = tempo_phase_from_records(records)
        phase_bins = np.minimum(
            np.floor(phase * phase_bin_count).astype(np.int16),
            phase_bin_count - 1,
        )
        strata = phase_bins
        strata_name = f"tempo_phase_{phase_bin_count}_bins"
    if stratified_wdl:
        wdl_codes = np.asarray(outcomes + 1.0, dtype=np.int16)
        if strata is None:
            strata = wdl_codes
            strata_name = "terminal_wdl_black"
        else:
            strata = wdl_codes * phase_bin_count + strata
            strata_name = f"terminal_wdl_black_x_tempo_phase_{phase_bin_count}_bins"
    shuffled, shuffle_report = shuffled_within_cohort_folds(
        predictions,
        folds,
        train_count,
        int(args.shuffle_seed),
        strata,
        strata_name,
    )
    alpha = float(args.alpha)
    if not 0.0 < alpha <= 1.0:
        raise ValueError("--alpha must be greater than 0 and at most 1")
    aligned_wdl = (1.0 - alpha) * outcomes + alpha * predictions
    shuffled_wdl = (1.0 - alpha) * outcomes + alpha * shuffled
    aligned = np.asarray((aligned_wdl + 1.0) * 0.5, dtype=np.float32)
    shuffled_targets = np.asarray((shuffled_wdl + 1.0) * 0.5, dtype=np.float32)
    if not (
        np.all(np.isfinite(aligned))
        and np.all(np.isfinite(shuffled_targets))
        and np.all((0.0 <= aligned) & (aligned <= 1.0))
        and np.all((0.0 <= shuffled_targets) & (shuffled_targets <= 1.0))
    ):
        raise RuntimeError("blended target left black-POV probability range")
    stratified_shuffle = strata is not None
    final_marginals_preserved = None
    if stratified_shuffle:
        final_marginals_preserved = True
        for start, stop in ((0, train_count), (train_count, len(outcomes))):
            for fold in np.unique(folds[start:stop]):
                for stratum in np.unique(strata[start:stop]):
                    members = np.flatnonzero(
                        (folds[start:stop] == fold)
                        & (strata[start:stop] == stratum)
                    ) + start
                    if not np.array_equal(
                        np.sort(aligned[members]), np.sort(shuffled_targets[members])
                    ):
                        final_marginals_preserved = False
                        break
    shuffle_report["all_final_target_marginals_preserved"] = (
        final_marginals_preserved
    )
    if stratified_shuffle and not final_marginals_preserved:
        raise RuntimeError("WDL-stratified shuffle changed a final target marginal")
    _atomic_save_npy(aligned_path, aligned)
    _atomic_save_npy(shuffled_path, shuffled_targets)
    report = {
        "schema": "jass.l3_conditional_targets.v2",
        "operation": "offline_conditional_target_transfer",
        "records": int(len(records)),
        "train_records": train_count,
        "holdout_records": int(len(records) - train_count),
        "meta_schema": meta_schema,
        "feature_width": width,
        "context_schema": context_schema,
        "target": {
            "formula": "(1-alpha)*terminal_wdl_black+alpha*conditional_wdl_black",
            "alpha": alpha,
            "output_pov": "black",
            "output_range": "win_probability_[0,1]",
            "oracle_or_egdb_signal": False,
            "new_selfplay_generated": False,
            "exact_legal_move_context": context_schema == "ctx2-phase-tactical-30",
        },
        "mapping": mapping,
        "shuffle_control": {
            **shuffle_report,
            "phase_bin_count": phase_bin_count,
            "phase_bin_counts": (
                None if phase_bins is None else {
                    str(index): int(np.sum(phase_bins == index))
                    for index in range(phase_bin_count)
                }
            ),
        },
        "source": {
            "data": str(data_path),
            "data_sha256": _sha256(data_path),
            "meta": str(meta_path),
            "meta_sha256": _sha256(meta_path),
            "feat": str(feat_path),
            "feat_sha256": _sha256(feat_path),
        },
        "outputs": {
            "aligned": str(aligned_path),
            "aligned_sha256": _sha256(aligned_path),
            "shuffled": str(shuffled_path),
            "shuffled_sha256": _sha256(shuffled_path),
        },
        "elapsed_seconds": time.monotonic() - started,
    }
    _atomic_write_json(report_path, report)
    replayed = json.loads(report_path.read_text(encoding="utf-8"))
    if replayed.get("schema") != report["schema"] or replayed["outputs"] != report["outputs"]:
        raise RuntimeError("conditional target report round-trip failed")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="aligned JNNW corpus")
    parser.add_argument("--meta", required=True, help="aligned JSM1/JSM2 sidecar")
    parser.add_argument(
        "--feat",
        required=True,
        help="aligned FEAT dump matching --context-schema",
    )
    parser.add_argument(
        "--context-schema",
        choices=tuple(CONTEXT_SCHEMAS),
        default="ctx1-legacy-120",
    )
    parser.add_argument(
        "--group-by",
        choices=("game_id", "opening_id"),
        default="game_id",
        help="atomic unit for OOF folds and train/holdout leakage checks",
    )
    parser.add_argument(
        "--row-weighting",
        choices=("uniform", "game_equal"),
        default="uniform",
        help="game_equal gives every complete trajectory total weight one",
    )
    parser.add_argument("--train-count", required=True, type=int)
    parser.add_argument("--aligned-out", required=True, help="aligned float32 .npy")
    parser.add_argument("--shuffled-out", required=True, help="shuffled float32 .npy")
    parser.add_argument("--report", required=True)
    parser.add_argument("--alpha", type=float, default=0.30)
    parser.add_argument("--fold-count", type=int, default=5)
    parser.add_argument("--fold-seed", type=int, default=20260811)
    parser.add_argument("--shuffle-seed", type=int, default=20260812)
    parser.add_argument(
        "--shuffle-within-wdl",
        action="store_true",
        help=(
            "shuffle predictions within cohort/fold/terminal-WDL so the "
            "complete blended-target marginal is preserved"
        ),
    )
    parser.add_argument(
        "--shuffle-phase-bins",
        type=int,
        default=0,
        help="also preserve tempo-phase bins inside every cohort/fold (0 disables)",
    )
    parser.add_argument("--ridge", type=float, default=1e-4)
    parser.add_argument("--max-iterations", type=int, default=50)
    parser.add_argument("--tolerance", type=float, default=1e-8)
    parser.add_argument("--line-search-steps", type=int, default=20)
    parser.add_argument(
        "--require-convergence",
        action="store_true",
        help="fail closed if any OOF or final mapper fit does not converge",
    )
    args = parser.parse_args(argv)
    report = run(args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
