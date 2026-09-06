from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import scipy.sparse as sp

from jobs.tools import d1_decision_prepare as prep
from jobs.tools import d1_listwise_fit as fit
from jobs.tools import d1_postfit_readout as readout


class D1ListwiseTests(unittest.TestCase):
    def test_fingerprint_roundtrip_fields(self) -> None:
        fp = "0000000000001:0000000000002:0000000000004:0000000000008:1"
        self.assertEqual(prep.parse_fingerprint(fp), (1, 2, 4, 8, 1))
        with self.assertRaises(prep.D1PrepareError):
            prep.parse_fingerprint("bad")
        with self.assertRaises(prep.D1PrepareError):
            prep.parse_fingerprint("0000000000001:0000000000001:0000000000000:0000000000000:0")

    def test_listwise_gradient_matches_finite_difference(self) -> None:
        x = sp.csr_matrix(np.array([
            [1.0, 0.0, 0.3],
            [0.0, 1.0, -0.2],
            [1.0, 1.0, 0.1],
            [-0.5, 0.2, 1.0],
            [0.3, -0.1, 0.7],
        ], dtype=np.float64))
        groups = [
            {"start": 0, "count": 3, "selected_local_action_index": 1, "parent_stm": 1},
            {"start": 3, "count": 2, "selected_local_action_index": 0, "parent_stm": 0},
        ]
        w = np.array([0.2, -0.4, 0.3], dtype=np.float64)
        loss, grad, stats = fit.listwise_loss_grad(w, x, groups)
        self.assertTrue(np.isfinite(loss))
        self.assertEqual(stats["parents"], 2.0)
        eps = 1e-6
        for j in range(w.size):
            wp = w.copy(); wm = w.copy(); wp[j] += eps; wm[j] -= eps
            lp = fit.listwise_loss_grad(wp, x, groups)[0]
            lm = fit.listwise_loss_grad(wm, x, groups)[0]
            numerical = (lp - lm) / (2 * eps)
            self.assertAlmostEqual(numerical, grad[j], places=6)

    def test_parent_pov_sign_changes_preference(self) -> None:
        x = sp.eye(2, format="csr", dtype=np.float64)
        w = np.array([2.0, -2.0])
        black = [{"start": 0, "count": 2, "selected_local_action_index": 0, "parent_stm": 1}]
        white = [{"start": 0, "count": 2, "selected_local_action_index": 0, "parent_stm": 0}]
        lb = fit.listwise_loss_grad(w, x, black)[0]
        lw = fit.listwise_loss_grad(w, x, white)[0]
        self.assertLess(lb, lw)

    def test_bootstrap_contract_is_deterministic(self) -> None:
        delta = np.linspace(-0.1, 0.3, 400, dtype=np.float64)
        a = readout.bootstrap_delta(delta)
        b = readout.bootstrap_delta(delta)
        self.assertEqual(a, b)
        self.assertEqual(a["seed"], 2026110901)
        self.assertEqual(a["replications"], 200000)

    def test_prepare_rejects_qscore_freeform_not_needed(self) -> None:
        # Contract-level guard: the preparation module has no qscore/full-ladder input argument.
        parser = prep.parse_args([
            "--dataset", "/tmp/d.jsonl", "--out-jnnw", "/tmp/c.jnnw",
            "--out-groups", "/tmp/g.json", "--out-receipt", "/tmp/r.json",
        ])
        self.assertEqual(str(parser.dataset), "/tmp/d.jsonl")
        self.assertNotIn("qscore", vars(parser))
        self.assertNotIn("full_ladder", vars(parser))


if __name__ == "__main__":
    unittest.main()
