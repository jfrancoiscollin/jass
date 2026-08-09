"""M21 — ce qui separe « les generations apportent » de « il y a plus de donnees ».

La cellule n'a de valeur que si son contraste primaire est `MIX − G1_WIDE` et si
les comptes uniques des deux bras sont EGAUX. Ces tests verrouillent ce point,
le veto de l'arena, et le fait que la reduction des strates de `MATCHED_LATE`
est declaree plutot que dissimulee.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "run_learning_signal_composition.py"
_SPEC = importlib.util.spec_from_file_location("run_m21", _TOOL)
assert _SPEC and _SPEC.loader
M21 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M21)

SEEDS = list(range(210001, 210021))
CRITICAL = 2.093024054408263
CONTRASTS = [
    ["G1_TO_G8_MIX", "G1_WIDE"],
    ["G1_WIDE", "G1_ONLY"],
    ["G1_TO_G8_MIX", "G1_ONLY"],
    ["G8_ONLY", "G1_ONLY"],
    ["G1_PLUS_NOVEL_LATE", "G1_ONLY"],
    ["G1_PLUS_NOVEL_LATE", "G1_PLUS_MATCHED_LATE"],
]


def _gate():
    return {
        "paired_confidence_critical_95": CRITICAL,
        "minimum_practical_arena_gain": 0.050,
        "minimum_practical_learning_gain": 0.010,
    }


def _rows(mix_learning=0.10, wide_learning=0.05, mix_arena=0.70, wide_arena=0.70,
          novel_learning=0.06, matched_learning=0.06):
    levels = {
        "G1_ONLY": (0.02, 0.60),
        "G8_ONLY": (0.021, 0.60),
        "G1_TO_G8_MIX": (mix_learning, mix_arena),
        "G1_WIDE": (wide_learning, wide_arena),
        "G1_PLUS_NOVEL_LATE": (novel_learning, 0.63),
        "G1_PLUS_MATCHED_LATE": (matched_learning, 0.63),
    }
    rows = {}
    for phase, (arm, (learning, arena)) in enumerate(levels.items()):
        rows[arm] = {
            seed: {
                # Bruit DIFFERENT par bras : une fixture qui applique le meme
                # bruit partout rend les ecarts constants et tout IC degenere.
                "learning_delta": learning + 0.002 * (((index + phase) % 5) - 2),
                "arena_vs_initial": arena + 0.004 * (((index + 2 * phase) % 7) - 3),
                "unique_samples": 800,
            }
            for index, seed in enumerate(SEEDS)
        }
    return rows


def _aggregate(**kwargs):
    rows = _rows(**kwargs)
    return {"contrasts": M21.build_contrasts(rows, CONTRASTS, SEEDS, CRITICAL)}


# --------------------------------------------------------------------------- #
#  ⛔ L'ARENA DECIDE. La v1 de cette porte exigeait que le score
#  d'apprentissage passe D'ABORD ; sur cpx62-1211 le score etait non concluant
#  (+0,0141, IC traversant zero) et l'arena valait +0,2375 IC95 [+0,088 ;
#  +0,387] -- la porte a imprime FAIL sur le seul effet de la journee dont l'IC
#  excluait zero. Ces tests verrouillent la correction.
# --------------------------------------------------------------------------- #
def test_a_positive_arena_passes_even_when_the_learning_score_is_inconclusive():
    """Reproduit cpx62-1211 : arena franche, apprentissage non concluant."""
    rec = M21.build_recommendation(
        _aggregate(mix_learning=0.041, wide_learning=0.038,
                   mix_arena=0.7875, wide_arena=0.5500), _gate())
    assert rec["status"] == "PASS"
    assert rec["composition_is_the_mechanism"] is True
    assert rec["primary_endpoint"] == "arena_vs_initial"


def test_a_flat_arena_fails_whatever_the_learning_score_says():
    rec = M21.build_recommendation(
        _aggregate(mix_learning=0.20, wide_learning=0.02,
                   mix_arena=0.70, wide_arena=0.70), _gate())
    assert rec["status"] == "FAIL"
    assert rec["composition_is_the_mechanism"] is False


def test_a_confidently_negative_learning_score_is_FLAGGED_not_swallowed():
    """L'arena decide, mais une divergence doit rester visible."""
    rec = M21.build_recommendation(
        _aggregate(mix_learning=0.00, wide_learning=0.08,
                   mix_arena=0.7875, wide_arena=0.5500), _gate())
    assert rec["learning_confidently_negative"] is True
    assert rec["status"] == "PASS"


