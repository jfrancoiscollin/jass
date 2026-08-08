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
#  Le primaire, et le piege qu'il evite.
# --------------------------------------------------------------------------- #
def test_generation_identity_beating_equal_volume_is_the_mechanism():
    rec = M21.build_recommendation(_aggregate(), _gate())
    assert rec["status"].startswith("PASS")
    assert rec["composition_is_the_mechanism"] is True
    assert rec["primary_contrast"] == "G1_TO_G8_MIX_minus_G1_WIDE"


def test_a_gain_that_G1_WIDE_reproduces_is_VOLUME_not_generations():
    """Le scenario que la cellule existe pour distinguer : MIX > G1_ONLY, mais
    G1_WIDE fait aussi bien que MIX. Ce n'est pas l'identite de generation."""
    rec = M21.build_recommendation(
        _aggregate(mix_learning=0.10, wide_learning=0.10), _gate())
    assert rec["status"] == "FAIL"
    assert rec["composition_is_the_mechanism"] is False
    assert rec["next_step"] == "M22_isolate_the_sequential_optimizer_path"
    # Et le volume est chiffre, pas seulement ecarte.
    assert rec["volume_effect_learning"] > 0.0


def test_the_arena_has_a_veto_over_the_learning_score():
    """Preinscrit : si les deux criteres se contredisent, rien n'est valide."""
    rec = M21.build_recommendation(
        _aggregate(mix_arena=0.55, wide_arena=0.75), _gate())
    assert rec["status"] == "PASS_LEARNING_BUT_WEAKER_MODEL"
    assert rec["composition_is_the_mechanism"] is False
    assert "do_not_endorse" in rec["next_step"]


def test_a_gain_below_the_practical_bar_does_not_pass():
    rec = M21.build_recommendation(
        _aggregate(mix_learning=0.055, wide_learning=0.05), _gate())
    assert rec["status"] == "FAIL"


def test_an_unresolved_novelty_contrast_downgrades_the_pass():
    """MIX gagne, mais nouveaute et appariement sont indiscernables."""
    rec = M21.build_recommendation(
        _aggregate(novel_learning=0.06, matched_learning=0.06), _gate())
    assert rec["status"] == "PASS_COMPOSITION_MECHANISM_UNRESOLVED"
    assert rec["mechanism_attributed"] is False


def test_a_resolved_novelty_contrast_gives_a_full_pass():
    rec = M21.build_recommendation(
        _aggregate(novel_learning=0.09, matched_learning=0.04), _gate())
    assert rec["status"] == "PASS"
    assert rec["mechanism_attributed"] is True


def test_no_outcome_is_ever_promotable():
    for kwargs in ({}, {"wide_learning": 0.10}, {"mix_arena": 0.55, "wide_arena": 0.75}):
        assert M21.build_recommendation(_aggregate(**kwargs), _gate())["promotable"] is False


def test_every_outcome_carries_the_keys_the_results_parser_reads():
    for kwargs in ({}, {"wide_learning": 0.10}, {"mix_arena": 0.55, "wide_arena": 0.75},
                   {"novel_learning": 0.06, "matched_learning": 0.06}):
        rec = M21.build_recommendation(_aggregate(**kwargs), _gate())
        for key in ("status", "finding", "primary_contrast", "volume_effect_learning",
                    "recency_effect_learning", "novelty_minus_matched_learning",
                    "composition_is_the_mechanism", "next_step", "promotable"):
            assert key in rec, key


def test_both_endpoints_are_reported_for_every_contrast():
    contrasts = M21.build_contrasts(_rows(), CONTRASTS, SEEDS, CRITICAL)
    assert len(contrasts) == len(CONTRASTS)
    for row in contrasts.values():
        assert set(row) == {"learning", "arena"}
        assert "confidence_95" in row["learning"] and "confidence_95" in row["arena"]


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
