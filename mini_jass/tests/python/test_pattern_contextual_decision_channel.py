"""Contracts for M15-C6 separate contextual decision channels."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

from mini_jass_lab.replay import ReplaySample  # noqa: E402
from run_pattern_contextual_decision_channel import (  # noqa: E402
    ARM_ORDER,
    MATCHUPS,
    _recommendation,
    _resolve,
    _write_json_roundtrip,
    build_training_targets,
    calibrate_delta,
)
import run_pattern_contextual_decision_channel as m15c6  # noqa: E402


def _sample(state: int, value: float, ply: int) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[ply] = 1.0
    return ReplaySample(
        state_id=state,
        value_target=value,
        policy_target=policy,
        generation=1,
        game_id=10 + ply // 2,
        ply=ply,
        selected_action=ply,
    )


def test_preregistered_config_is_fail_closed() -> None:
    root = Path(__file__).resolve().parents[2]
    config, loop = _resolve(
        root / "configs" / "l1_pattern_contextual_decision_channel.yaml"
    )
    assert tuple(config["arms"]) == ARM_ORDER
    assert tuple(config["strength_arena"]["matchups"]) == MATCHUPS
    assert config["scientific_gate"]["minimum_effect_floor"] == 0.0
    assert config["scientific_gate"]["static_diagnostics_cannot_rescue_strength_failure"]
    assert loop["model"]["architecture"] == "folded_pattern_value"


def test_context_heads_remain_separate_from_temporal_value() -> None:
    outcome = [
        _sample(0, 1.0, 0),
        _sample(1, -1.0, 1),
        _sample(2, 0.0, 2),
        _sample(3, 1.0, 3),
    ]
    temporal_values = np.asarray([0.4, -0.2, 0.1, 0.6])
    temporal = [
        replace(sample, value_target=float(value))
        for sample, value in zip(outcome, temporal_values, strict=True)
    ]
    aligned = np.asarray([0.7, -0.5, 0.2, 0.8])
    shuffled = np.asarray([-0.5, 0.8, 0.7, 0.2])
    exact = np.asarray([1.0, -1.0, 0.0, 1.0])
    tables, contract = build_training_targets(
        outcome, temporal, aligned, shuffled, exact
    )

    assert np.allclose(
        [row.value_target for row in tables["LAMBDA_50"]], temporal_values
    )
    assert np.allclose(
        [row.value_target for row in tables["ALIGNED_CONTEXT_HEAD"]], aligned
    )
    assert np.allclose(
        [row.value_target for row in tables["SHUFFLED_CONTEXT_HEAD"]], shuffled
    )
    assert np.allclose(
        [row.value_target for row in tables["CONTEXT_30"]],
        0.70 * np.asarray([1.0, -1.0, 0.0, 1.0]) + 0.30 * aligned,
    )
    assert contract["scalar_temporal_context_blend_for_candidate"] is False
    assert len(set(contract["structure_fingerprints"].values())) == 1


def test_delta_calibration_filters_single_action_states_before_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Graph:
        @staticmethod
        def terminal_value(state: int) -> None:
            return None

        @staticmethod
        def legal_actions(state: int) -> list[int]:
            return [0] if state in {0, 2, 4} else [0, 1]

    seen: list[int] = []

    def fake_search(graph, model, state, config, cache):
        seen.append(state)
        return SimpleNamespace(action_scores={0: 0.5, 1: 0.25})

    monkeypatch.setattr(m15c6, "bounded_negamax", fake_search)
    samples = [_sample(state, 1.0, state) for state in range(6)]
    result = calibrate_delta(
        Graph(),
        object(),
        samples,
        object(),
        seed=17,
        spec={
            "calibration_state_count": 3,
            "calibration_seed_offset": 100,
            "minimum_valid_calibration_states": 3,
            "calibration_quantile": 0.25,
        },
    )

    assert sorted(seen) == [1, 3, 5]
    assert result["valid_gap_count"] == 3
    assert result["cohort"].endswith("with_at_least_two_legal_actions")


def test_strength_gate_requires_both_primary_contrasts() -> None:
    def interval(lower: float, upper: float, center: float) -> dict[str, float]:
        return {"lower": lower, "upper": upper, "mean": center}

    passing = {
        "arena_strength": {
            "ALIGNED_VS_SHUFFLED": interval(0.0001, 0.0020, 0.0010),
            "ALIGNED_VS_LAMBDA_50": interval(0.0002, 0.0022, 0.0011),
        }
    }
    assert _recommendation(passing)["status"] == "PASS"

    inconclusive = {
        "arena_strength": {
            "ALIGNED_VS_SHUFFLED": interval(-0.0001, 0.0020, 0.0009),
            "ALIGNED_VS_LAMBDA_50": interval(0.0002, 0.0022, 0.0011),
        },
        "static_diagnostics": {"irrelevant_positive": 1.0},
    }
    verdict = _recommendation(inconclusive)
    assert verdict["status"] == "INCONCLUSIVE"
    assert verdict["static_diagnostics_can_rescue"] is False

    failing = {
        "arena_strength": {
            "ALIGNED_VS_SHUFFLED": interval(-0.0020, -0.0001, -0.0010),
            "ALIGNED_VS_LAMBDA_50": interval(0.0002, 0.0022, 0.0011),
        }
    }
    assert _recommendation(failing)["status"] == "FAIL"


def test_reporting_roundtrip_reads_what_it_writes(tmp_path: Path) -> None:
    payload = {"schema": "test", "n": 24, "status": "PASS"}
    output = tmp_path / "summary.json"
    _write_json_roundtrip(payload, [output])
    assert output.read_text(encoding="utf-8").endswith("\n")


def test_home_wrapper_reuses_persistent_torch_and_fails_closed() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (
        root / "jobs" / "run_pattern_contextual_decision_channel_home.sh"
    ).read_text(encoding="utf-8")
    assert "mj-m15p-venv" in script
    assert "pip install" not in script
    assert "never reinstalls PyTorch" in script
    assert "timeout -k 60s" in script
    assert "n=0 is a hard failure" in script
    assert "scientific-summary.json exceeds 64 KiB" in script
    assert ") >/dev/null 2>&1 &" in script
