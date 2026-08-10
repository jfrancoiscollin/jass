"""Leakage and signal contracts for cross-fitted conditional targets."""

from __future__ import annotations

import numpy as np
import pytest

from mini_jass_lab.conditional_targets import (
    cross_fitted_conditional_wdl,
    game_group_folds,
    permute_predictions_within_folds,
)
from mini_jass_lab.context import COMPONENTS
from mini_jass_lab.replay import ReplaySample


def _sample(game: int, ply: int, outcome: float) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[3] = 1.0
    return ReplaySample(game + ply, outcome, policy, 1, game, ply, 3)


def test_game_group_folds_are_deterministic_and_keep_complete_games_together() -> None:
    samples = [
        _sample(game, ply, 1.0 if game % 2 else -1.0)
        for game in range(20)
        for ply in range(3)
    ]
    first = game_group_folds(samples, fold_count=5, namespace="fixture")
    second = game_group_folds(samples, fold_count=5, namespace="fixture")
    assert np.array_equal(first, second)
    assert set(first.tolist()) == set(range(5))
    for game in range(20):
        rows = [
            fold
            for sample, fold in zip(samples, first, strict=True)
            if sample.game_id == game
        ]
        assert len(set(rows)) == 1


def test_cross_fitted_conditional_wdl_beats_state_blind_on_predictive_context() -> None:
    samples = [_sample(game, 0, 1.0 if game % 2 else -1.0) for game in range(40)]
    outcomes = np.asarray([sample.value_target for sample in samples], dtype=np.float64)
    contexts = np.zeros((len(samples), len(COMPONENTS)), dtype=np.float64)
    contexts[:, 0] = outcomes
    result = cross_fitted_conditional_wdl(
        contexts,
        outcomes,
        samples,
        fold_count=5,
        namespace="predictive-fixture",
        ridge=1.0e-4,
        max_iterations=64,
        tolerance=1.0e-10,
        line_search_steps=24,
    )
    assert result["all_games_fold_disjoint"] is True
    assert result["conditional_mse_gain_vs_state_blind"] > 0.5
    assert np.all(np.abs(result["conditional_predictions"]) <= 1.0)
    assert all(row["game_disjoint"] for row in result["folds"])


def test_conditional_cross_fit_rejects_non_wdl_or_misaligned_inputs() -> None:
    samples = [_sample(game, 0, 1.0) for game in range(5)]
    contexts = np.zeros((5, len(COMPONENTS)), dtype=np.float64)
    kwargs = {
        "fold_count": 5,
        "namespace": "fixture",
        "ridge": 1.0e-4,
        "max_iterations": 2,
        "tolerance": 1.0e-6,
        "line_search_steps": 2,
    }
    with pytest.raises(ValueError, match="terminal WDL"):
        cross_fitted_conditional_wdl(
            contexts, np.asarray([1.0, 1.0, 0.5, -1.0, 0.0]), samples, **kwargs
        )
    with pytest.raises(ValueError, match="wrong shape"):
        cross_fitted_conditional_wdl(
            contexts[:-1], np.ones(5), samples, **kwargs
        )


def test_fold_permutation_preserves_marginals_but_moves_every_source_row() -> None:
    samples = [_sample(game, ply, 1.0) for game in range(6) for ply in range(2)]
    folds = np.asarray([game % 3 for game in range(6) for _ in range(2)])
    predictions = np.linspace(-0.9, 0.9, len(samples))
    result = permute_predictions_within_folds(
        predictions, folds, samples, namespace="shuffle-fixture"
    )
    assert result["fixed_point_count"] == 0
    assert result["all_sources_within_same_fold"] is True
    for fold in range(3):
        members = folds == fold
        assert np.array_equal(
            np.sort(result["predictions"][members]), np.sort(predictions[members])
        )
    repeated = permute_predictions_within_folds(
        predictions, folds, samples, namespace="shuffle-fixture"
    )
    assert np.array_equal(result["predictions"], repeated["predictions"])
