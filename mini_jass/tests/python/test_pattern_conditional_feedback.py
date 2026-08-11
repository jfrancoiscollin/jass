"""Contracts for M15-C5 conditional on-policy feedback."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_pattern_conditional_feedback.py"
SPEC = importlib.util.spec_from_file_location("run_pattern_conditional_feedback", TOOL)
assert SPEC is not None and SPEC.loader is not None
M15C5 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M15C5)

from mini_jass_lab.replay import ReplaySample  # noqa: E402


def _sample(index: int, value: float) -> ReplaySample:
    return ReplaySample(
        state_id=index,
        value_target=value,
        policy_target=np.asarray([1.0, 0.0], dtype=np.float32),
        generation=1,
        game_id=index // 2,
        ply=index % 2,
        selected_action=0,
    )


def _interval(mean: float, lower: float, upper: float) -> dict:
    return {
        "count": 24,
        "mean": mean,
        "lower": lower,
        "upper": upper,
        "standard_error": 0.001,
    }


def test_config_freezes_home_feedback_and_sealed_cohort() -> None:
    path = ROOT / "configs" / "l1_pattern_conditional_feedback.yaml"
    config, loop = M15C5._resolve(path)
    assert config["expected_execution_host"] == "User"
    assert config["paired_seeds"] == list(range(278001, 278025))
    assert config["feedback"]["alpha"] == pytest.approx(0.30)
    assert config["feedback"]["g1_shared_replay"] is True
    assert config["feedback"]["g2_each_primary_arm_generates_own_replay"] is True
    assert config["feedback"]["decomposition_starts_from_context_g1"] is True
    assert config["feedback"]["extra_inference_parameters"] == 0
    assert config["scientific_gate"]["minimum_effect_floor"] == 0.0
    assert config["boundaries"]["cohorts_never_read_by_this_cell"] == ["frozen_test"]
    assert config["boundaries"]["additional_frozen_test_reads_authorized"] == 0
    assert loop["model"]["architecture"] == "folded_pattern_value"
    assert loop["training"]["policy_weight"] == 0.0


def test_context_target_changes_only_value_and_uses_retained_alpha() -> None:
    samples = [_sample(0, 1.0), _sample(1, -1.0), _sample(2, 0.0)]
    predictions = np.asarray([0.2, -0.4, 0.6])
    rows = M15C5.build_context_target(samples, predictions, 0.30)
    np.testing.assert_allclose(
        [row.value_target for row in rows],
        [0.76, -0.82, 0.18],
        rtol=0.0,
        atol=1e-15,
    )
    assert [row.state_id for row in rows] == [row.state_id for row in samples]
    assert [row.game_id for row in rows] == [row.game_id for row in samples]
    assert all(row.policy_target is sample.policy_target for row, sample in zip(rows, samples))


def test_primary_gate_has_no_effect_floor_and_requires_both_axes() -> None:
    base = {
        "g2_on_policy_context_effect": {
            "zero_regret_rate": _interval(0.0002, 0.00001, 0.00039),
            "arena_score_minus_half": _interval(0.0001, 0.00001, 0.00019),
        }
    }
    passed = M15C5.build_recommendation(base)
    assert passed["status"] == "PASS"
    assert passed["minimum_effect_floor"] == 0.0

    base["g2_on_policy_context_effect"]["arena_score_minus_half"] = _interval(
        0.0001, -0.0001, 0.0003
    )
    assert M15C5.build_recommendation(base)["status"] == "INCONCLUSIVE"
    base["g2_on_policy_context_effect"]["zero_regret_rate"] = _interval(
        -0.0002, -0.0003, -0.0001
    )
    assert M15C5.build_recommendation(base)["status"] == "FAIL"


def test_contrast_change_is_difference_in_differences() -> None:
    arms = {
        "OUTCOME_G1": {"zero_regret_rate": 0.50, "value_sign_accuracy": 0.50},
        "CONTEXT_30_G1": {"zero_regret_rate": 0.51, "value_sign_accuracy": 0.52},
        "OUTCOME_G2": {"zero_regret_rate": 0.53, "value_sign_accuracy": 0.54},
        "CONTEXT_30_G2_OWN_REPLAY": {
            "zero_regret_rate": 0.55,
            "value_sign_accuracy": 0.57,
        },
        "CONTEXT_30_G2_ON_OUTCOME_REPLAY": {
            "zero_regret_rate": 0.54,
            "value_sign_accuracy": 0.55,
        },
    }
    arenas = {
        "g1_context_effect": {"score_minus_half": 0.01},
        "g2_on_policy_context_effect": {"score_minus_half": 0.03},
        "g2_feedback_distribution_effect": {"score_minus_half": 0.02},
    }
    contrasts = M15C5.build_contrasts(
        [{"arms": arms, "arenas": arenas}, {"arms": arms, "arenas": arenas}],
        1.0,
    )
    change = contrasts["g2_minus_g1_context_effect"]
    assert change["zero_regret_rate"]["mean"] == pytest.approx(0.01)
    assert change["value_sign_accuracy"]["mean"] == pytest.approx(0.01)
    assert change["arena_score_minus_half"]["mean"] == pytest.approx(0.02)


def test_home_wrapper_reuses_persistent_torch_and_has_job_guards() -> None:
    wrapper = (ROOT / "jobs" / "run_pattern_conditional_feedback_home.sh").read_text(
        encoding="utf-8"
    )
    assert "hostname" in wrapper and "nproc" in wrapper
    assert "/home/jf/.cache/mj-m15p-venv" in wrapper
    assert "pip install" not in wrapper
    assert "disk guard" in wrapper
    assert "PROGRESS.json" in wrapper
    assert "n=0 is a hard failure" in wrapper
    assert "scientific-summary.json exceeds 64 KiB" in wrapper
    assert (
        'oracle="$repo/mini_jass/artefacts/'
        'oracle.l1.pattern-m15c5-$job_id.jsonl"' in wrapper
    )
    assert 'oracle="$work/oracle.l1.jsonl"' not in wrapper


def test_yaml_declares_probe_timing_only() -> None:
    config = yaml.safe_load(
        (ROOT / "configs" / "l1_pattern_conditional_feedback.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert config["probe"]["seed"] == 278000
    assert config["probe"]["expected_nproc"] == 16
    assert config["probe"]["scientific_metrics_must_not_be_published"] is True
