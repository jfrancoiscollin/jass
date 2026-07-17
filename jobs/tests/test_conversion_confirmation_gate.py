#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools/conversion_confirmation_gate.py"
SPEC = importlib.util.spec_from_file_location("conversion_confirmation_gate", MODULE)
CG = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CG)


def report(rate: float, n: int = 30000) -> dict:
    return {
        "n_pos": n,
        "n_win": round(rate * n),
        "complete": True,
    }


def payload(candidate_p3: float = 0.53, candidate_p4: float = 0.50) -> dict:
    return {
        "smoke_decision": {
            "decision": "confirm",
            "scientific_status": "confirm_b1",
            "winner": "B1",
        },
        "winner": "B1",
        "baseline_p3": report(0.50),
        "candidate_p3": report(candidate_p3),
        "baseline_p4": report(0.50),
        "candidate_p4": report(candidate_p4),
        "vs_a": {"n": 1200, "ci_high": 0.53},
        "vs_absolute": {"n": 1200, "ci_high": 0.52},
    }


class ConversionConfirmationGateTests(unittest.TestCase):
    def test_power_plan_is_conservative_and_finite(self):
        plan = CG.power_plan(report(0.50, 600), min_delta=0.02)
        self.assertGreater(plan["required_n_per_arm"], 5000)
        self.assertEqual(plan["method"], "two_independent_proportions_conservative")

    def test_strong_fresh_p3_signal_confirms(self):
        result = CG.decide(payload())
        self.assertEqual(result["scientific_status"], "confirmed")
        self.assertEqual(result["winner"], "B1")
        self.assertGreater(result["p3"]["ci_low"], 0.0)

    def test_small_sample_is_underpowered(self):
        data = payload()
        data["baseline_p3"] = report(0.50, 500)
        data["candidate_p3"] = report(0.55, 500)
        result = CG.decide(data)
        self.assertEqual(result["scientific_status"], "complete_underpowered")

    def test_generalist_regression_blocks(self):
        data = payload()
        data["vs_absolute"] = {"n": 1200, "ci_high": 0.49}
        result = CG.decide(data)
        self.assertEqual(result["scientific_status"], "stop_regression")

    def test_p4_point_regression_blocks(self):
        result = CG.decide(payload(candidate_p4=0.47))
        self.assertEqual(result["scientific_status"], "stop_p4_regression")

    def test_smoke_winner_mismatch_is_technical(self):
        data = payload()
        data["winner"] = "B3"
        result = CG.decide(data)
        self.assertEqual(result["scientific_status"], "stop_technical")


if __name__ == "__main__":
    unittest.main()
