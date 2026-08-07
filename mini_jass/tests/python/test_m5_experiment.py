from __future__ import annotations

from pathlib import Path

from mini_jass_lab.experiment import (
    build_comparison,
    build_recommendation,
    expand_arm_configs,
    resolve_pack_config,
    summarize_values,
)


def pack_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs/l1_first_experiment_pack.yaml"


def test_m5_pack_expands_all_arms_over_five_paired_seeds() -> None:
    resolved = resolve_pack_config(pack_config_path())
    expanded = expand_arm_configs(resolved)
    assert len(expanded) == 55
    counts = {
        experiment: sum(item[0] == experiment for item in expanded)
        for experiment in ("E1", "E2", "E3", "E4")
    }
    assert counts == {"E1": 5, "E2": 10, "E3": 20, "E4": 20}
    e1 = next(config for experiment, _, _, config in expanded if experiment == "E1")
    assert e1["self_play"]["mode"] == "outcome_only"
    assert e1["self_play"]["search_enabled"] is True
    assert e1["self_play"]["node_budgets"] == [16]
    assert e1["replay"]["strategy"] == "disabled"


def test_summary_includes_raw_counts_and_confidence_interval() -> None:
    summary = summarize_values([1.0, 2.0, 3.0, 4.0, 5.0])
    assert summary["count"] == 5
    assert summary["mean"] == 3.0
    assert summary["confidence_95"][0] < 3.0 < summary["confidence_95"][1]
    assert summary["raw"] == [1.0, 2.0, 3.0, 4.0, 5.0]


def _record(experiment: str, arm: str, seed: int, offset: float) -> dict:
    return {
        "experiment": experiment,
        "arm": arm,
        "seed": seed,
        "status": "PASS",
        "nodes": {"consumed": 100 + offset, "requested": 110 + offset, "positions": 20},
        "coverage": {"unique_states": 10 + offset},
        "development": {"value_sign_delta": 0.01 + offset / 1000, "optimal_mass_delta": 0.02},
        "frozen_test": {
            "candidate": {"value_sign_accuracy": 0.6, "optimal_probability_mass": 0.7},
            "value_error": 0.4 - offset / 1000,
            "zero_sample_count": 1000,
            "by_training_sample_count": {
                "zero": {
                    "count": 1000,
                    "value_sign_accuracy": 0.55,
                    "optimal_probability_mass": 0.65,
                }
            },
        },
        "trace": {
            "unique_optimal_states_reached": 8 + offset,
            "optimal_selection_rate": 0.7,
            "mean_oracle_regret": 0.2,
        },
    }


def test_comparison_is_paired_and_recommendation_never_skips_l2() -> None:
    resolved = resolve_pack_config(pack_config_path())
    records = []
    for experiment, arm, seed, _ in expand_arm_configs(resolved):
        arm_index = list(resolved["experiments"][experiment]["arms"]).index(arm)
        records.append(_record(experiment, arm, seed, float(arm_index)))
    comparison = build_comparison(resolved, records)
    assert comparison["experiments"]["E3"]["arms"]["fixed_32"]["run_count"] == 5
    assert (
        comparison["experiments"]["E4"]["paired_comparisons"]["top_2_uniform"]
        ["paired_seed_count"]
        == 5
    )
    recommendation = build_recommendation(comparison)
    assert recommendation["decision"] == "advance_to_L2_not_10x10"
    assert recommendation["direct_10x10_transfer_authorized"] is False
