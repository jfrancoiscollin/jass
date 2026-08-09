"""Contracts of the PatternEval reconstruction program (M24-P/M14-P/M17-P)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
import yaml

from mini_jass_lab.pattern_reconstruction import replay_fingerprint
from mini_jass_lab.replay import ReplaySample

ROOT = Path(__file__).resolve().parents[2]


def _tool(name: str):
    path = ROOT / "tools" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M24P = _tool("run_pattern_supervised_ceiling.py")
M14P = _tool("run_pattern_value_target_ablation.py")
M17P = _tool("run_pattern_generation_ladder.py")
M18P = _tool("run_pattern_state_distribution_decomposition.py")


def _sample(value: float = 1.0, policy_action: int = 3) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[policy_action] = 1.0
    return ReplaySample(7, value, policy, 1, 2, 4)


def test_replay_fingerprint_covers_value_and_policy_targets() -> None:
    original = replay_fingerprint([_sample()])
    assert original == replay_fingerprint([_sample()])
    assert original != replay_fingerprint([_sample(value=-1.0)])
    assert original != replay_fingerprint([_sample(policy_action=8)])


def test_m24p_saturation_is_selected_on_development_not_frozen_test() -> None:
    by_dose = {
        "12": {"development": {"zero_regret_rate": 0.80}},
        "48": {"development": {"zero_regret_rate": 0.90}},
        "192": {"development": {"zero_regret_rate": 0.903}},
    }
    result = M24P.build_recommendation(
        by_dose, {"saturation_tolerance": 0.005}
    )
    assert result["status"] == "PASS"
    assert result["selection_cohort"] == "development"
    assert result["frozen_test_may_be_read"] is True


def test_m24p_keeps_frozen_test_closed_while_ladder_moves() -> None:
    by_dose = {
        "12": {"development": {"zero_regret_rate": 0.80}},
        "48": {"development": {"zero_regret_rate": 0.90}},
        "192": {"development": {"zero_regret_rate": 0.92}},
    }
    result = M24P.build_recommendation(
        by_dose, {"saturation_tolerance": 0.005}
    )
    assert result["status"] == "CEILING_NOT_SATURATED"
    assert result["frozen_test_may_be_read"] is False


def test_m17p_no_deployed_advance_is_inconclusive() -> None:
    aggregate = {
        "rungs": [1, 2, 4, 8],
        "mean_zero_regret_delta_by_rung": {
            "1": 0.0, "2": 0.0, "4": 0.0, "8": 0.0
        },
        "mean_advancing_generations": 0.0,
    }
    result = M17P.build_recommendation(
        aggregate,
        {"minimum_monotone_rungs": 3, "minimum_final_zero_regret_delta": 0.0},
        {"minimum_advancing_generations": 1},
    )
    assert result["iteration_compounds"] is None
    assert result["decision"].startswith("INCONCLUSIVE")
    assert result["status"] == "INCONCLUSIVE"


def test_m17p_diagnoses_the_blocking_gate_when_diagnostics_are_available() -> None:
    aggregate = {
        "rungs": [1, 2, 4, 8],
        "mean_zero_regret_delta_by_rung": {
            "1": 0.0, "2": 0.0, "4": 0.0, "8": 0.0
        },
        "mean_advancing_generations": 0.0,
        "development_pass_count": 7,
        "arena_pass_count": 0,
    }
    result = M17P.build_recommendation(
        aggregate,
        {"minimum_monotone_rungs": 3, "minimum_final_zero_regret_delta": 0.0},
        {"minimum_advancing_generations": 1},
    )
    assert result["blocked_component"] == "arena"
    assert result["finding"] == "ladder_did_not_advance_arena_gate_blocked"


def test_m17p_reads_zero_regret_as_primary_response() -> None:
    aggregate = {
        "rungs": [1, 2, 4, 8],
        "mean_zero_regret_delta_by_rung": {
            "1": 0.01, "2": 0.02, "4": 0.03, "8": 0.04
        },
        "mean_advancing_generations": 4.0,
    }
    result = M17P.build_recommendation(
        aggregate,
        {"minimum_monotone_rungs": 3, "minimum_final_zero_regret_delta": 0.0},
        {"minimum_advancing_generations": 1},
    )
    assert result["iteration_compounds"] is True
    assert result["status"] == "PASS"


@pytest.mark.parametrize(
    "name,schema,milestone",
    [
        ("l1_pattern_supervised_ceiling.yaml", M24P.SCHEMA, "M24-P"),
        ("l1_pattern_value_target_ablation.yaml", M14P.SCHEMA, "M14-P"),
        ("l1_pattern_generation_ladder.yaml", M17P.SCHEMA, "M17-P"),
        ("l1_pattern_generation_ladder_v2.yaml", M17P.SCHEMA_V2, "M17-P2"),
        (
            "l1_pattern_generation_ladder_replication.yaml",
            M17P.SCHEMA_REPLICATION,
            "M17-P2R",
        ),
        (
            "l1_pattern_state_distribution_decomposition.yaml",
            M18P.SCHEMA,
            "M18-P",
        ),
    ],
)
def test_new_evidence_namespaces_do_not_collide_with_historical_results(
    name: str, schema: str, milestone: str
) -> None:
    config = yaml.safe_load((ROOT / "configs" / name).read_text(encoding="utf-8"))
    assert config["schema"] == schema
    assert config["milestone"] == milestone
    assert schema not in {
        "mini_jass.supervised_ceiling.v1",
        "mini_jass.m14_value_target_ablation.v1",
        "mini_jass.generation_ladder.v1",
    }


def test_m14p_uses_fresh_paired_seeds_and_keeps_frozen_test_sealed() -> None:
    path = ROOT / "configs" / "l1_pattern_value_target_ablation.yaml"
    config = M14P._resolve(path)
    assert len(config["paired_seeds"]) == 20
    assert len(set(config["paired_seeds"])) == 20
    assert config["boundaries"]["cohorts_sealed"] == ["frozen_test"]
    assert config["boundaries"]["promotable"] is False


def test_m17p2_repairs_arena_power_without_duplicating_v1_games() -> None:
    v1_config, v1_loop = M17P._resolve(
        ROOT / "configs" / "l1_pattern_generation_ladder.yaml"
    )
    v2_config, v2_loop = M17P._resolve(
        ROOT / "configs" / "l1_pattern_generation_ladder_v2.yaml"
    )
    threshold = float(v1_loop["promotion"]["minimum_arena_lower_bound"])
    assert v1_loop["arena"]["pairs"] == 4
    assert v1_loop["arena"]["epsilon"] == 0.0
    assert v2_loop["arena"]["pairs"] == 128
    assert v2_loop["arena"]["epsilon"] == 0.0
    assert v2_loop["arena"]["confidence_unit"] == "pairs"
    assert v2_loop["arena"]["start_state_source"] == "provided"
    assert M17P.arena_score_lower_bound(0.5, 4, 1.96) < threshold
    assert M17P.arena_score_lower_bound(0.5, 128, 1.96, "pairs") >= threshold
    assert len(v2_config["paired_seeds"]) == 20
    assert len(set(v2_config["paired_seeds"])) == 20
    assert set(v2_config["paired_seeds"]).isdisjoint(v1_config["paired_seeds"])
    assert v2_config["boundaries"]["cohorts_sealed"] == ["frozen_test"]


def test_m17p2_rejects_the_fixed_initial_start(tmp_path: Path) -> None:
    source = ROOT / "configs" / "l1_pattern_generation_ladder_v2.yaml"
    config = yaml.safe_load(source.read_text(encoding="utf-8"))
    config["base_loop_config"] = str(
        (ROOT / "configs" / "l1_pattern_reconstruction_loop.yaml").resolve()
    )
    config["promotion_control"]["arena_start_state_source"] = "initial"
    path = tmp_path / "underpowered.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="varied development start states"):
        M17P._resolve(path)


def test_m17p2r_reuses_control_with_fresh_preregistered_seeds() -> None:
    v1_config, _ = M17P._resolve(
        ROOT / "configs" / "l1_pattern_generation_ladder.yaml"
    )
    v2_config, v2_loop = M17P._resolve(
        ROOT / "configs" / "l1_pattern_generation_ladder_v2.yaml"
    )
    replication, replication_loop = M17P._resolve(
        ROOT / "configs" / "l1_pattern_generation_ladder_replication.yaml"
    )
    assert replication["paired_seeds"] == list(range(264001, 264021))
    assert set(replication["paired_seeds"]).isdisjoint(v1_config["paired_seeds"])
    assert set(replication["paired_seeds"]).isdisjoint(v2_config["paired_seeds"])
    assert replication["promotion_control"] == v2_config["promotion_control"]
    assert replication_loop["arena"] == v2_loop["arena"]
    assert replication["boundaries"]["cohorts_sealed"] == ["frozen_test"]


@pytest.mark.parametrize(
    "primary,expected_finding",
    [
        (
            {"mean": 0.012, "lower": 0.004, "upper": 0.020},
            "pattern_iteration_compounding_replicates",
        ),
        (
            {"mean": 0.008, "lower": 0.002, "upper": 0.014},
            "compounding_detected_below_practical_threshold",
        ),
        (
            {"mean": 0.012, "lower": -0.001, "upper": 0.025},
            "pattern_iteration_compounding_does_not_replicate",
        ),
    ],
)
def test_m17p2r_applies_confidence_and_practical_gates(
    primary: dict[str, float], expected_finding: str
) -> None:
    result = M17P.build_replication_recommendation(
        {
            "mean_advancing_generations": 6.0,
            "paired_zero_regret_g8_minus_g1": primary,
        },
        {
            "require_primary_ci_above_zero": True,
            "minimum_practical_compounding_gain": 0.01,
        },
        {"minimum_advancing_generations": 1},
    )
    assert result["status"] == "PASS"
    assert result["finding"] == expected_finding
    assert result["replication_confirms"] is (
        expected_finding == "pattern_iteration_compounding_replicates"
    )
    assert result["promotable"] is False


def test_m17p2r_is_inconclusive_when_the_ladder_does_not_advance() -> None:
    result = M17P.build_replication_recommendation(
        {
            "mean_advancing_generations": 0.0,
            "paired_zero_regret_g8_minus_g1": {
                "mean": 0.02,
                "lower": 0.01,
                "upper": 0.03,
            },
        },
        {
            "require_primary_ci_above_zero": True,
            "minimum_practical_compounding_gain": 0.01,
        },
        {"minimum_advancing_generations": 1},
    )
    assert result["status"] == "INCONCLUSIVE"
    assert result["replication_confirms"] is None
