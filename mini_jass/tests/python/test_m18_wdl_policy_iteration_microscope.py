"""Guards for the M18 Scan-like WDL policy-iteration microscope."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

from mini_jass_lab.replay import ReplaySample

_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "run_wdl_policy_iteration_microscope.py"
_SPEC = importlib.util.spec_from_file_location("run_m18", _TOOL)
assert _SPEC and _SPEC.loader
M18 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M18)


def _sample(state: int, value: float, ply: int = 0, generation: int = 1):
    return ReplaySample(
        state_id=state,
        value_target=value,
        policy_target=np.asarray([1.0, 0.0], dtype=np.float32),
        generation=generation,
        game_id=state,
        ply=ply,
    )


def test_wdl_quality_reports_exactness_and_true_win_to_draw_confusion():
    oracle = SimpleNamespace(values=np.asarray([1, 1, 0, -1], dtype=np.int8))
    rows = [_sample(0, 1), _sample(1, 0), _sample(2, 0), _sample(3, -1)]
    out = M18._wdl_quality(rows, oracle)
    assert out["count"] == 4
    assert out["exact_rate"] == pytest.approx(0.75)
    assert out["confusion"]["W"]["D"] == 1
    assert out["true_decisive_labelled_draw_rate"] == pytest.approx(1.0 / 3.0)


def test_start_only_quality_excludes_later_plies():
    oracle = SimpleNamespace(values=np.asarray([1, -1], dtype=np.int8))
    rows = [_sample(0, 1, ply=0), _sample(1, 0, ply=1)]
    assert M18._wdl_quality([row for row in rows if row.ply == 0], oracle)["exact_rate"] == 1.0


def test_frozen_generator_reuses_the_first_model_object_semantics():
    calls = []

    class Model:
        def __init__(self, tag):
            self.tag = tag

    def original(_graph, model, _config, generation, _seed, _starts):
        calls.append((model.tag, generation))
        return generation

    wrapped = M18._frozen_generator(original)
    assert wrapped(None, Model("g0"), None, 1, 0, None) == 1
    assert wrapped(None, Model("g1"), None, 2, 0, None) == 2
    assert calls == [("g0", 1), ("g0", 2)]


def test_arena_only_contract_requires_promotion_to_equal_arena_pass():
    execution = SimpleNamespace(core={"generations": [
        {"promotion": {"development_pass": True, "arena_pass": True, "provisional_advance": True}},
        {"promotion": {"development_pass": True, "arena_pass": False, "provisional_advance": False}},
    ]})
    M18._verify_promotion_contract(execution, "arena_only")


def test_arena_only_contract_refuses_oracle_dependent_rejection():
    execution = SimpleNamespace(core={"generations": [
        {"promotion": {"development_pass": False, "arena_pass": True, "provisional_advance": False}},
    ]})
    with pytest.raises(ValueError, match="development gate"):
        M18._verify_promotion_contract(execution, "arena_only")


def test_forced_contract_requires_every_generation_to_advance():
    execution = SimpleNamespace(core={"generations": [
        {"promotion": {"development_pass": True, "arena_pass": True, "provisional_advance": False}},
    ]})
    with pytest.raises(ValueError, match="forced-advance"):
        M18._verify_promotion_contract(execution, "always")


def test_deployed_state_reconstruction_keeps_parent_when_candidate_rejected():
    initial = {"w": "initial"}
    candidates = [{"w": "c1"}, {"w": "c2"}, {"w": "c3"}]
    records = [
        {"promotion": {"provisional_advance": True}},
        {"promotion": {"provisional_advance": False}},
        {"promotion": {"provisional_advance": True}},
    ]
    states = M18._deployed_states_by_rung(initial, candidates, records, [0, 1, 2, 3])
    assert states["0"]["w"] == "initial"
    assert states["1"]["w"] == "c1"
    assert states["2"]["w"] == "c1"
    assert states["3"]["w"] == "c3"


def test_paired_confidence_interval_above_zero():
    row = M18._paired_summary([0.10, 0.12, 0.09, 0.11, 0.13], 2.7764451051977987)
    assert row["mean"] > 0.0
    assert row["confidence_95"][0] > 0.0


def _aggregate(advances=3.0, loop=0.05, feedback=0.04, search=0.03,
               final_v=0.10, final_p=0.02, arena=0.60):
    return {
        "arms": {
            "evolving_arena_gate": {
                "mean_advancing_generations": advances,
                "mean_final_development_value_sign_delta": final_v,
                "mean_final_development_optimal_mass_delta": final_p,
                "mean_final_arena_score_vs_initial": arena,
            }
        },
        "contrasts": {
            "evolving_g8_minus_g0": {"mean": loop, "confidence_95": [loop - 0.01, loop + 0.01]},
            "evolving_gain_minus_frozen_gain": {"mean": feedback, "confidence_95": [feedback - 0.01, feedback + 0.01]},
            "evolving_gain_minus_shallow_gain": {"mean": search, "confidence_95": [search - 0.01, search + 0.01]},
            "evolving_gain_minus_forced_gain": {"mean": 0.01, "confidence_95": [-0.01, 0.03]},
        },
        "execution": {"all_runs_completed": True, "start_schedules_paired": True},
    }


def _gate():
    return {
        "minimum_mean_advancing_generations": 1.0,
        "minimum_practical_loop_gain": 0.03,
        "minimum_practical_feedback_gain": 0.02,
        "minimum_practical_search_gain": 0.02,
        "require_paired_confidence_95_above_zero": True,
        "minimum_final_development_value_sign_delta": 0.0,
        "minimum_final_development_optimal_mass_delta": 0.0,
        "minimum_final_arena_score_vs_initial": 0.50,
    }


def test_no_real_promotion_is_inconclusive():
    rec = M18.build_recommendation(_aggregate(advances=0.0), _gate())
    assert rec["status"] == "INCONCLUSIVE"
    assert rec["loop_is_virtuous"] is None


def test_all_causal_criteria_pass_the_microscope():
    rec = M18.build_recommendation(_aggregate(), _gate())
    assert rec["status"] == "PASS"
    assert rec["loop_is_virtuous"] is True
    assert rec["generator_feedback_is_causal"] is True
    assert rec["search_is_cliquet"] is True
    assert rec["promotable"] is False


def test_rising_loop_without_feedback_does_not_claim_virtuous_generator():
    rec = M18.build_recommendation(_aggregate(feedback=0.0), _gate())
    assert rec["status"] == "FAIL"
    assert rec["generator_feedback_is_causal"] is False


def test_config_is_oracle_observer_only_and_has_exact_four_arms():
    config = yaml.safe_load((_ROOT / "configs" / "l1_wdl_policy_iteration_microscope.yaml").read_text())
    assert config["schema"] == M18.SCHEMA
    assert config["paired_seeds"] == [180001, 180002, 180003, 180004, 180005]
    assert config["arms"] == M18.EXPECTED_ARMS
    forbidden = set(config["observer_contract"]["oracle_reads_forbidden_for"])
    assert forbidden == {"training_targets", "selfplay_generation", "promotion_decision"}
    assert config["boundaries"]["promotable"] is False
    assert config["boundaries"]["direct_10x10_transfer_authorized"] is False


def test_primary_probe_has_rung_zero_and_eight():
    config = yaml.safe_load((_ROOT / "configs" / "l1_wdl_policy_iteration_microscope.yaml").read_text())
    assert config["report_rungs"][0] == 0
    assert config["report_rungs"][-1] == config["ladder_max"] == 8
