#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools/teacher_smoke_gate.py"
SPEC = importlib.util.spec_from_file_location("teacher_smoke_gate", MODULE)
TG = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TG)


def cell(hard: float, gate: float = 0.55) -> dict:
    return {
        "conversion": {"p3_mince": hard, "p4_egal": hard},
        "vs_a": {"n": 600, "ci_high": gate},
        "vs_absolute": {"n": 600, "ci_high": gate},
    }


class TeacherSmokeGateTests(unittest.TestCase):
    def test_b1_wins_within_simplicity_tolerance(self):
        result = TG.decide({
            "A": cell(0.50), "B1": cell(0.525),
            "B2": cell(0.527), "B3": cell(0.529),
        })
        self.assertEqual(result["winner"], "B1")
        self.assertEqual(result["scientific_status"], "confirm_b1")

    def test_b3_wins_when_materially_better(self):
        result = TG.decide({
            "A": cell(0.50), "B1": cell(0.51),
            "B2": cell(0.52), "B3": cell(0.54),
        })
        self.assertEqual(result["winner"], "B3")

    def test_regression_disqualifies_cell(self):
        result = TG.decide({
            "A": cell(0.50), "B1": cell(0.54, gate=0.49),
            "B2": cell(0.51), "B3": cell(0.51),
        })
        self.assertEqual(result["scientific_status"], "complete_no_signal")

    def test_missing_measure_is_technical(self):
        cells = {"A": cell(0.50), "B1": cell(0.53), "B2": cell(0.53), "B3": cell(0.53)}
        cells["B2"]["vs_a"] = {"n": 0, "ci_high": None}
        result = TG.decide(cells)
        self.assertEqual(result["scientific_status"], "stop_technical")


if __name__ == "__main__":
    unittest.main()
