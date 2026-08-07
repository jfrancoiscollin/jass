from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np

from mini_jass_lab.experiment import build_comparison
from mini_jass_lab.learning_gate import (
    M6_SUMMARY_METRICS,
    build_learning_recommendation,
    expand_learning_gate_configs,
    resolve_learning_gate_config,
    target_diagnostics,
)
from mini_jass_lab.replay import ReplaySample
from mini_jass_lab.split import build_split


def gate_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs/l1_learning_gate.yaml"


def test_m6_pack_expands_eleven_arms_over_five_paired_seeds() -> None:
    resolved = resolve_learning_gate_config(gate_config_path()).resolved
    expanded = expand_learning_gate_configs(resolved)
    assert len(expanded) == 55
    counts = {
        experiment: sum(item[0] == experiment for item in expanded)
        for experiment in ("E5", "E6", "E7", "E8", "E9")
    }
    assert counts == {"E5": 10, "E6": 15, "E7": 10, "E8": 10, "E9": 10}
    restart = next(
        config
        for experiment, arm, _, config in expanded
        if experiment == "E5" and arm == "train_restarts"
    )
    assert restart["self_play"]["start_state_source"] == "train_split"
    assert restart["training"]["steps"] == 256
    outcome = next(
        config
        for experiment, arm, _, config in expanded
        if experiment == "E7" and arm == "outcome_selected_action"
    )
    assert outcome["self_play"]["mode"] == "outcome_only"
    assert outcome["self_play"]["search_enabled"] is True


def _record(experiment: str, arm: str, seed: int, strong: bool) -> dict:
    value_delta = 0.10 if strong else 0.05
    mass_delta = 0.02 if strong else 0.01
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
                    "count": 100,
                    "value_sign_accuracy": 0.55,
                    "optimal_probability_mass": 0.75,
                }
            },
        },
        "targets": {
            "overall": {
                "value_exact_rate": 0.80,
                "value_mae": 0.20,
                "policy_optimal_mass": 0.90,
                "policy_argmax_optimal_rate": 0.90,
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


def test_m6_recommendation_requires_joint_value_and_policy_progress() -> None:
    resolved = resolve_learning_gate_config(gate_config_path()).resolved
    records = []
    for experiment, arm, seed, _ in expand_learning_gate_configs(resolved):
        records.append(_record(experiment, arm, seed, experiment == "E6" and arm == "strong_1024"))
    comparison = build_comparison(
        resolved,
        records,
        metric_paths=M6_SUMMARY_METRICS,
        schema="mini_jass.l1_learning_comparison.v1",
    )
    recommendation = build_learning_recommendation(resolved, comparison)
    assert recommendation["decision"] == "advance_to_L2_not_10x10"
    assert recommendation["l2_transfer_authorized"] is True
    assert recommendation["direct_10x10_transfer_authorized"] is False

    failed = deepcopy(comparison)
    selected = failed["experiments"]["E6"]["arms"]["strong_1024"]["metrics"]
    selected["development.optimal_mass_delta"]["mean"] = -0.001
    failed_recommendation = build_learning_recommendation(resolved, failed)
    assert failed_recommendation["decision"] == "continue_L1_policy_gate"
    assert failed_recommendation["l2_transfer_authorized"] is False


def test_target_diagnostics_are_stratified_after_generation(synthetic_oracle) -> None:
    split = build_split(synthetic_oracle, 20260806)
    state_id = 0
    action = int(np.flatnonzero(synthetic_oracle.optimal_mask[state_id])[0])
    policy = np.zeros(72, dtype=np.float32)
    policy[action] = 1.0
    sample = ReplaySample(
        state_id=state_id,
        value_target=float(synthetic_oracle.values[state_id]),
        policy_target=policy,
        generation=1,
        game_id=0,
        ply=0,
    )
    diagnostics = target_diagnostics([sample], synthetic_oracle, split)
    assert diagnostics["overall"]["value_exact_rate"] == 1.0
    assert diagnostics["overall"]["policy_optimal_mass"] == 1.0
    assert sum(
        cohort["count"] for cohort in diagnostics["by_cohort"].values()
    ) == 1
