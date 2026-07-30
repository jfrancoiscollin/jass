from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jobs.tools import l3_reverse_seed_readout as readout


CONTROL_SHA = "1" * 64
TREATMENT_SHA = "2" * 64
SOURCE_SHA = "3" * 40


def coverage(visited: int) -> dict:
    return {
        "visited_buckets": visited,
        "visited_pct": visited / 10_000,
        "gini": 0.9,
        "buckets_ge_10": visited // 2,
        "buckets_ge_100": visited // 4,
    }


def training() -> dict:
    return {
        "verdict": "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY",
        "code_sha": SOURCE_SHA,
        "primary_contrast": (
            "HARD_SEED_SELFPLAY minus MATCHED_RANDOM_SEED_SELFPLAY"
        ),
        "design": {
            "single_factor": "seed_root_selection_policy",
            "records_per_arm": 2_000_000,
            "seed_frac": 100,
            "historical_replay_records": 0,
            "same_parent": True,
            "same_search_policy": True,
            "same_shard_seeds": True,
            "same_split_contract": True,
            "same_fit": True,
        },
        "external_teacher_inputs": 0,
        "scientific_result": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "arms": {
            "control": {
                "model_sha256": CONTROL_SHA,
                "fit": {"converged": True},
                "coverage": coverage(100_000),
            },
            "treatment": {
                "model_sha256": TREATMENT_SHA,
                "fit": {"converged": True},
                "coverage": coverage(110_000),
            },
        },
    }


class ReverseSeedReadoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.force = self.root / "force"
        self.force.mkdir()
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
        (self.force / f"force-{view}-TREATMENT-vs-CONTROL.json").write_text(
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

    def build(self) -> dict:
        return readout.build_readout(
            force_dir=self.force,
            training_summary_path=self.root / "training.json",
            opening_manifest_path=self.root / "openings.json",
            expected_games_per_view=200,
            expected_openings=100,
            code_sha="5" * 40,
            source_job="cpx62-source",
            source_attempt="attempt",
            source_code_sha=SOURCE_SHA,
            expected_control_sha=CONTROL_SHA,
            expected_treatment_sha=TREATMENT_SHA,
        )

    def test_directional_gain_and_coverage_are_reported(self) -> None:
        self.write_force("q00", 104, 0, 96)
        self.write_force("native", 103, 0, 97)
        result = self.build()
        self.assertEqual(result["verdict"], readout.DIRECTIONAL)
        self.assertEqual(result["force_views_summed"]["n"], 400)
        self.assertGreater(result["force_views_summed"]["rate_treatment"], 0.5)
        self.assertEqual(
            result["training_coverage"]["treatment_minus_control"][
                "visited_buckets"
            ],
            10_000,
        )
        self.assertTrue(result["scientific_result"])
        self.assertFalse(result["promotion_authorized"])
        self.assertIsNone(result["automatic_next_job"])

    def test_clear_gain_reaches_ic95_verdict(self) -> None:
        self.write_force("q00", 130, 0, 70)
        self.write_force("native", 128, 0, 72)
        result = self.build()
        self.assertEqual(result["verdict"], readout.ABOVE_95)
        self.assertGreater(result["force_views_summed"]["ci95"][0], 0.5)

    def test_clear_loss_is_below(self) -> None:
        self.write_force("q00", 70, 0, 130)
        self.write_force("native", 75, 0, 125)
        result = self.build()
        self.assertEqual(result["verdict"], readout.BELOW)

    def test_source_hash_drift_is_rejected(self) -> None:
        document = training()
        document["arms"]["treatment"]["model_sha256"] = "9" * 64
        (self.root / "training.json").write_text(json.dumps(document))
        self.write_force("q00", 100, 0, 100)
        self.write_force("native", 100, 0, 100)
        with self.assertRaisesRegex(ValueError, "hash/convergence"):
            self.build()

    def test_short_force_cell_is_rejected(self) -> None:
        self.write_force("q00", 99, 0, 100)
        self.write_force("native", 100, 0, 100)
        with self.assertRaisesRegex(ValueError, "expected exactly"):
            self.build()


if __name__ == "__main__":
    unittest.main()
