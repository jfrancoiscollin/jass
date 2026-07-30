from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from jobs.tools import l3_hard_replay_readout as readout


UNIFORM_SHA = "1" * 64
HARD_SHA = "2" * 64
SOURCE_SHA = "3" * 40


def coverage(visited: int) -> dict:
    return {
        "stage": "l3_bucket_visits",
        "geometry": {"trained_buckets_total": 2_125_768},
        "corpus": {"total_records": 2_000_000},
        "coverage": {
            "visited_buckets": visited,
            "coverage_fraction": visited / 2_125_768,
            "buckets_with_at_least": {
                "ge_10": visited // 2,
                "ge_100": visited // 4,
            },
        },
        "concentration": {"gini": 0.9},
    }


def conversion(outcomes: list[str]) -> dict:
    return {
        "complete": True,
        "n_pos": len(outcomes),
        "n_win": outcomes.count("win"),
        "n_draw": outcomes.count("draw"),
        "n_loss": outcomes.count("loss"),
        "n_skipped_draw_label": 0,
        "n_errors": 0,
        "error_rate": 0.0,
        "conversion": outcomes.count("win") / len(outcomes),
        "position_results": [
            {"index": index, "result": outcome}
            for index, outcome in enumerate(outcomes)
        ],
    }


def training() -> dict:
    return {
        "verdict": "L3_PURE_HARD_REPLAY_CAUSAL_AB_ARMS_READY",
        "code_sha": SOURCE_SHA,
        "primary_contrast": "HARD_REPLAY minus UNIFORM_REPLAY",
        "design": {
            "single_factor": "historical_replay_selection_policy",
            "same_parent": True,
            "same_fresh_corpus": True,
            "same_fit": True,
            "same_holdout": True,
        },
        "external_teacher_inputs": 0,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "assembly": {"records": {"per_arm": 2_000_000}},
        "arms": {
            "UNIFORM_REPLAY": {
                "model_sha256": UNIFORM_SHA,
                "optimizer": {"success": True},
                "coverage": coverage(100_000),
            },
            "HARD_REPLAY": {
                "model_sha256": HARD_SHA,
                "optimizer": {"success": True},
                "coverage": coverage(110_000),
            },
        },
    }


class HardReplayReadoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.force = self.root / "force"
        self.conv = self.root / "conversion"
        self.force.mkdir()
        self.conv.mkdir()
        (self.root / "training.json").write_text(json.dumps(training()))
        (self.root / "openings.json").write_text(
            json.dumps(
                {
                    "records": 100,
                    "unique_records": 100,
                    "overlap_records": 0,
                    "sha256": "4" * 64,
                }
            )
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_force(self, view: str, wins: int, draws: int, losses: int) -> None:
        (self.force / f"force-{view}-HARD_REPLAY-vs-UNIFORM_REPLAY.json").write_text(
            json.dumps(
                {
                    "n": wins + draws + losses,
                    "wins_a": wins,
                    "draws": draws,
                    "wins_b": losses,
                    "rate": (wins + 0.5 * draws) / (wins + draws + losses),
                }
            )
        )

    def write_conversion(self, hard: list[str], uniform: list[str]) -> None:
        for stratum in ("p3_mince", "p4_egal"):
            (self.conv / f"HARD_REPLAY-{stratum}.json").write_text(
                json.dumps(conversion(hard))
            )
            (self.conv / f"UNIFORM_REPLAY-{stratum}.json").write_text(
                json.dumps(conversion(uniform))
            )

    def build(self) -> dict:
        return readout.build_readout(
            force_dir=self.force,
            conversion_dir=self.conv,
            training_summary_path=self.root / "training.json",
            opening_manifest_path=self.root / "openings.json",
            expected_games_per_view=200,
            expected_openings=100,
            code_sha="5" * 40,
            source_job="cpx62-source",
            source_attempt="attempt",
            source_code_sha=SOURCE_SHA,
            expected_uniform_sha=UNIFORM_SHA,
            expected_hard_sha=HARD_SHA,
        )

    def test_paired_conversion_exact_distribution_and_directional_readout(self) -> None:
        self.write_force("q00", 104, 0, 96)
        self.write_force("native", 103, 0, 97)
        uniform = ["win"] * 50 + ["loss"] * 50
        hard = ["win"] * 55 + ["loss"] * 45
        self.write_conversion(hard, uniform)
        result = self.build()
        self.assertEqual(result["verdict"], readout.DIRECTIONAL)
        paired = result["conversion"]["p3_mince"][
            "paired_delta_hard_minus_uniform"
        ]
        self.assertEqual(paired["delta_hard_minus_uniform"], 0.05)
        self.assertEqual(paired["uniform_nonwin_to_hard_win"], 5)
        self.assertEqual(paired["uniform_win_to_hard_nonwin"], 0)
        self.assertEqual(result["force_views_summed"]["n"], 400)
        self.assertFalse(result["promotion_authorized"])
        self.assertIsNone(result["automatic_next_job"])

    def test_clear_force_gain_reaches_ic95_verdict(self) -> None:
        self.write_force("q00", 130, 0, 70)
        self.write_force("native", 128, 0, 72)
        outcomes = ["win"] * 50 + ["loss"] * 50
        self.write_conversion(outcomes, outcomes)
        result = self.build()
        self.assertEqual(result["verdict"], readout.ABOVE_95)
        self.assertGreater(result["force_views_summed"]["ci95"][0], 0.5)

    def test_source_hash_drift_is_rejected(self) -> None:
        document = training()
        document["arms"]["HARD_REPLAY"]["model_sha256"] = "9" * 64
        (self.root / "training.json").write_text(json.dumps(document))
        self.write_force("q00", 100, 0, 100)
        self.write_force("native", 100, 0, 100)
        outcomes = ["win", "loss"] * 50
        self.write_conversion(outcomes, outcomes)
        with self.assertRaisesRegex(ValueError, "hash/convergence"):
            self.build()

    def test_conversion_requires_common_position_indices(self) -> None:
        hard = conversion(["win"])
        uniform = conversion(["loss"])
        hard["position_results"][0]["index"] = 1
        uniform["position_results"][0]["index"] = 2
        with self.assertRaisesRegex(ValueError, "no common"):
            readout.paired_conversion(hard, uniform)


if __name__ == "__main__":
    unittest.main()
