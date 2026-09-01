#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import jfi_active_select
import patterneval_identifiability


class IdentifiabilityTests(unittest.TestCase):
    def setUp(self):
        # [[1, 0, 2, 0], [0, 3, 0, 0], [1, 0, -1, 0]]
        self.indptr = np.asarray([0, 2, 3, 5])
        self.indices = np.asarray([0, 2, 1, 0, 2])
        self.values = np.asarray([1.0, 2.0, 3.0, 1.0, -1.0])

    def test_known_diagonal_fisher_and_counts(self):
        visits, squared, fisher, gradient = patterneval_identifiability.diagonal_statistics(
            self.indptr, self.indices, self.values, 4,
            probability=np.full(3, 0.5), target=np.asarray([1.0, 0.0, 1.0]),
        )
        np.testing.assert_array_equal(visits, [2, 1, 2, 0])
        np.testing.assert_allclose(squared, [2.0, 9.0, 5.0, 0.0])
        np.testing.assert_allclose(fisher, [0.5, 2.25, 1.25, 0.0])
        np.testing.assert_allclose(gradient, [-1.0, 1.5, -0.5, 0.0])

    def test_zero_l2_unseen_conventions_are_total(self):
        variance, effective, ratio, classes = patterneval_identifiability.summarize(
            np.asarray([0.5, 0.0]), np.asarray([2, 0]), 0.0
        )
        self.assertEqual(variance[0], 2.0)
        self.assertTrue(np.isinf(variance[1]))
        np.testing.assert_array_equal(effective, [1.0, 0.0])
        self.assertEqual(classes.tolist(), ["DATA_DOMINATED", "UNSEEN"])

    def test_feature_only_mode_has_no_gradient(self):
        *_, gradient = patterneval_identifiability.diagonal_statistics(
            self.indptr, self.indices, self.values, 4
        )
        self.assertIsNone(gradient)


class ActiveSelectionTests(unittest.TestCase):
    def test_leverage_and_tie_break_are_deterministic(self):
        scores = jfi_active_select.leverage_scores(
            np.asarray([0, 1, 2, 2]), np.asarray([0, 0]), np.asarray([1.0, 1.0]),
            np.asarray([1.0]), 1.0,
        )
        np.testing.assert_allclose(scores, [0.5, 0.5, 0.0])
        first = jfi_active_select.deterministic_order(scores, ["a", "b", "c"], 17)
        second = jfi_active_select.deterministic_order(scores, ["a", "b", "c"], 17)
        np.testing.assert_array_equal(first, second)
        self.assertEqual(first[-1], 2)

    def test_zero_l2_is_refused(self):
        with self.assertRaisesRegex(ValueError, "strictly positive"):
            jfi_active_select.leverage_scores(
                np.asarray([0, 1]), np.asarray([0]), np.asarray([1.0]),
                np.asarray([0.0]), 0.0,
            )


if __name__ == "__main__":
    unittest.main()
