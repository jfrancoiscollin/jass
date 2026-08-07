from __future__ import annotations

import numpy as np

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
