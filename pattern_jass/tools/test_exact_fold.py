# SPDX-License-Identifier: AGPL-3.0-or-later
"""Le fold EXACT impose la vraie symétrie, et seulement elle.

Deux propriétés, et la seconde compte autant que la première :

1. un modèle plié puis ré-étendu satisfait `rot180∘colour-swap` **exactement** —
   c'est la symétrie que les règles du damier garantissent ;
2. il ne satisfait **pas** `colour-swap` seule — c'est une contrainte
   approximative, que `--color-fold` imposait et que ce mode retire.

Sans le point 2 le test passerait aussi sur l'ancien comportement, et on ne
saurait pas si le changement a fait quoi que ce soit.
"""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import patterns as P          # noqa: E402
import symmetry as S          # noqa: E402
import train_stream as ts     # noqa: E402

NB = 3 ** P.PATTERN_SIZE
NP = P.NUM_PATTERNS


def violation(pat, sigma_of):
    """Part de l'énergie qui viole `w_p[u] = -w_{q}[σ(u)]`."""
    ok = bad = 0.0
    for p in range(NP):
        q, sigma = sigma_of(p)
        if q is None:
            continue
        a = pat[p].astype(np.float64)
        b = -pat[q][sigma].astype(np.float64)
        ok += float(np.sum((0.5 * (a + b)) ** 2))
        bad += float(np.sum((0.5 * (a - b)) ** 2))
    return bad / (ok + bad) if (ok + bad) else 0.0


def rot_cs_pairs():
    cs = S.colorswap_map()
    rp, rotperm = S.rot_structure()

    def of(p):
        if rp[p] < 0:
            return None, None
        return rp[p], cs[S._reorder_all(rotperm[p])]
    return of


def cs_only_pairs():
    cs = S.colorswap_map()
    return lambda p: (p, cs)


class ExactCanon(unittest.TestCase):
    def test_canonical_space_is_exactly_scans_parameter_count(self):
        canon, sign = S.build_exact_canon()
        self.assertEqual(len(np.unique(canon)), NB * NP // 2)
        # 8cf : aucun pattern n'est son propre miroir, donc aucun poids épinglé à 0
        self.assertNotIn(0, np.unique(sign))

    def test_every_pattern_has_a_rot180_partner_in_8cf(self):
        rp, _ = S.rot_structure()
        self.assertTrue(all(r >= 0 for r in rp), rp)


class ExpandedWeightsObeyTheTrueSymmetryOnly(unittest.TestCase):
    def setUp(self):
        folder = ts.Folder("exact")
        rng = np.random.default_rng(17)
        canon = rng.normal(0.0, 0.05, size=folder.TB)
        mg, eg = ts.expand_pat(folder, canon, canon.copy(), 1000)
        self.pat = mg.reshape(NP, NB)

    def test_rot180_colourswap_is_exact(self):
        self.assertAlmostEqual(violation(self.pat, rot_cs_pairs()), 0.0, places=12)

    def test_colourswap_alone_is_NOT_imposed(self):
        """La contrainte fausse a bien disparu. Si elle était encore là, ce fold
        ne changerait rien à ce que faisait --color-fold."""
        self.assertGreater(violation(self.pat, cs_only_pairs()), 0.01)


class ColorFoldImposesTheApproximateOne(unittest.TestCase):
    """Contre-épreuve sur l'ancien mode : il impose cs seule et laisse la vraie
    symétrie libre. C'est la situation qu'on corrige."""

    def setUp(self):
        folder = ts.Folder("color")
        rng = np.random.default_rng(23)
        canon = rng.normal(0.0, 0.05, size=folder.TB)
        mg, eg = ts.expand_pat(folder, canon, canon.copy(), 1000)
        self.pat = mg.reshape(NP, NB)

    def test_colourswap_alone_is_exact_under_color_fold(self):
        self.assertAlmostEqual(violation(self.pat, cs_only_pairs()), 0.0, places=12)

    def test_the_true_symmetry_is_left_free_under_color_fold(self):
        self.assertGreater(violation(self.pat, rot_cs_pairs()), 0.01)


def lr_pairs():
    lp, lrperm = S.lr_structure()

    def of(p):
        if lp[p] < 0:
            return None, None
        return lp[p], S._reorder_all(lrperm[p])
    return of


def violation_plus(pat, sigma_of):
    """Comme `violation`, mais pour une symétrie de signe +1 : `w_p[u] = +w_q[σ(u)]`."""
    ok = bad = 0.0
    for p in range(NP):
        q, sigma = sigma_of(p)
        if q is None:
            continue
        a = pat[p].astype(np.float64)
        b = pat[q][sigma].astype(np.float64)
        ok += float(np.sum((0.5 * (a + b)) ** 2))
        bad += float(np.sum((0.5 * (a - b)) ** 2))
    return bad / (ok + bad) if (ok + bad) else 0.0


class ExactLrCanon(unittest.TestCase):
    def test_the_canonical_space_halves_again(self):
        canon, sign = S.build_exact_canon(reflect=True)
        self.assertEqual(len(np.unique(canon)), NB * NP // 4)
        self.assertNotIn(0, np.unique(sign))

    def test_every_pattern_has_an_LR_partner_in_8cf(self):
        lp, _ = S.lr_structure()
        self.assertTrue(all(x >= 0 for x in lp), lp)


class ExactLrObeysBothTrueSymmetries(unittest.TestCase):
    def setUp(self):
        folder = ts.Folder("exact-lr")
        rng = np.random.default_rng(29)
        canon = rng.normal(0.0, 0.05, size=folder.TB)
        mg, eg = ts.expand_pat(folder, canon, canon.copy(), 1000)
        self.pat = mg.reshape(NP, NB)

    def test_rot180_colourswap_is_exact(self):
        self.assertAlmostEqual(violation(self.pat, rot_cs_pairs()), 0.0, places=12)

    def test_left_right_reflection_is_exact_with_sign_plus_one(self):
        self.assertAlmostEqual(violation_plus(self.pat, lr_pairs()), 0.0, places=12)

    def test_colourswap_alone_is_still_NOT_imposed(self):
        """La contrainte fausse ne doit pas revenir par la porte de derrière."""
        self.assertGreater(violation(self.pat, cs_only_pairs()), 0.01)


class ExactWithoutReflectDoesNotImposeLR(unittest.TestCase):
    """Contre-épreuve : sans `reflect`, LR reste libre. Sans ce test, le mode
    exact-lr pourrait n'avoir aucun effet propre et les tests passeraient."""

    def setUp(self):
        folder = ts.Folder("exact")
        rng = np.random.default_rng(31)
        canon = rng.normal(0.0, 0.05, size=folder.TB)
        mg, eg = ts.expand_pat(folder, canon, canon.copy(), 1000)
        self.pat = mg.reshape(NP, NB)

    def test_LR_is_free_under_the_plain_exact_fold(self):
        self.assertGreater(violation_plus(self.pat, lr_pairs()), 0.01)


if __name__ == "__main__":
    unittest.main()
