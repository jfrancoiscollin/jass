"""M24 — un plafond non sature n'est pas un plafond.

La cellule existe pour rendre lisible une courbe de convergence : plateau AU
plafond = la boucle a fait ce que le modele permet ; plateau SOUS = c'est la
boucle qui sature. Ces tests verrouillent la garde qui empeche de publier « le
plafond » alors qu'on n'a mesure que « la duree qu'on a bien voulu payer ».
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "run_supervised_ceiling.py"
_SPEC = importlib.util.spec_from_file_location("run_m24", _TOOL)
assert _SPEC and _SPEC.loader
M24 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M24)


def _gate():
    return {
        "saturation_tolerance": 0.005,
        "frozen_recipe_hidden_size": 32,
        "capacity_relevance_threshold": 0.02,
    }


def _cohort(value):
    return {key: value for key in M24.REPORTED}


def _aggregate(curve, capacity=None):
    doses = {
        str(dose): {c: _cohort(v) for c in M24.COHORTS}
        for dose, v in curve.items()
    }
    return {
        "by_dose": doses,
        "by_capacity": {
            str(size): {c: _cohort(v) for c in M24.COHORTS}
            for size, v in (capacity or {}).items()
        },
    }


def test_a_still_improving_ladder_refuses_to_publish_a_ceiling():
    """Le cas du smoke : +0,0099 sur la derniere marche, au-dessus de 0,005."""
    rec = M24.build_recommendation(
        _aggregate({12: 0.90, 48: 0.91, 192: 0.9119, 768: 0.9218}), _gate())
    assert rec["status"] == "CEILING_NOT_SATURATED"
    assert rec["ceiling"] is None
    assert "extend_the_dose_ladder" in rec["next_step"]


def test_a_saturated_ladder_publishes_the_ceiling():
    rec = M24.build_recommendation(
        _aggregate({12: 0.90, 48: 0.94, 192: 0.961, 768: 0.9635}), _gate())
    assert rec["status"] == "PASS"
    assert rec["ceiling_primary_frozen_test"] == pytest.approx(0.9635)
    assert rec["distance_to_oracle"] == pytest.approx(1.0 - 0.9635)


def test_a_bigger_model_that_climbs_says_the_architecture_binds():
    rec = M24.build_recommendation(
        _aggregate({12: 0.90, 48: 0.94, 192: 0.961, 768: 0.9635},
                   capacity={32: 0.9635, 64: 0.99, 128: 0.995}), _gate())
    assert rec["architecture_is_the_binding_constraint"] is True
    assert rec["capacity_gain_from_bigger_models"] == pytest.approx(0.0315)


def test_a_bigger_model_that_gains_nothing_clears_the_architecture():
    rec = M24.build_recommendation(
        _aggregate({12: 0.90, 48: 0.94, 192: 0.961, 768: 0.9635},
                   capacity={32: 0.9635, 64: 0.964, 128: 0.9645}), _gate())
    assert rec["architecture_is_the_binding_constraint"] is False


def test_the_ceiling_is_never_a_candidate():
    for curve in ({12: 0.9, 768: 0.9218}, {12: 0.9, 768: 0.9005}):
        rec = M24.build_recommendation(_aggregate(curve), _gate())
        assert rec["promotable"] is False
        assert rec["is_an_upper_bound_not_a_candidate"] is True


def test_every_outcome_carries_the_keys_the_results_parser_reads():
    for curve in ({12: 0.9, 768: 0.9218}, {12: 0.9, 768: 0.9005}):
        rec = M24.build_recommendation(_aggregate(curve), _gate())
        for key in ("status", "finding", "primary_metric", "dose_ladder",
                    "frozen_test_by_dose", "last_dose_step",
                    "saturation_tolerance", "is_an_upper_bound_not_a_candidate",
                    "next_step", "promotable"):
            assert key in rec, key


def _config():
    return yaml.safe_load(
        (_ROOT / "configs" / "l1_supervised_ceiling.yaml").read_text())


def test_the_config_declares_the_oracle_as_its_training_signal():
    """Traversee de frontiere DELIBEREE : elle doit etre ecrite, pas subie."""
    boundaries = _config()["boundaries"]
    assert boundaries["oracle_is_the_training_signal"] is True
    assert boundaries["promotable"] is False


def test_a_config_that_hides_the_boundary_crossing_is_refused(tmp_path):
    config = _config()
    del config["boundaries"]["oracle_is_the_training_signal"]
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="oracle IS its training signal"):
        M24._resolve(path)


def test_the_dose_ladder_is_sorted_and_has_at_least_two_rungs():
    ladder = _config()["dose_ladder"]
    assert ladder == sorted(ladder) and len(ladder) >= 2


def test_an_untested_capacity_question_is_reported_as_NULL_not_as_FALSE():
    """Sans echelle de capacite, « l'architecture borne-t-elle ? » n'a pas ete
    POSEE. Rendre False la ferait passer pour repondue par la negative."""
    rec = M24.build_recommendation(
        _aggregate({12: 0.90, 48: 0.94, 192: 0.961, 768: 0.9635}), _gate())
    assert rec["status"] == "PASS"
    assert rec["architecture_is_the_binding_constraint"] is None
    assert rec["capacity_gain_from_bigger_models"] is None


def test_the_shipped_config_leaves_the_capacity_question_unasked():
    config = _config()
    assert config["capacity_ladder"] == [], (
        "poser cette question coute les deux tiers du budget et n'est "
        "actionnable qu'une fois le plafond connu")
