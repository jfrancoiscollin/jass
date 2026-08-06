"""`--prior-decay-ext` : le bloc extras a son propre amortissement.

Motivation. `build_sequential_prior` facture aux extras `visites/N = 1` par
construction, alors qu'un bucket de pattern moyen est vu ~123 fois sur 2 M
records (`TB = 8 x 531 441`, 130 086 buckets retenus). Sous un amortissement
PARTAGE, la precision du prior des extras vaut `l2 + decay*lam` sans aucune
dependance aux visites, soit ~9 850x celle du bucket moyen -- et ce rapport
est structurel, pas dosable : il vaut `1 + lam*decay/l2` a toute dose.

Un knob unique confond donc deux interventions tres differentes : le
retrecissement adaptatif aux visites sur les patterns, et l'epinglage des
extras sur le parent. Ces tests verrouillent la separation ET, surtout, le
fait que NE PAS passer le nouveau drapeau reproduit l'ancien comportement
bit pour bit -- aucun resultat publie ne bouge.
"""
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from pattern_jass.tools import train_stream


L2 = 1e-5
LAM = 0.25
PAT_N = 6           # slot 0 = fallback + 5 buckets retenus
E = 4               # 4 extras
N = 2_000_000
KEPT = np.array([400_000, 1_000, 246, 10, 1], dtype=np.int64)


def _args(decay, decay_ext=None):
    return SimpleNamespace(prior_mean='/champion.pjtw', prior_visit_scale=LAM,
                           prior_decay=decay, prior_decay_ext=decay_ext)


def _prior(decay, decay_ext=None):
    mu_stub = np.zeros(2 * PAT_N + 2 * E, dtype=np.float64)
    with mock.patch.object(train_stream, 'project_champion_mean',
                           return_value=(mu_stub, 1000)):
        return train_stream.build_sequential_prior(
            _args(decay, decay_ext), folder=None, keep=None, kept_counts=KEPT,
            PAT_N=PAT_N, E=E, N=N, l2=L2)


def _blocks(prec):
    """(patterns mg, extras mg) -- la precision est [pat|pat|ext|ext]."""
    return prec[1:PAT_N], prec[2 * PAT_N:2 * PAT_N + E]


class PriorDecayExtDefault(unittest.TestCase):
    """Omettre le drapeau doit etre un no-op EXACT, pas approximatif."""

    def test_omitted_is_bit_identical_to_shared_decay(self):
        for decay in (0.0, 0.001, 0.25, 1.0):
            with self.subTest(decay=decay):
                _, ref = _prior(decay)                       # comportement historique
                _, got = _prior(decay, decay_ext=decay)      # explicite, meme valeur
                # bit pour bit : c'est l'invariant qui protege les runs publies
                self.assertEqual(got.tobytes(), ref.tobytes())

    def test_none_is_not_read_as_zero(self):
        """Piege classique : `or` au lieu de `is None` collapserait 0.0 et None."""
        _, shared = _prior(1.0)
        _, ext_off = _prior(1.0, decay_ext=0.0)
        self.assertFalse(np.array_equal(shared, ext_off),
                         'decay_ext=0 doit differer du defaut partage decay=1')


class PriorDecayExtSeparation(unittest.TestCase):

    def test_ext_decay_leaves_patterns_untouched(self):
        _, base = _prior(1.0)
        _, split = _prior(1.0, decay_ext=0.0)
        pat_base, ext_base = _blocks(base)
        pat_split, ext_split = _blocks(split)
        np.testing.assert_array_equal(pat_split, pat_base)   # patterns intacts
        np.testing.assert_allclose(ext_split, L2)            # extras rendus au ridge nu
        self.assertGreater(ext_base[0], ext_split[0])

    def test_pattern_decay_leaves_extras_untouched(self):
        """Le bras scientifique : patterns adaptatifs, extras au ridge nu."""
        _, control = _prior(0.0)
        _, treat = _prior(1.0, decay_ext=0.0)
        pat_ctl, ext_ctl = _blocks(control)
        pat_tr, ext_tr = _blocks(treat)
        np.testing.assert_allclose(ext_tr, ext_ctl)          # SEUL facteur : les patterns
        self.assertTrue(np.all(pat_tr >= pat_ctl))
        self.assertGreater(pat_tr[0], pat_ctl[0])

    def test_visit_weighting_is_monotone_in_counts(self):
        _, prec = _prior(1.0, decay_ext=0.0)
        pat, _ = _blocks(prec)
        self.assertTrue(np.all(np.diff(pat) <= 0), 'KEPT est decroissant, pat doit l etre')
        expected = L2 + LAM * (KEPT.astype(np.float64) / N)
        np.testing.assert_allclose(pat, expected, rtol=0, atol=0)


class PriorDecayExtAsymmetryIsReal(unittest.TestCase):
    """Chiffre la raison d'etre du drapeau, pour qu'elle ne se reperde pas."""

    def test_shared_decay_hits_extras_thousands_of_times_harder(self):
        _, prec = _prior(1.0)
        pat, ext = _blocks(prec)
        mean_bucket = L2 + LAM * (123.0 / N)                 # bucket moyen d'un corpus 2 M
        ratio = ext[0] / mean_bucket
        self.assertGreater(ratio, 5_000)
        self.assertLess(ratio, 20_000)      # ~9850x, borne les deux cotes

    def test_asymmetry_is_structural_not_dosable(self):
        """Meme a dose minuscule les extras restent des dizaines de fois l2."""
        _, prec = _prior(0.001)
        _, ext = _blocks(prec)
        self.assertGreater(ext[0] / L2, 20)


if __name__ == '__main__':
    unittest.main()