def test_an_arena_gain_below_the_practical_bar_does_not_pass():
    rec = M21.build_recommendation(
        _aggregate(mix_arena=0.72, wide_arena=0.70), _gate())
    assert rec["status"] == "FAIL"


# --------------------------------------------------------------------------- #
#  La replication : garde d'heterogeneite et chainage par precision.
# --------------------------------------------------------------------------- #
def _prior(mean=0.2375, se=0.07133):
    return {"label": "cpx62-1211", "mean": mean, "standard_error": se, "n": 20}


def _handmade(primary_arena, primary_arena_se, critical=CRITICAL):
    """Contrastes construits a la main : controle exact des moyennes ET des IC.

    Les fixtures a bruit fin donnent des IC tres serres, ce qui rend impossible
    de fabriquer le cas « ce pool seul ne conclut pas, le chainage oui ». Ici on
    pose directement la moyenne et son ecart-type.
    """
    half = critical * primary_arena_se
    flat = {"mean": 0.0, "confidence_95": [-0.01, 0.01], "count": 20, "values": []}
    return {
        "contrasts": {
            "G1_TO_G8_MIX_minus_G1_WIDE": {
                "learning": flat,
                "arena": {
                    "mean": primary_arena,
                    "confidence_95": [primary_arena - half, primary_arena + half],
                    "count": 20,
                    "values": [],
                },
            },
            "G1_WIDE_minus_G1_ONLY": {"learning": flat, "arena": flat},
            "G8_ONLY_minus_G1_ONLY": {"learning": flat, "arena": flat},
            "G1_PLUS_NOVEL_LATE_minus_G1_PLUS_MATCHED_LATE": {
                "learning": flat, "arena": flat},
        }
    }


def test_both_criteria_met_is_the_full_pass():
    gate = {**_gate(), "replication_of": _prior()}
    rec = M21.build_recommendation(_handmade(0.2375, 0.07133), gate)
    assert rec["status"] == "PASS_BOTH_CRITERIA"
    assert rec["single_pool_criterion_met"] is True
    assert rec["chained_criterion_met"] is True
    assert rec["criteria_agree"] is True


def test_the_M21R_case_the_house_chained_criterion_alone_gets_its_own_name():
    """Pool seul non concluant, chainage franc. C'est exactement cpx62-1212.

    Ce cas ne doit ni sortir FAIL -- ce serait jeter l'information des pools
    anterieurs -- ni sortir un PASS indistinct : il repose SUR le chainage, et
    le nom du statut doit le dire.
    """
    gate = {**_gate(), "replication_of": _prior()}
    rec = M21.build_recommendation(_handmade(0.1000, 0.09493), gate)
    assert rec["status"] == "PASS_CHAINED_ONLY"
    assert rec["single_pool_criterion_met"] is False
    assert rec["chained_criterion_met"] is True
    assert rec["criteria_agree"] is False
    assert rec["chained_probability_above_zero"] > 0.95


def test_a_pool_that_passes_alone_against_a_dead_chain_is_distrusted():
    gate = {**_gate(), "replication_of": _prior(mean=-0.05, se=0.02)}
    rec = M21.build_recommendation(_handmade(0.08, 0.01), gate)
    # Des pools aussi eloignes se contredisent : l'heterogeneite passe d'abord.
    assert rec["status"] == "INCONCLUSIVE"


def test_neither_criterion_met_is_a_clean_fail():
    gate = {**_gate(), "replication_of": _prior(mean=0.01, se=0.09)}
    rec = M21.build_recommendation(_handmade(0.00, 0.09), gate)
    assert rec["status"] == "FAIL"
    assert rec["chained_criterion_met"] is False
    assert "inflated" in rec["next_step"]


