"""Contracts for M15-C6 separate contextual decision channels."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import hashlib
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
    _build_aggregate,
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


def _aggregate_row(seed: int, value: float) -> dict:
    endpoints = {
        "zero_regret_rate": value,
        "value_sign_accuracy": value,
        "value_mae": value,
        "mean_selected_regret": value,
    }
    zeros = {name: 0.0 for name in endpoints}
    return {
        "seed": seed,
        "arenas": {
            matchup: {"score_minus_half": value} for matchup in MATCHUPS
        },
        "arms": {
            "OUTCOME": {"after": zeros},
            "LAMBDA_50": {"after": endpoints},
            "CONTEXT_30": {"after": endpoints},
        },
        "decision_diagnostics": {
            "aligned_minus_shuffled_zero_regret": value,
            "aligned_minus_lambda_zero_regret": value,
            "activation_rate": 0.25,
            "aligned_changed_action_rate": 0.10,
            "shuffled_changed_action_rate": 0.12,
        },
        "delta_calibration": {"delta": 0.2},
        "conditional_mapping": {
            "conditional_mse_gain_vs_state_blind": 0.01,
            "all_games_fold_disjoint": True,
        },
        "replay": {
            "all_rows_train_only": True,
            "all_training_targets_oracle_blind": True,
        },
        "shuffle_control": {"all_fold_marginals_preserved": True},
    }


def test_aggregate_passes_frozen_critical_to_every_interval() -> None:
    rows = [
        _aggregate_row(279001, -0.1),
        _aggregate_row(279002, 0.0),
        _aggregate_row(279003, 0.1),
    ]
    aggregate = _build_aggregate(rows, critical=2.0)
    expected_half_width = 2.0 * 0.1 / np.sqrt(3.0)
    arena = aggregate["arena_strength"]["ALIGNED_VS_SHUFFLED"]
    static = aggregate["static_diagnostics"]["LAMBDA_50_minus_OUTCOME"][
        "zero_regret_rate"
    ]
    decision = aggregate["decision_diagnostics"][
        "aligned_minus_shuffled_zero_regret"
    ]
    for interval in (arena, static, decision):
        assert interval["mean"] == pytest.approx(0.0)
        assert interval["lower"] == pytest.approx(-expected_half_width)
        assert interval["upper"] == pytest.approx(expected_half_width)


def test_recovery_authenticates_all_preregistered_seed_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    row_root = source / "mini-jass-pattern-m15c6-full" / "run"
    row_root.mkdir(parents=True)
    source_job = "home-1260-mini-jass-pattern-m15c6-full-v2"
    source_attempt = "20260812T061436Z-85e428bb"
    source_sha = "8" * 40
    manifest = {
        "job_id": source_job,
        "attempt_id": source_attempt,
        "code_sha": source_sha,
        "state": "failed",
        "exit_code": 1,
    }
    (source / "manifest.json").write_text(json.dumps(manifest) + "\n")
    inventory_rows = []
    checksums = {}

    def register(relative: str) -> None:
        path = source / relative
        raw = path.read_bytes()
        digest_value = hashlib.sha256(raw).hexdigest()
        inventory_rows.append({
            "path": relative,
            "size_bytes": len(raw),
            "sha256": digest_value,
        })
        checksums[relative] = digest_value

    register("manifest.json")
    for seed in range(279001, 279025):
        relative = f"mini-jass-pattern-m15c6-full/run/seed-{seed}.json"
        (source / relative).write_text(json.dumps(_aggregate_row(seed, 0.001)) + "\n")
        register(relative)
    (source / "inventory.json").write_text(
        json.dumps({"files": inventory_rows}) + "\n"
    )
    checksums["inventory.json"] = hashlib.sha256(
        (source / "inventory.json").read_bytes()
    ).hexdigest()
    (source / "checksums.sha256").write_text(
        "".join(f"{digest_value}  {relative}\n" for relative, digest_value in checksums.items())
    )

    captured = {}
    monkeypatch.setattr(
        m15c6,
        "_build_result",
        lambda config, base, seeds, rows, timings, host, run_dir, compact, recovery: captured.update(
            seeds=seeds, rows=rows, timings=timings, recovery=recovery
        ) or {"status": "PASS", "result_hash": "x"},
    )
    root = Path(__file__).resolve().parents[2]
    result = m15c6.recover_m15c6(
        root / "configs" / "l1_pattern_contextual_decision_channel.yaml",
        source,
        tmp_path / "run",
        tmp_path / "result.json",
        source_job,
        source_attempt,
        source_sha,
        "User",
    )
    assert result["status"] == "PASS"
    assert len(captured["rows"]) == 24
    assert captured["timings"] == []
    assert captured["recovery"]["scientific_compute_repeated"] is False


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


def test_home_recovery_reads_only_authenticated_seed_results() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (
        root / "jobs" / "recover_pattern_contextual_decision_channel_home.sh"
    ).read_text(encoding="utf-8")
    assert "home-1260-mini-jass-pattern-m15c6-full-v2" in script
    assert "--files-from-raw" in script
    assert "--no-traverse" in script
    assert "seed-*.json" in script
    assert "scientific_compute_repeated=false" in script
    assert "additional_frozen_test_reads=0" in script
    assert "pip install" not in script
