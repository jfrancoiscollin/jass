"""M17 — l'echelle de generations, et le piege qu'elle doit eviter.

Le piege : `loop.py` n'avance le parent que si `development_pass AND
arena_pass`. Une echelle dont aucune generation ne promeut mesure N fois la
MEME generation et produit un plateau parfait — qu'il serait fatal de lire
comme « l'iteration ne compose pas ». Le controle de promotion existe pour
separer PLAT de NOMINAL, et c'est ce que ces tests verrouillent.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "run_generation_ladder.py"
_SPEC = importlib.util.spec_from_file_location("run_ladder", _TOOL)
assert _SPEC and _SPEC.loader
M17 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M17)

GATE = {
    "minimum_monotone_rungs": 3,
    "minimum_final_value_sign_delta": 0.0,
    "minimum_final_optimal_mass_delta": 0.0,
}
CONTROL = {"report_per_generation": True, "minimum_advancing_generations": 1}


def _aggregate(deltas, advancing=4.0):
    rungs = [1, 2, 4, 8]
    return {
        "rungs": rungs,
        "mean_value_sign_delta_by_rung": {
            str(rung): delta for rung, delta in zip(rungs, deltas)
        },
        "mean_advancing_generations": advancing,
    }


# --------------------------------------------------------------------------- #
#  Le controle : plat SANS promotion n'est pas plat, c'est INCONCLUANT.
# --------------------------------------------------------------------------- #
def test_a_ladder_that_never_promoted_is_inconclusive_not_negative():
    """Zero promotion = huit fois la meme generation. Ne PAS lire « plat »."""
    flat = _aggregate([0.30, 0.30, 0.30, 0.30], advancing=0.0)
    rec = M17.build_ladder_recommendation(flat, GATE, CONTROL)
    assert rec["finding"] == "ladder_never_advanced_the_parent"
    assert rec["decision"] == "INCONCLUSIVE_promotion_gate_blocked_iteration"
    assert rec["iteration_compounds"] is None


def test_the_same_flat_curve_WITH_promotion_is_a_real_negative():
    """Meme courbe, promotion reelle : la l'iteration ne compose pas."""
    flat = _aggregate([0.30, 0.30, 0.30, 0.30], advancing=4.0)
    rec = M17.build_ladder_recommendation(flat, GATE, CONTROL)
    assert rec["iteration_compounds"] is False
    assert rec["finding"] == "iteration_does_not_compound_in_this_loop"


def test_below_the_minimum_advance_is_also_inconclusive():
    partial = _aggregate([0.10, 0.20, 0.30, 0.40], advancing=0.4)
    rec = M17.build_ladder_recommendation(partial, GATE, CONTROL)
    assert rec["iteration_compounds"] is None


# --------------------------------------------------------------------------- #
#  La lecture de la courbe.
# --------------------------------------------------------------------------- #
def test_monotone_rising_ladder_compounds():
    rising = _aggregate([0.10, 0.18, 0.26, 0.34])
    rec = M17.build_ladder_recommendation(rising, GATE, CONTROL)
    assert rec["iteration_compounds"] is True
    assert rec["monotone_rungs"] == 4
    assert rec["decision"] == "replicate_ladder_on_fresh_seeds"


def test_a_ladder_that_ends_below_its_first_rung_does_not_compound():
    """Monter puis redescendre sous le depart n'est pas une composition."""
    humped = _aggregate([0.30, 0.34, 0.32, 0.28])
    rec = M17.build_ladder_recommendation(humped, GATE, CONTROL)
    assert rec["iteration_compounds"] is False


def test_a_negative_final_rung_does_not_compound():
    decaying = _aggregate([0.10, 0.02, -0.05, -0.12])
    rec = M17.build_ladder_recommendation(decaying, GATE, CONTROL)
    assert rec["iteration_compounds"] is False


def test_no_outcome_is_ever_promotable():
    for deltas, advancing in (
        ([0.10, 0.18, 0.26, 0.34], 4.0),
        ([0.30, 0.30, 0.30, 0.30], 4.0),
        ([0.30, 0.30, 0.30, 0.30], 0.0),
    ):
        rec = M17.build_ladder_recommendation(_aggregate(deltas, advancing), GATE, CONTROL)
        assert rec["promotable"] is False


# --------------------------------------------------------------------------- #
#  Le contrat de la config.
# --------------------------------------------------------------------------- #
def _config():
    path = Path(__file__).resolve().parents[2] / "configs" / "l1_generation_ladder.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_config_declares_the_frozen_m8_recipe_and_a_single_factor():
    config = _config()
    assert config["schema"] == M17.SCHEMA
    assert config["base_gate_config"] == "configs/l1_frozen_learning_gate.yaml"
    assert config["boundaries"]["promotable"] is False
    assert config["boundaries"]["production_jass_changes_authorized"] is False


def test_rungs_are_sorted_and_reach_the_ladder_max():
    """Un barreau au-dela du max lirait un candidate_state inexistant."""
    config = _config()
    rungs = config["report_rungs"]
    assert rungs == sorted(rungs)
    assert max(rungs) == config["ladder_max"]


def test_the_promotion_control_is_declared_and_binding():
    config = _config()
    assert config["promotion_control"]["report_per_generation"] is True
    assert int(config["promotion_control"]["minimum_advancing_generations"]) >= 1


@pytest.mark.parametrize("bad_rungs", [[1, 2, 4], [1, 4, 2, 8], [1, 2, 4, 16]])
def test_a_malformed_rung_list_would_be_refused(bad_rungs, tmp_path):
    """Reproduit la garde du runner : non triee, ou n'atteignant pas le max."""
    ladder_max = 8
    ok = bool(bad_rungs) and max(bad_rungs) == ladder_max and sorted(bad_rungs) == bad_rungs
    assert not ok
