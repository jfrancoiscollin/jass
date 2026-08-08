"""M19 — le cliquet de recherche, et le defaut de M18 qu'il repare.

Le defaut : la sonde de M18 heritait de la profondeur DU BRAS, donc le bras
`shallow` mesurait 0,6937 au barreau 0 contre 0,7469 -- avant tout
entrainement. Les niveaux n'etaient pas comparables, le contraste se rabattait
sur les GAINS, et le bras parti le plus bas gagnait mecaniquement plus. Ces
tests verrouillent la reparation : sonde commune, contraste sur le NIVEAU, et
un controle au barreau 0 qui rend la cellule INCONCLUANTE si la sonde n'a pas
ete commune -- parce que repeter le defaut en le declarant repare serait pire
que de ne rien mesurer.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "run_search_ratchet.py"
_SPEC = importlib.util.spec_from_file_location("run_m19", _TOOL)
assert _SPEC and _SPEC.loader
M19 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M19)

CRITICAL = 2.7764451051977987


def _gate():
    return {
        "paired_confidence_critical_95": CRITICAL,
        "minimum_mean_advancing_generations": 1.0,
        "minimum_practical_level_gap": 0.02,
        "require_paired_confidence_95_above_zero": True,
        "maximum_rung0_level_gap": 0.0001,
        "maximum_consumed_node_imbalance": 0.35,
    }


def _rows(reference_g8, shallow_g8, reference_g0=0.75, shallow_g0=0.75):
    def row(seed, g0, g8):
        return {
            "seed": seed,
            "by_rung": {
                "0": {"probe_start_wdl": {"exact_rate": g0}},
                "8": {"probe_start_wdl": {"exact_rate": g8}},
            },
        }

    return {
        "reference_depth32": [
            row(seed, reference_g0, reference_g8) for seed in M19.EXPECTED_SEEDS
        ],
        "shallow_depth1": [
            row(seed, shallow_g0, shallow_g8) for seed in M19.EXPECTED_SEEDS
        ],
    }


def _aggregate(reference_g8=0.80, shallow_g8=0.75, reference_g0=0.75,
               shallow_g0=0.75, advancing=2.0, imbalance=0.20):
    rows = _rows(reference_g8, shallow_g8, reference_g0, shallow_g0)
    return {
        "arms": {
            "reference_depth32": {"mean_advancing_generations": advancing},
            "shallow_depth1": {"mean_advancing_generations": advancing},
        },
        "contrasts": M19.build_contrasts(rows, CRITICAL),
        "execution": {
            "all_runs_completed": True,
            "start_schedules_paired": True,
            "oracle_has_no_causal_role": True,
            "consumed_node_imbalance": imbalance,
        },
    }


# --------------------------------------------------------------------------- #
#  LE controle : sans sonde commune, on ne lit RIEN.
# --------------------------------------------------------------------------- #
def test_a_probe_that_was_not_common_makes_the_cell_inconclusive():
    """Reproduit le defaut de M18 : 0,7469 contre 0,6937 au barreau 0."""
    aggregate = _aggregate(reference_g0=0.7469, shallow_g0=0.6937)
    rec = M19.build_recommendation(aggregate, _gate())
    assert rec["status"] == "INCONCLUSIVE"
    assert rec["finding"] == "probe_was_not_common_rung0_levels_differ"
    assert rec["search_is_cliquet"] is None
    assert rec["rung0_level_gap"] == pytest.approx(0.0532)


def test_the_control_fires_before_anything_else_is_read():
    """Meme un ecart de niveau enorme ne doit pas sauver une sonde non commune."""
    aggregate = _aggregate(reference_g8=0.95, shallow_g8=0.50,
                           reference_g0=0.7469, shallow_g0=0.6937)
    assert M19.build_recommendation(aggregate, _gate())["status"] == "INCONCLUSIVE"


def test_a_reference_arm_that_never_promoted_is_inconclusive_too():
    rec = M19.build_recommendation(_aggregate(advancing=0.0), _gate())
    assert rec["status"] == "INCONCLUSIVE"
    assert rec["finding"] == "reference_arm_never_advanced_the_parent"


# --------------------------------------------------------------------------- #
#  La lecture du contraste, une fois le controle passe.
# --------------------------------------------------------------------------- #
def test_a_clear_level_gap_with_a_common_probe_is_a_ratchet():
    rec = M19.build_recommendation(_aggregate(), _gate())
    assert rec["status"] == "PASS"
    assert rec["search_is_cliquet"] is True
    assert rec["promotable"] is False


def test_no_level_gap_means_search_depth_changed_nothing():
    rec = M19.build_recommendation(_aggregate(reference_g8=0.75), _gate())
    assert rec["status"] == "FAIL"
    assert rec["finding"] == "search_depth_did_not_change_the_model_measurably"
    assert rec["next_step"] == "search_depth_is_not_the_missing_ingredient_on_L1"


def test_a_gap_below_the_practical_bar_does_not_pass():
    rec = M19.build_recommendation(_aggregate(reference_g8=0.76), _gate())
    assert rec["criteria"]["level_gap_practical"] is False


# --------------------------------------------------------------------------- #
#  Le compute : rapporte, jamais un critere.
# --------------------------------------------------------------------------- #
def test_a_large_node_imbalance_is_reported_but_never_fails_the_cell():
    """La reserve compute doit etre LISIBLE, pas fatale.

    Baisser la profondeur consomme moins de noeuds : c'est inherent au facteur
    teste. En faire un critere d'echec reviendrait a interdire de mesurer le
    facteur. On le chiffre, et on laisse la lecture au lecteur.
    """
    rec = M19.build_recommendation(_aggregate(imbalance=0.90), _gate())
    assert rec["status"] == "PASS"
    assert rec["compute_balanced_within_m8_tolerance"] is False
    assert rec["consumed_node_imbalance"] == pytest.approx(0.90)
    assert "consumed_node_imbalance" not in rec["criteria"]


# --------------------------------------------------------------------------- #
#  La forme de la sortie : ce qui a coute le verdict de cpx62-1206.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "aggregate",
    [
        _aggregate(),
        _aggregate(reference_g8=0.75),
        _aggregate(advancing=0.0),
        _aggregate(reference_g0=0.7469, shallow_g0=0.6937),
    ],
)
def test_every_outcome_carries_the_keys_the_results_parser_reads(aggregate):
    """Une sortie precoce qui omet une cle = KeyError APRES tout le calcul."""
    rec = M19.build_recommendation(aggregate, _gate())
    for key in ("status", "finding", "rung0_level_gap", "consumed_node_imbalance",
                "compute_balanced_within_m8_tolerance", "search_is_cliquet",
                "next_step", "promotable"):
        assert key in rec, key


def test_no_outcome_is_ever_promotable():
    for aggregate in (_aggregate(), _aggregate(reference_g8=0.75),
                      _aggregate(advancing=0.0)):
        assert M19.build_recommendation(aggregate, _gate())["promotable"] is False


# --------------------------------------------------------------------------- #
#  Le contrat de la config, et le contrat du job.
# --------------------------------------------------------------------------- #
def _config():
    path = _ROOT / "configs" / "l1_search_ratchet.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_config_reuses_the_m18_seeds_so_the_loops_are_identical():
    """Memes graines = memes boucles : le SEUL facteur change est la sonde."""
    assert _config()["paired_seeds"] == M19.EXPECTED_SEEDS == [
        180001, 180002, 180003, 180004, 180005
    ]


def test_config_declares_a_single_common_probe_depth_and_two_arms():
    config = _config()
    assert config["schema"] == M19.SCHEMA
    assert tuple(config["arms"]) == M19.ARM_ORDER
    assert int(config["common_probe_search_depth"]) == 32
    assert config["arms"]["shallow_depth1"]["search_depth"] == 1
    assert config["boundaries"]["promotable"] is False


def test_the_primary_contrast_is_a_level_not_a_gain():
    """Le gain est ce qui portait le biais de M18 : il ne peut pas decider."""
    config = _config()
    assert config["primary_contrasts"] == ["reference_minus_shallow_level_g8"]
    assert "reference_minus_shallow_gain" in config["secondary_contrasts"]


def test_the_job_carries_the_64kib_guard_and_merges_phase_timings():
    job = (_ROOT / "jobs" / "run_m19_search_ratchet_cpx.sh").read_text()
    assert "65536" in job and "ABORT reporting" in job
    # C : les timings doivent passer par le summary, seul canal inline.
    assert "phase_timings_seconds" in job