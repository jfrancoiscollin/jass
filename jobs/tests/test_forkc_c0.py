#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


C0 = load("forkc_c0_gate", ROOT / "jobs/tools/forkc_c0_gate.py")
PA = load("policy_agreement", ROOT / "jobs/tools/policy_agreement.py")


def policy(divergence: float) -> dict:
    return {"complete": 200, "divergence": divergence, "agreement": 1 - divergence}


def conversion(p3: float, p4: float) -> dict:
    return {"p3_mince": p3, "p4_egal": p4}


class ForkCC0Tests(unittest.TestCase):
    def test_proceed_requires_divergence_and_hard_gain(self):
        result = C0.decide(
            policy_raw=policy(0.08),
            policy_refit=policy(0.12),
            gate_refit_vs_strong={"n": 600, "ci_high": 0.56},
            conversion_baseline=conversion(0.49, 0.51),
            conversion_refit=conversion(0.53, 0.53),
        )
        self.assertEqual(result["scientific_status"], "proceed_t1")

    def test_same_policy_stops(self):
        result = C0.decide(
            policy_raw=policy(0.01),
            policy_refit=policy(0.02),
            gate_refit_vs_strong={"n": 600, "ci_high": 0.56},
            conversion_baseline=conversion(0.49, 0.51),
            conversion_refit=conversion(0.60, 0.60),
        )
        self.assertEqual(result["scientific_status"], "stop_same_policy")

    def test_flat_hard_conversion_stops(self):
        result = C0.decide(
            policy_raw=policy(0.10),
            policy_refit=policy(0.10),
            gate_refit_vs_strong={"n": 600, "ci_high": 0.56},
            conversion_baseline=conversion(0.49, 0.51),
            conversion_refit=conversion(0.50, 0.51),
        )
        self.assertEqual(result["scientific_status"], "stop_flat_c0")

    def test_absolute_regression_stops(self):
        result = C0.decide(
            policy_raw=policy(0.10),
            policy_refit=policy(0.10),
            gate_refit_vs_strong={"n": 600, "ci_high": 0.49},
            conversion_baseline=conversion(0.49, 0.51),
            conversion_refit=conversion(0.55, 0.55),
        )
        self.assertEqual(result["scientific_status"], "stop_regression")

    def test_policy_summary_does_not_hide_errors(self):
        rows = [
            {"move_a": [1, 2, []], "move_b": [1, 2, []]},
            {"move_a": [1, 2, []], "move_b": [1, 3, []]},
            {"move_a": None, "move_b": [1, 3, []]},
        ]
        report = PA.summarize(rows, requested=3)
        self.assertEqual(report["complete"], 2)
        self.assertEqual(report["errors"], 1)
        self.assertEqual(report["divergence"], 0.5)


if __name__ == "__main__":
    unittest.main()
