"""Contracts for direct conditional-information injection into M15-C targets."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from mini_jass_lab.replay import ReplaySample

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_pattern_conditional_target_screen.py"
SPEC = importlib.util.spec_from_file_location("run_pattern_m15c", TOOL)
assert SPEC and SPEC.loader
M15C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M15C)


def _sample(game: int, outcome: float) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[3] = 1.0
    return ReplaySample(game, outcome, policy, 1, game, 0, 3)


def _interval(mean: float, lower: float, upper: float) -> dict[str, float]:
    return {"mean": mean, "lower": lower, "upper": upper}


def _contrasts(
    attribution: tuple[float, float, float],
    operational: tuple[float, float, float],
) -> dict[str, object]:
    return {
        "attribution_conditional_vs_shuffled": {
            "zero_regret_gain": _interval(*attribution)
        },
        "operational_conditional_vs_outcome": {
            "zero_regret_gain": _interval(*operational)
        },
    }


GATE = {"minimum_operational_gain": 0.004}


def test_m15c_config_freezes_causal_control_fresh_seeds_and_no_test_read() -> None:
    config, loop = M15C._resolve(
        ROOT / "configs" / "l1_pattern_conditional_target_screen.yaml"
    )
    assert config["paired_seeds"] == list(range(272001, 272021))
    assert loop["model"]["architecture"] == "folded_pattern_value"
    assert config["conditional_mapping"]["fold_unit"] == "complete_game"
    assert config["conditional_mapping"]["initialization"] == "zero"
    assert (
        config["conditional_mapping"]["shuffle_control"]
        == "within_fold_hash_order_rotate_one_v1"
    )
    assert (
        config["targets"]["GLOBAL_BLEND_50"]["control_role"]
        == "matched_state_blind_shrinkage"
    )
    assert (
        config["targets"]["SHUFFLED_CONTEXT_BLEND_50"]["control_role"]
        == "marginal_matched_broken_state_alignment"
    )
    assert config["scientific_gate"]["require_both_contrasts_ci_above_zero"] is True
    assert M15C.estimate_power(config["power_sizing"]) == pytest.approx(0.91149)
    assert config["boundaries"]["additional_frozen_test_reads_authorized"] == 0
    assert config["boundaries"]["scientific_dependency_on_m15p_result"] == "none"


def test_m15c_changes_only_value_target_with_matched_smoothing() -> None:
    samples = [_sample(1, 1.0), _sample(2, -1.0)]
    exact = np.zeros(3, dtype=np.float32)
    exact[1:] = [-1.0, 1.0]
    arms, contract = M15C.build_target_arms(
        samples,
        conditional_predictions=np.asarray([0.6, -0.2]),
        shuffled_conditional_predictions=np.asarray([-0.2, 0.6]),
        state_blind_predictions=np.asarray([0.1, 0.1]),
        exact_values=exact,
    )
    assert [row.value_target for row in arms["OUTCOME"]] == [1.0, -1.0]
    assert [
        row.value_target for row in arms["GLOBAL_BLEND_50"]
    ] == pytest.approx([0.55, -0.45])
    assert [
        row.value_target for row in arms["SHUFFLED_CONTEXT_BLEND_50"]
    ] == pytest.approx([0.4, -0.2])
    assert [
        row.value_target for row in arms["CONTEXT_BLEND_50"]
    ] == pytest.approx([0.8, -0.6])
    assert [row.value_target for row in arms["CONTEXT_ONLY"]] == pytest.approx(
        [0.6, -0.2]
    )
    assert len(set(contract["structure_fingerprints"].values())) == 1
    for arm in M15C.ARM_ORDER:
        assert arms[arm][0].policy_target is samples[0].policy_target
        assert arms[arm][0].selected_action == samples[0].selected_action


def test_m15c_pass_requires_attribution_and_operational_gain() -> None:
    result = M15C.build_recommendation(
        _contrasts((0.005, 0.001, 0.009), (0.006, 0.001, 0.011)), GATE
    )
    assert result["status"] == "PASS"
    assert result["decision"] == "replicate_CONTEXT_BLEND_50_strength_on_fresh_seeds"
    assert result["promotable"] is False


def test_m15c_fails_if_conditioning_does_not_beat_matched_global_smoothing() -> None:
    result = M15C.build_recommendation(
        _contrasts((-0.002, -0.004, 0.0), (0.006, 0.002, 0.010)), GATE
    )
    assert result["status"] == "FAIL"
    assert result["finding"] == "aligned_context_does_not_beat_marginal_matched_shuffle"
    assert result["context_only_can_rescue_primary"] is False


def test_m15c_is_inconclusive_when_effect_can_still_reach_threshold() -> None:
    result = M15C.build_recommendation(
        _contrasts((0.002, -0.001, 0.005), (0.004, -0.001, 0.009)), GATE
    )
    assert result["status"] == "INCONCLUSIVE"


def test_m15c_result_write_read_round_trip_preserves_verdict(tmp_path: Path) -> None:
    result = {
        "schema": M15C.SCHEMA,
        "milestone": "M15-C",
        "status": "PASS",
        "result_hash": "fixture-hash",
        "recommendation": {"finding": "fixture-finding"},
    }
    run_dir = tmp_path / "run"
    compact = tmp_path / "result.full.json"
    M15C._write_outputs(result, run_dir, compact)
    assert (run_dir / "result.json").read_bytes() == compact.read_bytes()
