"""M20 — l'opposition EST le resultat, et un seul cote ne prouve rien.

Le motif de M18/M19 (etiquettes hautes, arena basse) repose sur quatre bras qui
different par des choses differentes, et sur des scores d'arena sans IC. Ces
tests verrouillent ce qui transforme un motif en resultat : deux paires a un
seul facteur, les DEUX criteres apparies avec IC, et une conclusion qui exige
les signes opposes ET les deux IC hors de zero.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "run_label_quality_vs_strength.py"
_SPEC = importlib.util.spec_from_file_location("run_m20", _TOOL)
assert _SPEC and _SPEC.loader
M20 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M20)

SEEDS = list(range(200001, 200021))
CRITICAL = 2.093024054408263
PAIRS = {
    "promotion": {
        "high_label_arm": "forced_advance",
        "reference_arm": "gate_arena",
        "single_factor": "promotion_rule",
    }
}


def _gate():
    return {
        "paired_confidence_critical_95": CRITICAL,
        "minimum_practical_label_gap": 0.010,
        "minimum_practical_arena_gap": 0.050,
        "maximum_rung0_level_gap": 0.0001,
        "maximum_reference_arm_divergence": 0.0,
    }


def _rows(label_hi, arena_hi, label_ref=0.79, arena_ref=0.70,
          rung0_hi=0.7469, rung0_ref=0.7469, jitter=0.002):
    """Bruit par graine, ET DIFFERENT ENTRE BRAS.

    ⚠️ Une fixture qui applique le MEME bruit aux deux bras rend les ecarts
    par graine strictement constants : variance nulle, IC degenere, correlation
    indefinie. Elle serait PLUS UNIFORME QUE LA REALITE — l'erreur exacte qui a
    laisse passer la garde d'appariement de `cpx62-1208`. Chaque bras a donc sa
    propre phase de bruit, comme deux executions reelles.
    """
    def make(label, arena, rung0, phase):
        return [
            {
                "seed": seed,
                "probe_start_signature": f"sig-{seed}",
                "by_rung": {
                    "0": {"probe_start_wdl": {"exact_rate": rung0}},
                    "8": {"probe_start_wdl": {
                        "exact_rate": label + jitter * (((index + phase) % 5) - 2)}},
                },
                "final_arena_vs_initial": {
                    "score": arena + jitter * (((index + 2 * phase) % 7) - 3)},
                "advancing_generations": 3,
                "loop_consumed_nodes": 50000,
                "oracle_causal_reads": 0,
            }
            for index, seed in enumerate(SEEDS)
        ]

    return {
        "forced_advance": make(label_hi, arena_hi, rung0_hi, phase=0),
        "gate_arena": make(label_ref, arena_ref, rung0_ref, phase=3),
    }


def _aggregate(rows, divergence=0.0):
    return {
        "pairs": M20.build_pair_contrasts(rows, PAIRS, SEEDS, CRITICAL),
        "execution": {"reference_arm_divergence": divergence},
    }


# --------------------------------------------------------------------------- #
#  Le coeur : il faut LES DEUX cotes, et opposes.
# --------------------------------------------------------------------------- #
def test_the_measured_pattern_reproduced_is_an_anti_correlation():
    """Chiffres de M18 : etiquettes +0,034, arena -0,25."""
    rec = M20.build_recommendation(
        _aggregate(_rows(label_hi=0.825, arena_hi=0.45)), _gate())
    assert rec["status"] == "PASS"
    assert rec["anti_correlation_established"] is True
    assert rec["pairs"]["promotion"]["signs_opposed"] is True
    assert rec["next_step"].startswith("stop_using_label_exactness_as_a_proxy")


def test_both_endpoints_moving_the_SAME_way_is_not_an_anti_correlation():
    """Meilleures etiquettes ET meilleure arena : le motif est simplement faux."""
    rec = M20.build_recommendation(
        _aggregate(_rows(label_hi=0.825, arena_hi=0.90)), _gate())
    assert rec["status"] == "FAIL"
    assert rec["pairs"]["promotion"]["signs_opposed"] is False


def test_a_label_gap_alone_proves_nothing_without_the_arena_side():
    """L'arena ne bouge pas : c'est exactement le cas que M18 ne pouvait exclure."""
    rec = M20.build_recommendation(
        _aggregate(_rows(label_hi=0.825, arena_hi=0.70)), _gate())
    assert rec["status"] == "FAIL"
    assert rec["pairs"]["promotion"]["label_gap_practical_and_confident"] is True
    assert rec["pairs"]["promotion"]["arena_gap_practical_and_confident"] is False
    assert rec["pairs"]["promotion"]["anti_correlated"] is False


def test_an_arena_gap_alone_proves_nothing_either():
    rec = M20.build_recommendation(
        _aggregate(_rows(label_hi=0.79, arena_hi=0.45)), _gate())
    assert rec["status"] == "FAIL"
    assert rec["pairs"]["promotion"]["anti_correlated"] is False


def test_opposed_signs_below_the_practical_bars_do_not_pass():
    """Signes opposes mais effets minuscules : pas un resultat."""
    rec = M20.build_recommendation(
        _aggregate(_rows(label_hi=0.7920, arena_hi=0.690)), _gate())
    assert rec["anti_correlation_established"] is False


# --------------------------------------------------------------------------- #
#  Les controles.
# --------------------------------------------------------------------------- #
def test_an_uncommon_probe_makes_the_cell_inconclusive_not_negative():
    """Le defaut de M18 : niveaux non comparables au barreau 0."""
    rows = _rows(label_hi=0.825, arena_hi=0.45, rung0_hi=0.6937)
    rec = M20.build_recommendation(_aggregate(rows), _gate())
    assert rec["status"] == "INCONCLUSIVE"
    assert rec["finding"] == "probe_was_not_common_rung0_label_levels_differ"
    assert rec["anti_correlation_established"] is None


def test_identical_reference_arms_that_diverge_fail_the_harness_check():
    """gate_arena et depth32 ont la meme spec : diverger = harnais non deterministe."""
    rows = _rows(label_hi=0.825, arena_hi=0.45)
    rows["depth32"] = [dict(row) for row in rows["gate_arena"]]
    rows["depth32"][7] = {**rows["depth32"][7],
                          "final_arena_vs_initial": {"score": 0.42}}
    with pytest.raises(ValueError, match="diverged by"):
        M20.assert_reference_arms_agree(rows, SEEDS, 0.0)


def test_identical_reference_arms_that_agree_pass_the_harness_check():
    rows = _rows(label_hi=0.825, arena_hi=0.45)
    rows["depth32"] = [dict(row) for row in rows["gate_arena"]]
    assert M20.assert_reference_arms_agree(rows, SEEDS, 0.0) == 0.0


def test_the_probe_guard_allows_per_seed_variation_but_not_per_arm():
    """La garde qui a tue cpx62-1208, reprise correctement."""
    rows = _rows(label_hi=0.825, arena_hi=0.45)
    M20.assert_paired_probe_schedules(rows, SEEDS)
    rows["forced_advance"][3] = {**rows["forced_advance"][3],
                                 "probe_start_signature": "sig-OTHER"}
    with pytest.raises(ValueError, match=f"seed={SEEDS[3]}"):
        M20.assert_paired_probe_schedules(rows, SEEDS)


def test_within_pair_correlation_is_reported():
    contrasts = M20.build_pair_contrasts(
        _rows(label_hi=0.825, arena_hi=0.45), PAIRS, SEEDS, CRITICAL)
    assert contrasts["promotion"]["within_pair_correlation"] is not None


def test_no_outcome_is_ever_promotable():
    for rows in (_rows(0.825, 0.45), _rows(0.825, 0.90), _rows(0.79, 0.70)):
        assert M20.build_recommendation(_aggregate(rows), _gate())["promotable"] is False


# --------------------------------------------------------------------------- #
#  Le contrat de la config : la puissance, et les graines fraiches.
# --------------------------------------------------------------------------- #
def _config():
    return yaml.safe_load(
        (_ROOT / "configs" / "l1_label_quality_vs_strength.yaml").read_text())


def test_config_commits_to_twenty_seeds_because_power_is_nearly_free():
    seeds = _config()["paired_seeds"]
    assert len(seeds) == 20 and len(set(seeds)) == 20


def test_config_does_not_reuse_the_seeds_that_suggested_the_pattern():
    """Rejouer le motif sur son propre tirage, ce n'est pas le tester."""
    assert not set(_config()["paired_seeds"]) & {180001, 180002, 180003, 180004, 180005}


def test_config_declares_two_single_factor_pairs():
    pairs = _config()["pairs"]
    assert set(pairs) == {"promotion", "depth"}
    assert pairs["promotion"]["single_factor"] == "promotion_rule"
    assert pairs["depth"]["single_factor"] == "selfplay_search_depth"


def test_the_two_reference_arms_share_one_specification():
    arms = _config()["arms"]
    assert arms["gate_arena"] == arms["depth32"]


def test_critical_value_matches_nineteen_degrees_of_freedom():
    """20 graines appariees : t(0,975 ; 19) = 2,093, pas le 2,776 de n=5."""
    assert _config()["scientific_gate"]["paired_confidence_critical_95"] == pytest.approx(
        2.093024054408263)


def test_the_job_carries_the_64kib_guard_and_merges_phase_timings():
    job = (_ROOT / "jobs" / "run_m20_label_quality_vs_strength_cpx.sh").read_text()
    assert "65536" in job and "ABORT reporting" in job
    assert "phase_timings_seconds" in job
