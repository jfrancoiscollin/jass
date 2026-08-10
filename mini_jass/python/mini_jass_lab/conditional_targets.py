"""Leakage-resistant conditional WDL targets for scalar PatternEval."""

from __future__ import annotations

import hashlib
from typing import Any, Sequence

import numpy as np

from .context import COMPONENTS
from .context_c3 import fit_tanh_linear
from .replay import ReplaySample


def game_group_folds(
    samples: Sequence[ReplaySample],
    *,
    fold_count: int,
    namespace: str,
) -> np.ndarray:
    """Assign complete games to deterministic, approximately balanced folds."""
    if not samples:
        raise ValueError("conditional targets require replay samples")
    if fold_count < 2:
        raise ValueError("conditional targets require at least two folds")
    games = sorted({int(sample.game_id) for sample in samples})
    if len(games) < fold_count:
        raise ValueError("conditional target folds exceed unique replay games")
    ranked = sorted(
        games,
        key=lambda game: hashlib.sha256(
            f"{namespace}|game={game}".encode("utf-8")
        ).digest(),
    )
    assignment = {game: index % fold_count for index, game in enumerate(ranked)}
    folds = np.asarray(
        [assignment[int(sample.game_id)] for sample in samples], dtype=np.int64
    )
    if set(int(value) for value in np.unique(folds)) != set(range(fold_count)):
        raise RuntimeError("conditional target assignment produced an empty fold")
    for game in games:
        observed = {
            int(fold)
            for sample, fold in zip(samples, folds, strict=True)
            if int(sample.game_id) == game
        }
        if len(observed) != 1:
            raise RuntimeError("one replay game crossed conditional target folds")
    return folds


def cross_fitted_conditional_wdl(
    contexts: np.ndarray,
    outcomes: np.ndarray,
    samples: Sequence[ReplaySample],
    *,
    fold_count: int,
    namespace: str,
    ridge: float,
    max_iterations: int,
    tolerance: float,
    line_search_steps: int,
) -> dict[str, Any]:
    """Predict each row from models that never observed its complete game."""
    matrix = np.asarray(contexts, dtype=np.float64)
    values = np.asarray(outcomes, dtype=np.float64)
    if matrix.shape != (len(samples), len(COMPONENTS)):
        raise ValueError("conditional context matrix has the wrong shape")
    if values.shape != (len(samples),) or not np.all(np.isin(values, (-1.0, 0.0, 1.0))):
        raise ValueError("conditional outcomes must be aligned terminal WDL")
    folds = game_group_folds(
        samples, fold_count=int(fold_count), namespace=str(namespace)
    )
    conditional = np.empty(values.shape, dtype=np.float64)
    state_blind = np.empty(values.shape, dtype=np.float64)
    fold_rows: list[dict[str, Any]] = []
    zero = np.zeros(len(COMPONENTS), dtype=np.float64)
    game_ids = np.asarray([int(sample.game_id) for sample in samples], dtype=np.int64)

    for fold in range(int(fold_count)):
        evaluation = folds == fold
        training = ~evaluation
        if not np.any(evaluation) or not np.any(training):
            raise RuntimeError("conditional cross-fit fold is empty")
        training_games = set(int(value) for value in game_ids[training])
        evaluation_games = set(int(value) for value in game_ids[evaluation])
        if training_games & evaluation_games:
            raise RuntimeError("conditional cross-fit leaked a complete game")
        theta, fit = fit_tanh_linear(
            matrix[training],
            values[training],
            initial_theta=zero,
            ridge=float(ridge),
            max_iterations=int(max_iterations),
            tolerance=float(tolerance),
            line_search_steps=int(line_search_steps),
        )
        conditional[evaluation] = np.tanh(matrix[evaluation] @ theta)
        global_mean = float(np.mean(values[training]))
        state_blind[evaluation] = global_mean
        fold_rows.append(
            {
                "fold": fold,
                "training_row_count": int(np.count_nonzero(training)),
                "evaluation_row_count": int(np.count_nonzero(evaluation)),
                "training_game_count": len(training_games),
                "evaluation_game_count": len(evaluation_games),
                "game_disjoint": True,
                "global_training_wdl_mean": global_mean,
                "theta": [float(value) for value in theta],
                "fit": fit,
            }
        )

    if not np.all(np.isfinite(conditional)) or not np.all(np.isfinite(state_blind)):
        raise RuntimeError("conditional cross-fit produced non-finite targets")
    conditional_mse = float(np.mean((conditional - values) ** 2))
    state_blind_mse = float(np.mean((state_blind - values) ** 2))
    return {
        "fold_ids": folds,
        "conditional_predictions": conditional,
        "state_blind_predictions": state_blind,
        "folds": fold_rows,
        "row_count": len(samples),
        "unique_game_count": len(set(int(value) for value in game_ids)),
        "all_games_fold_disjoint": True,
        "conditional_oof_mse_vs_wdl": conditional_mse,
        "state_blind_oof_mse_vs_wdl": state_blind_mse,
        "conditional_mse_gain_vs_state_blind": state_blind_mse - conditional_mse,
    }


def permute_predictions_within_folds(
    predictions: np.ndarray,
    fold_ids: np.ndarray,
    samples: Sequence[ReplaySample],
    *,
    namespace: str,
) -> dict[str, Any]:
    """Break state alignment while preserving each fold's prediction multiset."""
    values = np.asarray(predictions, dtype=np.float64)
    folds = np.asarray(fold_ids, dtype=np.int64)
    if values.shape != (len(samples),) or folds.shape != values.shape:
        raise ValueError("conditional permutation inputs must align with replay rows")
    if not namespace:
        raise ValueError("conditional permutation namespace must be non-empty")
    shuffled = np.empty_like(values)
    sources = np.empty(len(samples), dtype=np.int64)
    for fold in sorted(int(value) for value in np.unique(folds)):
        members = np.flatnonzero(folds == fold)
        if members.size < 2:
            raise ValueError("conditional permutation fold has fewer than two rows")
        ordered = np.asarray(
            sorted(
                (int(index) for index in members),
                key=lambda index: hashlib.sha256(
                    (
                        f"{namespace}|fold={fold}|game={samples[index].game_id}|"
                        f"ply={samples[index].ply}|state={samples[index].state_id}|"
                        f"row={index}"
                    ).encode("utf-8")
                ).digest(),
            ),
            dtype=np.int64,
        )
        rotated = np.roll(ordered, 1)
        shuffled[ordered] = values[rotated]
        sources[ordered] = rotated
        if not np.array_equal(np.sort(shuffled[ordered]), np.sort(values[ordered])):
            raise RuntimeError("conditional permutation changed a fold marginal")
    if np.any(sources == np.arange(len(samples), dtype=np.int64)):
        raise RuntimeError("conditional permutation retained a source row")
    if not np.all(folds[sources] == folds):
        raise RuntimeError("conditional permutation crossed held-out folds")
    return {
        "predictions": shuffled,
        "source_row_indices": sources,
        "fixed_point_count": 0,
        "all_sources_within_same_fold": True,
        "all_fold_marginals_preserved": True,
        "permutation_hash": hashlib.sha256(sources.tobytes(order="C")).hexdigest(),
    }
