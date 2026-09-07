from __future__ import annotations

import math
import unittest

import numpy as np

from jobs.tools import d3_relational_action_residual as d3


class D3RelationalActionResidualTests(unittest.TestCase):
    def test_canonical_square_uses_one_to_fifty_domain(self) -> None:
        self.assertEqual(d3.canonical_square(1, 1), 1)
        self.assertEqual(d3.canonical_square(50, 1), 50)
        self.assertEqual(d3.canonical_square(1, 0), 50)
        self.assertEqual(d3.canonical_square(50, 0), 1)
        self.assertEqual(d3.canonical_square(17, 0), 34)
        with self.assertRaises(d3.D3Error):
            d3.canonical_square(0, 1)
        with self.assertRaises(d3.D3Error):
            d3.canonical_square(51, 0)

    def test_capture_mask_rotates_180_for_white(self) -> None:
        bb = (1 << 0) | (1 << 49) | (1 << 9)
        black = d3.canonical_capture_mask(bb, 1)
        white = d3.canonical_capture_mask(bb, 0)
        self.assertEqual(np.flatnonzero(black).tolist(), [0, 9, 49])
        self.assertEqual(np.flatnonzero(white).tolist(), [0, 40, 49])

    def test_base_action_vector_is_exactly_158(self) -> None:
        action = {
            "from": 1,
            "to": 50,
            "captured_square_bitboard": (1 << 4) | (1 << 9),
            "num_captures": 2,
            "promotes": True,
            "moving_king": False,
            "captured_kings": 1,
            "material_count_delta_parent": 2,
            "child_pieces": 18,
            "child_legal_moves": 7,
            "child_forced_capture": True,
        }
        v = d3.base_action_vector(action, 0)
        self.assertEqual(v.shape, (158,))
        self.assertEqual(v[49], 1.0)  # white parent: from 1 -> canonical 50
        self.assertEqual(v[50], 1.0)  # to 50 -> canonical 1
        self.assertEqual(float(np.sum(v[100:150])), 2.0)
        self.assertAlmostEqual(v[150], 0.1)
        self.assertEqual(v[151], 1.0)
        self.assertEqual(v[152], 0.0)
        self.assertAlmostEqual(v[153], 0.05)
        self.assertAlmostEqual(v[154], 0.1)
        self.assertAlmostEqual(v[155], 18 / 40)
        self.assertAlmostEqual(v[156], 7 / 64)
        self.assertEqual(v[157], 1.0)

    def test_pairwise_gradient_matches_finite_difference(self) -> None:
        old_actions = d3.ACTIONS
        try:
            d3.ACTIONS = 5
            rng = np.random.default_rng(31)
            phi = rng.normal(size=(5, d3.WIDTH)) * 0.03
            base = np.asarray([0.2, -0.1, 0.4, 0.0, -0.2], dtype=np.float64)
            groups = [{"start": 0, "count": 5, "selected_local_action_index": 2}]
            beta = rng.normal(size=d3.WIDTH) * 0.01
            loss, grad, _ = d3.listwise_loss_grad(beta, phi, base, groups)
            self.assertTrue(math.isfinite(loss))
            for j in (0, 49, 50, 149, 157, 158, 631):
                eps = 1e-6
                bp = beta.copy(); bm = beta.copy()
                bp[j] += eps; bm[j] -= eps
                lp = d3.listwise_loss_grad(bp, phi, base, groups)[0]
                lm = d3.listwise_loss_grad(bm, phi, base, groups)[0]
                self.assertAlmostEqual(float(grad[j]), float((lp - lm) / (2 * eps)), places=6)
        finally:
            d3.ACTIONS = old_actions

    def test_beta_zero_score_is_exact_base(self) -> None:
        rng = np.random.default_rng(3)
        phi = rng.normal(size=(7, d3.WIDTH))
        base = rng.normal(size=7)
        self.assertTrue(np.array_equal(base + phi @ np.zeros(d3.WIDTH), base))

    def test_frozen_constants(self) -> None:
        self.assertEqual(d3.BASE_WIDTH, 158)
        self.assertEqual(d3.PHASES, 4)
        self.assertEqual(d3.WIDTH, 632)
        self.assertEqual(d3.L2, 1e-3)
        self.assertEqual(d3.MAX_ITER, 500)
        self.assertEqual(d3.MAXCOR, 10)
        self.assertEqual(d3.GTOL, 1e-6)
        self.assertEqual(d3.BOOTSTRAPS, 200_000)
        self.assertEqual(d3.SEED, 2026111201)


if __name__ == "__main__":
    unittest.main()
