from __future__ import annotations

import copy
import unittest

from jobs.tools import adaptive_sibling_b2_projection as projection
from jobs.tools import adaptive_sibling_b2_statistical_completion_recovery as recovery


def population():
    allocations = []
    lines = []
    receipts = []
    for parent_id in range(4000):
        first = parent_id * 2
        value = {
            "schema": projection.INPUT_SCHEMA,
            "parent_id": parent_id,
            "phase": "P0",
            "stm": parent_id % 2,
            "rows": [
                {
                    "row_index": first,
                    "child_rule_terminal": False,
                    "child_tb_exact": False,
                    "exact_parent_utility": 2,
                    "q5k_parent": 10,
                    "q50_parent": 10,
                    "nodes5k": 5000,
                    "nodes50k": 50000,
                    "nodes200k": 200000,
                },
                {
                    "row_index": first + 1,
                    "child_rule_terminal": False,
                    "child_tb_exact": False,
                    "exact_parent_utility": 2,
                    "q5k_parent": 0,
                    "q50_parent": 0,
                    "nodes5k": 5000,
                    "nodes50k": 50000,
                    "nodes200k": 200000,
                },
            ],
        }
        line = projection.canonical_json_line(value)
        receipt, _ = projection.project_parent(projection.parse_parent(value))
        allocations.append(value)
        lines.append(line)
        receipts.append(receipt)
    return allocations, lines, receipts


class CompletionRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allocations, cls.lines, cls.receipts = population()

    def test_repairs_only_hash_binding_on_authenticated_parent_1216(self):
        receipts = copy.deepcopy(self.receipts)
        receipts[1216]["projection_input_sha256"] = "0" * 64
        repaired, changes = recovery.repair_projection_receipts(
            self.allocations, self.lines, receipts)
        self.assertEqual(changes, [{
            "parent_id": 1216,
            "fields": ["projection_input_sha256"],
        }])
        self.assertEqual(
            repaired[1216]["projection_input_sha256"],
            recovery.sha(self.lines[1216]),
        )
        for key, value in self.receipts[1216].items():
            if key not in recovery.HASH_FIELDS:
                self.assertEqual(repaired[1216][key], value)

    def test_refuses_policy_or_cost_drift(self):
        receipts = copy.deepcopy(self.receipts)
        receipts[1216]["projection_input_sha256"] = "0" * 64
        receipts[1216]["shadow_nodes5"] += 1
        with self.assertRaisesRegex(recovery.RecoveryError, "policy/cost receipt drift"):
            recovery.repair_projection_receipts(self.allocations, self.lines, receipts)

    def test_rebuild_manifest_changes_only_receipt_bindings(self):
        receipts = copy.deepcopy(self.receipts)
        receipts[1216]["projection_input_sha256"] = "0" * 64
        repaired, _ = recovery.repair_projection_receipts(
            self.allocations, self.lines, receipts)
        allocation_raw = b"".join(self.lines)
        original = {
            "schema": projection.MANIFEST_SCHEMA,
            "policy": {"M5": 100, "M50": 60, "minimum_survivors": 2},
            "parents": 4000,
            "rows": 8000,
            "input_jsonl_sha256": "0" * 64,
            "allocation_receipts_jsonl_sha256": "0" * 64,
            "canonical_serialization": "UTF-8, compact sorted-key JSON, LF per record",
            "q200_value_reads": 0,
            "q200_label_reads": 0,
            "q200_branches": 0,
            "nodes200k_validated_rows": 8000,
            "nodes200k_policy_reads": 0,
            "nodes200k_policy_branches": 0,
            "nodes200k_preseal_aggregation_reads": 0,
            "nodes200k_aggregation_reads": 8000,
            "searches": 0,
            "fits": 0,
            "strength_games": 0,
            "parent_receipts": [],
        }
        rebuilt, receipt_raw, manifest_raw = recovery.rebuild_projection_manifest(
            original, allocation_raw, repaired)
        self.assertEqual(rebuilt["policy"], original["policy"])
        self.assertEqual(rebuilt["q200_value_reads"], 0)
        self.assertEqual(rebuilt["q200_label_reads"], 0)
        self.assertEqual(rebuilt["q200_branches"], 0)
        self.assertEqual(rebuilt["input_jsonl_sha256"], recovery.sha(allocation_raw))
        self.assertEqual(
            rebuilt["allocation_receipts_jsonl_sha256"], recovery.sha(receipt_raw))
        self.assertEqual(len(rebuilt["parent_receipts"]), 4000)
        self.assertEqual(manifest_raw, recovery.canonical(rebuilt))

    def test_failure_summary_never_authorizes_science(self):
        summary = recovery.failure_summary("RECOVERY", "synthetic")
        self.assertIsNone(summary["scientific_verdict"])
        self.assertEqual(summary["new_teacher_searches"], 0)
        self.assertEqual(summary["fits"], 0)
        self.assertEqual(summary["strength_games"], 0)
        self.assertEqual(summary["promotions"], 0)
        self.assertEqual(summary["bakes"], 0)


if __name__ == "__main__":
    unittest.main()
