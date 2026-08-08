"""Focused guards for the M16 temporal value-target screen."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from mini_jass_lab.replay import ReplaySample
from mini_jass_lab.selfplay import GenerationResult


_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "run_m16_temporal_value_target_screen.py"
_SPEC = importlib.util.spec_from_file_location("run_m16", _TOOL)
assert _SPEC and _SPEC.loader
M16 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M16)


def _sample(game_id: int, ply: int, outcome: float) -> ReplaySample:
    return ReplaySample(
        state_id=20 + ply,
        value_target=outcome,
        policy_target=np.asarray([0.2, 0.3, 0.5], dtype=np.float32),
        generation=1,
        game_id=game_id,
        ply=ply,
    )


def _fake_generation() -> GenerationResult:
    # Final outcomes alternate by side to move: -1, +1, -1.
    samples = [
        _sample(2, 0, -1.0),
        _sample(2, 1, +1.0),
        _sample(2, 2, -1.0),
    ]
    return GenerationResult(
        samples=samples,
        metrics={
            "search_trace": [
                {"game_id": 2, "ply": 0, "root_score": +0.60},
                {"game_id": 2, "ply": 1, "root_score": -0.20},
                {"game_id": 2, "ply": 2, "root_score": +0.40},
            ]
        },
        coverage={"unique_states": 3},
    )


def test_next_search_reprojects_successor_score_across_turn() -> None:
    source = _fake_generation()
    original_policy = [sample.policy_target.copy() for sample in source.samples]

    def original(*_args, **_kwargs):
        return source

    wrapped = M16._temporal_targeted_generation(original, 0.0)
    result = wrapped()

    # t0 <- -score(t1) = +0.2 ; t1 <- -score(t2) = -0.4 ;
    # last sample falls back to its honest terminal outcome.
    assert [sample.value_target for sample in result.samples] == pytest.approx(
        [+0.20, -0.40, -1.0]
    )
    for rebuilt, policy in zip(result.samples, original_policy, strict=True):
        np.testing.assert_array_equal(rebuilt.policy_target, policy)
    assert [sample.state_id for sample in result.samples] == [20, 21, 22]
    assert [sample.game_id for sample in result.samples] == [2, 2, 2]
    assert [sample.ply for sample in result.samples] == [0, 1, 2]

    # The wrapper must not mutate the honest source samples.
    assert [sample.value_target for sample in source.samples] == [-1.0, +1.0, -1.0]


def test_lambda_half_matches_the_backward_temporal_recurrence() -> None:
    def original(*_args, **_kwargs):
        return _fake_generation()

    result = M16._temporal_targeted_generation(original, 0.5)()
    # g2=-1
    # g1=-[(1-.5)*0.4 + .5*(-1)] = +0.3
    # g0=-[(1-.5)*(-.2) + .5*(+.3)] = -0.05
    assert [sample.value_target for sample in result.samples] == pytest.approx(
        [-0.05, +0.30, -1.0]
    )


def test_lambda_eighty_keeps_more_terminal_outcome_mass() -> None:
    def original(*_args, **_kwargs):
        return _fake_generation()

    result = M16._temporal_targeted_generation(original, 0.8)()
    assert [sample.value_target for sample in result.samples] == pytest.approx(
        [-0.536, +0.72, -1.0]
    )


def test_single_sample_game_uses_terminal_outcome() -> None:
    generated = GenerationResult(
        samples=[_sample(7, 0, +1.0)],
        metrics={
            "search_trace": [
                {"game_id": 7, "ply": 0, "root_score": -0.75},
            ]
        },
        coverage={},
    )

    result = M16._temporal_targeted_generation(lambda: generated, 0.5)()
    assert result.samples[0].value_target == 1.0


def test_search_scores_are_clipped_before_bootstrap() -> None:
    generated = _fake_generation()
    generated.metrics["search_trace"][1]["root_score"] = -3.0

    result = M16._temporal_targeted_generation(lambda: generated, 0.0)()
    assert result.samples[0].value_target == 1.0


def test_missing_successor_trace_fails_closed() -> None:
    generated = _fake_generation()
    generated.metrics["search_trace"] = generated.metrics["search_trace"][:2]

    with pytest.raises(ValueError, match="missing root score"):
        M16._temporal_targeted_generation(lambda: generated, 0.5)()


def test_duplicate_trace_row_fails_closed() -> None:
    generated = _fake_generation()
    generated.metrics["search_trace"].append(
        {"game_id": 2, "ply": 1, "root_score": 0.0}
    )

    with pytest.raises(ValueError, match="duplicate root score"):
        M16._temporal_targeted_generation(lambda: generated, 0.5)()


def test_non_contiguous_samples_fail_closed() -> None:
    generated = _fake_generation()
    generated.samples.pop(1)

    with pytest.raises(ValueError, match="contiguous"):
        M16._temporal_targeted_generation(lambda: generated, 0.5)()


@pytest.mark.parametrize("bad_lambda", [-0.01, 1.0, 1.01])
def test_invalid_lambda_is_rejected(bad_lambda: float) -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\)"):
        M16._temporal_targeted_generation(lambda: _fake_generation(), bad_lambda)


def test_m16_preregistration_is_exactly_five_arms_and_twenty_seeds() -> None:
    config = M16._resolve_config(
        _ROOT / "configs" / "l2_temporal_value_target_screen.yaml"
    )
    assert config["paired_seeds"] == list(range(132001, 132021))
    assert config["arms"] == M16.EXPECTED_ARMS
    assert config["contracts"]["one_generation_only"] is True
    assert config["contracts"]["temporal_targets_use_oracle"] is False
    assert config["contracts"]["production_jass_changes_authorized"] is False
    assert config["contracts"]["direct_10x10_transfer_authorized"] is False


def test_m16_is_bound_to_the_retained_m15_failure() -> None:
    config = M16._resolve_config(
        _ROOT / "configs" / "l2_temporal_value_target_screen.yaml"
    )
    evidence = config["m15_evidence_resolved"]
    assert evidence["result_hash"] == (
        "03f15b12a22ca27536efae5342dcc5d862f64a769c2a5afbf77e15a4c99d69b8"
    )
    assert evidence["status"] == "FAIL"
    assert evidence["selected_mechanism"] is None
    assert evidence["candidates"]["blend"]["oracle_gain_recovery_fraction"] < 0.50


def test_m16_success_gate_requires_paired_confidence_and_half_oracle_gain() -> None:
    config = M16._resolve_config(
        _ROOT / "configs" / "l2_temporal_value_target_screen.yaml"
    )
    rule = config["success_rule"]
    assert rule["minimum_oracle_gain_recovery_fraction"] == 0.50
    assert rule["require_paired_value_gain_confidence_95_above_zero"] is True
    assert rule["maximum_absolute_policy_mass_delta"] == 0.005
    assert rule["paired_confidence_critical_95"] == pytest.approx(
        2.093024054408263
    )