def test_heterogeneous_pools_are_checked_BEFORE_either_criterion():
    gate = {**_gate(), "replication_of": _prior(mean=1.20, se=0.05)}
    rec = M21.build_recommendation(_handmade(0.10, 0.05), gate)
    assert rec["status"] == "INCONCLUSIVE"
    assert rec["replication"]["pools_disagree"] is True
    assert rec["composition_is_the_mechanism"] is None


def test_three_pools_chain_and_are_checked_pairwise():
    gate = {**_gate(), "replication_of": [
        {"label": "cpx62-1211", "mean": 0.2375, "standard_error": 0.07133},
        {"label": "cpx62-1212", "mean": 0.1000, "standard_error": 0.09493},
    ]}
    rec = M21.build_recommendation(_handmade(0.15, 0.09), gate)
    check = rec["replication"]
    assert check["pool_count"] == 3
    assert len(check["pairwise_z"]) == 3        # toutes les paires, pas seulement
    assert check["pools_disagree"] is False     # la premiere
    assert check["chained_probability_above_zero"] > 0.95


def test_opposite_signs_alone_never_block_the_chaining():
    """Correction L3 du 6 aout : le SIGNE n'est pas un critere.

    Un effet vrai proche de zero produit des signes opposes une fois sur deux ;
    refuser sur ce motif, c'est refuser precisement quand la bonne reponse est
    « l'effet est nul ».
    """
    check = M21.replication_check(
        {"mean": 0.06, "confidence_95": [0.055, 0.065]},
        _prior(mean=-0.02, se=0.30), 2.093024054408263)
    assert check["same_sign"] is False          # rapporte...
    assert check["pools_disagree"] is False     # ...mais ne bloque pas


def test_the_chained_mean_is_precision_weighted():
    critical = 2.093024054408263
    check = M21.replication_check(
        {"mean": 0.10, "confidence_95": [0.10 - critical * 0.05,
                                         0.10 + critical * 0.05]},
        _prior(mean=0.30, se=0.05), critical)
    assert check["chained_mean"] == pytest.approx(0.20, abs=1e-6)
    assert check["shrinkage_vs_prior"] == pytest.approx(1.0 / 3.0, abs=1e-6)


def test_the_anticorrelation_on_recency_is_reported():
    """M21 l'a vue sur G8_ONLY : apprentissage +, arena -, les deux IC hors de zero."""
    rows = _rows()
    for index, seed in enumerate(SEEDS):
        rows["G8_ONLY"][seed]["arena_vs_initial"] = 0.40 + 0.004 * ((index % 5) - 2)
        rows["G8_ONLY"][seed]["learning_delta"] = 0.05 + 0.001 * ((index % 5) - 2)
    aggregate = {"contrasts": M21.build_contrasts(rows, CONTRASTS, SEEDS, CRITICAL)}
    rec = M21.build_recommendation(aggregate, _gate())
    assert rec["recency_shows_label_strength_anticorrelation"] is True


def test_no_outcome_is_ever_promotable():
    gate = {**_gate(), "replication_of": _prior()}
    for kwargs in ({}, {"mix_arena": 0.70, "wide_arena": 0.70},
                   {"mix_arena": 0.7875, "wide_arena": 0.5500}):
        assert M21.build_recommendation(_aggregate(**kwargs), gate)["promotable"] is False


def test_every_outcome_carries_the_keys_the_results_parser_reads():
    gate = {**_gate(), "replication_of": _prior()}
    for kwargs in ({}, {"mix_arena": 0.70, "wide_arena": 0.70},
                   {"mix_arena": 0.7875, "wide_arena": 0.5500}):
        rec = M21.build_recommendation(_aggregate(**kwargs), gate)
        for key in ("status", "finding", "primary_contrast", "primary_endpoint",
                    "primary_arena_mean", "primary_learning_mean",
                    "learning_confidently_negative", "volume_effect_arena",
                    "recency_effect_arena", "novelty_minus_matched_arena",
                    "recency_shows_label_strength_anticorrelation",
                    "composition_is_the_mechanism", "next_step", "promotable"):
            assert key in rec, key


def test_both_endpoints_are_reported_for_every_contrast():
    contrasts = M21.build_contrasts(_rows(), CONTRASTS, SEEDS, CRITICAL)
    assert len(contrasts) == len(CONTRASTS)
    for row in contrasts.values():
        assert set(row) == {"learning", "arena"}


