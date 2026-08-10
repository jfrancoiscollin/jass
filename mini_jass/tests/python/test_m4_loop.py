from __future__ import annotations

import numpy as np
import pytest

from mini_jass_lab.loop import execute_loop
from mini_jass_lab.split import build_split


def tiny_config(manifest_hash: str) -> dict:
    return {
        "schema": "mini_jass.selfplay.v1",
        "mode": "outcome_only",
        "seed": 444,
        "deterministic": True,
        "generations": 1,
        "split_seed": 20260806,
        "expected_split_manifest_hash": manifest_hash,
        "model": {
            "hidden_size": 32,
            "linear": False,
            "action_count": 72,
            "enforce_baseline_limit": True,
        },
        "self_play": {
            "mode": "outcome_only",
            "games": 2,
            "max_plies": 4,
            "search_depth": 1,
            "budget_policy": "fixed",
            "node_budgets": [1],
            "exploration": {
                "strategy": "greedy",
                "epsilon": 0.0,
                "top_k": 1,
                "temperature": 1.0,
            },
        },
        "replay": {"capacity": 32, "strategy": "uniform", "training_samples": 8},
        "training": {
            "steps": 2,
            "batch_size": 4,
            "learning_rate": 0.001,
            "weight_decay": 0.0,
            "value_weight": 1.0,
            "policy_weight": 1.0,
        },
        "arena": {
            "pairs": 1,
            "max_plies": 4,
            "search_depth": 1,
            "node_budget": 1,
            "epsilon": 0.0,
            "confidence_z": 1.96,
        },
        "development": {"batch_size": 32},
        "promotion": {
            "minimum_development_improvement": 0.0,
            "minimum_arena_lower_bound": 0.0,
        },
        "runtime": {"threads": 1},
    }


def test_complete_loop_repeats_with_identical_hashes(synthetic_oracle) -> None:
    split = build_split(synthetic_oracle, 20260806)
    config = tiny_config(split.manifest["manifest_hash"])
    development = split.indices("development")
    first = execute_loop(config, synthetic_oracle, development)
    second = execute_loop(config, synthetic_oracle, development)
    assert first.core["execution_hash"] == second.core["execution_hash"]
    assert first.core["final_model_hash"] == second.core["final_model_hash"]
    assert first.core["training_target_contract"]["forbidden_fields"] == [
        "oracle_value",
        "dtw",
        "optimal_actions",
    ]


def test_arena_uses_distinct_provided_start_states_by_pair(synthetic_oracle) -> None:
    split = build_split(synthetic_oracle, 20260806)
    config = tiny_config(split.manifest["manifest_hash"])
    config["arena"].update(
        {
            "pairs": 3,
            "confidence_unit": "pairs",
            "start_state_source": "provided",
        }
    )
    development = split.indices("development")
    execution = execute_loop(config, synthetic_oracle, development)
    arena = execution.core["generations"][0]["arena"]
    assert arena["start_state_source"] == "provided"
    assert arena["unique_start_state_count"] == 3
    assert arena["effective_observations"] == 3
    assert len(arena["start_state_ids"]) == 3
    assert set(arena["start_state_ids"]).issubset(set(development.tolist()))
    assert sum(arena["pair_score_histogram"].values()) == 3


def test_training_state_mask_excludes_holdout_positions_from_replay(
    synthetic_oracle,
) -> None:
    split = build_split(synthetic_oracle, 20260806)
    config = tiny_config(split.manifest["manifest_hash"])
    config["replay"]["strategy"] = "disabled"
    mask = np.zeros(synthetic_oracle.state_count, dtype=np.bool_)
    mask[:2] = True
    execution = execute_loop(
        config,
        synthetic_oracle,
        split.indices("development"),
        training_state_mask=mask,
    )
    eligible = sum(bool(mask[sample.state_id]) for sample in execution.samples)
    assert eligible > 0
    assert eligible < len(execution.samples)
    assert execution.core["generations"][0]["training"]["sample_pool"] == eligible


def test_folded_pattern_value_loop_is_wired_end_to_end(synthetic_oracle) -> None:
    split = build_split(synthetic_oracle, 20260806)
    config = tiny_config(split.manifest["manifest_hash"])
    config["model"] = {
        "architecture": "folded_pattern_value",
        "pattern_window": 2,
        "include_reversible_plies": True,
    }
    config["self_play"]["search_enabled"] = True
    config["self_play"]["node_budgets"] = [2]
    config["training"]["policy_weight"] = 0.0
    development = split.indices("development")
    first = execute_loop(config, synthetic_oracle, development)
    second = execute_loop(config, synthetic_oracle, development)
    assert first.core["execution_hash"] == second.core["execution_hash"]
    assert first.core["model"]["architecture"] == "folded_pattern_value"
    assert first.core["model"]["value_only"] is True
    contract = first.core["training_target_contract"]
    assert contract["policy"] == "none_value_only_search_supplies_actions"
    assert contract["replay_policy_field_consumed"] is False
    training = first.core["generations"][0]["training"]
    assert training["policy_trained"] is False
    # ⚠️ `None` et non `0.0` : une perte a zero se lirait comme une politique
    # parfaitement apprise, alors qu'il n'y en a aucune.
    assert training["policy_loss"] is None
    development_metrics = first.core["generations"][0]["development"]["candidate"]
    assert development_metrics["action_source"] == "search_one_ply"
    assert development_metrics["optimal_probability_mass"] is None
    # `policy_count` reste litteralement le nombre d'etats ou une TETE a
    # repondu -- zero ici. Les taux de regret ont donc besoin de LEUR
    # denominateur, sinon ils se lisent comme portant sur rien.
    assert development_metrics["policy_count"] == 0
    assert development_metrics["response_count"] > 0
    assert development_metrics["zero_regret_rate"] is not None


def test_folded_pattern_value_loop_refuses_to_play_without_search(
    synthetic_oracle,
) -> None:
    split = build_split(synthetic_oracle, 20260806)
    config = tiny_config(split.manifest["manifest_hash"])
    config["model"] = {
        "architecture": "folded_pattern_value",
        "pattern_window": 2,
    }
    config["training"]["policy_weight"] = 0.0
    config["self_play"]["search_enabled"] = False
    with pytest.raises(ValueError, match="requires search"):
        execute_loop(config, synthetic_oracle, split.indices("development"))
