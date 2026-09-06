from __future__ import annotations

import unittest

from jobs.tools import adaptive_sibling_b2_recovery_admissibility_preflight as preflight


class RecoveryAdmissibilityPreflightTests(unittest.TestCase):
    def test_hash_only_stored_failure_fresh_pass_is_admissible(self):
        result = preflight.classify_divergence(
            stored_failed=True,
            fresh_failed=False,
            differences=[{
                "path": "$.projection_input_sha256",
                "kind": "value",
                "left": "0" * 64,
                "right": "1" * 64,
            }],
        )
        self.assertEqual(result, {
            "admissible": True,
            "classification": "STALE_BINDING_METADATA_ONLY",
        })

    def test_fresh_projection_still_rejected_is_contract_mismatch(self):
        result = preflight.classify_divergence(
            stored_failed=True,
            fresh_failed=True,
            differences=[],
        )
        self.assertEqual(result, {
            "admissible": False,
            "classification": "PRODUCER_CONSUMER_CONTRACT_MISMATCH",
        })

    def test_non_hash_receipt_drift_is_blocked(self):
        result = preflight.classify_divergence(
            stored_failed=True,
            fresh_failed=False,
            differences=[{"path": "$.shadow_nodes5", "kind": "value", "left": 1, "right": 2}],
        )
        self.assertEqual(result, {
            "admissible": False,
            "classification": "NON_BINDING_RECEIPT_DRIFT",
        })

    def test_json_diff_reports_exact_nested_path(self):
        left = {"policy": {"S5_rows": [3, 4]}, "shadow_nodes5": 10}
        right = {"policy": {"S5_rows": [3, 5]}, "shadow_nodes5": 11}
        diff = preflight.json_diff(left, right)
        self.assertEqual([item["path"] for item in diff], [
            "$.policy.S5_rows[1]", "$.shadow_nodes5",
        ])

    def test_failure_summary_is_zero_science(self):
        summary = preflight.failure_summary("synthetic")
        self.assertIsNone(summary["scientific_verdict"])
        self.assertEqual(summary["bootstrap_replications_executed"], 0)
        self.assertEqual(summary["statistics_invocations"], 0)
        self.assertEqual(summary["new_teacher_searches"], 0)
        self.assertEqual(summary["fits"], 0)
        self.assertEqual(summary["strength_games"], 0)
        self.assertEqual(summary["promotions"], 0)
        self.assertEqual(summary["bakes"], 0)


if __name__ == "__main__":
    unittest.main()
