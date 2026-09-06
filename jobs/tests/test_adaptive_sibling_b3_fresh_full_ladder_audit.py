from __future__ import annotations

import unittest

from jobs.tools import adaptive_sibling_b2_teacher_source as full_teacher
from jobs.tools import adaptive_sibling_b3_fresh_audit_subset as subset
from jobs.tools import adaptive_sibling_b3_fresh_full_ladder_audit as subject


class FreshB3FullLadderAuditTests(unittest.TestCase):
    def _report(self, shard: int) -> dict:
        processed = len(range(shard, subject.AUDIT_PARENTS, subject.SHARDS))
        emitted = 2 * processed
        return {
            "schema": full_teacher.SHARD_SCHEMA,
            "input_parents": subject.AUDIT_PARENTS,
            "shard": shard,
            "nshards": subject.SHARDS,
            "book_enabled": False,
            "threads_per_search": 1,
            "fresh_tt_each_search": True,
            "fresh_engine_each_search": True,
            "engine_constructions": 3 * emitted,
            "jass_prefixed_environment_count": 0,
            "egdb_configuration_source": "explicit_positional_arguments",
            "egdb_required_available": True,
            "egdb_cache_mb": subject.EGDB_CACHE_MB,
            "node_limit_mode": "exact",
            "cheap_budget_nodes": 5_000,
            "screen_budget_nodes": 50_000,
            "teacher_budget_nodes": 200_000,
            "tt_mb": subject.TT_MB,
            "egdb_max_pieces": 7,
            "source_rows": subject.AUDIT_PARENTS,
            "processed_parent_rows": processed,
            "invalid_rows": 0,
            "duplicate_move_entries": 0,
            "emitted_siblings": emitted,
            "rule_terminal_children": 0,
            "exact_tb_children": 0,
            "cheap_searches": emitted,
            "screen_searches": emitted,
            "teacher_searches": emitted,
            "cheap_nodes": emitted * 5_000,
            "screen_nodes": emitted * 50_000,
            "teacher_nodes": emitted * 200_000,
            "teacher_scores_produced": True,
            "stable_pairs_selected": False,
            "fits": 0,
            "strength_games": 0,
            "promotion_authorized": False,
        }

    def test_frozen_contract(self) -> None:
        self.assertEqual(subject.AUDIT_PARENTS, 1000)
        self.assertEqual(subset.AUDIT_SEED, 2026110817)
        self.assertEqual(full_teacher.BUDGETS, (5_000, 50_000, 200_000))
        self.assertEqual(
            full_teacher.BASE_SOURCE_NORMALIZED_SHA256,
            "50813baaae1934ad155d05b6d28c8a908925b06d510863976c7cee9d6e98deb4",
        )
        self.assertEqual(subject.VERDICT, "B3_FRESH_FULL_LADDER_AUDIT_COMPLETE_V1")

    def test_complete_ladder_reports_validate_and_aggregate(self) -> None:
        reports = [self._report(shard) for shard in range(subject.SHARDS)]
        for shard, report in enumerate(reports):
            subject.validate_full_report(report, shard)
        aggregate = subject.aggregate_reports(reports)
        self.assertEqual(aggregate["processed_parent_rows"], 1000)
        self.assertEqual(aggregate["cheap_searches"], aggregate["emitted_siblings"])
        self.assertEqual(aggregate["screen_searches"], aggregate["emitted_siblings"])
        self.assertEqual(aggregate["teacher_searches"], aggregate["emitted_siblings"])
        self.assertEqual(aggregate["engine_constructions"], 3 * aggregate["emitted_siblings"])
        self.assertTrue(aggregate["full_ladder_executed"])

    def test_missing_ladder_search_fails_closed(self) -> None:
        report = self._report(0)
        report["screen_searches"] -= 1
        with self.assertRaisesRegex(subject.StageError, "screen_searches"):
            subject.validate_full_report(report, 0)

    def test_reference_source_identity_is_frozen_to_1837(self) -> None:
        self.assertEqual(subject.SOURCE_JOB,
                         "cpx62-1837-l3-decision-math-b3-fresh-source-selection-v1")
        self.assertEqual(subject.SOURCE_ATTEMPT, "20260906T141235Z-29084b25")
        self.assertEqual(subject.SOURCE_CODE_SHA,
                         "29084b25789b1a88c19a86f73c476eedc52acbc6")


if __name__ == "__main__":
    unittest.main()
