import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools.l3_turnover_l2_confirmation import (
    CANDIDATE_MODEL_SHA,
    CHAMPION_REVIEW,
    CONTROL_MODEL_SHA,
    DIRECTION_REPLICATED,
    EFFECT_CONFIRMED,
    F2M_MODEL_SHA,
    NOT_REPLICATED,
    PREVIOUS_OPENING_SEED,
    PREVIOUS_OPENING_SHA,
    PREVIOUS_RECOMMENDATION,
    PREVIOUS_VERDICT,
    TURNOVER_CORPUS_SHA,
    TURNOVER_META_SHA,
    build_confirmation,
    summarize_counts,
    validate_openings,
)


OPENING_SEED = 2_718_281
OPENING_SHA = "b" * 64
CANDIDATE_SHA = "c" * 64


def row(n: int, rate: float) -> dict:
    """Build an internally consistent force row at the requested score rate."""
    wins = round(rate * n)
    value = summarize_counts(wins, 0, n - wins)
    value["complete"] = True
    return value


def previous_certificate(rate_control: float = 0.5015) -> dict:
    force = {}
    for view in ("q00", "native"):
        force[f"{view}_L2_1E5_vs_TURNOVER"] = row(1000, rate_control)
        force[f"{view}_L2_1E5_vs_F2M"] = row(1000, 0.526)
    return {
        "verdict": PREVIOUS_VERDICT,
        "recommendation": PREVIOUS_RECOMMENDATION,
        "recommended_l2_arm": "L2_1E5",
        "directional_arms": ["L2_1E5"],
        "confirmed_leads": [],
        "eligible_for_guard_cells": ["L2_1E5"],
        "promotion_authorized": False,
        "automatic_next_job": None,
        "guardrails": {"L2_1E5": {"all_pass": True, "checks": {"a": True}}},
        "force": force,
        "primary_checks": {
            "L2_1E5": {
                view: {
                    "positive_point_estimate": True,
                    "superiority_established": False,
                    "regression_not_established": True,
                }
                for view in ("q00", "native")
            }
        },
        "training_summary": {
            "arms": {"L2_1E5": {"model_sha256": CANDIDATE_MODEL_SHA, "l2": 1e-05}},
            "control": {"model_sha256": CONTROL_MODEL_SHA, "l2": 3e-05},
            "parent_model_sha256": F2M_MODEL_SHA,
            "training_corpus_sha256": TURNOVER_CORPUS_SHA,
            "training_meta_sha256": TURNOVER_META_SHA,
            "experiment_variant": "TURNOVER_1_1_L2_SCREEN",
            "training_records": 2_000_000,
            "new_generation_performed": False,
            "external_teacher_inputs": 0,
        },
        "opening_manifest": {
            "records": 500,
            "unique_records": 500,
            "overlap_records": 0,
            "generator_seed": PREVIOUS_OPENING_SEED,
            "sha256": PREVIOUS_OPENING_SHA,
        },
    }


def manifest(sha: str = OPENING_SHA, seed: int = OPENING_SEED) -> dict:
    return {
        "records": 1000,
        "unique_records": 1000,
        "overlap_records": 0,
        "generator_seed": seed,
        "sha256": sha,
        "candidate_sha256": CANDIDATE_SHA,
        "mode": "deterministic-ordered-filter",
    }


def write_force(directory: Path, control_rate: float, champion_rate: float) -> None:
    for view in ("q00", "native"):
        (directory / f"force-{view}-L2_1E5-vs-TURNOVER.json").write_text(
            json.dumps(row(2000, control_rate)), encoding="utf-8"
        )
        (directory / f"force-{view}-L2_1E5-vs-F2M.json").write_text(
            json.dumps(row(2000, champion_rate)), encoding="utf-8"
        )


