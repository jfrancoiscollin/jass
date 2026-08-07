from __future__ import annotations

from pathlib import Path

from mini_jass_lab.experiment import build_comparison
from mini_jass_lab.learning_gate import (
    M6_SUMMARY_METRICS,
    build_learning_recommendation,
    expand_learning_gate_configs,
    resolve_learning_gate_config,
)


def gate_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs/l1_frozen_learning_gate.yaml"


def test_m8_replays_the_full_pack_with_the_frozen_m7_target() -> None:
    loaded = resolve_learning_gate_config(gate_config_path())
    assert loaded.milestone == "M8"
    assert loaded.upstream_key == "m7"
    calibration = loaded.resolved["report_procedure"]["execution_calibration"]
    assert calibration["evidence_scope"] == "execution_node_counts_only"
    assert calibration["prior_protocol_hash"] == (
        "0919cdb0a6bf491f62cb51d71b0c4dc4b1a4345eed51817219ad32cdf722c455"
    )
    expanded = expand_learning_gate_configs(loaded.resolved)
    assert len(expanded) == 55
    outcome_arms = 0
    for experiment, arm, _, config in expanded:
        self_play = config["self_play"]
        assert self_play["root_allocation"] == "balanced"
        assert self_play["behavior_policy"] == "search_scores"
        if self_play["mode"] == "outcome_only":
            assert (experiment, arm) == ("E7", "outcome_selected_action")
            outcome_arms += 1
        else:
            assert self_play["policy_target"] == "score_softmax"
            assert self_play["policy_target_temperature"] == 0.25
    assert outcome_arms == 5
    greedy = next(
        config
        for experiment, arm, _, config in expanded
        if experiment == "E8" and arm == "greedy"
    )
    assert greedy["self_play"]["games"] == 102


def _record(experiment: str, arm: str, seed: int) -> dict:
    outcome_control = experiment == "E7" and arm == "outcome_selected_action"
    selected = experiment == "E6" and arm == "strong_1024"
    value_delta = 0.90 if outcome_control else 0.10 if selected else 0.05
    mass_delta = 0.90 if outcome_control else 0.03 if selected else 0.01
    coverage = 100 if experiment == "E5" and arm == "initial_state" else 400
    return {
        "experiment": experiment,
        "arm": arm,
        "seed": seed,
        "status": "PASS",
        "nodes": {"consumed": 100, "requested": 110, "positions": 20},
        "starts": {"unique": 10},
        "training": {"optimizer_steps": 32, "final_sample_pool": 20},
        "coverage": {"unique_states": coverage},
        "development": {
            "value_sign_delta": value_delta,
            "optimal_mass_delta": mass_delta,
            "selection_score_delta": value_delta + mass_delta,
            "sampled": {
                "count": 10,
                "value_sign_delta": value_delta,
                "optimal_mass_delta": mass_delta,
            },
        },
        "frozen_test": {
            "candidate": {
                "value_sign_accuracy": 0.6,
                "optimal_probability_mass": 0.8,
            },
            "value_error": 0.4,
            "zero_sample_count": 100,
            "by_training_sample_count": {
                "zero": {
                    "value_sign_accuracy": 0.55,
                    "optimal_probability_mass": 0.75,
                }
            },
        },
        "targets": {
            "overall": {
                "value_exact_rate": 0.8,
                "value_mae": 0.2,
                "policy_optimal_mass": 0.9,
                "policy_argmax_optimal_rate": 0.9,
                "unique_states": coverage,
            }
        },
        "trace": {
            "unique_optimal_states_reached": 20,
            "optimal_selection_rate": 0.8,
            "mean_oracle_regret": 0.1,
        },
        "promotion": {
            "eligible_generation_count": 1,
            "provisional_advance_count": 1,
        },
    }


def test_m8_recommendation_ignores_the_outcome_control_for_target_replication() -> None:
    resolved = resolve_learning_gate_config(gate_config_path()).resolved
    records = [
        _record(experiment, arm, seed)
        for experiment, arm, seed, _ in expand_learning_gate_configs(resolved)
    ]
    comparison = build_comparison(
        resolved,
        records,
        metric_paths=M6_SUMMARY_METRICS,
        schema="mini_jass.l1_learning_comparison.v1",
    )
    recommendation = build_learning_recommendation(resolved, comparison)
    assert recommendation["gate"]["status"] == "PASS"
    assert recommendation["evidence"]["selected_experiment"] == "E6"
    assert recommendation["evidence"]["selected_arm"] == "strong_1024"
    assert recommendation["evidence"]["frozen_policy_target"] == "score_softmax"
    assert recommendation["decision"] == "advance_to_L2_not_10x10"
    assert recommendation["l2_transfer_authorized"] is True
    assert recommendation["direct_10x10_transfer_authorized"] is False
