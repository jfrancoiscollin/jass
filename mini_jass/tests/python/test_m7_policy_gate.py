from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from mini_jass_lab.experiment import build_comparison
from mini_jass_lab.policy_gate import (
    M7_SUMMARY_METRICS,
    build_policy_recommendation,
    expand_policy_gate_configs,
    resolve_policy_gate_config,
)


def gate_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs/l1_policy_target_gate.yaml"


def test_m7_pack_is_a_target_only_fifteen_run_contrast() -> None:
    resolved = resolve_policy_gate_config(gate_config_path()).resolved
    expanded = expand_policy_gate_configs(resolved)
    assert len(expanded) == 15
    assert {arm for _, arm, _, _ in expanded} == {
        "visit_distribution",
        "best_action",
        "score_softmax",
    }
    signatures = set()
    for _, _, _, config in expanded:
        assert config["self_play"]["root_allocation"] == "balanced"
        assert config["self_play"]["behavior_policy"] == "search_scores"
        signature = deepcopy(config)
        signature["seed"] = 0
        signature["self_play"]["policy_target"] = "target"
        signature["experiment"]["arm"] = "target"
        signatures.add(repr(signature))
    assert len(signatures) == 1


def _record(arm: str, seed: int, strong: bool) -> dict:
    value_delta = 0.10 if strong else 0.04
    mass_delta = 0.03 if strong else -0.01
    return {
        "experiment": "E10",
        "arm": arm,
        "seed": seed,
        "status": "PASS",
        "nodes": {"consumed": 100, "requested": 110, "positions": 20},
        "coverage": {"unique_states": 100},
        "development": {
            "value_sign_delta": value_delta,
            "optimal_mass_delta": mass_delta,
            "selection_score_delta": value_delta + mass_delta,
        },
        "frozen_test": {
            "candidate": {
                "value_sign_accuracy": 0.6,
                "optimal_probability_mass": 0.8,
            }
        },
        "targets": {
            "overall": {
                "value_exact_rate": 0.8,
                "policy_optimal_mass": 0.91,
                "policy_argmax_optimal_rate": 0.92,
            }
        },
        "root": {"action_coverage": 1.0, "maximum_budget_imbalance": 1},
        "promotion": {"eligible_generation_count": 1},
    }


def test_m7_success_requires_joint_progress_and_never_authorizes_transfer() -> None:
    resolved = resolve_policy_gate_config(gate_config_path()).resolved
    records = [
        _record(arm, seed, arm == "best_action")
        for _, arm, seed, _ in expand_policy_gate_configs(resolved)
    ]
    comparison = build_comparison(
        resolved,
        records,
        metric_paths=M7_SUMMARY_METRICS,
        schema="mini_jass.policy_target_comparison.v1",
    )
    recommendation = build_policy_recommendation(resolved, comparison)
    assert recommendation["gate"]["status"] == "PASS"
    assert recommendation["decision"] == "rerun_frozen_M6_gate_before_L2"
    assert recommendation["l2_transfer_authorized"] is False
    assert recommendation["direct_10x10_transfer_authorized"] is False

    failed = deepcopy(comparison)
    selected = failed["experiments"]["E10"]["arms"]["best_action"]["metrics"]
    selected["development.optimal_mass_delta"]["mean"] = 0.0
    failed_recommendation = build_policy_recommendation(resolved, failed)
    assert failed_recommendation["gate"]["status"] == "FAIL"
