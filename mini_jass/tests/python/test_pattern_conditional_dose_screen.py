"""Contracts for the preregistered M15-C2 conditional-target dose screen."""

from __future__ import annotations

import importlib.util
import json
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


def _replication_inputs(
    primary: tuple[float, float, float] = (0.004, 0.002, 0.006),
    secondary: tuple[float, float, float] = (0.005, 0.003, 0.007),
    dose: tuple[float, float, float] = (0.001, 0.0002, 0.0018),
) -> tuple[dict[str, object], dict[str, object]]:
    contrasts = {
        "attribution_30": {"zero_regret_gain": _interval(*primary)},
        "operational_30": {"zero_regret_gain": _interval(*primary)},
        "attribution_40": {"zero_regret_gain": _interval(*secondary)},
        "operational_40": {"zero_regret_gain": _interval(*secondary)},
        "dose_40_minus_30": {"zero_regret_gain": _interval(*dose)},
    }
    arena = {
        name: {"arena_score_minus_half": value["zero_regret_gain"]}
        for name, value in contrasts.items()
    }
    return contrasts, arena


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
    assert config["probe"]["seed"] == 273000
    assert config["probe"]["scientific_metrics_must_not_be_published"] is True


def test_m15c2_replication_refactor_preserves_frozen_discovery_protocol_hash() -> None:
    config, loop = M15C2._resolve(
        ROOT / "configs" / "l1_pattern_conditional_dose_screen.yaml"
    )
    power = M15C2.deepcopy(config["power_sizing"])
    power["recomputed_power"] = M15C2.estimate_power(config["power_sizing"])
    protocol = {
        "schema": M15C2.SCHEMA,
        "milestone": "M15-C2",
        "base_loop_config": config["base_loop_config"],
        "resolved_model": M15C2.model_descriptor(M15C2.build_model(loop["model"])),
        "paired_seeds": config["paired_seeds"],
        "arms": list(M15C2.ARM_ORDER),
        "replay": config["replay"],
        "conditional_mapping": config["conditional_mapping"],
        "dose_screen": config["dose_screen"],
        "training_schedule": config["training_schedule"],
        "strength_arena": config["strength_arena"],
        "power_sizing": power,
        "scientific_gate": config["scientific_gate"],
        "source_evidence": config["source_evidence"],
        "boundaries": config["boundaries"],
        "execution_host": "cpx62",
    }
    assert M15C2.digest(protocol) == M15C2.EXPECTED_M15C2_PROTOCOL


def test_cpx_wrapper_reuses_a_host_persistent_venv_outside_results() -> None:
    wrapper = (ROOT / "jobs" / "run_pattern_reconstruction_cpx.sh").read_text(
        encoding="utf-8"
    )
    assert 'venv="$work/venv"' not in wrapper
    assert "/root/.cache/mini-jass-pattern-venv" in wrapper
    assert 'if [[ ! -x "$venv/bin/python" ]]' in wrapper
    assert "python3 -m venv --system-site-packages" in wrapper
    assert "m15c2r)" in wrapper
    assert "m15c2rprobe)" in wrapper
    assert "l1_pattern_conditional_dose_replication.yaml" in wrapper


def test_m15c2r_config_freezes_fresh_primary_secondary_and_power_only_effects() -> None:
    config, loop = M15C2._resolve(
        ROOT / "configs" / "l1_pattern_conditional_dose_replication.yaml"
    )
    assert config["paired_seeds"] == list(range(275001, 275021))
    assert config["probe"]["seed"] == 275000
    assert config["arms"] == list(M15C2.REPLICATION_ARM_ORDER)
    assert config["dose_replication"]["primary_alpha"] == pytest.approx(0.30)
    assert config["dose_replication"]["secondary_alpha"] == pytest.approx(0.40)
    assert config["dose_replication"]["secondary_cannot_rescue_primary"] is True
    assert config["scientific_gate"]["minimum_effect_floor"] == 0.0
    assert config["strength_arena"]["arms"] == list(M15C2.REPLICATION_ARENA_ARMS)
    assert M15C2.estimate_power(
        config["power_sizing"]["primary_replication"]
    ) == pytest.approx(0.92362)
    assert M15C2.estimate_power(
        config["power_sizing"]["secondary_40_minus_30"]
    ) == pytest.approx(0.8442)
    assert config["boundaries"]["additional_frozen_test_reads_authorized"] == 0
    assert loop["model"]["architecture"] == "folded_pattern_value"


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


