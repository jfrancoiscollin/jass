from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np

from jobs.tools import d2_policy_adapter as d2


class D2PolicyAdapterTests(unittest.TestCase):
    def test_frozen_science_constants(self) -> None:
        self.assertEqual(d2.PARENTS, 4000)
        self.assertEqual(d2.ACTIONS, 38053)
        self.assertEqual(d2.SPLITS, {"train": 3200, "valid": 400, "test": 400})
        self.assertEqual(d2.EXTRAS, 120)
        self.assertEqual(d2.WIDTH, 240)
        self.assertEqual(d2.L2, 1e-3)
        self.assertEqual(d2.MAX_ITER, 500)
        self.assertEqual(d2.MAXCOR, 10)
        self.assertEqual(d2.GTOL, 1e-6)
        self.assertEqual(d2.BOOTSTRAPS, 200000)
        self.assertEqual(d2.SEED, 2026111001)

    def test_production_extra_replay_is_exact(self) -> None:
        extras = np.arange(4 * d2.EXTRAS, dtype=np.float64).reshape(4, d2.EXTRAS) / 37.0
        wmg = np.array([0.0, 0.25, 0.75, 1.0], dtype=np.float64)
        weg = 1.0 - wmg
        phi, equal = d2.build_phi_from_arrays(extras, wmg, weg)
        self.assertTrue(equal)
        self.assertEqual(phi.shape, (4, d2.WIDTH))
        np.testing.assert_array_equal(phi[:, : d2.EXTRAS], extras * wmg[:, None])
        np.testing.assert_array_equal(phi[:, d2.EXTRAS :], extras * weg[:, None])

    def test_listwise_gradient_matches_finite_difference(self) -> None:
        phi = np.array([
            [1.0, 0.0, 0.3],
            [0.0, 1.0, -0.2],
            [1.0, 1.0, 0.1],
            [-0.5, 0.2, 1.0],
            [0.3, -0.1, 0.7],
        ], dtype=np.float64)
        groups = [
            {"start": 0, "count": 3, "selected_local_action_index": 1, "parent_stm": 1},
            {"start": 3, "count": 2, "selected_local_action_index": 0, "parent_stm": 0},
        ]
        beta = np.array([0.2, -0.4, 0.3], dtype=np.float64)
        loss, grad, stats = d2.listwise_loss_grad(beta, phi, groups)
        self.assertTrue(np.isfinite(loss))
        self.assertEqual(stats["parents"], 2.0)
        eps = 1e-6
        for j in range(beta.size):
            bp = beta.copy(); bm = beta.copy()
            bp[j] += eps; bm[j] -= eps
            lp = d2.listwise_loss_grad(bp, phi, groups)[0]
            lm = d2.listwise_loss_grad(bm, phi, groups)[0]
            self.assertAlmostEqual((lp - lm) / (2 * eps), grad[j], places=6)

    def test_parent_pov_is_only_a_sign_flip(self) -> None:
        phi = np.eye(2, dtype=np.float64)
        beta = np.array([2.0, -2.0], dtype=np.float64)
        black = [{"start": 0, "count": 2, "selected_local_action_index": 0, "parent_stm": 1}]
        white = [{"start": 0, "count": 2, "selected_local_action_index": 0, "parent_stm": 0}]
        self.assertLess(
            d2.listwise_loss_grad(beta, phi, black)[0],
            d2.listwise_loss_grad(beta, phi, white)[0],
        )

    def test_adapter_serialization_is_float64_and_immutable(self) -> None:
        beta = np.linspace(-1.0, 1.0, d2.WIDTH, dtype=np.float64)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "adapter.npy"
            receipt = d2._write_adapter_new(path, beta)
            self.assertEqual(receipt["width"], d2.WIDTH)
            self.assertEqual(receipt["dtype"], "float64")
            np.testing.assert_array_equal(np.load(path, allow_pickle=False), beta)
            with self.assertRaises(d2.D2Error):
                d2._write_adapter_new(path, beta)

    def test_paired_diagnostics_sign_convention(self) -> None:
        control = [
            {"parent_id": 0, "ce": 1.0, "selected_probability": 0.2, "top1": 0, "top2": 1},
            {"parent_id": 1, "ce": 3.0, "selected_probability": 0.1, "top1": 0, "top2": 0},
        ]
        adapter = [
            {"parent_id": 0, "ce": 0.5, "selected_probability": 0.4, "top1": 1, "top2": 1},
            {"parent_id": 1, "ce": 4.5, "selected_probability": 0.05, "top1": 0, "top2": 0},
        ]
        paired = d2._paired(control, adapter)
        self.assertAlmostEqual(paired["delta_decision_mean"], -0.5)
        self.assertEqual(paired["fraction_ce_improved"], 0.5)
        self.assertEqual(paired["catastrophic_regression_rate_delta_lt_minus1"], 0.5)

    def test_bootstrap_seed_is_deterministic(self) -> None:
        delta = np.linspace(-0.1, 0.3, d2.SPLITS["test"], dtype=np.float64)
        original = d2.BOOTSTRAPS
        try:
            d2.BOOTSTRAPS = 1000
            a = d2.bootstrap_delta(delta)
            b = d2.bootstrap_delta(delta)
        finally:
            d2.BOOTSTRAPS = original
        self.assertEqual(a, b)
        self.assertEqual(a["seed"], 2026111001)
        self.assertEqual(a["replications"], 1000)

    def test_cli_has_no_forbidden_teacher_or_value_inputs(self) -> None:
        pre = d2.parse_args([
            "preflight",
            "--decision-data", "/tmp/d.jnnw",
            "--decision-feat", "/tmp/d.feat",
            "--decision-groups", "/tmp/g.json",
            "--control-model", "/tmp/c.pjtw",
            "--out", "/tmp/pre.json",
        ])
        fit = d2.parse_args([
            "fit",
            "--decision-data", "/tmp/d.jnnw",
            "--decision-feat", "/tmp/d.feat",
            "--decision-groups", "/tmp/g.json",
            "--control-model", "/tmp/c.pjtw",
            "--preflight", "/tmp/pre.json",
            "--adapter-out", "/tmp/a.npy",
            "--fit-report", "/tmp/f.json",
            "--out", "/tmp/r.json",
        ])
        for parsed in (pre, fit):
            keys = set(vars(parsed))
            for forbidden in (
                "q5", "q50", "q200", "full_ladder", "target_values", "temperature",
                "lambda_decision", "runtime_scale", "wdl_target", "listwise_model",
            ):
                self.assertNotIn(forbidden, keys)


if __name__ == "__main__":
    unittest.main()
