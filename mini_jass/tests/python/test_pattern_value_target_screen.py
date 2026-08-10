"""Contracts for the architecture-correct M15-P value-target screen."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from mini_jass_lab.replay import ReplaySample

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_pattern_value_target_screen.py"
SPEC = importlib.util.spec_from_file_location("run_pattern_m15p", TOOL)
assert SPEC and SPEC.loader
M15P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M15P)


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


GATE = {
    "minimum_absolute_response_gain": 0.004,
    "minimum_oracle_gain_recovery_fraction": 0.5,
}


def _contrasts(
    primary: tuple[float, float, float],
    oracle: tuple[float, float, float],
    search: tuple[float, float, float] = (0.0, -0.01, 0.01),
) -> dict[str, object]:
    return {
        "primary_blend": {"zero_regret_gain": _interval(*primary)},
        "mechanistic_search": {"zero_regret_gain": _interval(*search)},
        "oracle_gap": {"zero_regret_gain": _interval(*oracle)},
    }


def test_m15p_config_freezes_fresh_seeds_power_and_sealed_boundary() -> None:
    config, loop = M15P._resolve(
        ROOT / "configs" / "l1_pattern_value_target_screen.yaml"
    )
    assert config["paired_seeds"] == list(range(271001, 271021))
    assert loop["model"]["architecture"] == "folded_pattern_value"
    assert loop["training"]["policy_weight"] == 0.0
    assert config["replay"]["source"] == "G1_WIDE_OUTCOME"
    assert config["scientific_gate"]["primary_contrast"] == "BLEND_50_minus_OUTCOME"
    assert config["scientific_gate"]["SEARCH_ROOT_is_mechanistic_only"] is True
    assert config["power_sizing"]["estimated_power_ci_above_zero"] > 0.90
    assert M15P.estimate_power(config["power_sizing"]) == pytest.approx(0.91212)
    assert config["boundaries"]["existing_frozen_test_read_count"] == 1
    assert config["boundaries"]["additional_frozen_test_reads_authorized"] == 0


def test_m15p_changes_only_value_target_on_shared_replay_structure() -> None:
    samples = [_sample(1, 0, 7, 1.0), _sample(1, 1, 8, -1.0)]
    traces = [_trace(1, 0, 7, 0.6), _trace(1, 1, 8, -0.2)]
    exact = np.zeros(16, dtype=np.float32)
    exact[7] = -1.0
    exact[8] = 1.0
    arms, contract = M15P.build_target_arms(samples, traces, exact)

    assert [row.value_target for row in arms["OUTCOME"]] == [1.0, -1.0]
    assert [row.value_target for row in arms["SEARCH_ROOT"]] == pytest.approx(
        [0.6, -0.2]
    )
    assert [row.value_target for row in arms["BLEND_50"]] == pytest.approx(
        [0.8, -0.6]
    )
    assert [row.value_target for row in arms["EXACT_ORACLE"]] == [-1.0, 1.0]
    assert len(set(contract["structure_fingerprints"].values())) == 1
    assert contract["search_trace_rows_consumed"] == len(samples)
    assert contract["search_root_scores_clipped"] == 0


def test_m15p_clips_search_targets_and_rejects_trace_identity_drift() -> None:
    samples = [_sample(1, 0, 7, 1.0)]
    exact = np.zeros(16, dtype=np.float32)
    arms, contract = M15P.build_target_arms(
        samples, [_trace(1, 0, 7, 1.5)], exact
    )
    assert arms["SEARCH_ROOT"][0].value_target == 1.0
    assert contract["search_root_scores_clipped"] == 1

    bad = _trace(1, 0, 9, 0.5)
    with pytest.raises(ValueError, match="identity mismatch"):
        M15P.build_target_arms(samples, [bad], exact)


def test_m15p_allows_behavior_action_to_differ_from_search_best_action() -> None:
    sample = _sample(1, 0, 7, 1.0)
    trace = _trace(1, 0, 7, 0.5)
    trace["selected_action"] = 8
    arms, contract = M15P.build_target_arms(
        [sample], [trace], np.zeros(16, dtype=np.float32)
    )
    assert arms["OUTCOME"][0].selected_action == 3
    assert contract["search_trace_rows_consumed"] == 1


def test_m15p_primary_pass_requires_positive_ci_and_half_oracle_recovery() -> None:
    passed = M15P.build_recommendation(
        _contrasts((0.006, 0.001, 0.011), (0.010, 0.006, 0.014)), GATE
    )
    assert passed["status"] == "PASS"
    assert passed["deployable_target_signal"] is True
    assert passed["decision"] == "replicate_BLEND_50_strength_on_fresh_seeds"
    assert passed["promotable"] is False


def test_m15p_search_arm_cannot_rescue_a_failed_primary() -> None:
    result = M15P.build_recommendation(
        _contrasts(
            (0.001, -0.001, 0.003),
            (0.010, 0.007, 0.013),
            search=(0.010, 0.008, 0.012),
        ),
        GATE,
    )
    assert result["status"] == "FAIL"
    assert result["deployable_target_signal"] is False
    assert result["decision"] == "prepare_M16P_temporal_targets"
    assert result["search_root_arm_can_rescue_primary"] is False


def test_m15p_reports_underpowered_primary_without_launching_m16p() -> None:
    result = M15P.build_recommendation(
        _contrasts((0.004, -0.001, 0.009), (0.010, 0.007, 0.013)), GATE
    )
    assert result["status"] == "INCONCLUSIVE"
    assert result["decision"] == "replicate_M15P_with_power_sized_fresh_seeds"


def test_m15p_closes_target_axis_if_selected_replay_has_no_oracle_gap() -> None:
    result = M15P.build_recommendation(
        _contrasts((0.0, -0.001, 0.001), (0.0, -0.002, 0.003)), GATE
    )
    assert result["status"] == "FAIL"
    assert result["decision"] == "close_M15P_and_do_not_launch_M16P"


def test_m15p_result_write_read_round_trip_preserves_verdict(tmp_path: Path) -> None:
    result = {
        "schema": M15P.SCHEMA,
        "milestone": "M15-P",
        "status": "PASS",
        "result_hash": "fixture-hash",
        "recommendation": {"finding": "fixture-finding"},
    }
    run_dir = tmp_path / "run"
    compact = tmp_path / "result.full.json"
    M15P._write_outputs(result, run_dir, compact)
    assert (run_dir / "result.json").read_bytes() == compact.read_bytes()


def test_m15p_progress_reports_seed_rate(tmp_path: Path) -> None:
    output = tmp_path / "PROGRESS.json"
    M15P._write_progress(output, 2, 20, 271002, M15P.time.monotonic() - 120.0)
    payload = M15P.json.loads(output.read_text(encoding="utf-8"))
    assert payload["completed_seeds"] == 2
    assert payload["total_seeds"] == 20
    assert payload["eta_remaining_seconds"] > 0.0
