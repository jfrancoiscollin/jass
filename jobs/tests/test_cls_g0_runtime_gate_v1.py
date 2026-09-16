from __future__ import annotations

import math
from pathlib import Path
import unittest

import numpy as np

from jobs.tools import cls_g0_runtime_gate as gate

ROOT = Path(__file__).resolve().parents[2]


class CLSG0RuntimeGateV1Tests(unittest.TestCase):
    def test_identity_candidate_passes_all_four_gates(self) -> None:
        probe = []
        deep512 = []
        deep = []
        for i, phase in enumerate(gate.PHASES):
            root = str(100 + i)
            move = f"{10+i}-{15+i}"
            deep512.append({"parent_id": root, "phase": phase})
            deep.append({"root_id": root, "budget": str(gate.DEEP_BUDGET),
                         "bestmove_canonical": move})
            for arm in ("parent", "candidate"):
                probe.append({
                    "root_id": root,
                    "arm": arm,
                    "nps": "100000",
                    "completed_nominal_depth": "10",
                    "nodes_to_target": "50000",
                    "target_depth": "9",
                    "bestmove_canonical": move,
                })
        vectors = gate.paired_vectors(probe, deep512, deep, roots_per_phase=1)
        metrics = gate.bootstrap(vectors, replicates=2000, seed=123)
        result = gate.decide(metrics)
        self.assertTrue(result["pass"])
        self.assertEqual(result["terminal"], gate.PASS_TERMINAL)
        self.assertEqual(result["alpha_spent"], 0)
        self.assertFalse(result["promotion_authorized"])
        self.assertFalse(result["bake_authorized"])

    def test_each_frozen_catastrophe_boundary_can_fail(self) -> None:
        zero = {"q025": 0.0, "median": 0.0, "q975": 0.0}
        metrics = {
            "log_nps_ratio": dict(zero),
            "depth_delta": dict(zero),
            "log_nodes_to_depth_ratio": dict(zero),
            "agreement_delta": dict(zero),
        }
        self.assertTrue(gate.decide(metrics)["pass"])

        bad = {key: dict(value) for key, value in metrics.items()}
        bad["log_nps_ratio"]["q025"] = math.log(0.79)
        self.assertFalse(gate.decide(bad)["gates"]["nps"]["pass"])

        bad = {key: dict(value) for key, value in metrics.items()}
        bad["depth_delta"]["q025"] = -1.01
        self.assertFalse(gate.decide(bad)["gates"]["completed_nominal_depth"]["pass"])

        bad = {key: dict(value) for key, value in metrics.items()}
        bad["log_nodes_to_depth_ratio"]["q975"] = math.log(1.51)
        self.assertFalse(gate.decide(bad)["gates"]["nodes_to_depth"]["pass"])

        bad = {key: dict(value) for key, value in metrics.items()}
        bad["agreement_delta"]["q025"] = -0.051
        self.assertFalse(gate.decide(bad)["gates"]["search_transfer"]["pass"])

    def test_gate_thresholds_match_frozen_contract(self) -> None:
        self.assertEqual(gate.BOOTSTRAP_REPLICATES, 100_000)
        self.assertEqual(gate.BOOTSTRAP_SEED, 2026091605)
        self.assertEqual(gate.NPS_FLOOR, 0.80)
        self.assertEqual(gate.DEPTH_FLOOR, -1.0)
        self.assertEqual(gate.NODES_TO_DEPTH_CEILING, 1.50)
        self.assertEqual(gate.TRANSFER_FLOOR, -0.05)

    def test_probe_enforces_parent_trace_parity_before_candidate(self) -> None:
        text = (ROOT / "jobs/tools/cls_g0_runtime_probe.cpp").read_text(encoding="utf-8")
        first = text.index("// Phase 1: prove SearchDecisionTrace is passive")
        second = text.index("// Phase 2: only after all trace passivity checks succeed")
        self.assertLess(first, second)
        self.assertIn("same_public_result(off.result, on.result)", text)
        self.assertIn("SearchDecisionBound::Exact", text)
        self.assertIn("attempt.all_actions_searched", text)
        self.assertIn("value = attempt.nodes_after", text)
        self.assertNotIn("go depth", text.lower())

    def test_phase_or_arm_drift_fails_closed(self) -> None:
        with self.assertRaises(gate.GateError):
            gate.build_phase_map([{"parent_id": "1", "phase": "P0"}], roots_per_phase=1)
        with self.assertRaises(gate.GateError):
            gate.index_probe([
                {"root_id": "1", "arm": "parent"},
                {"root_id": "1", "arm": "parent"},
            ])


if __name__ == "__main__":
    unittest.main()
