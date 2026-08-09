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
    SQUARE_ROT180,
    STATE_COLOUR_SWAP,
    STATES_PER_SQUARE,
    PatternSet,
    fold_image_map,
    fold_map,
    folded_class_count,
    perspective_fold_map,
    perspective_folded_class_count,
    rot180_preserves_diagonal_adjacency,
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


# --------------------------------------------------------------------------- #
#  LE PLI EXACT `rot180 ∘ colour-swap`.
# --------------------------------------------------------------------------- #
def test_rot180_preserves_diagonal_adjacency_before_anything_is_folded():
    """Le critere non negociable de L3, ou le pli melangerait des positions
    qui ne se correspondent pas. Le miroir gauche-droite y echoue a 10x10."""
    assert rot180_preserves_diagonal_adjacency() is True


def test_rot180_is_an_involution_on_the_playable_squares():
    for square in range(PLAYABLE):
        assert SQUARE_ROT180[SQUARE_ROT180[square]] == square


def test_the_colour_swap_exchanges_men_and_kings_by_colour():
    """Plans : white_men, black_men, white_kings, black_kings -> etats 1..4."""
    assert STATE_COLOUR_SWAP == (0, 2, 1, 4, 3)
    for state in range(STATES_PER_SQUARE):
        assert STATE_COLOUR_SWAP[STATE_COLOUR_SWAP[state]] == state


def test_the_complete_bucket_image_is_an_involution():
    pattern_set = PatternSet.from_window(3)
    images = fold_image_map(pattern_set)
    assert np.array_equal(images[images], np.arange(pattern_set.bucket_count))


def test_the_side_aware_fold_pairs_opposite_turns_without_losing_turn_information():
    pattern_set = PatternSet.from_window(3)
    classes = perspective_fold_map(pattern_set)
    assert classes.shape == (2 * pattern_set.bucket_count,)
    assert perspective_folded_class_count(pattern_set) == pattern_set.bucket_count


def test_the_fold_is_idempotent_and_halves_the_free_parameters():
    """Une involution a peu de points fixes doit mutualiser environ la moitie."""
    for window in (2, 3):
        pattern_set = PatternSet.from_window(window)
        classes = fold_map(pattern_set)
        assert np.array_equal(classes[classes], classes)   # idempotent
        share = folded_class_count(pattern_set) / pattern_set.bucket_count
        assert 0.45 < share < 0.55


def test_folding_only_ever_merges_buckets_never_invents_one():
    pattern_set = PatternSet.from_window(2)
    classes = fold_map(pattern_set)
    assert classes.max() < pattern_set.bucket_count
    assert folded_class_count(pattern_set) < pattern_set.bucket_count


def test_a_pattern_set_not_closed_under_rot180_is_refused():
    """Plier hors de l'espace represente enverrait un bucket nulle part."""
    base = PatternSet.from_window(2)
    truncated = PatternSet(base.patterns[:1], (0,),
                           STATES_PER_SQUARE ** len(base.patterns[0]))
    with pytest.raises(ValueError, match="not closed under rot180"):
        fold_map(truncated)


def test_the_describe_block_reports_the_fold_rather_than_claiming_none():
    described = PatternSet.from_window(2).describe()
    assert described["fold"] == "rot180_colour_swap"
    assert described["folded_class_count"] < described["bucket_count"]
    assert described["side_aware_folded_class_count"] == described["bucket_count"]
