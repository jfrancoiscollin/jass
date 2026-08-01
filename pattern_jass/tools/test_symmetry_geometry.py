# SPDX-License-Identifier: AGPL-3.0-or-later
"""Quelles transformations du plateau sont VRAIMENT des symétries.

Ce fichier existe parce qu'un docstring a affirmé pendant longtemps que la
réflexion gauche-droite était « exacte, signe +1 ». Elle ne l'est pas, et un fold
a été construit sur cette affirmation avant qu'une question de JFC ne la mette en
doute : *si LR donnait la moitié des poids gratuitement, pourquoi Scan ne le
ferait-il pas ?*

Le critère est mécanique et ne dépend d'aucune convention d'écriture : **une
symétrie du damier préserve l'adjacence diagonale**. Deux cases jouables voisines
en diagonale doivent le rester après transformation, sinon la transformation
n'envoie pas des coups légaux sur des coups légaux et ne peut pas laisser
l'évaluation invariante.

Toute transformation ajoutée à `symmetry.py` doit passer ici AVANT d'être pliée.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def coord(n):
    """Case FMJD 1..50 -> (rangée, colonne) sur le damier 10x10."""
    r = (n - 1) // 5
    return r, 2 * ((n - 1) % 5) + (1 if r % 2 == 0 else 0)


def diagonally_adjacent(a, b):
    ra, ca = coord(a)
    rb, cb = coord(b)
    return abs(ra - rb) == 1 and abs(ca - cb) == 1


ADJACENT_PAIRS = [(a, b) for a in range(1, 51) for b in range(a + 1, 51)
                  if diagonally_adjacent(a, b)]


def broken_by(f):
    """Paires adjacentes que `f` cesse de rendre adjacentes."""
    return [(a, b) for a, b in ADJACENT_PAIRS
            if not diagonally_adjacent(f(a), f(b))]


def rot180(n):
    return 51 - n


def left_right(n):
    """La transformation que `symmetry.lr_structure` applique : inverser les cinq
    cases jouables dans chaque rangée."""
    r, i = (n - 1) // 5, (n - 1) % 5
    return r * 5 + (4 - i) + 1


class TheBoardHasEightyOneAdjacencies(unittest.TestCase):
    def test_the_count_is_what_a_10x10_draughts_board_has(self):
        self.assertEqual(len(ADJACENT_PAIRS), 81)

    def test_square_1_touches_6_and_7(self):
        self.assertTrue(diagonally_adjacent(1, 6))
        self.assertTrue(diagonally_adjacent(1, 7))

    def test_square_5_is_on_the_edge_and_touches_only_10(self):
        self.assertTrue(diagonally_adjacent(5, 10))
        self.assertFalse(diagonally_adjacent(5, 9))


class Rot180IsASymmetry(unittest.TestCase):
    def test_it_preserves_every_adjacency(self):
        self.assertEqual(broken_by(rot180), [])

    def test_it_is_an_involution(self):
        for n in range(1, 51):
            self.assertEqual(rot180(rot180(n)), n)


class LeftRightIsNOTASymmetry(unittest.TestCase):
    """Le test qui a coûté un job tué. Il doit rester rouge-si-on-ment.

    Géométriquement : un miroir gauche-droite d'un damier 10x10 envoie les cases
    sombres sur les claires. La surface de jeu n'est pas conservée, donc il n'y a
    pas de réflexion gauche-droite du jeu de dames — seulement de l'échiquier vu
    comme un quadrillage.
    """

    def test_it_breaks_diagonal_adjacency(self):
        broken = broken_by(left_right)
        self.assertEqual(len(broken), 36)
        self.assertIn((1, 7), broken)

    def test_the_concrete_counterexample(self):
        """1 et 7 se touchent ; leurs images 5 et 9 ne se touchent pas — 5 est au
        bord droit et ne descend que sur 10."""
        self.assertTrue(diagonally_adjacent(1, 7))
        self.assertEqual((left_right(1), left_right(7)), (5, 9))
        self.assertFalse(diagonally_adjacent(5, 9))


class TheExactFoldUsesOnlyRealSymmetries(unittest.TestCase):
    def test_build_exact_canon_takes_no_reflect_argument(self):
        """Si quelqu'un rouvre la porte, il devra d'abord faire passer LR au test
        d'adjacence ci-dessus — ce qu'elle ne peut pas."""
        import inspect

        import symmetry as S
        self.assertEqual(list(inspect.signature(S.build_exact_canon).parameters), [])

    def test_the_canonical_space_is_the_rot180_cs_one(self):
        import numpy as np

        import patterns as P
        import symmetry as S
        canon, _ = S.build_exact_canon()
        self.assertEqual(len(np.unique(canon)),
                         3 ** P.PATTERN_SIZE * P.NUM_PATTERNS // 2)


if __name__ == "__main__":
    unittest.main()
