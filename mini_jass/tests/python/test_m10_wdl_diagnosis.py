from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from mini_jass_lab.replay import ReplaySample
from mini_jass_lab.wdl_diagnosis import (
    build_wdl_diagnosis_recommendation,
    resolve_wdl_diagnosis_config,
    target_noise_diagnostics,
)


def _sample(state_id: int, target: float, game_id: int) -> ReplaySample:
    policy = np.zeros(4, dtype=np.float32)
    policy[0] = 1.0
    return ReplaySample(state_id, target, policy, 1, game_id, 0)


def test_target_noise_diagnostics_attributes_only_truncated_mismatches() -> None:
    oracle = SimpleNamespace(
        values=np.asarray([1, 0, -1, 1], dtype=np.int8),
        dtw=np.asarray([3, -1, 10, 0], dtype=np.int16),
    )
    samples = [
        _sample(0, 1.0, 0),
        _sample(1, 0.0, 0),
        _sample(2, 0.0, 1),
        _sample(3, 0.0, 1),
    ]
    result = target_noise_diagnostics(samples, oracle, {1})
    assert result["exact_rate"] == 0.5
    assert result["mismatch_count"] == 2
    assert result["mismatch_attributed_to_safety_draws"] == 1.0
    assert result["rule_terminated_exact_rate"] == 1.0
    assert result["by_dtw"]["long_9_plus"]["count"] == 1


def test_m10_config_is_train_only_and_preregisters_four_causal_arms() -> None:
    root = Path(__file__).resolve().parents[2]
    resolved = resolve_wdl_diagnosis_config(root / "configs/l2_wdl_diagnosis.yaml")
    assert list(resolved["arms"]) == [
        "baseline_64",
        "horizon_128",
        "budget_64",
        "greedy_behavior",
    ]
    assert resolved["meaningful_exact_rate_delta"] == 0.03
    assert "frozen_test" not in str(resolved["arms"]).lower()


def test_m10_recommendation_selects_largest_meaningful_factor_but_never_10x10() -> None:
    aggregate = {
        "paired_exact_rate_deltas": {
            "horizon_128": {"mean": 0.0},
            "budget_64": {"mean": 0.04},
            "greedy_behavior": {"mean": 0.12},
        }
    }
    recommendation = build_wdl_diagnosis_recommendation(aggregate, 0.03)
    assert recommendation["primary_arm"] == "greedy_behavior"
    assert recommendation["finding"] == "exploration_outcome_noise"
    assert recommendation["l2_replication_authorized"] is False
    assert recommendation["direct_10x10_transfer_authorized"] is False
