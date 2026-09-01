#!/usr/bin/env python3
from __future__ import annotations

import unittest

import numpy as np

from jobs.tools.jfi_fit_readout import path_pair, select_positive_l2_one_se
from jobs.tools.jfi_patterneval_identifiability import add_sparse


class JfiFitReadoutTests(unittest.TestCase):
    def test_one_se_selects_largest_eligible_positive_lambda(self):
        clusters = np.repeat(np.arange(20), 4)
        base = np.linspace(0.45, 0.55, len(clusters))
        losses = {
            0.0: base - 0.010,
            1e-6: base,
            1e-5: base + 0.001,
            1e-4: base + 0.100,
        }
        result = select_positive_l2_one_se(losses, clusters, samples=2000, seed=9)
        self.assertEqual(result["best_positive_l2"], 1e-6)
        self.assertEqual(result["selected_l2"], 1e-5)
        self.assertTrue(result["zero_l2_diagnostic_only"])

    def test_zero_is_never_selected_even_if_best(self):
        clusters = np.repeat(np.arange(10), 2)
        losses = {0.0: np.zeros(20), 1e-6: np.ones(20), 1e-5: np.ones(20)+1,
                  1e-4: np.ones(20)+2}
        result = select_positive_l2_one_se(losses, clusters, samples=500, seed=3)
        self.assertEqual(result["selected_l2"], 1e-6)

    def test_path_gate_thresholds(self):
        healthy = path_pair(np.zeros(5), np.full(5, 0.1), 1.0, 1.0 + 1e-9)
        self.assertTrue(healthy["pass"])
        bad = path_pair(np.zeros(5), np.full(5, 3.0), 1.0, 1.0)
        self.assertFalse(bad["pass"])

    def test_sparse_accumulator_preserves_duplicate_coordinate_mass(self):
        accumulator = np.zeros(4, dtype=np.float64)
        add_sparse(accumulator, np.asarray([[0, 1], [0, 3]]),
                   np.asarray([[1.0, 2.0], [4.0, 8.0]]))
        np.testing.assert_array_equal(accumulator, [5.0, 2.0, 0.0, 8.0])


if __name__ == "__main__":
    unittest.main()
