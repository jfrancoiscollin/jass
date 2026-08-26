#!/usr/bin/env python3
import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("deep_sibling_pairwise", ROOT / "tools" / "deep_sibling_pairwise.py")
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def sib(idx, *, parent=0, q50=0, q200=0, exact=2):
    return mod.SiblingMeta(
        row_index=idx, parent_id=parent, parent_stm=0, from_sq=idx + 1, to_sq=idx + 2,
        num_captures=0, captured_kings=0, promotes=0, moving_king=0,
        exact_parent_utility=exact, t_baseline_parent=0, q5k_parent=0,
        q50_parent=q50, q200_parent=q200,
    )


class DeepSiblingPairwiseTests(unittest.TestCase):
    def test_stable_pair_thresholds_and_sign(self):
        b = sib(1)
        self.assertEqual(mod.stable_relation(sib(0, q50=10, q200=30), b), 1)
        self.assertEqual(mod.stable_relation(sib(0, q50=-10, q200=-30), b), -1)
        self.assertEqual(mod.stable_relation(sib(0, q50=9, q200=100), b), 0)
        self.assertEqual(mod.stable_relation(sib(0, q50=100, q200=29), b), 0)
        self.assertEqual(mod.stable_relation(sib(0, q50=10, q200=-30), b), 0)
        self.assertEqual(mod.stable_relation(sib(0, q50=0, q200=100), b), 0)

    def test_exact_wdl_precedence(self):
        a = sib(0, q50=-100, q200=-100, exact=1)
        b = sib(1, q50=100, q200=100, exact=0)
        self.assertEqual(mod.stable_relation(a, b), 1)
        c = sib(2, q50=20, q200=40, exact=0)
        d = sib(3, q50=0, q200=0, exact=0)
        self.assertEqual(mod.stable_relation(c, d), 1)

    def test_deterministic_pair_cap_is_canonical_prefix(self):
        pairs = {1: [(4, 5), (6, 7)], 0: [(0, 1), (2, 3)]}
        x = np.arange(8 * 3, dtype=np.float64).reshape(8, 3)
        d, keys = mod.pair_matrix(pairs, [1, 0], x, 3)
        self.assertEqual(keys, [(0, 0, 1), (0, 2, 3), (1, 4, 5)])
        np.testing.assert_allclose(d[0], x[0] - x[1])

    def test_top_hit_uses_only_stable_partial_order(self):
        rows = [0, 1, 2]
        pairs = [(0, 1)]
        good = np.asarray([3.0, 2.0, 1.0])
        pair, top = mod.parent_metrics(rows, pairs, good)
        self.assertEqual(pair, 1.0)
        self.assertEqual(top, 1.0)
        unstable_selected = np.asarray([2.0, 1.0, 9.0])
        _, top2 = mod.parent_metrics(rows, pairs, unstable_selected)
        self.assertEqual(top2, 0.0)

    def test_bootstrap_is_reproducible_from_frozen_seed(self):
        p = np.asarray([0.1, 0.2, -0.1, 0.3])
        t = np.asarray([0.0, 0.1, 0.2, -0.1])
        a = mod.bootstrap_deltas(p, t, 1000, 2026083103)
        b = mod.bootstrap_deltas(p, t, 1000, 2026083103)
        self.assertEqual(a, b)
        self.assertEqual(a["pairwise"]["seed"], 2026083103)
        self.assertEqual(a["top_hit"]["seed"], 2026083103)


if __name__ == "__main__":
    unittest.main()
