#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs/tools"))

import imbalance2_d0_report as report  # noqa: E402
import imbalance2_d0_replay as replay  # noqa: E402
import imbalance2_d0_select as select  # noqa: E402

RUNNER = ROOT / "jobs/templates/l3-imbalance2-d0-diagnostic-v1.sh"
PREPARED = ROOT / "jobs/prepared/l3-imbalance2-d0-20260720"
WRAPPERS = [
    PREPARED / "ccx33-l3-imbalance2-d0-diagnostic.sh",
    PREPARED / "cpx62-l3-imbalance2-d0-diagnostic.sh",
]


def trace(move: str, score: int = 0) -> dict[str, object]:
    return {"best_move": move, "score": score, "pv": [move], "nodes": 1}


class D0DiagnosticTests(unittest.TestCase):
    def test_rank_sentinels_is_bounded_unique_and_deterministic(self):
        rows = []
        for index in range(80):
            rows.append({
                "pool": "plateau-a.jnnw" if index % 2 == 0 else "plateau-b.jnnw",
                "index": index,
                "stratum": f"{index % 18 + 1}v{index % 18 + 3}",
                "g8_minus_g4_cost": 2.0 if index < 20 else (1.0 if index < 40 else -1.0),
                "g4_minus_reference_cost": 1.0 if 10 <= index < 50 else 0.0,
                "g8_minus_reference_cost": 2.0 if 10 <= index < 60 else 0.0,
                "stratum_ab_divergence": (index % 10) / 10.0,
            })
        first = select.rank_sentinels(rows, per_family=10, max_total=30)
        second = select.rank_sentinels(rows, per_family=10, max_total=30)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 30)
        keys = {(item["pool"], item["index"]) for item in first}
        self.assertEqual(len(keys), 30)
        self.assertEqual(first[0]["sentinel_id"], "D0-01")
        self.assertTrue(all(item["family"] for item in first))

    def test_depth_ladder_is_frozen(self):
        self.assertEqual(replay.parse_depths("8,10,12,14"), [8, 10, 12, 14])
        with self.assertRaises(ValueError):
            replay.parse_depths("8,10,12")

    def test_causal_hypotheses_are_separated(self):
        sentinel = {"fen": "W:W31:B1,2,3", "advantaged_side": "B", "g8_minus_g4_cost": 1.0}
        horizon = {
            "g4": {d: trace("1-2") for d in report.DEPTHS},
            "g8": {8: trace("1-2"), 10: trace("1-2"), 12: trace("3-4"), 14: trace("3-4")},
            "scan": {d: trace("3-4") for d in report.DEPTHS},
        }
        self.assertEqual(report.classify(sentinel, horizon)[0], "SEARCH_HORIZON_CANDIDATE")

        representation = {
            "g4": {d: trace("1-2") for d in report.DEPTHS},
            "g8": {d: trace("5-6") for d in report.DEPTHS},
            "scan": {d: trace("3-4") for d in report.DEPTHS},
        }
        self.assertEqual(
            report.classify(sentinel, representation)[0],
            "REPRESENTATION_OR_OBJECTIVE_CANDIDATE",
        )

        training = {
            "g4": {8: trace("1-2"), 10: trace("1-2"), 12: trace("3-4"), 14: trace("3-4")},
            "g8": {d: trace("5-6") for d in report.DEPTHS},
            "scan": {d: trace("3-4") for d in report.DEPTHS},
        }
        self.assertEqual(
            report.classify(sentinel, training)[0],
            "TRAINING_CREDIT_OR_DISTRIBUTION_CANDIDATE",
        )

    def test_recommendation_never_authorizes_d1(self):
        self.assertEqual(
            report.recommend(report.Counter({"SEARCH_HORIZON_CANDIDATE": 12}), 20),
            "PRIORITIZE_SEARCH_MECHANISM_PILOT",
        )
        self.assertEqual(
            report.recommend(report.Counter({"REPRESENTATION_OR_OBJECTIVE_CANDIDATE": 10}), 20),
            "PRIORITIZE_CONVERSION_FEATURE_PILOT",
        )

    def test_runner_and_wrappers_are_shell_valid(self):
        for path in (RUNNER, *WRAPPERS):
            subprocess.run(["bash", "-n", str(path)], check=True)
        runner = RUNNER.read_text()
        for token in (
            "D0_DIAGNOSTIC_GO",
            'DEPTHS="${DEPTHS:-8,10,12,14}"',
            'SENTINELS="${SENTINELS:-30}"',
            "imbalance2_symmetric_exclusion.py",
            "imbalance2_d0_select.py",
            "imbalance2_d0_replay.py",
            "imbalance2_d0_report.py",
            "replayed_selfplay_games':0",
            "'training_records':0",
            "'d1_authorized':False",
            "'training_authorized':False",
            "'promotion_authorized':False",
            "'automatic_next_job':None",
        ):
            self.assertIn(token, runner)
        self.assertNotIn("l3-imbalance2-runner-v2.sh", runner)
        self.assertNotIn("P3", runner)

    def test_box_wrappers_have_identical_scientific_contracts(self):
        texts = [path.read_text() for path in WRAPPERS]
        exports = []
        for text in texts:
            exports.append([
                line for line in text.splitlines()
                if line.startswith("export ")
            ])
            for token in (
                "0852-l3-imbalance2-role-v2-p1",
                "0859-l3-imbalance2-role-v2-p2",
                "0853-l3-imbalance2-p1-v1-v2-a64-compare",
                "0864-l3-imbalance2-role-v2-p2-plateau",
                "0862-l3-imbalance2-a64-b64-difficulty-reference",
                'DEPTHS="8,10,12,14" NSHARDS=8 PAR=8',
                "SENTINELS=30 PER_FAMILY=10",
                "SCAN_BB_SIZE=0",
                "l3-imbalance2-d0-diagnostic-v1.sh",
            ):
                self.assertIn(token, text)
            self.assertRegex(text, re.compile(r"do not queue without explicit go"))
        self.assertEqual(exports[0], exports[1])


if __name__ == "__main__":
    unittest.main()
