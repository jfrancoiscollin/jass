#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

from jobs.tools import l3_curriculum_error_trace_variability_screen as target
from jobs.tools import l3_curriculum_error_paired_coverage_screen as coverage
from jobs.tools import l3_curriculum_search_error_atlas as source


def _profile(index: int, *, variable: bool = True) -> dict:
    actions = ("1-2", "3-4", "5-6")
    def orientation(reverse: bool) -> dict:
        depths = {}
        for depth in (6, 7, 8, 9):
            moves = []
            for offset, action in enumerate(actions):
                score = float((offset + index + depth) % 5) if variable else 0.0
                moves.append({"action": source._mapped_image_action(action) if reverse else action, "score": score})
            if variable and (index + depth) % 3 == 0:
                moves = moves[:-1]
            depths[str(depth)] = {"moves": moves}
        return {"depths": depths}
    return {
        "source": {"opening_id": f"o{index}", "game_uid": f"g{index}", "exact_state_key": f"s{index}"},
        "trace": {"original": orientation(False), "exact_image": orientation(True)},
    }


def _inputs(n: int = 140) -> tuple[dict, dict]:
    pairs = []
    for index in range(n):
        pairs.append({"pair_id": index, "split": "discovery" if index < 120 else "confirm", "error": _profile(index), "control": _profile(index + 1000)})
    matched = {
        "schema": source.SCHEMA_PAIRS,
        "matching_passed": True,
        "matched_pairs": n,
        "pairs_by_split": {"discovery": 120, "confirm": 20},
        "pairs": pairs,
    }
    failed = {
        "schema": coverage.SCHEMA,
        "verdict": coverage.NOT_ESTABLISHED,
        "fixed_gate": {"lower_margin_cp": 0.0, "upper_margin_cp": 0.0},
        "exact_action_value_reads": 0,
        "outer_confirm_action_value_reads": 0,
        "diagnostic_fits": 0,
        "strength_games": 0,
        "frozen_reads": 0,
    }
    return matched, failed


class TraceVariabilityScreenTests(unittest.TestCase):
    def test_target_free_diagnostic_selects_first_supported_proxy(self):
        pairs, failed = _inputs()
        report = target.run(pairs, failed)
        self.assertTrue(report["passed"])
        self.assertEqual(report["verdict"], target.READY)
        self.assertIsNotNone(report["selected_proxy"])
        self.assertEqual(report["exact_action_value_reads"], 0)
        self.assertEqual(report["outer_confirm_profile_rows_examined"], 0)
        self.assertFalse(report["promotion_authorized"])

    def test_confirm_target_is_not_traversed(self):
        pairs, failed = _inputs()
        for row in pairs["pairs"]:
            if row["split"] == "confirm":
                row["error"]["action_values"] = {"sealed": True}
        report = target.run(pairs, failed)
        self.assertEqual(report["outer_confirm_profile_rows_examined"], 0)

    def test_discovery_target_fails_closed(self):
        pairs, failed = _inputs()
        pairs["pairs"][0]["error"]["action_values"] = {}
        with self.assertRaisesRegex(ValueError, "contains action targets"):
            target.run(pairs, failed)

    def test_nonzero_margin_failure_is_not_reopened(self):
        pairs, failed = _inputs()
        failed = copy.deepcopy(failed); failed["fixed_gate"]["upper_margin_cp"] = 1.0
        with self.assertRaisesRegex(ValueError, "zero-width"):
            target.run(pairs, failed)


if __name__ == "__main__":
    unittest.main()
