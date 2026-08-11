"""Contracts for the preregistered M15-C4 residual conditional path."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from mini_jass_lab.model_factory import build_model
from mini_jass_lab.pattern_eval import PatternEval
from mini_jass_lab.pattern_residual import collapse_pattern_evals, combined_values
from mini_jass_lab.patterns import PLAYABLE
from mini_jass_lab.replay import ReplaySample

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_pattern_conditional_dose_screen.py"
SPEC = importlib.util.spec_from_file_location("run_pattern_m15c4", TOOL)
assert SPEC and SPEC.loader
M15C4 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M15C4)


def _sample(state: int, game: int, ply: int, outcome: float) -> ReplaySample:
    policy = np.zeros(72, dtype=np.float32)
    policy[3] = 1.0
    return ReplaySample(state, outcome, policy, 1, game, ply, 3)


def _interval(lower: float) -> dict[str, float]:
    return {"mean": lower + 0.001, "lower": lower, "upper": lower + 0.002}


def test_m15c4_config_freezes_path_power_and_sealed_cohort() -> None:
    config, loop = M15C4._resolve(
        ROOT / "configs" / "l1_pattern_conditional_residual_path.yaml"
    )
    assert config["paired_seeds"] == list(range(277001, 277025))
    assert config["probe"]["seed"] == 277000
    assert config["arms"] == list(M15C4.RESIDUAL_ARM_ORDER)
    assert config["conditional_residual_path"]["alpha"] == pytest.approx(0.30)
    assert config["conditional_residual_path"]["extra_inference_parameters"] == 0
    assert config["training_schedule"]["direct_steps"] == 2048
    assert config["training_schedule"]["residual_base_steps"] == 1024
    assert config["training_schedule"]["residual_correction_steps"] == 1024
    assert config["scientific_gate"]["minimum_effect_floor"] == 0.0
    assert config["boundaries"]["additional_frozen_test_reads_authorized"] == 0
    assert config["boundaries"]["execution_is_not_queued_by_this_pr"] is True
    assert loop["model"]["architecture"] == "folded_pattern_value"
    for cell in config["power_sizing"].values():
        assert M15C4.estimate_power(cell) >= 0.80
        assert cell["gate_has_no_minimum_effect_floor"] is True


def test_m15c4_additive_target_preserves_temporal_and_matches_residual() -> None:
    samples = [_sample(1, 7, 0, 1.0), _sample(2, 8, 0, -1.0)]
    temporal = [_sample(1, 7, 0, 0.2), _sample(2, 8, 0, -0.4)]
    exact = np.zeros(3, dtype=np.float32)
    arms, contract = M15C4.build_residual_target_arms(
        samples,
        temporal,
        conditional_predictions=np.asarray([0.6, -0.2]),
        shuffled_predictions=np.asarray([-0.2, 0.6]),
        exact_values=exact,
    )
    assert tuple(arms) == M15C4.RESIDUAL_ARM_ORDER
    assert [row.value_target for row in arms["CONTEXT_30"]] == pytest.approx(
        [0.88, -0.76]
    )
    assert [row.value_target for row in arms["ADDITIVE_30"]] == pytest.approx(
        [0.08, -0.16]
    )
    assert [
        row.value_target for row in arms["SHUFFLED_ADDITIVE_30"]
    ] == pytest.approx([-0.16, 0.08])
    assert M15C4.replay_fingerprint(
        arms["ADDITIVE_30"]
    ) == M15C4.replay_fingerprint(arms["RESIDUAL_30"])
    assert contract["direct_and_residual_targets_identical"] is True
    assert contract["all_targets_bounded"] is True
    assert contract["all_targets_oracle_blind"] is True


def test_pattern_eval_additive_paths_collapse_to_one_exact_model() -> None:
    _, loop = M15C4._resolve(
        ROOT / "configs" / "l1_pattern_conditional_residual_path.yaml"
    )
    base = build_model(loop["model"])
    residual = build_model(loop["model"])
    assert isinstance(base, PatternEval) and isinstance(residual, PatternEval)
    generator = torch.Generator().manual_seed(441)
    with torch.no_grad():
        for model in (base, residual):
            for parameter in model.parameters():
                parameter.copy_(
                    torch.randn(parameter.shape, generator=generator) * 0.01
                )
    features = torch.zeros((9, 4 * PLAYABLE + 2), dtype=torch.float32)
    features[::2, 4 * PLAYABLE] = 1.0
    features[:, 4 * PLAYABLE + 1] = torch.linspace(0.0, 1.0, 9)
    collapsed = collapse_pattern_evals(base, residual)
    before = combined_values(base, residual, features)
    after, _ = collapsed(features)
    assert torch.allclose(before, after, rtol=0.0, atol=1.0e-7)
    assert collapsed.parameter_total() == base.parameter_total()


def test_m15c4_primary_cannot_be_rescued_by_descriptive_direct_arm() -> None:
    names = M15C4.RESIDUAL_CONTRASTS
    contrasts = {
        name: {
            "zero_regret_gain": _interval(
                -0.003 if name == "pathway_attribution" else 0.001
            )
        }
        for name in names
    }
    arenas = {
        name: {"arena_score_minus_half": _interval(0.001)} for name in names
    }
    verdict = M15C4.build_residual_recommendation(contrasts, arenas)
    assert verdict["status"] == "FAIL"
    assert verdict["retained_target"] == "CONTEXT_30"
    assert verdict["direct_additive_and_singletons_can_rescue_primary"] is False


def test_m15c4_round_trip_uses_residual_schemas(tmp_path: Path) -> None:
    result = {
        "schema": M15C4.RESIDUAL_SCHEMA,
        "milestone": "M15-C4",
        "status": "PASS",
        "result_hash": "m15c4-result-hash",
        "recommendation": {"finding": "fixture"},
    }
    M15C4._write_outputs(
        result,
        tmp_path / "run",
        tmp_path / "result.full.json",
        M15C4.RESIDUAL_SCHEMA,
        "M15-C4",
    )
    assert (
        json.loads((tmp_path / "result.full.json").read_text())["status"]
        == "PASS"
    )
    probe = {
        "schema": M15C4.RESIDUAL_PROBE_SCHEMA,
        "milestone": "M15-C4-PROBE",
        "status": "PROBE_COMPLETE",
        "scientific_metrics_published": False,
        "promotable": False,
        "result_hash": "m15c4-probe-hash",
    }
    M15C4._write_probe_outputs(
        probe,
        tmp_path / "probe",
        tmp_path / "probe.full.json",
        M15C4.RESIDUAL_PROBE_SCHEMA,
    )


def test_cpx_wrapper_supports_m15c4_probe_and_full_cell() -> None:
    wrapper = (ROOT / "jobs" / "run_pattern_reconstruction_cpx.sh").read_text()
    assert "m15c4)" in wrapper
    assert "m15c4probe)" in wrapper
    assert "l1_pattern_conditional_residual_path.yaml" in wrapper
