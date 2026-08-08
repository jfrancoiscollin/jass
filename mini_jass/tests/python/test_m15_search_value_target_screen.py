"""Focused guards for the M15 search-derived value-target screen."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from mini_jass_lab.replay import ReplaySample
from mini_jass_lab.selfplay import GenerationResult


_TOOL = Path(__file__).resolve().parents[2] / "tools" / "run_m15_search_value_target_screen.py"
_SPEC = importlib.util.spec_from_file_location("run_m15", _TOOL)
assert _SPEC and _SPEC.loader
M15 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M15)


def _sample(game_id: int, ply: int, outcome: float) -> ReplaySample:
    return ReplaySample(
        state_id=17 + ply,
        value_target=outcome,
        policy_target=np.asarray([0.2, 0.3, 0.5], dtype=np.float32),
        generation=1,
        game_id=game_id,
        ply=ply,
    )


def _fake_generation() -> GenerationResult:
    samples = [_sample(2, 0, -1.0), _sample(2, 1, 1.0)]
    return GenerationResult(
        samples=samples,
        metrics={
            "search_trace": [
                {"game_id": 2, "ply": 0, "root_score": 0.60},
                {"game_id": 2, "ply": 1, "root_score": -0.20},
            ]
        },
        coverage={"unique_states": 2},
    )


def test_search_root_score_changes_only_value_target():
    source = _fake_generation()
    original_policy = [sample.policy_target.copy() for sample in source.samples]

    def original(*_args, **_kwargs):
        return source

    wrapped = M15._search_targeted_generation(original, "search_root_score", 1.0)
    result = wrapped()
    assert [sample.value_target for sample in result.samples] == pytest.approx([0.60, -0.20])
    assert [sample.state_id for sample in result.samples] == [17, 18]
    assert [sample.game_id for sample in result.samples] == [2, 2]
    assert [sample.ply for sample in result.samples] == [0, 1]
    for rebuilt, policy in zip(result.samples, original_policy, strict=True):
        np.testing.assert_array_equal(rebuilt.policy_target, policy)
    # Source samples remain the honest terminal-outcome labels.
    assert [sample.value_target for sample in source.samples] == [-1.0, 1.0]


def test_blend_is_exactly_half_search_half_outcome():
    def original(*_args, **_kwargs):
        return _fake_generation()

    wrapped = M15._search_targeted_generation(original, "outcome_search_blend", 0.50)
    result = wrapped()
    assert [sample.value_target for sample in result.samples] == pytest.approx([-0.20, 0.40])


def test_search_target_is_clipped_to_wdl_range():
    generated = _fake_generation()
    generated.metrics["search_trace"][0]["root_score"] = 3.0

    def original(*_args, **_kwargs):
        return generated

    wrapped = M15._search_targeted_generation(original, "search_root_score", 1.0)
    assert wrapped().samples[0].value_target == 1.0


def test_missing_trace_row_fails_closed():
    generated = _fake_generation()
    generated.metrics["search_trace"] = generated.metrics["search_trace"][:1]

    def original(*_args, **_kwargs):
        return generated

    wrapped = M15._search_targeted_generation(original, "search_root_score", 1.0)
    with pytest.raises(ValueError, match="missing root score"):
        wrapped()


def test_unknown_search_target_fails_closed():
    def original(*_args, **_kwargs):
        return _fake_generation()

    wrapped = M15._search_targeted_generation(original, "mystery", 1.0)
    with pytest.raises(ValueError, match="unknown M15 search target"):
        wrapped()


def test_m15_preregistration_is_exactly_four_arms_and_twenty_seeds():
    config = M15._resolve_config(
        Path(__file__).resolve().parents[2] / "configs" / "l2_search_value_target_screen.yaml"
    )
    assert config["paired_seeds"] == list(range(132001, 132021))
    assert config["arms"] == M15.EXPECTED_ARMS
    assert config["contracts"]["one_generation_only"] is True
    assert config["contracts"]["production_jass_changes_authorized"] is False
    assert config["contracts"]["direct_10x10_transfer_authorized"] is False


def test_policy_shift_gate_is_frozen_at_half_percent_point():
    config = M15._resolve_config(
        Path(__file__).resolve().parents[2] / "configs" / "l2_search_value_target_screen.yaml"
    )
    assert config["success_rule"]["maximum_absolute_policy_mass_delta"] == 0.005
    assert config["success_rule"]["minimum_oracle_gain_recovery_fraction"] == 0.50
