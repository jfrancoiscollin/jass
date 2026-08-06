"""`--prior-alpha-cap` : borner la PART du parent dans chaque bucket.

Motivation. Sous `--prior-mean`, la moyenne a posteriori de chaque bucket est un
melange convexe `w = a*mu + (1-a)*w_donnees` avec

    a_j = prec_j / (prec_j + lam*visites_j/N)

puisque `lam*visites/N` est l'echelle de la Fisher logistique des donnees --
c'est exactement ce que documente `--prior-visit-scale`. A precision CONSTANTE
(`prec = l2`, la recette championne), `a` tend vers 1 sur les buckets rares : le
modele porte des buckets qui sont a ~100 % du parent, et RIEN ne le borne.

Le plafond resout `a_j <= cap`, donc `prec_j = min(l2, cap/(1-cap)*lam*visites/N)`,
en gardant `l2` comme plafond : il ne peut donc QUE relacher le rappel, jamais le
renforcer. Il interpole continument entre les deux poles mesures par cpx62-1192 :
`cap -> 1` redonne la recette a `l2` constant, `cap -> 0` tend vers un fit depuis
zero.
"""
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from pattern_jass.tools import train_stream


L2 = 1e-5
LAM = 0.25
PAT_N = 6           # slot 0 = fallback + 5 buckets retenus
E = 4
N = 2_000_000
# du bucket tres vu au bucket vu une seule fois (queue lourde reelle)
KEPT = np.array([400_000, 1_000, 246, 10, 1], dtype=np.int64)


def _args(cap=None, decay=train_stream.PRIOR_DECAY_DEFAULT, decay_ext=None):
    return SimpleNamespace(prior_mean='/champion.pjtw', prior_visit_scale=LAM,
                           prior_decay=decay, prior_decay_ext=decay_ext,
                           prior_alpha_cap=cap)


def _prior(cap=None, decay=train_stream.PRIOR_DECAY_DEFAULT, decay_ext=None):
    mu_stub = np.zeros(2 * PAT_N + 2 * E, dtype=np.float64)
    with mock.patch.object(train_stream, 'project_champion_mean',
                           return_value=(mu_stub, 1000)):
        return train_stream.build_sequential_prior(
            _args(cap, decay, decay_ext), folder=None, keep=None, kept_counts=KEPT,
            PAT_N=PAT_N, E=E, N=N, l2=L2)


def _blocks(prec):
    return prec[1:PAT_N], prec[2 * PAT_N:2 * PAT_N + E]


def _alpha(prec_pat):
    """Part effective du parent, telle que la definit le melange convexe."""
    return prec_pat / (prec_pat + LAM * (KEPT.astype(np.float64) / N))


class CapIsANoOpWhenAbsent(unittest.TestCase):
    """Ne pas passer le drapeau doit rester bit pour bit l'ancien comportement."""

    def test_absent_is_bit_identical(self):
        for decay in (0.0, 0.25, 1.0):
            with self.subTest(decay=decay):
                _, ref = _prior(cap=None, decay=decay)
                self.assertEqual(
                    ref.tobytes(),
                    np.concatenate([
                        np.concatenate([[L2], L2 + decay * LAM * (KEPT / N)]),
                        np.concatenate([[L2], L2 + decay * LAM * (KEPT / N)]),
                        np.full(E, L2 + decay * LAM), np.full(E, L2 + decay * LAM),
                    ]).tobytes())


