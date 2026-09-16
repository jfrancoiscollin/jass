from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/experiments/L3_CLS_G0_RUNTIME_CATASTROPHE_CONTRACT_V1_20260916.json"


class CLSG0RuntimeContractV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_immutable_curriculum_anchor(self) -> None:
        anchor = self.contract["anchor"]
        self.assertEqual(
            anchor["sha256"],
            "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
        )
        self.assertTrue(anchor["generation_1_direct_parent"])
        self.assertTrue(anchor["required_in_every_strength_gauntlet"])

    def test_catastrophe_thresholds_are_frozen(self) -> None:
        gates = self.contract["gates"]
        self.assertEqual(gates["nps"]["operator"], ">=")
        self.assertEqual(gates["nps"]["threshold"], 0.8)
        self.assertEqual(gates["completed_nominal_depth"]["threshold"], -1.0)
        self.assertEqual(gates["nodes_to_depth"]["operator"], "<=")
        self.assertEqual(gates["nodes_to_depth"]["threshold"], 1.5)
        self.assertEqual(gates["nodes_to_depth"]["missing_root"], "FAIL")
        self.assertEqual(gates["search_transfer"]["threshold"], -0.05)
        self.assertTrue(self.contract["decision"]["all_gates_required"])
        self.assertEqual(self.contract["decision"]["missing_or_nonfinite"], "FAIL")

    def test_same_search_nodes_to_depth_is_mandatory(self) -> None:
        runtime = self.contract["runtime"]
        self.assertTrue(runtime["same_search_nodes_to_depth_required"])
        self.assertEqual(runtime["nodes_to_depth_source"], "SearchDecisionTrace")
        self.assertTrue(runtime["depth_n_surrogate_forbidden"])
        search_hpp = (ROOT / "src/search.hpp").read_text(encoding="utf-8")
        self.assertIn("struct SearchDecisionAttemptTrace", search_hpp)
        self.assertIn("std::uint64_t nodes_before", search_hpp)
        self.assertIn("std::uint64_t nodes_after", search_hpp)
        self.assertIn("SearchDecisionTrace* search_decision_trace", search_hpp)

    def test_zero_alpha_no_promotion_boundary(self) -> None:
        decision = self.contract["decision"]
        self.assertEqual(decision["alpha_spent"], 0)
        self.assertFalse(decision["promotion_authorized"])
        self.assertFalse(decision["bake_authorized"])
        self.assertFalse(decision["same_candidate_retry_after_failure"])
        self.assertFalse(self.contract["strength_boundary"]["automatic_promotion"])

    def test_upstream_is_fail_closed_until_terminal_pin(self) -> None:
        upstream = self.contract["upstream"]
        self.assertEqual(
            upstream["job_id"],
            "cpx62-2015-l3-cls-bottleneck-classification-production-v1",
        )
        self.assertEqual(upstream["required_terminal"], "CLS_DIAGNOSIS_COMPLETE_V1")
        self.assertEqual(upstream["required_classification"], "mixed")
        self.assertEqual(upstream["required_supported_axes"], ["SEARCH", "DECISION-EVAL"])
        if self.contract["status"] == "ACTIVE":
            self.assertRegex(upstream["attempt_id"], r"^20260916T\d{6}Z-[0-9a-f]{8}$")
            self.assertRegex(upstream["code_sha"], r"^[0-9a-f]{40}$")
            self.assertRegex(upstream["launch_receipt_sha256"], r"^[0-9a-f]{64}$")
        else:
            self.assertEqual(self.contract["status"], "DRAFT_PENDING_CLS_DIAGNOSIS_PRODUCTION_PIN")
            self.assertIsNone(upstream["attempt_id"])
            self.assertIsNone(upstream["code_sha"])
            self.assertIsNone(upstream["launch_receipt_sha256"])


if __name__ == "__main__":
    unittest.main()
