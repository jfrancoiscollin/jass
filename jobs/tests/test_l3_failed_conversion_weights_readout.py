from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jobs.tools import l3_failed_conversion_weights_readout as readout


CONTROL_SHA = "1" * 64
TREATMENT_SHA = "2" * 64
SOURCE_SHA = "3" * 40


def coverage(visited: int = 100_000) -> dict:
    return {
        "visited_buckets": visited,
        "visited_pct": visited / 42_515.28,
        "gini": 0.9,
        "buckets_ge_10": visited // 2,
        "buckets_ge_100": visited // 4,
    }


def canonical_coverage(visited: int = 100_000) -> dict:
    total = 2_125_768
    return {
        "schema": 1,
        "stage": "l3_bucket_visits",
        "geometry": {"trained_buckets_total": total},
        "corpus": {"total_records": 2_000_000},
        "coverage": {
            "visited_buckets": visited,
            "coverage_fraction": round(visited / total, 6),
            "buckets_with_at_least": {
                "ge_1": visited,
                "ge_10": visited // 2,
                "ge_100": visited // 4,
            },
        },
        "concentration": {"gini": 0.9},
    }


def trainer_weights(*, uniform: bool, sw_used: bool, ess: float) -> dict:
    return {
        "split": {"holdout_weighted": False},
        "optimizer": {
            "uniform_after_normalization": uniform,
            "sw_all_used": sw_used,
        },
        "effective_sample_size": {"ess_fraction": ess},
    }


def training() -> dict:
    return {
        "verdict": "L3_PURE_FAILED_CONVERSION_WEIGHTS_CAUSAL_AB_ARMS_READY",
        "code_sha": SOURCE_SHA,
        "primary_contrast": "FAILED_X2 minus UNWEIGHTED",
        "design": {
            "single_factor": "train_failed_conversion_weight",
            "control_weight": 1.0,
            "treatment_weight": 2.0,
            "same_records": True,
            "same_opening_split": True,
            "same_feature_matrix": True,
            "same_warm_start": True,
            "same_fit": True,
            "holdout_weighted": False,
            "oversampling": False,
            "control_reproduced_historical_model": True,
        },
        "external_teacher_inputs": 0,
        "scientific_result": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "training_coverage": {
            "common_to_both_arms": True,
            "common": coverage(),
            "control_minus_treatment": {
                "visited_buckets": 0,
                "visited_pct": 0.0,
                "gini": 0.0,
                "buckets_ge_10": 0,
                "buckets_ge_100": 0,
            },
        },
        "arms": {
            "UNWEIGHTED": {
                "model_sha256": CONTROL_SHA,
                "optimizer": {"success": True},
                "trainer_weights": trainer_weights(
                    uniform=True, sw_used=False, ess=1.0
                ),
            },
            "FAILED_X2": {
                "model_sha256": TREATMENT_SHA,
                "optimizer": {"success": True},
                "trainer_weights": trainer_weights(
                    uniform=False, sw_used=True, ess=0.91
                ),
            },
        },
    }


class FailedConversionWeightsReadoutTests(unittest.TestCase):
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
        path = self.force / f"force-{view}-FAILED_X2-vs-UNWEIGHTED.json"
        path.write_text(
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

    def test_directional_gain_and_common_coverage_are_reported(self) -> None:
        self.write_force("q00", 104, 0, 96)
        self.write_force("native", 103, 0, 97)
        result = self.build()
        self.assertEqual(result["verdict"], readout.DIRECTIONAL)
        self.assertEqual(result["force_views_summed"]["n"], 400)
        self.assertGreater(result["force_views_summed"]["rate_treatment"], 0.5)
        self.assertTrue(result["training_coverage"]["common_to_both_arms"])
        self.assertEqual(
            result["training_coverage"]["treatment_minus_control"][
                "visited_buckets"
            ],
            0,
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
        self.assertEqual(self.build()["verdict"], readout.BELOW)

    def test_control_reproduction_drift_is_rejected(self) -> None:
        document = training()
        document["design"]["control_reproduced_historical_model"] = False
        (self.root / "training.json").write_text(json.dumps(document))
        self.write_force("q00", 100, 0, 100)
        self.write_force("native", 100, 0, 100)
        with self.assertRaisesRegex(ValueError, "training certificate"):
            self.build()

    def test_low_treatment_ess_is_rejected(self) -> None:
        document = training()
        document["arms"]["FAILED_X2"]["trainer_weights"][
            "effective_sample_size"
        ]["ess_fraction"] = 0.79
        (self.root / "training.json").write_text(json.dumps(document))
        self.write_force("q00", 100, 0, 100)
        self.write_force("native", 100, 0, 100)
        with self.assertRaisesRegex(ValueError, "effective sample size"):
            self.build()

    def test_canonical_bucket_visit_coverage_is_normalized(self) -> None:
        document = training()
        document["training_coverage"]["common"] = canonical_coverage()
        (self.root / "training.json").write_text(json.dumps(document))
        self.write_force("q00", 104, 0, 96)
        self.write_force("native", 103, 0, 97)
        result = self.build()
        normalized = result["training_coverage"]["common"]
        self.assertEqual(normalized["visited_buckets"], 100_000)
        self.assertAlmostEqual(
            normalized["visited_pct"],
            100.0 * round(100_000 / 2_125_768, 6),
        )
        self.assertEqual(normalized["buckets_ge_10"], 50_000)
        self.assertEqual(normalized["buckets_ge_100"], 25_000)

    def test_malformed_canonical_coverage_is_rejected(self) -> None:
        document = training()
        raw = canonical_coverage()
        raw["coverage"]["buckets_with_at_least"]["ge_100"] = 60_000
        document["training_coverage"]["common"] = raw
        (self.root / "training.json").write_text(json.dumps(document))
        self.write_force("q00", 100, 0, 100)
        self.write_force("native", 100, 0, 100)
        with self.assertRaisesRegex(ValueError, "coverage certificate"):
            self.build()


if __name__ == "__main__":
    unittest.main()