class ConfirmationTest(unittest.TestCase):
    def build(self, *, control_rate, champion_rate=0.51, previous=None):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_force(directory, control_rate, champion_rate)
            return build_confirmation(
                force_dir=directory,
                previous=previous or previous_certificate(),
                openings=manifest(),
            )

    def test_confirmed_effect_when_both_views_establish_superiority(self):
        report = self.build(control_rate=0.56)
        self.assertEqual(report["verdict"], EFFECT_CONFIRMED)
        self.assertFalse(report["promotion_authorized"])
        self.assertIsNone(report["automatic_next_job"])

    def test_champion_review_when_champion_cells_also_establish_superiority(self):
        report = self.build(control_rate=0.56, champion_rate=0.58)
        self.assertEqual(report["verdict"], CHAMPION_REVIEW)
        self.assertFalse(report["promotion_authorized"])

    def test_direction_replicated_without_established_lead(self):
        report = self.build(control_rate=0.508)
        self.assertEqual(report["verdict"], DIRECTION_REPLICATED)

    def test_not_replicated_closes_the_factor_on_3e5(self):
        report = self.build(control_rate=0.48)
        self.assertEqual(report["verdict"], NOT_REPLICATED)
        self.assertEqual(
            report["recommendation"], "retain_l2_3e5_and_close_l2_factor"
        )

    def test_established_champion_regression_blocks_confirmation(self):
        report = self.build(control_rate=0.56, champion_rate=0.40)
        self.assertEqual(report["verdict"], NOT_REPLICATED)
        self.assertFalse(report["all_guardrails_pass"])

    def test_pooled_cells_total_three_thousand_games(self):
        report = self.build(control_rate=0.56)
        for key, value in report["pooled_force"].items():
            self.assertEqual(value["n"], 3000, key)
            self.assertEqual(value["source_games"], [1000, 2000], key)

    def test_incomplete_fresh_cell_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_force(directory, 0.56, 0.51)
            path = directory / "force-q00-L2_1E5-vs-TURNOVER.json"
            value = json.loads(path.read_text())
            value["complete"] = False
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_confirmation(
                    force_dir=directory,
                    previous=previous_certificate(),
                    openings=manifest(),
                )

    def test_truncated_fresh_cell_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            write_force(directory, 0.56, 0.51)
            path = directory / "force-native-L2_1E5-vs-F2M.json"
            path.write_text(json.dumps(row(1500, 0.51)), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_confirmation(
                    force_dir=directory,
                    previous=previous_certificate(),
                    openings=manifest(),
                )

    def test_wrong_previous_verdict_is_rejected(self):
        previous = previous_certificate()
        previous["verdict"] = "TURNOVER_L2_SCREEN_LEAD_REVIEW"
        with self.assertRaises(ValueError):
            self.build(control_rate=0.56, previous=previous)

    def test_previous_certificate_with_failed_guardrails_is_rejected(self):
        previous = previous_certificate()
        previous["guardrails"]["L2_1E5"]["checks"]["a"] = False
        with self.assertRaises(ValueError):
            self.build(control_rate=0.56, previous=previous)

    def test_previous_candidate_model_drift_is_rejected(self):
        previous = previous_certificate()
        previous["training_summary"]["arms"]["L2_1E5"]["model_sha256"] = "d" * 64
        with self.assertRaises(ValueError):
            self.build(control_rate=0.56, previous=previous)

    def test_confirmation_pool_must_differ_from_the_screen_pool(self):
        with self.assertRaises(ValueError):
            validate_openings(
                manifest(sha=PREVIOUS_OPENING_SHA, seed=PREVIOUS_OPENING_SEED),
                expected_seed=PREVIOUS_OPENING_SEED,
                expected_sha256=PREVIOUS_OPENING_SHA,
                expected_candidate_sha256=CANDIDATE_SHA,
            )

    def test_opening_pool_hash_drift_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_openings(
                manifest(),
                expected_seed=OPENING_SEED,
                expected_sha256="e" * 64,
                expected_candidate_sha256=CANDIDATE_SHA,
            )

    def test_overlapping_pool_is_rejected(self):
        value = manifest()
        value["overlap_records"] = 3
        with self.assertRaises(ValueError):
            validate_openings(
                value,
                expected_seed=OPENING_SEED,
                expected_sha256=OPENING_SHA,
                expected_candidate_sha256=CANDIDATE_SHA,
            )


if __name__ == "__main__":
    unittest.main()
