#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from jobs.tools.l3_context4_uncertainty_screen import (
    _donor_map,
    aggregate_rows,
    prepare_selection,
)


class Context4UncertaintyScreenTests(unittest.TestCase):
    def test_prepare_selection_is_deterministic_and_balanced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p1 = root / "p1.fen"
            p2 = root / "p2.fen"
            p1.write_text("\n".join(f"W:W{i}:B{51-i}" for i in range(1, 11)) + "\n")
            p2.write_text("\n".join(f"B:W{i}:B{51-i}" for i in range(11, 21)) + "\n")
            a = prepare_selection([("P1", p1), ("P2", p2)], per_pool=4, seed=7)
            b = prepare_selection([("P1", p1), ("P2", p2)], per_pool=4, seed=7)
            self.assertEqual(a, b)
            self.assertEqual(a["total"], 8)
            self.assertEqual(sum(row["pool_index"] == 1 for row in a["rows"]), 4)
            self.assertEqual(sum(row["pool_index"] == 2 for row in a["rows"]), 4)

    def test_pool_shuffle_has_no_fixed_points_and_preserves_membership(self):
        rows = [
            {"ordinal": 0, "pool_index": 1},
            {"ordinal": 1, "pool_index": 1},
            {"ordinal": 2, "pool_index": 1},
            {"ordinal": 3, "pool_index": 2},
            {"ordinal": 4, "pool_index": 2},
            {"ordinal": 5, "pool_index": 2},
        ]
        donor, report = _donor_map(rows, 123)
        self.assertEqual(report["fixed_points"], 0)
        by_ord = {row["ordinal"]: row["pool_index"] for row in rows}
        self.assertEqual(set(donor), set(by_ord))
        for target, source in donor.items():
            self.assertNotEqual(target, source)
            self.assertEqual(by_ord[target], by_ord[source])

    def test_positive_directional_signal_passes(self):
        rows = []
        ordinal = 0
        # Within each pool, own context prefers top2 exactly on rows whose
        # deeper judge says top2 is better.  The poolwise rotated control
        # breaks that alignment while preserving the same delta marginal.
        for pool in (1, 2):
            for index in range(16):
                judge = 30.0 if index % 2 == 0 else -30.0
                context = 1.0 if index % 2 == 0 else -1.0
                rows.append(
                    {
                        "ordinal": ordinal,
                        "pool_index": pool,
                        "pool_label": f"P{pool}",
                        "context_delta_top2_minus_top1": context,
                        "judge_delta_top2_minus_top1_cp": judge,
                    }
                )
                ordinal += 1
        result = aggregate_rows(
            rows,
            shuffle_seed=1,
            bootstrap_samples=5000,
            bootstrap_seed=2,
            min_total=16,
            min_per_pool=8,
            min_aligned_flips=8,
        )
        self.assertTrue(result["screen_passed"])
        self.assertEqual(result["verdict"], "JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_PASSED")
        self.assertGreater(result["aligned_vs_shuffled_gain"]["ci95_cp"][0], 0.0)

    def test_nonpositive_signal_fails(self):
        rows = []
        ordinal = 0
        for pool in (1, 2):
            for index in range(12):
                rows.append(
                    {
                        "ordinal": ordinal,
                        "pool_index": pool,
                        "pool_label": f"P{pool}",
                        "context_delta_top2_minus_top1": 1.0 if index % 2 == 0 else -1.0,
                        "judge_delta_top2_minus_top1_cp": -10.0,
                    }
                )
                ordinal += 1
        result = aggregate_rows(
            rows,
            shuffle_seed=7,
            bootstrap_samples=2000,
            bootstrap_seed=8,
            min_total=16,
            min_per_pool=8,
            min_aligned_flips=8,
        )
        self.assertFalse(result["screen_passed"])
        self.assertEqual(result["verdict"], "JASS_CONTEXT4_UNCERTAINTY_DECISION_SCREEN_FAILED")


if __name__ == "__main__":
    unittest.main()
