#!/usr/bin/env python3
"""Le compteur de couverture doit compter dans l'espace que le fit optimise.

Depuis le 1er août 2026 tout fit L3 tourne sous `--exact-fold`. Un audit de
couverture resté en `--color-fold` mesurerait un autre espace de buckets et
rendrait un chiffre qui *ressemble* à de la couverture sans en être.

Le contrôle décisif ne porte pas sur des cardinaux mais sur la sémantique :
une position et son image par `rot180 ∘ colour-swap` sont la MÊME position pour
le modèle exact, donc elles doivent toucher exactement les mêmes buckets. Le
fold couleur, lui, ne peut pas le faire — et c'est précisément l'inversion de
contrainte que la campagne a payée 17 Elo.
"""
from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pattern_jass" / "tools"))

MODULE = ROOT / "jobs" / "tools" / "l3_bucket_visits.py"
SPEC = importlib.util.spec_from_file_location("l3_bucket_visits", MODULE)
BV = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = BV
SPEC.loader.exec_module(BV)

import patterns as P  # noqa: E402  (après l'insertion du PYTHONPATH 8cf)


def rot180_colourswap(black_men, white_men):
    """La seule symétrie exacte du damier : demi-tour + échange des couleurs.

    Sur 50 cases, le demi-tour envoie la case `n` sur `51 - n`, soit le
    renversement des 50 bits.
    """
    def rev50(x):
        out = np.zeros_like(x)
        for i in range(50):
            out |= ((x >> np.uint64(i)) & np.uint64(1)) << np.uint64(49 - i)
        return out
    return rev50(white_men), rev50(black_men)


def random_positions(n, seed):
    rng = np.random.default_rng(seed)
    black = rng.integers(0, 1 << 50, size=n, dtype=np.uint64)
    white = rng.integers(0, 1 << 50, size=n, dtype=np.uint64) & ~black
    return black, white


class TheExactFoldIdentifiesTheSymmetricPosition(unittest.TestCase):
    def setUp(self):
        self.black, self.white = random_positions(400, seed=11)
        self.image = rot180_colourswap(self.black, self.white)

    def _agreement(self, folder):
        a = np.sort(folder.columns(self.black, self.white), axis=1)
        b = np.sort(folder.columns(*self.image), axis=1)
        return int((a == b).all(axis=1).sum())

    def test_exact_fold_maps_both_to_the_same_buckets(self):
        self.assertEqual(self._agreement(BV.ExactFolder()), 400)

    def test_colour_fold_does_not(self):
        """Rouge si quelqu'un « corrige » le fold couleur pour qu'il y arrive :
        il ne le peut pas, et prétendre le contraire est l'erreur d'origine."""
        self.assertEqual(self._agreement(BV.ColorFolder()), 0)


class TheDenominatorIsTheRealParameterSpace(unittest.TestCase):
    def test_exact_space_is_half_the_unfolded_one(self):
        self.assertEqual(BV.ExactFolder().TB,
                         P.NUM_PATTERNS * 3 ** P.PATTERN_SIZE // 2)

    def test_columns_stay_inside_the_dense_range(self):
        folder = BV.ExactFolder()
        cols = folder.columns(*random_positions(300, seed=5))
        self.assertGreaterEqual(int(cols.min()), 0)
        self.assertLess(int(cols.max()), folder.TB)

    def test_the_two_folds_do_not_share_a_denominator(self):
        self.assertNotEqual(BV.ExactFolder().TB, BV.ColorFolder().TB)


class TheReportSaysWhichFoldProducedIt(unittest.TestCase):
    """Deux nombres non comparables ne doivent pas pouvoir être confondus."""

    def _write(self, path, black, white):
        rec = np.zeros(len(black), dtype=BV.JNNW_DTYPE)
        rec["bm"] = black
        rec["wm"] = white
        with open(path, "wb") as fh:
            fh.write(b"JNNW" + struct.pack("<I", len(black)))
            fh.write(rec.tobytes())

    def _corpus(self, path, n=64):
        self._write(path, *random_positions(n, seed=3))

    def test_fold_is_reported_and_per_pattern_is_withheld_when_meaningless(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "c.jnnw"
            self._corpus(data)

            colour = BV.compute([data], chunk=32, top_k=10, fold="color")
            exact = BV.compute([data], chunk=32, top_k=10, fold="exact")

            self.assertEqual(colour["fold"], "color")
            self.assertEqual(exact["fold"], "exact")
            self.assertIsNotNone(colour["per_pattern"])
            # Sous le fold exact les blocs par pattern ne sont ni contigus ni
            # de même taille : mieux vaut rien que huit lignes trompeuses.
            self.assertIsNone(exact["per_pattern"])
            self.assertFalse(exact["geometry"]["per_pattern_blocks_are_contiguous"])

    def test_adding_the_mirror_images_buys_coverage_only_under_the_wrong_fold(self):
        """Le contrôle qui montre pourquoi les deux chiffres ne se comparent pas.

        On double le corpus avec l'image `rot180 ∘ cs` de chaque position. Ce
        sont les MÊMES positions pour le modèle exact : la couverture ne doit
        pas bouger d'un bucket. Sous le fold couleur elle monte — de la
        couverture achetée avec zéro information neuve.
        """
        with tempfile.TemporaryDirectory() as tmp:
            plain, doubled = Path(tmp) / "a.jnnw", Path(tmp) / "b.jnnw"
            black, white = random_positions(256, seed=3)
            self._write(plain, black, white)
            image = rot180_colourswap(black, white)
            self._write(doubled, np.concatenate([black, image[0]]),
                        np.concatenate([white, image[1]]))

            for fold, expect_growth in (("exact", False), ("color", True)):
                before = BV.compute([plain], 64, 10, fold)["coverage"]["visited_buckets"]
                after = BV.compute([doubled], 64, 10, fold)["coverage"]["visited_buckets"]
                if expect_growth:
                    self.assertGreater(after, before, fold)
                else:
                    self.assertEqual(after, before, fold)


if __name__ == "__main__":
    unittest.main()
