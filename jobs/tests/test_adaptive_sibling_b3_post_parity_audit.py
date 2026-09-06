from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tools import adaptive_sibling_b3_post_parity_audit as subject


class B3PostParityAuditTests(unittest.TestCase):
    def test_classify_zero_cost_distinguishes_all_exact_from_exact_win_shortcuts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            groups = root / "groups.tsv"
            receipts = root / "receipts.jsonl"
            parity_dir = root / "parity"
            parity_dir.mkdir()
            parity_path = parity_dir / "b3-real-adaptive-parity.json"

            with groups.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["parent_id", "child_rule_terminal", "child_tb_exact"],
                    delimiter="\t", lineterminator="\n",
                )
                writer.writeheader()
                for parent in range(4000):
                    zero = parent in subject.EXPECTED_ZERO_SEARCH
                    all_exact = parent in subject.EXPECTED_ALL_EXACT_ZERO_COST
                    mixed = parent in subject.EXPECTED_EXACT_WIN_ZERO_SEARCH
                    writer.writerow({
                        "parent_id": parent,
                        "child_rule_terminal": 1 if all_exact or mixed else 0,
                        "child_tb_exact": 0,
                    })
                    if mixed:
                        writer.writerow({
                            "parent_id": parent,
                            "child_rule_terminal": 0,
                            "child_tb_exact": 0,
                        })

            with receipts.open("w", encoding="utf-8", newline="") as handle:
                for parent in range(4000):
                    zero = parent in subject.EXPECTED_ZERO_SEARCH
                    value = {
                        "parent_id": parent,
                        "shadow_nodes_total": 0 if zero else 1,
                        "exact_shortcut_reason": (
                            "EXACT_WIN" if parent in subject.EXPECTED_EXACT_WIN_ZERO_SEARCH
                            else ("ALL_EXACT_DRAW" if parent in subject.EXPECTED_ALL_EXACT_ZERO_COST else None)
                        ),
                    }
                    handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")

            parity_path.write_bytes(subject.canonical({
                "zero_cost_parent_ids": subject.EXPECTED_ZERO_SEARCH,
            }))
            result = subject.classify_zero_cost(
                groups, receipts, {"b3-real-adaptive-parity.json": parity_path})
            self.assertEqual(result["all_exact_zero_cost_parent_ids"],
                             subject.EXPECTED_ALL_EXACT_ZERO_COST)
            self.assertEqual(result["mixed_exact_win_zero_search_parent_ids"],
                             subject.EXPECTED_EXACT_WIN_ZERO_SEARCH)
            self.assertEqual(result["zero_search_parent_count"], 8)
            self.assertEqual(result["all_exact_zero_cost_parent_count"], 6)

    def test_authenticate_parity_requires_frozen_policy_and_horizon_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            searches = {"5": 37789, "50": 25854, "200": 21420}
            nodes = {"5": 185536452, "50": 1271148094, "200": 4191356664}
            aggregate = {
                "processed_parent_rows": 4000,
                "emitted_siblings": 37811,
                "cheap_searches": searches["5"],
                "screen_searches": searches["50"],
                "teacher_searches": searches["200"],
                "cheap_nodes": nodes["5"],
                "screen_nodes": nodes["50"],
                "teacher_nodes": nodes["200"],
                "rule_terminal_children": 12,
                "exact_tb_children": 6,
                "engine_constructions": sum(searches.values()),
            }
            report = {
                "schema": "jass.adaptive_sibling_b3_parity.v1",
                "state": "completed",
                "verdict": subject.PARITY_VERDICT,
                "parents": 4000,
                "mismatches": [],
                "mismatch_count_capped": 0,
                "projection_policy": subject.POLICY,
                "fresh_b3_generation_authorized": True,
                "elapsed_fields_compared": False,
                "actual_searches": searches,
                "actual_nodes": nodes,
                "total_nodes": 5648041210,
                "fits": 0,
                "strength_games": 0,
                "promotion_authorized": False,
                "bake_authorized": False,
            }
            render = {
                "schema": "jass.adaptive_sibling_b3_teacher_source_adapter.v1",
                "policy": subject.POLICY,
                "budgets_nodes": subject.BUDGETS,
                "fresh_engine_each_search": True,
                "fresh_tt_each_search": True,
                "book_enabled": False,
                "threads_per_search": 1,
                "node_limit_mode": "exact",
                "q200_used_before_s50_seal": False,
                "search_decision_trace_affects_allocation": False,
                "fits": 0,
                "strength_games": 0,
                "promotion_authorized": False,
                "bake_authorized": False,
                "rendered_source_sha256": "f" * 64,
            }
            summary = {
                "schema": "jass.adaptive_sibling_b3_parity_stage.v1",
                "state": "completed",
                "verdict": subject.PARITY_VERDICT,
                "b2_terminal_prerequisite": "B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1",
                "b2_parents_replayed": 4000,
                "fresh_b3_parents": 0,
                "policy": subject.POLICY,
                "budgets_nodes": subject.BUDGETS,
                "fresh_b3_generation_authorized": True,
                "teacher": aggregate,
                "parity": {"actual_searches": searches, "actual_nodes": nodes,
                           "total_nodes": 5648041210},
                "rendered_source_sha256": "f" * 64,
                "fits": 0, "strength_games": 0, "promotions": 0, "bakes": 0,
            }
            values = {
                "b3-real-adaptive-parity.json": report,
                "b3-teacher-aggregate.json": aggregate,
                "b3-render-receipt.json": render,
                "scientific-summary.json": summary,
            }
            paths = {}
            for name, value in values.items():
                path = root / name
                path.write_bytes(subject.canonical(value))
                paths[name] = path
            with mock.patch.object(subject, "require_blob"):
                auth = subject.authenticate_parity(paths)
            self.assertTrue(auth["per_parent_real_node_cost_parity_authenticated"])
            self.assertEqual(auth["actual_searches"], searches)
            self.assertEqual(auth["total_nodes"], 5648041210)

    def test_diagnose_1834_preserves_exact_error_without_authorizing_fresh_data(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(subject, "require_blob"), \
             mock.patch.object(subject.exclusion_v2, "run", side_effect=RuntimeError("exact technical failure")):
            result = subject.diagnose_1834(Path(tmp))
        self.assertTrue(result["reproduced"])
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertEqual(result["error"], "exact technical failure")
        self.assertEqual(result["fresh_positions_generated"], 0)
        self.assertEqual(result["teacher_searches"], 0)


if __name__ == "__main__":
    unittest.main()
