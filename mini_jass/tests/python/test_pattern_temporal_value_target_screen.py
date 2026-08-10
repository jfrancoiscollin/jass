"""Contracts for the architecture-correct M16-P temporal target screen."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from mini_jass_lab.replay import ReplaySample

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_pattern_temporal_value_target_screen.py"
SPEC = importlib.util.spec_from_file_location("run_pattern_m16p", TOOL)
assert SPEC and SPEC.loader
M16P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M16P)


def _sample(game: int, ply: int, state: int, outcome: float) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[3] = 1.0
    return ReplaySample(state, outcome, policy, 1, game, ply, 3)


def _trace(game: int, ply: int, state: int, score: float) -> dict[str, object]:
    return {
        "game_id": game,
        "ply": ply,
        "state_id": state,
        "selected_action": 3,
        "root_score": score,
    }


def _interval(mean: float, lower: float, upper: float) -> dict[str, float]:
    return {"mean": mean, "lower": lower, "upper": upper}


def _contrasts(
    primary: tuple[float, float, float],
    oracle: tuple[float, float, float],
) -> dict[str, object]:
    return {
        "primary_lambda_50": {"zero_regret_gain": _interval(*primary)},
        "oracle_gap": {"zero_regret_gain": _interval(*oracle)},
    }


GATE = {
    "minimum_absolute_response_gain": 0.006,
    "minimum_oracle_gain_recovery_fraction": 0.5,
}


def test_m16p_config_freezes_pattern_architecture_fresh_seeds_and_home() -> None:
    config, loop = M16P._resolve(
        ROOT / "configs" / "l1_pattern_temporal_value_target_screen.yaml"
    )
    assert config["paired_seeds"] == list(range(274001, 274021))
    assert config["expected_execution_host"] == "User"
    assert loop["model"]["architecture"] == "folded_pattern_value"
    assert loop["training"]["policy_weight"] == 0.0
    assert config["scientific_gate"]["primary_contrast"] == "LAMBDA_50_minus_OUTCOME"
    assert config["scientific_gate"]["exploratory_arms_cannot_rescue_primary"]
    assert M16P.estimate_power(config["power_sizing"]) == pytest.approx(0.99944)
    assert config["probe"]["seed"] == 274000
    assert config["probe"]["overlaps_scientific_seeds"] is False
    assert config["boundaries"]["additional_frozen_test_reads_authorized"] == 0


def test_m16p_builds_temporal_returns_before_train_filter() -> None:
    samples = [
        _sample(1, 0, 7, 1.0),
        _sample(1, 1, 8, -1.0),
        _sample(1, 2, 9, 1.0),
    ]
    traces = [
        _trace(1, 0, 7, 0.2),
        _trace(1, 1, 8, -0.4),
        _trace(1, 2, 9, 0.6),
    ]
    train_mask = np.zeros(16, dtype=np.bool_)
    train_mask[[7, 9]] = True
    exact = np.zeros(16, dtype=np.float32)
    exact[7] = -1.0
    exact[9] = 1.0
    arms, contract = M16P.build_target_arms(samples, traces, exact, train_mask)

    assert [row.state_id for row in arms["OUTCOME"]] == [7, 9]
    assert [row.value_target for row in arms["NEXT_SEARCH"]] == pytest.approx(
        [0.4, 1.0]
    )
    assert [row.value_target for row in arms["LAMBDA_50"]] == pytest.approx(
        [0.6, 1.0]
    )
    assert [row.value_target for row in arms["LAMBDA_80"]] == pytest.approx(
        [0.816, 1.0]
    )
    assert [row.value_target for row in arms["EXACT_ORACLE"]] == [-1.0, 1.0]
    assert contract["raw_generated_sample_count"] == 3
    assert contract["train_sample_count"] == 2
    assert contract["temporal_returns_built_before_train_row_filter"] is True
    assert contract["temporal_bootstrap_row_count"] == 2
    assert len(set(contract["structure_fingerprints"].values())) == 1


def test_m16p_rejects_noncontiguous_games_and_trace_identity_drift() -> None:
    samples = [_sample(1, 0, 7, 1.0), _sample(1, 2, 8, -1.0)]
    traces = [_trace(1, 0, 7, 0.2), _trace(1, 2, 8, -0.4)]
    mask = np.ones(16, dtype=np.bool_)
    with pytest.raises(ValueError, match="contiguous"):
        M16P.build_target_arms(samples, traces, np.zeros(16), mask)

    samples = [_sample(1, 0, 7, 1.0)]
    bad = [_trace(1, 0, 8, 0.2)]
    with pytest.raises(ValueError, match="identity mismatch"):
        M16P.build_target_arms(samples, bad, np.zeros(16), mask)


def test_m16p_pass_requires_positive_ci_and_half_oracle_recovery() -> None:
    result = M16P.build_recommendation(
        _contrasts((0.007, 0.002, 0.012), (0.012, 0.009, 0.015)), GATE
    )
    assert result["status"] == "PASS"
    assert result["decision"] == "replicate_LAMBDA_50_strength_on_fresh_seeds"
    assert result["exploratory_arms_can_rescue_primary"] is False
    assert result["promotable"] is False


def test_m16p_fails_when_primary_precisely_excludes_required_recovery() -> None:
    result = M16P.build_recommendation(
        _contrasts((0.002, 0.001, 0.004), (0.012, 0.009, 0.015)), GATE
    )
    assert result["status"] == "FAIL"
    assert result["finding"] == "lambda_50_excludes_practical_temporal_recovery"
    assert result["decision"] == "close_M16P_temporal_target_axis"


def test_m16p_is_inconclusive_when_primary_can_still_reach_gate() -> None:
    result = M16P.build_recommendation(
        _contrasts((0.005, -0.001, 0.011), (0.012, 0.009, 0.015)), GATE
    )
    assert result["status"] == "INCONCLUSIVE"
    assert result["decision"] == "power_size_fresh_M16P_replication"


def test_m16p_probe_roundtrip_publishes_no_scientific_metrics(tmp_path: Path) -> None:
    probe = {
        "schema": M16P.PROBE_SCHEMA,
        "milestone": "M16-P-PROBE",
        "status": "PROBE_ONLY",
        "scientific_metrics_published": False,
        "result_hash": "probe-hash",
    }
    first = tmp_path / "probe.json"
    second = tmp_path / "copy.json"
    M16P._write_json_roundtrip(probe, [first, second])
    assert first.read_bytes() == second.read_bytes()
    assert "aggregate" not in M16P.json.loads(first.read_text(encoding="utf-8"))


def test_m16p_result_write_read_round_trip_preserves_verdict(tmp_path: Path) -> None:
    result = {
        "schema": M16P.SCHEMA,
        "milestone": "M16-P",
        "status": "PASS",
        "result_hash": "fixture-hash",
        "recommendation": {"finding": "fixture-finding"},
    }
    run_dir = tmp_path / "run"
    compact = tmp_path / "result.full.json"
    M16P._write_outputs(result, run_dir, compact)
    assert (run_dir / "result.json").read_bytes() == compact.read_bytes()
