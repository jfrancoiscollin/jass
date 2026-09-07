from __future__ import annotations

import struct
from pathlib import Path
import tempfile
import unittest

import numpy as np

from jobs.tools import d1_terminal_autopsy as autopsy


class D1TerminalAutopsyTests(unittest.TestCase):
    def test_parent_rows_and_aggregate_detect_reversal_shape(self) -> None:
        groups = [
            {"parent_id": 0, "start": 0, "count": 2, "selected_local_action_index": 0,
             "parent_stm": 1, "split": "train", "cell": "P0_stm1"},
            {"parent_id": 1, "start": 2, "count": 2, "selected_local_action_index": 0,
             "parent_stm": 1, "split": "valid", "cell": "P0_stm1"},
            {"parent_id": 2, "start": 4, "count": 2, "selected_local_action_index": 0,
             "parent_stm": 0, "split": "test", "cell": "P0_stm0"},
        ]
        # Treatment improves the selected action on train, but pushes it the wrong
        # way on held-out parents. White POV uses the negated black score.
        z_a = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        z_b = np.array([2.0, -2.0, -2.0, 2.0, 2.0, -2.0])
        rows = autopsy.parent_rows(z_a, z_b, groups)
        train = autopsy._aggregate([rows[0]])
        valid = autopsy._aggregate([rows[1]])
        test = autopsy._aggregate([rows[2]])
        self.assertGreater(train["delta_ce_mean"], 0.0)
        self.assertLess(valid["delta_ce_mean"], 0.0)
        self.assertLess(test["delta_ce_mean"], 0.0)
        self.assertEqual(rows[0]["action_band"], "2-4")

    def test_probability_can_rise_while_cross_entropy_worsens(self) -> None:
        rows = [
            {
                "delta_ce_control_minus_listwise": -2.0,
                "control": {"cross_entropy": 0.5, "selected_probability": 0.60, "top1": 1, "top2": 1},
                "listwise": {"cross_entropy": 2.5, "selected_probability": 0.08, "top1": 0, "top2": 0},
            },
            {
                "delta_ce_control_minus_listwise": 0.2,
                "control": {"cross_entropy": 2.0, "selected_probability": 0.10, "top1": 0, "top2": 0},
                "listwise": {"cross_entropy": 1.8, "selected_probability": 0.80, "top1": 1, "top2": 1},
            },
        ]
        agg = autopsy._aggregate(rows)
        self.assertLess(agg["delta_ce_mean"], 0.0)
        self.assertGreater(agg["selected_probability_delta"], 0.0)
        self.assertGreater(agg["catastrophic_regression_rate_delta_lt_minus1"], 0.0)

    def test_model_displacement_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.pjtw"
            b = Path(td) / "b.pjtw"
            header = struct.pack("<5I", 0x57544A50, 3, 1000, 3, 2)
            wa = np.array([1, -2, 0, 3, 4, -5, 6, 7, -8, 9], dtype="<i4")
            wb = np.array([2, 2, 0, 1, 4, -3, 6, -7, -8, 19], dtype="<i4")
            a.write_bytes(header + wa.tobytes())
            b.write_bytes(header + wb.tobytes())
            result = autopsy.model_displacement(a, b)
            self.assertEqual(result["header"]["n_patterns"], 3)
            self.assertEqual(result["header"]["n_extras"], 2)
            self.assertGreater(result["blocks"]["all"]["changed"], 0)
            self.assertGreater(result["blocks"]["all"]["sign_flips"], 0)


if __name__ == "__main__":
    unittest.main()
