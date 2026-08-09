"""M23-A — ce qui empeche un ecran a sept bras de fabriquer un faux resultat.

Deux dangers, tous deux mesures sur ce banc :
  - le VOLUME : `CURRENT_ONLY` naif n'a qu'un `unit` d'uniques la ou un melange
    en a deux ; sans egalisation, la cellule mesure « loi + volume ». C'est le
    piege que `G1_WIDE` a leve dans M21.
  - la SELECTION : garder le maximum de six contrastes porte ~26 % de faux
    positif sous H0, et la campagne a chiffre trois fois le degonflement entre
    selection et replication (x0,30, x0,04, x0,42).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_TOOL = _ROOT / "tools" / "run_mix_strategy_screen.py"
_SPEC = importlib.util.spec_from_file_location("run_m23", _TOOL)
assert _SPEC and _SPEC.loader
M23 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(M23)

SEEDS = list(range(240001, 240021))
CRITICAL = 2.093024054408263


def _gate():
    return {
        "paired_confidence_critical_95": CRITICAL,
        "minimum_practical_arena_gain": 0.05,
    }


def _rows(primary_gain=0.26, shape_gains=None):
    """`CURRENT_ONLY_WIDE` est la reference ; les autres bras s'en ecartent."""
    shape_gains = shape_gains or {}
    base = {"CURRENT_ONLY_WIDE": 0.0, "UNIFORM_HISTORY_50": primary_gain}
    for arm in M23.ARM_ORDER:
        base.setdefault(arm, shape_gains.get(arm, 0.05))
    rows = {}
    for phase, arm in enumerate(M23.ARM_ORDER):
        rows[arm] = {
            seed: {
                "arena_vs_initial": 0.55 + base[arm]
                + 0.004 * (((index + phase) % 7) - 3),
                "learning_delta": 0.36 + 0.01 * base[arm]
                + 0.002 * (((index + 2 * phase) % 5) - 2),
                "unique_samples": 1392,
            }
            for index, seed in enumerate(SEEDS)
        }
    return rows


def _aggregate(**kwargs):
    return {"contrasts": M23.build_contrasts(_rows(**kwargs), SEEDS, CRITICAL)}


# --------------------------------------------------------------------------- #
#  L'egalisation des uniques : fail-closed, pas une ligne de config.
# --------------------------------------------------------------------------- #
class _Sample:
    def __init__(self, state_id, generation):
        self.state_id = state_id
        self.generation = generation


def _pack(sizes):
    return {g: [_Sample(g * 10_000 + i, g) for i in range(n)]
            for g, n in enumerate(sizes, start=1)}


def _config_for_pools():
    return yaml.safe_load(
        (_ROOT / "configs" / "l1_mix_strategy_screen.yaml").read_text())


def test_every_arm_holds_exactly_the_same_unique_count():
    pools, census = M23.build_pools(
        _pack([120] * 8), [_Sample(9_000_000 + i, 8) for i in range(1000)],
        _config_for_pools(), seed=1)
    assert census["target_unique_samples"] == 240
    assert set(census["unique_samples_by_arm"].values()) == {240}
    assert set(pools) == set(M23.ARM_ORDER)


def test_a_wide_current_pool_too_small_fails_closed():
    """Sans assez de parties elargies, CURRENT_ONLY_WIDE ne peut pas etre
    volume-apparie -- et la cellule doit REFUSER, pas rendre un bras plus maigre."""
    with pytest.raises(ValueError, match="pool needs"):
        M23.build_pools(_pack([120] * 8),
                        [_Sample(9_000_000 + i, 8) for i in range(50)],
                        _config_for_pools(), seed=1)


def test_the_half_current_arms_never_over_draw_generation_eight():
    """La cible `2 x unit` existe pour que « 50 % courant » tienne dans G8."""
    pools, census = M23.build_pools(
        _pack([90, 100, 110, 120, 130, 140, 150, 90]),
        [_Sample(9_000_000 + i, 8) for i in range(1000)],
        _config_for_pools(), seed=7)
    assert census["unit_samples_per_generation"] == 90
    assert census["target_unique_samples"] == 180
    for arm in ("UNIFORM_HISTORY_50", "RECENT_WINDOW_50", "EXP_DECAY_50"):
        current = [s for s in pools[arm] if s.generation == 8]
        assert len(current) == 90