def test_m15c2r_builds_only_preregistered_replication_arms() -> None:
    samples = [_sample(1, 1.0), _sample(2, -1.0)]
    exact = np.zeros(3, dtype=np.float32)
    arms, contract = M15C2.build_target_arms(
        samples,
        conditional_predictions=np.asarray([0.6, -0.2]),
        shuffled_predictions=np.asarray([-0.2, 0.6]),
        exact_values=exact,
        doses=M15C2.REPLICATION_DOSES,
        arm_order=M15C2.REPLICATION_ARM_ORDER,
    )
    assert tuple(arms) == M15C2.REPLICATION_ARM_ORDER
    assert "CONTEXT_20" not in arms
    assert [row.value_target for row in arms["CONTEXT_40"]] == pytest.approx(
        [0.84, -0.68]
    )
    assert len(set(contract["structure_fingerprints"].values())) == 1


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


def test_m15c2r_selects_alpha_40_only_after_primary_and_direct_superiority_pass() -> None:
    contrasts, arena = _replication_inputs()
    result = M15C2.build_replication_recommendation(contrasts, arena)
    assert result["status"] == "PASS"
    assert result["primary_replication_status"] == "PASS"
    assert result["secondary_control_status"] == "PASS"
    assert result["dose_40_minus_30_status"] == "PASS"
    assert result["retained_alpha"] == pytest.approx(0.40)
    assert result["decision"] == "prepare_alpha_40_temporal_composition"


def test_m15c2r_retains_alpha_30_when_secondary_superiority_is_not_precise() -> None:
    contrasts, arena = _replication_inputs(dose=(0.0005, -0.0002, 0.0012))
    result = M15C2.build_replication_recommendation(contrasts, arena)
    assert result["status"] == "PASS"
    assert result["retained_alpha"] == pytest.approx(0.30)
    assert result["dose_40_minus_30_status"] == "INCONCLUSIVE"
    assert result["decision"] == "prepare_alpha_30_temporal_composition"


def test_m15c2r_secondary_cannot_rescue_failed_alpha_30() -> None:
    contrasts, arena = _replication_inputs(primary=(-0.001, -0.002, 0.0))
    result = M15C2.build_replication_recommendation(contrasts, arena)
    assert result["status"] == "FAIL"
    assert result["retained_alpha"] is None
    assert result["secondary_can_rescue_primary"] is False
    assert result["decision"] == "do_not_compose_unreplicated_conditional_target"


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


def test_m15c2_probe_round_trip_publishes_timing_only(tmp_path: Path) -> None:
    result = {
        "schema": M15C2.PROBE_SCHEMA,
        "milestone": "M15-C2-PROBE",
        "status": "PROBE_COMPLETE",
        "seed": 273000,
        "timing": {"total_seconds": 42.0},
        "workload": {"selfplay_games": 1024},
        "reporting": "timing_and_contract_only",
        "scientific_metrics_published": False,
        "promotable": False,
        "result_hash": "probe-fixture-hash",
    }
    run_dir = tmp_path / "run"
    compact = tmp_path / "probe.full.json"
    M15C2._write_probe_outputs(result, run_dir, compact)
    replayed = json.loads(compact.read_text(encoding="utf-8"))
    assert replayed["seed"] == 273000
    assert replayed["scientific_metrics_published"] is False
    assert "aggregate" not in replayed
    assert "recommendation" not in replayed


def test_m15c2r_result_and_probe_round_trips_use_replication_schemas(
    tmp_path: Path,
) -> None:
    result = {
        "schema": M15C2.REPLICATION_SCHEMA,
        "milestone": "M15-C2R",
        "status": "PASS",
        "result_hash": "replication-result-hash",
        "recommendation": {"finding": "replication-fixture"},
    }
    run_dir = tmp_path / "run"
    compact = tmp_path / "result.full.json"
    M15C2._write_outputs(
        result,
        run_dir,
        compact,
        M15C2.REPLICATION_SCHEMA,
        "M15-C2R",
    )
    probe = {
        "schema": M15C2.REPLICATION_PROBE_SCHEMA,
        "milestone": "M15-C2R-PROBE",
        "status": "PROBE_COMPLETE",
        "scientific_metrics_published": False,
        "promotable": False,
        "result_hash": "replication-probe-hash",
    }
    M15C2._write_probe_outputs(
        probe,
        tmp_path / "probe",
        tmp_path / "probe.full.json",
        M15C2.REPLICATION_PROBE_SCHEMA,
    )
