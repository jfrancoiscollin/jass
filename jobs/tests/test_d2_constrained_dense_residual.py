from __future__ import annotations

import math
from pathlib import Path
import unittest

import numpy as np

from jobs.tools import d2_constrained_dense_residual_fit as fit
from jobs.tools import d2_constrained_dense_residual_readout as readout


class D2ConstrainedDenseResidualTests(unittest.TestCase):
    def test_pairwise_gradient_matches_finite_difference(self) -> None:
        rng = np.random.default_rng(7)
        x = rng.normal(size=(5, fit.RESIDUAL_COLS)) * 0.05
        base = np.asarray([0.1, -0.2, 0.3, 0.0, 0.2], dtype=np.float64)
        groups = [{
            "count": 5,
            "hard_competitor_local_action_indices": [1, 3, 4],
            "parent_stm": 1,
            "selected_local_action_index": 2,
            "start": 0,
        }]
        d = rng.normal(size=fit.RESIDUAL_COLS) * 0.01
        loss, grad, _ = fit.pairwise_loss_grad(d, x, base, groups)
        self.assertTrue(math.isfinite(loss))
        for j in (0, 3, 17, 119, 120, 239):
            eps = 1e-6
            dp = d.copy(); dm = d.copy(); dp[j] += eps; dm[j] -= eps
            lp = fit.pairwise_loss_grad(dp, x, base, groups)[0]
            lm = fit.pairwise_loss_grad(dm, x, base, groups)[0]
            num = (lp - lm) / (2 * eps)
            self.assertAlmostEqual(float(grad[j]), float(num), places=6)

    def test_competitor_order_invariant_and_parent_equal(self) -> None:
        x = np.zeros((6, fit.RESIDUAL_COLS), dtype=np.float64)
        base = np.asarray([2.0, 0.0, 1.0, -1.0, 0.5, -0.5], dtype=np.float64)
        g1 = {"count": 3, "hard_competitor_local_action_indices": [1, 2],
              "parent_stm": 1, "selected_local_action_index": 0, "start": 0}
        g1r = dict(g1); g1r["hard_competitor_local_action_indices"] = [2, 1]
        g2 = {"count": 3, "hard_competitor_local_action_indices": [1],
              "parent_stm": 1, "selected_local_action_index": 0, "start": 3}
        a = fit.pairwise_loss_grad(np.zeros(fit.RESIDUAL_COLS), x, base, [g1, g2])[0]
        b = fit.pairwise_loss_grad(np.zeros(fit.RESIDUAL_COLS), x, base, [g1r, g2])[0]
        self.assertAlmostEqual(a, b, places=14)
        l1 = np.mean(np.logaddexp(0.0, -np.asarray([2.0, 1.0])))
        l2 = np.logaddexp(0.0, -(0.5 - (-0.5)))
        self.assertAlmostEqual(a, (float(l1) + float(l2)) / 2.0, places=14)

    def test_parent_pov_sign_symmetry(self) -> None:
        x = np.zeros((3, fit.RESIDUAL_COLS), dtype=np.float64)
        d = np.zeros(fit.RESIDUAL_COLS)
        black = [{"count": 3, "hard_competitor_local_action_indices": [1, 2],
                  "parent_stm": 1, "selected_local_action_index": 0, "start": 0}]
        white = [{"count": 3, "hard_competitor_local_action_indices": [1, 2],
                  "parent_stm": 0, "selected_local_action_index": 0, "start": 0}]
        z = np.asarray([1.2, 0.3, -0.4])
        lb = fit.pairwise_loss_grad(d, x, z, black)[0]
        lw = fit.pairwise_loss_grad(d, x, -z, white)[0]
        self.assertAlmostEqual(lb, lw, places=14)

    def test_candidate_ints_freeze_pattern_prefix(self) -> None:
        n_pat = 7
        base = np.arange(2 * (n_pat + fit.EXTRAS), dtype=np.int64) - 50
        delta = np.linspace(-0.5, 0.5, fit.RESIDUAL_COLS)
        cand, inc = fit._candidate_ints(base, n_pat, delta, 0.37)
        self.assertTrue(np.array_equal(cand[:2 * n_pat], base[:2 * n_pat]))
        self.assertEqual(inc.shape, (fit.RESIDUAL_COLS,))
        self.assertTrue(np.array_equal(cand[2 * n_pat:] - base[2 * n_pat:], inc))

    def test_readout_aggregate_uses_only_eligible_for_pairwise(self) -> None:
        rows = [
            {"eligible": True, "full_ce": 2.0, "selected_probability": 0.2, "top1": 1.0, "top2": 1.0,
             "pairwise_loss": 0.4, "pairwise_accuracy": 0.75},
            {"eligible": False, "full_ce": 4.0, "selected_probability": 0.1, "top1": 0.0, "top2": 0.0,
             "pairwise_loss": None, "pairwise_accuracy": None},
        ]
        a = readout.aggregate(rows)
        self.assertEqual(a["eligible_parents"], 1)
        self.assertAlmostEqual(a["full_cross_entropy"], 3.0)
        self.assertAlmostEqual(a["survived5_pairwise_loss"], 0.4)
        self.assertAlmostEqual(a["survived5_pairwise_accuracy"], 0.75)

    def test_frozen_constants(self) -> None:
        self.assertEqual(fit.RESIDUAL_COLS, 240)
        self.assertEqual(fit.EXTRAS, 120)
        self.assertEqual(fit.L2, 1e-5)
        self.assertEqual(fit.WDL_TOLERANCE, 0.002)
        self.assertEqual(fit.BISECTION_STEPS, 32)
        self.assertEqual(readout.SEED, 2026111001)
        self.assertEqual(readout.BOOTSTRAPS, 200_000)
        self.assertEqual(readout.MIN_TEST_ELIGIBLE, 300)
        self.assertEqual(readout.MIN_CELL_ELIGIBLE, 25)

    def test_prepare_source_does_not_access_numeric_qscore_fields(self) -> None:
        source = Path("jobs/tools/d2_decision_prepare.py").read_text(encoding="utf-8")
        self.assertNotIn('get("score_parent")', source)
        self.assertNotIn("['score_parent']", source)
        self.assertNotIn('get("observations")', source)
        self.assertNotIn("['observations']", source)


if __name__ == "__main__":
    unittest.main()