def test_reservoir_and_uniform_history_are_actually_different_laws():
    """L'un est uniforme sur les GENERATIONS, l'autre sur les ECHANTILLONS."""
    pools, _ = M23.build_pools(
        _pack([50, 50, 50, 50, 50, 50, 400, 50]),
        [_Sample(9_000_000 + i, 8) for i in range(1000)],
        _config_for_pools(), seed=3)
    from_g7_uniform = sum(1 for s in pools["UNIFORM_HISTORY_50"] if s.generation == 7)
    from_g7_reservoir = sum(1 for s in pools["RESERVOIR_50"] if s.generation == 7)
    # G7 est 8x plus grosse : le reservoir doit y puiser bien davantage.
    assert from_g7_reservoir > from_g7_uniform


# --------------------------------------------------------------------------- #
#  Un seul contraste conclut ; les cinq autres ne font qu'un candidat.
# --------------------------------------------------------------------------- #
def test_the_primary_is_the_only_contrast_that_can_conclude():
    contrasts = M23.build_contrasts(_rows(), SEEDS, CRITICAL)
    roles = {name: row["role"] for name, row in contrasts.items()}
    assert sum(1 for r in roles.values() if r == "primary") == 1
    assert roles["UNIFORM_HISTORY_50_minus_CURRENT_ONLY_WIDE"] == "primary"
    assert sum(1 for r in roles.values() if r == "exploratory") == 5


def test_a_clear_primary_passes_but_the_shape_stays_a_candidate():
    rec = M23.build_recommendation(_aggregate(), _gate())
    assert rec["status"] == "PASS_PRIMARY_SHAPE_UNRESOLVED"
    assert rec["mixing_beats_current_only"] is True
    assert rec["screen_never_concludes_on_shape"] is True
    assert rec["shape_candidate"]["is_a_result"] is False
    assert rec["shape_candidate"]["requires_fresh_seed_replication"] is True


def test_the_best_shape_is_named_but_never_promoted_to_a_result():
    """Meme un bras de forme spectaculaire reste un candidat."""
    rec = M23.build_recommendation(
        _aggregate(shape_gains={"ANCHOR_50": 0.40}), _gate())
    assert rec["shape_candidate"]["arm"] == "ANCHOR_50"
    assert rec["shape_candidate"]["arena_mean_AT_SELECTION"] == pytest.approx(
        0.40, abs=0.02)
    assert rec["shape_candidate"]["is_a_result"] is False


def test_a_flat_primary_fails_whatever_the_shapes_do():
    rec = M23.build_recommendation(
        _aggregate(primary_gain=0.0, shape_gains={"ANCHOR_50": 0.40}), _gate())
    assert rec["status"] == "FAIL"
    assert rec["mixing_beats_current_only"] is False


def test_no_outcome_is_ever_promotable():
    for kwargs in ({}, {"primary_gain": 0.0}, {"shape_gains": {"ANCHOR_50": 0.4}}):
        assert M23.build_recommendation(_aggregate(**kwargs), _gate())["promotable"] is False


def test_every_outcome_carries_the_keys_the_results_parser_reads():
    for kwargs in ({}, {"primary_gain": 0.0}):
        rec = M23.build_recommendation(_aggregate(**kwargs), _gate())
        for key in ("status", "finding", "primary_contrast", "primary_arena_mean",
                    "primary_arena_ci95", "screen_never_concludes_on_shape",
                    "shape_candidate", "arms_compared", "mixing_beats_current_only",
                    "next_step", "promotable"):
            assert key in rec, key


# --------------------------------------------------------------------------- #
#  Le contrat de la config.
# --------------------------------------------------------------------------- #
def test_seeds_are_fresh_and_the_guard_refuses_the_three_consumed_families():
    config = _config_for_pools()
    seeds = set(config["paired_seeds"])
    assert len(seeds) == 20
    for lower in (210001, 220001, 230001):
        assert not seeds & set(range(lower, lower + 20))


def test_the_named_primary_is_in_the_config_and_matches_the_tool():
    config = _config_for_pools()
    assert config["primary_contrast"] == list(M23.PRIMARY)
    assert config["shape_contrasts_are_exploratory"] is True


def test_current_only_is_volume_matched_not_naive():
    arms = _config_for_pools()["arms"]
    assert "CURRENT_ONLY" not in arms, "le bras naif serait confondu par le volume"
    assert arms["CURRENT_ONLY_WIDE"]["volume_matched_by"] == "wider_generation_8"


def test_the_followup_sizes_on_the_replicated_effect_not_the_screen_maximum():
    followup = _config_for_pools()["followup"]
    assert followup["selected_shape_requires_fresh_seed_replication"] is True
    assert followup["size_replication_on_replicated_effect_not_on_screen_maximum"] is True


def test_the_job_carries_the_64kib_guard_and_merges_phase_timings():
    job = (_ROOT / "jobs" / "run_m23_mix_strategy_screen_cpx.sh").read_text()
    assert "65536" in job and "ABORT reporting" in job
    assert "phase_timings_seconds" in job