class CapBoundsTheParentShare(unittest.TestCase):

    def test_no_bucket_exceeds_the_cap(self):
        for cap in (0.2, 0.5, 0.8):
            with self.subTest(cap=cap):
                _, prec = _prior(cap=cap)
                pat, _ = _blocks(prec)
                # tolerance flottante seulement : le plafond est une inegalite dure
                self.assertLessEqual(_alpha(pat).max(), cap + 1e-12)

    def test_without_the_cap_thin_buckets_are_almost_pure_parent(self):
        """La raison d'etre du drapeau, chiffree sur la recette championne."""
        _, prec = _prior(cap=None, decay=0.0)          # recette L2LOW
        pat, _ = _blocks(prec)
        a = _alpha(pat)
        self.assertGreater(a.max(), 0.98)              # le bucket a 1 visite
        self.assertLess(a.min(), 0.30)                 # le bucket a 400k visites

    def test_cap_only_ever_relaxes_never_strengthens(self):
        _, base = _prior(cap=None, decay=0.0)          # prec = l2 partout
        for cap in (0.2, 0.5, 0.8):
            with self.subTest(cap=cap):
                _, capped = _prior(cap=cap)
                self.assertTrue(np.all(capped <= base + 1e-18),
                                'le plafond ne doit jamais AUGMENTER une precision')

    def test_cap_leaves_the_extras_at_l2(self):
        """Les extras portent visites/N = 1 : le plafond ne doit pas les toucher."""
        for cap in (0.2, 0.5, 0.8):
            with self.subTest(cap=cap):
                _, prec = _prior(cap=cap)
                _, ext = _blocks(prec)
                np.testing.assert_allclose(ext, L2)

    def test_cap_interpolates_between_the_two_poles(self):
        """cap -> 1 redonne l2 constant ; cap -> 0 annule la PART du parent.

        Piege : au pole bas ce n'est PAS la precision qui s'effondre partout.
        Un bucket vu 400 000 fois a deja une part de 2e-4 a `prec = l2`, donc il
        est deja SOUS le plafond et n'est pas touche -- et c'est le comportement
        voulu, le plafond ne relache que la ou le parent dominait. La grandeur
        bornee est la part, pas la precision.
        """
        _, high = _prior(cap=0.999)
        pat_hi, _ = _blocks(high)
        np.testing.assert_allclose(pat_hi, L2, rtol=1e-6)     # pole champion

        _, low = _prior(cap=0.001)
        pat_lo, _ = _blocks(low)
        self.assertLessEqual(_alpha(pat_lo).max(), 0.001 + 1e-12)   # pole scratch
        self.assertTrue(np.all(pat_lo > 0), 'la precision doit rester > 0 (convexite)')
        # le bucket a UNE visite, celui que le plafond vise, s'effondre bien
        self.assertLess(pat_lo[-1], L2 / 1000)
        # celui a 400 000 visites etait deja sous le plafond : intact
        self.assertAlmostEqual(pat_lo[0], L2, places=12)


class CapFailsClosed(unittest.TestCase):
    """Toute combinaison ambigue doit CRIER, jamais se resoudre en silence."""

    def _run_guard(self, **over):
        """Appelle la VRAIE garde, jamais une copie de sa logique."""
        a = SimpleNamespace(prior_mean='/c.pjtw', warm_start=None,
                            prior_decay=train_stream.PRIOR_DECAY_DEFAULT,
                            prior_decay_ext=None, prior_alpha_cap=0.5)
        a.__dict__.update(over)
        train_stream.validate_prior_alpha_cap(a)

    def test_absent_cap_is_never_refused(self):
        self._run_guard(prior_alpha_cap=None, prior_decay=0.0, prior_mean=None)

    def test_cap_without_parent_is_refused(self):
        with self.assertRaises(SystemExit):
            self._run_guard(prior_mean=None)

    def test_cap_outside_the_open_unit_interval_is_refused(self):
        for bad in (0.0, 1.0, -0.1, 1.5):
            with self.subTest(cap=bad), self.assertRaises(SystemExit):
                self._run_guard(prior_alpha_cap=bad)

    def test_cap_with_explicit_decay_is_refused(self):
        """decay 0 est la recette championne : la combiner serait tres tentant."""
        with self.assertRaises(SystemExit):
            self._run_guard(prior_decay=0.0)
        with self.assertRaises(SystemExit):
            self._run_guard(prior_decay_ext=0.0)

    def test_cap_with_the_untouched_decay_default_is_accepted(self):
        self._run_guard()                              # ne doit pas lever


if __name__ == '__main__':
    unittest.main()