# --------------------------------------------------------------------------- #
#  Les strates, lues dans le graphe et jamais dans l'oracle.
# --------------------------------------------------------------------------- #
class _Graph:
    """Quatre plans de 4 cases + trait + plies reversibles, comme encode_features."""

    def __init__(self):
        self.features = np.zeros((3, 4 * 4 + 2), dtype=np.float32)
        self.features[0, 0] = 1.0                    # un pion, plan 0
        self.features[1, 0] = self.features[1, 1] = 1.0   # deux pions, plan 0
        self.features[2, 0] = 1.0
        self.features[2, 16] = 1.0                   # meme materiel, trait oppose
        self.legal_mask = np.zeros((3, 5), dtype=bool)
        self.legal_mask[:, :2] = True


def test_strata_separate_material_and_side_to_move():
    keys = M21.coarse_strata(_Graph(), np.asarray([0, 1, 2], dtype=np.int64))
    assert keys[0] != keys[1], "un materiel different doit changer de strate"
    assert keys[0] != keys[2], "un trait different doit changer de strate"


def test_strata_read_no_oracle_field():
    """La strate ne touche que `features` et `legal_mask` du GRAPHE."""
    source = _TOOL.read_text()
    body = source.split("def coarse_strata")[1].split("\ndef ")[0]
    for forbidden in ("oracle.values", "optimal_mask", "dtw", "terminal_value"):
        assert forbidden not in body, forbidden


# --------------------------------------------------------------------------- #
#  Le contrat de la config.
# --------------------------------------------------------------------------- #
def _config():
    return yaml.safe_load(
        (_ROOT / "configs" / "l1_learning_signal_composition.yaml").read_text())


def test_the_primary_contrast_is_MIX_minus_G1_WIDE_and_comes_first():
    assert _config()["contrasts"][0] == ["G1_TO_G8_MIX", "G1_WIDE"]


def test_the_volume_control_arm_is_declared():
    config = _config()
    assert "G1_WIDE" in config["arms"]
    assert int(config["wide_games"]) == 1024


def test_config_commits_to_twenty_seeds():
    seeds = _config()["paired_seeds"]
    assert len(seeds) == 20 and len(set(seeds)) == 20


def test_arena_is_declared_as_a_paired_endpoint():
    assert int(_config()["arena"]["pairs"]) == 64


def test_the_strata_reduction_is_declared_not_hidden():
    """La strate preinscrite avait 4 dimensions ; on en implemente 3."""
    source = _TOOL.read_text()
    assert "matched_strata_preregistered_dimensions" in source
    assert "search-margin bin not retained per sample" in source


def test_the_job_carries_the_64kib_guard_and_merges_phase_timings():
    job = (_ROOT / "jobs" / "run_m21_learning_signal_composition_cpx.sh").read_text()
    assert "65536" in job and "ABORT reporting" in job
    assert "phase_timings_seconds" in job


def test_a_flat_pool_far_from_a_strong_prior_is_HETEROGENEITY_not_a_clean_null():
    """Un pool plat, mesure serre, contre un prior a +0,2375 : les deux se
    contredisent statistiquement. Sortir FAIL affirmerait « pas d'effet » en
    jetant le pool anterieur ; sortir INCONCLUSIVE dit la verite -- le desaccord
    EST le resultat, et il faut l'expliquer avant de chainer quoi que ce soit."""
    gate = {**_gate(), "replication_of": _prior()}
    rec = M21.build_recommendation(
        _aggregate(mix_arena=0.70, wide_arena=0.70), gate)
    assert rec["status"] == "INCONCLUSIVE"
    assert rec["finding"] == "the_pools_disagree_statistically"
    assert rec["replication"]["prior_mean"] == pytest.approx(0.2375)


def test_without_any_prior_the_cell_still_judges_on_its_own_pool():
    """Une cellule d'origine, sans pool anterieur, garde le verdict simple."""
    rec = M21.build_recommendation(_handmade(0.2375, 0.07133), _gate())
    assert rec["status"] == "PASS"
    assert "single_pool_criterion_met" not in rec
