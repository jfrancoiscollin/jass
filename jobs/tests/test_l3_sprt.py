import math
import unittest

from jobs.tools.l3_sprt import (
    ACCEPT_H0,
    ACCEPT_H1,
    CONTINUE,
    bounds,
    elo_to_score,
    evaluate,
    expected_games,
    llr,
    pentanomial_stats,
    score_to_elo,
    trinomial_stats,
)


class EloTest(unittest.TestCase):
    def test_zero_elo_is_even_score(self):
        self.assertAlmostEqual(elo_to_score(0.0), 0.5)

    def test_round_trip(self):
        for elo in (-50.0, -5.0, 0.0, 5.0, 13.77, 60.0):
            self.assertAlmostEqual(score_to_elo(elo_to_score(elo)), elo, places=6)


class StatsTest(unittest.TestCase):
    def test_trinomial_mean_and_variance(self):
        n, mu, var = trinomial_stats(600, 100, 300)
        self.assertEqual(n, 1000)
        self.assertAlmostEqual(mu, 0.65)
        self.assertAlmostEqual(var, (600 + 25) / 1000 - 0.65**2)

    def test_pentanomial_pairs_count_two_games_each(self):
        n, mu, _ = pentanomial_stats([0, 0, 100, 0, 0])
        self.assertEqual(n, 200)
        self.assertAlmostEqual(mu, 0.5)

    def test_pentanomial_has_lower_variance_than_trinomial(self):
        """Un résultat parfaitement apparié annule la variance de couleur."""
        _, _, penta_var = pentanomial_stats([0, 0, 500, 0, 0])
        _, _, tri_var = trinomial_stats(500, 0, 500)
        self.assertLess(penta_var, tri_var)

    def test_rejects_bad_shapes(self):
        with self.assertRaises(ValueError):
            pentanomial_stats([1, 2, 3])
        with self.assertRaises(ValueError):
            trinomial_stats(0, 0, 0)


class BoundsTest(unittest.TestCase):
    def test_symmetric_bounds(self):
        lower, upper = bounds(0.05, 0.05)
        self.assertAlmostEqual(lower, -upper, places=9)
        self.assertLess(lower, 0.0)
        self.assertGreater(upper, 0.0)

    def test_rejects_degenerate_error_rates(self):
        for a, b in ((0.0, 0.05), (0.05, 1.0), (-0.1, 0.05)):
            with self.assertRaises(ValueError):
                bounds(a, b)


class LlrTest(unittest.TestCase):
    def test_llr_is_positive_when_observed_beats_both_hypotheses(self):
        value = llr(n=1000, mu=0.60, var=0.24, elo0=0.0, elo1=5.0)
        self.assertGreater(value, 0.0)

    def test_llr_is_negative_when_observed_is_below_both(self):
        value = llr(n=1000, mu=0.40, var=0.24, elo0=0.0, elo1=5.0)
        self.assertLess(value, 0.0)

    def test_llr_scales_with_sample_size(self):
        a = llr(n=1000, mu=0.55, var=0.24, elo0=0.0, elo1=5.0)
        b = llr(n=2000, mu=0.55, var=0.24, elo0=0.0, elo1=5.0)
        self.assertAlmostEqual(b, 2 * a, places=9)

    def test_identical_hypotheses_are_rejected(self):
        with self.assertRaises(ValueError):
            llr(n=100, mu=0.5, var=0.25, elo0=3.0, elo1=3.0)


class EvaluateTest(unittest.TestCase):
    def test_clear_win_accepts_h1(self):
        report = evaluate(wins=1200, draws=40, losses=760, elo0=0.0, elo1=5.0)
        self.assertEqual(report["verdict"], ACCEPT_H1)
        self.assertEqual(report["model"], "trinomial")

    def test_clear_loss_accepts_h0(self):
        report = evaluate(wins=760, draws=40, losses=1200, elo0=0.0, elo1=5.0)
        self.assertEqual(report["verdict"], ACCEPT_H0)

    def test_small_sample_continues(self):
        report = evaluate(wins=52, draws=2, losses=46, elo0=0.0, elo1=5.0)
        self.assertEqual(report["verdict"], CONTINUE)

    def test_pentanomial_path_is_selected(self):
        report = evaluate(pentanomial=[10, 20, 300, 20, 10], elo0=0.0, elo1=5.0)
        self.assertEqual(report["model"], "pentanomial")
        self.assertEqual(report["n"], 720)

    def test_requires_counts(self):
        with self.assertRaises(ValueError):
            evaluate(wins=10, draws=1, elo0=0.0, elo1=5.0)


class ExpectedGamesTest(unittest.TestCase):
    def test_larger_true_effect_resolves_sooner(self):
        big = expected_games(
            true_elo=20.0, elo0=0.0, elo1=5.0, alpha=0.05, beta=0.05
        )
        small = expected_games(
            true_elo=6.0, elo0=0.0, elo1=5.0, alpha=0.05, beta=0.05
        )
        self.assertLess(big, small)

    def test_returns_a_positive_budget(self):
        self.assertGreater(
            expected_games(true_elo=10.0, elo0=0.0, elo1=5.0, alpha=0.05, beta=0.05),
            0,
        )


if __name__ == "__main__":
    unittest.main()
