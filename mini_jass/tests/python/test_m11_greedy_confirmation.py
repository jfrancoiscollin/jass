from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from mini_jass_lab.greedy_confirmation import (
    FRESH_PAIRED_SEEDS,
    build_greedy_confirmation_recommendation,
    derive_confirmation_holdout,
    resolve_greedy_confirmation_config,
)
from mini_jass_lab.split import SplitDefinition


def test_confirmation_holdout_is_deterministic_canonical_and_train_only() -> None:
    oracle = SimpleNamespace(
        manifest={"canonical_state_count": 6, "solver_hash": 42},
        canonical_ids=np.asarray([0, 0, 1, 2, 3, 4, 5], dtype=np.uint32),
        terminal_status=np.asarray([0, 1, 0, 0, 0, 0, 0], dtype=np.uint8),
        values=np.asarray([1, 1, 0, -1, 0, 1, -1], dtype=np.int8),
    )
    assignments = np.asarray([0, 0, 0, 1, 2, 0], dtype=np.uint8)
    split = SplitDefinition(
        assignments,
        assignments[oracle.canonical_ids],
        {"manifest_hash": "split-contract"},
    )
    first = derive_confirmation_holdout(oracle, split, 20260808, 0.5)
    second = derive_confirmation_holdout(oracle, split, 20260808, 0.5)
    assert first.manifest == second.manifest
    assert np.array_equal(first.state_ids, second.state_ids)
    assert first.canonical_ids.size == 2
    assert np.all(split.raw_assignments[first.state_ids] == 0)
    assert np.all(oracle.terminal_status[first.state_ids] == 0)
    assert set(oracle.canonical_ids[first.state_ids]).issubset(
        set(first.canonical_ids)
    )


def test_m11_config_freezes_fresh_seeds_and_behavior_only_contrast() -> None:
    root = Path(__file__).resolve().parents[2]
    resolved = resolve_greedy_confirmation_config(
        root / "configs/l2_greedy_confirmation.yaml"
    )
    assert tuple(resolved["paired_seeds"]) == FRESH_PAIRED_SEEDS
    assert resolved["games_per_arm"] == 256
    assert resolved["confirmation_holdout"] == {"seed": 20260808, "fraction": 0.2}
    assert resolved["arms"]["baseline_top2"]["overrides"] == {}
    assert resolved["arms"]["greedy_behavior"]["overrides"] == {
        "self_play.exploration.strategy": "greedy"
    }
    assert "frozen_test" not in str(
        {
            "seeds": resolved["paired_seeds"],
            "holdout": resolved["confirmation_holdout"],
            "arms": resolved["arms"],
        }
    ).lower()


def test_m11_gate_authorizes_only_a_fresh_l2_replication_rerun() -> None:
    aggregate = {
        "successful_run_count": 10,
        "paired_initial_weights": True,
        "paired_start_sequences": True,
        "historical_train_holdout_only": True,
        "m9_frozen_test_reads": 0,
        "arms": {
            "greedy_behavior": {
                "mean_exact_rate": 0.75,
                "mean_policy_optimal_mass": 0.90,
            }
        },
        "paired_exact_rate_delta": {
            "mean": 0.10,
            "confidence_95": [0.04, 0.16],
        },
        "paired_safety_draw_game_rate_delta": {"mean": 0.0},
    }
    thresholds = {
        "minimum_greedy_exact_rate": 0.70,
        "minimum_mean_exact_rate_delta": 0.03,
        "minimum_greedy_policy_optimal_mass": 0.85,
        "maximum_safety_draw_rate_increase": 0.01,
    }
    recommendation = build_greedy_confirmation_recommendation(
        aggregate, thresholds
    )
    assert recommendation["gate"]["status"] == "PASS"
    assert recommendation["l2_replication_rerun_authorized"] is True
    assert recommendation["l2_transfer_confirmed"] is False
    assert recommendation["implementation_preparation_authorized"] is False
    assert recommendation["direct_10x10_transfer_authorized"] is False
