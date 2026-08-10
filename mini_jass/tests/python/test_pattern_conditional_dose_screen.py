"""Contracts for the preregistered M15-C2 conditional-target dose screen."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from mini_jass_lab.replay import ReplaySample

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_pattern_conditional_dose_screen.py"
SPEC = importlib.util.spec_from_file_location("run_pattern_m15c2", TOOL)
assert SPEC and SPEC.loader
M15C2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M15C2)


def _sample(game: int, outcome: float) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[3] = 1.0
    return ReplaySample(game, outcome, policy, 1, game, 0, 3)


def _interval(mean: float, lower: float, upper: float) -> dict[str, float]:
    return {"mean": mean, "lower": lower, "upper": upper}


def _static(
    attribution: tuple[float, float, float],
    operational: tuple[float, float, float],
) -> dict[str, object]:
    return {
        "attribution_30": {"zero_regret_gain": _interval(*attribution)},
        "operational_30": {"zero_regret_gain": _interval(*operational)},
    }


def _arena(
    attribution: tuple[float, float, float],
    operational: tuple[float, float, float],
) -> dict[str, object]:
    return {
        "attribution_30": {"arena_score_minus_half": _interval(*attribution)},
        "operational_30": {"arena_score_minus_half": _interval(*operational)},
    }


def test_m15c2_config_freezes_primary_dose_fresh_seeds_and_no_test_read() -> None:
    config, loop = M15C2._resolve(
        ROOT / "configs" / "l1_pattern_conditional_dose_screen.yaml"
    )
    assert config["paired_seeds"] == list(range(273001, 273021))
    assert loop["model"]["architecture"] == "folded_pattern_value"
    assert config["dose_screen"]["primary_alpha"] == pytest.approx(0.30)
    assert config["dose_screen"]["exploratory_alphas"] == [0.20, 0.40]
    assert config["scientific_gate"]["minimum_effect_floor"] == 0.0
    assert config["scientific_gate"]["strength_is_separate_from_static_pass"]
    assert config["strength_arena"]["pairs"] == 512
    assert M15C2.estimate_power(config["power_sizing"]) == pytest.approx(0.92325)
    assert config["boundaries"]["additional_frozen_test_reads_authorized"] == 0
    assert config["boundaries"]["execution_is_not_queued_by_this_pr"] is True


def test_m15c2_changes_only_value_target_at_each_frozen_dose() -> None:
    samples = [_sample(1, 1.0), _sample(2, -1.0)]
    exact = np.zeros(3, dtype=np.float32)
    exact[1:] = [-1.0, 1.0]
    arms, contract = M15C2.build_target_arms(
        samples,
        conditional_predictions=np.asarray([0.6, -0.2]),
        shuffled_predictions=np.asarray([-0.2, 0.6]),
        exact_values=exact,
    )
    assert [row.value_target for row in arms["OUTCOME"]] == [1.0, -1.0]
    assert [row.value_target for row in arms["CONTEXT_20"]] == pytest.approx(
        [0.92, -0.84]
    )
    assert [row.value_target for row in arms["CONTEXT_30"]] == pytest.approx(
        [0.88, -0.76]
    )
    assert [row.value_target for row in arms["CONTEXT_40"]] == pytest.approx(
        [0.84, -0.68]
    )
    assert [
        row.value_target for row in arms["SHUFFLED_CONTEXT_30"]
    ] == pytest.approx([0.64, -0.52])
    assert len(set(contract["structure_fingerprints"].values())) == 1
    for arm in M15C2.ARM_ORDER:
        assert arms[arm][0].policy_target is samples[0].policy_target
        assert arms[arm][0].selected_action == samples[0].selected_action


def test_m15c2_static_pass_is_not_overwritten_by_inconclusive_strength() -> None:
    result = M15C2.build_recommendation(
        _static((0.004, 0.002, 0.006), (0.003, 0.001, 0.005)),
        _arena((0.001, -0.002, 0.004), (0.002, -0.001, 0.005)),
    )
    assert result["status"] == "PASS"
    assert result["mechanism_status"] == "PASS"
    assert result["operational_status"] == "PASS"
    assert result["strength_status"] == "INCONCLUSIVE"
    assert result["decision"] == "prepare_independent_strength_replication"
    assert result["minimum_effect_floor"] == 0.0


def test_m15c2_strength_pass_is_reported_separately() -> None:
    result = M15C2.build_recommendation(
        _static((0.004, 0.002, 0.006), (0.003, 0.001, 0.005)),
        _arena((0.003, 0.001, 0.005), (0.002, 0.0005, 0.0035)),
    )
    assert result["status"] == "PASS"
    assert result["strength_status"] == "PASS"
    assert result["decision"] == "prepare_independent_static_and_strength_replication"
    assert result["promotable"] is False


def test_m15c2_exploratory_doses_cannot_rescue_failed_primary() -> None:
    result = M15C2.build_recommendation(
        _static((-0.001, -0.003, 0.0), (0.003, 0.001, 0.005)),
        _arena((0.002, -0.001, 0.005), (0.002, -0.001, 0.005)),
    )
    assert result["status"] == "FAIL"
    assert result["finding"] == "primary_interior_conditional_dose_has_no_positive_static_signal"
    assert result["exploratory_doses_can_rescue_primary"] is False


def test_m15c2_is_inconclusive_when_primary_interval_crosses_zero() -> None:
    result = M15C2.build_recommendation(
        _static((0.002, -0.001, 0.005), (0.003, 0.001, 0.005)),
        _arena((0.002, -0.001, 0.005), (0.002, -0.001, 0.005)),
    )
    assert result["status"] == "INCONCLUSIVE"
    assert result["decision"] == "power_size_fresh_M15C2_replication"


def test_m15c2_result_write_read_round_trip_preserves_verdict(tmp_path: Path) -> None:
    result = {
        "schema": M15C2.SCHEMA,
        "milestone": "M15-C2",
        "status": "PASS",
        "result_hash": "fixture-hash",
        "recommendation": {"finding": "fixture-finding"},
    }
    run_dir = tmp_path / "run"
    compact = tmp_path / "result.full.json"
    M15C2._write_outputs(result, run_dir, compact)
    assert (run_dir / "result.json").read_bytes() == compact.read_bytes()
