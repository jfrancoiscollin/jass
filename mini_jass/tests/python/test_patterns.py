"""Features de patterns — l'analogue de l'archi de production.

Ce module existe parce que le laboratoire tournait sur un MLP alors que la
production est LINEAIRE sur des buckets de patterns : le banc mesurait une
boucle que la production ne peut pas reproduire, ce qui vide l'argument de
transposition au 10x10. Ces tests verrouillent la partie « features » de la
correction, et rapportent ce qui n'est PAS encore fidele.
"""
from __future__ import annotations

import numpy as np
import pytest

from mini_jass_lab.patterns import (
    PLAYABLE,
    STATES_PER_SQUARE,
    PatternSet,
    bucket_indices,
    pattern_features,
    square_states,
    window_patterns,
)


def _raw(pieces: dict[int, int], side: float = 0.0, reversible: float = 0.0):
    """Une ligne de features brutes, au format de `encode_features`."""
    row = np.zeros((1, 4 * PLAYABLE + 2), dtype=np.float32)
    for square, plane in pieces.items():
        row[0, plane * PLAYABLE + square] = 1.0
    row[0, 4 * PLAYABLE] = side
    row[0, 4 * PLAYABLE + 1] = reversible
    return row


def test_the_board_geometry_matches_the_cpp_rules():
    """13 cases jouables : `rules.hpp` fait foi, pas une supposition."""
    assert PLAYABLE == 13
    assert 4 * PLAYABLE + 2 == 54


def test_a_square_carries_one_of_five_states():
    row = _raw({0: 0, 5: 3})
    planes = row[:, : 4 * PLAYABLE].reshape(1, 4, PLAYABLE)
    states = square_states(planes)
    assert states[0, 0] == 1      # premier plan  -> etat 1
    assert states[0, 5] == 4      # quatrieme plan -> etat 4
    assert states[0, 1] == 0      # vide
    assert STATES_PER_SQUARE == 5


def test_two_pieces_on_one_square_is_refused_not_averaged():
    """Un etat impossible doit crier, pas se faire moyenner en silence."""
    planes = np.zeros((1, 4, PLAYABLE), dtype=np.float32)
    planes[0, 0, 3] = 1.0
    planes[0, 2, 3] = 1.0
    with pytest.raises(ValueError, match="two pieces at once"):
        square_states(planes)


def test_windows_that_cover_the_same_playable_squares_are_deduplicated():
    """Deux fenetres identiques en cases jouables doubleraient leurs poids."""
    for window in (2, 3, 4):
        patterns = window_patterns(window)
        assert len(patterns) == len(set(patterns))
        assert all(len(p) >= 2 for p in patterns)


def test_a_pattern_bucket_is_the_CONJUNCTION_of_its_squares():
    """Le bucket doit changer des qu'UNE case du pattern change d'etat."""
    pattern_set = PatternSet.from_window(2)
    first = pattern_set.patterns[0]
    base = np.zeros((2, PLAYABLE), dtype=np.int64)
    base[1, first[0]] = 3
    index = bucket_indices(base, pattern_set)
    assert index[0, 0] != index[1, 0]


def test_buckets_of_different_patterns_never_collide():
    """Chaque pattern a sa propre table : les offsets doivent la garantir."""
    pattern_set = PatternSet.from_window(3)
    states = np.zeros((1, PLAYABLE), dtype=np.int64)
    index = bucket_indices(states, pattern_set)[0]
    assert len(set(index.tolist())) == len(pattern_set.patterns)
    assert index.max() < pattern_set.bucket_count


def test_exactly_one_bucket_per_pattern_is_active():
    pattern_set = PatternSet.from_window(2)
    dense = pattern_features(_raw({0: 0, 6: 1}), pattern_set)
    active = dense[0, : pattern_set.bucket_count]
    assert active.sum() == pytest.approx(len(pattern_set.patterns))
    assert set(np.unique(active).tolist()) <= {0.0, 1.0}


def test_the_extras_are_carried_through_untouched():
    """La production a elle aussi un bloc d'extras a cote des buckets."""
    pattern_set = PatternSet.from_window(2)
    dense = pattern_features(_raw({}, side=1.0, reversible=0.25), pattern_set)
    assert dense[0, -2] == pytest.approx(1.0)
    assert dense[0, -1] == pytest.approx(0.25)
    assert dense.shape[1] == pattern_set.bucket_count + 2


def test_the_value_only_size_is_what_makes_the_production_shape_reachable():
    """La tete policy pese 98,6 % du modele : c'est ELLE qui empeche l'archi.

    Chiffres mesures : patterns 3x3 avec tete policy = 1 323 344 parametres ;
    valeur seule = 18 128. La production est valeur seule et derive les coups de
    la recherche -- tant qu'on garde deux tetes, un modele de patterns de taille
    raisonnable est hors d'atteinte.
    """
    pattern_set = PatternSet.from_window(3)
    inputs = pattern_set.bucket_count + 2
    value_only = inputs + 1
    with_policy = value_only + inputs * 72 + 72
    assert value_only == 18128
    assert with_policy > 50 * value_only


def test_the_missing_symmetry_fold_is_declared_not_hidden():
    """A L3 le pli exact vaut +17,1 Elo. Ici il n'est pas fait, et ca se dit."""
    assert PatternSet.from_window(2).describe()["symmetry_folded"] is False
