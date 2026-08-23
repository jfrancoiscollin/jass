import unittest
from unittest import mock

import numpy as np

from jobs.tools import l3_curriculum_error_action_margin_contrastive_screen as screen


def _state(*, error: bool, scale: float = 10.0):
    action_a = np.zeros(20, dtype=float)
    action_b = np.zeros(20, dtype=float)
    action_a[0] = scale
    if error:
        scores = {"A": -5.0, "B": 0.0}
        values = {"A": 100.0, "B": 0.0}
    else:
        scores = {"A": -30.0, "B": 0.0}
        values = {"A": -50.0, "B": 0.0}
    return {
        "features": {"A": action_a, "B": action_b},
        "original_scores": dict(scores),
        "image_scores": dict(scores),
        "values": values,
        "profile": {"source": {"opening_id": "o", "game_uid": "g"}},
    }


def _row(pair_id: int, pool: str):
    return {
        "pair_id": pair_id,
        "source_pool": pool,
        "error": _state(error=True),
        "control": _state(error=False),
    }


class ActionMarginContrastiveScreenTests(unittest.TestCase):
    def test_candidate_family_is_fixed_at_36(self):
        configurations = screen._configurations([0, 8, 9, 12, 16, 17])
        self.assertEqual(len(configurations), 36)
        self.assertEqual(len({row["name"] for row in configurations}), 36)
        self.assertEqual(
            {row["support_name"] for row in configurations}, {"stable6", "full20"}
        )
        self.assertTrue(all(row["cap_cp"] == 25.0 for row in configurations))

    def test_control_anchor_penalty_shrinks_the_action_correction(self):
        rows = [_row(index, "pool1") for index in range(24)]
        configs = screen._configurations([0])
        low = next(
            row for row in configs
            if row["support_name"] == "stable6"
            and row["alpha"] == 30.0
            and row["control_anchor_penalty"] == 1.0
            and row["threshold_cp"] == 5.0
        )
        high = dict(low)
        high["control_anchor_penalty"] = 100.0
        low_model = screen._fit(rows, low)
        high_model = screen._fit(rows, high)
        self.assertGreater(
            abs(float(low_model["coefficient"][0])),
            abs(float(high_model["coefficient"][0])),
        )
        self.assertGreater(low_model["error_rank"], 0)
        self.assertGreater(low_model["control_rank"], 0)

    def test_cross_pool_evaluation_is_error_specific_and_symmetric(self):
        rows = [
            _row(pool_index * 100 + index, pool)
            for pool_index, pool in enumerate(("pool1", "pool2"))
            for index in range(24)
        ]
        config = next(
            row for row in screen._configurations([0])
            if row["support_name"] == "stable6"
            and row["alpha"] == 30.0
            and row["control_anchor_penalty"] == 1.0
            and row["threshold_cp"] == 5.0
        )
        evaluation = screen._evaluate(rows, config)
        self.assertGreater(evaluation["by_pool"]["pool1"]["error_mean_cp"], 0.0)
        self.assertGreater(evaluation["by_pool"]["pool2"]["paired_mean_cp"], 0.0)
        self.assertEqual(evaluation["combined"]["control_interventions"], 0)
        self.assertTrue(evaluation["combined"]["abstentions_bit_identical"])
        self.assertTrue(evaluation["combined"]["aligned_intervention_symmetry"])

    def test_familywise_shams_are_batched_and_finite(self):
        rows = [
            _row(pool_index * 100 + index, pool)
            for pool_index, pool in enumerate(("pool1", "pool2"))
            for index in range(16)
        ]
        config = next(
            row for row in screen._configurations([0])
            if row["support_name"] == "stable6"
            and row["alpha"] == 30.0
            and row["control_anchor_penalty"] == 1.0
            and row["threshold_cp"] == 5.0
        )
        evaluation = screen._evaluate(rows, config)
        with mock.patch.object(screen, "SHAM_REPLICATES", 16):
            maxima = screen._sham_maxima([evaluation])
        self.assertEqual(len(maxima), 16)
        self.assertTrue(all(value == value and abs(value) < 1e9 for value in maxima))

    def test_negative_bucket_atlas_is_mandatory(self):
        target_report = {"target": "negative"}
        report = {
            "schema": screen.BUCKET_SOURCE_SCHEMA,
            "verdict": screen.bucket.READY,
            "passed": True,
            "scientific_source": {
                "target_specificity_report_sha256": screen._digest(target_report),
            },
            "bucket_treatment_screen": {
                "passed": False,
                "status": "bucket_treatment_rule_not_established",
            },
            "bucket_treatment_rule_candidate_established": False,
            "new_fresh_pool_preregistration_recommended": False,
            "anchored_local_refit_authorized": False,
            "production_model_authorized": False,
            "strength_gate_authorized": False,
            "promotion_authorized": False,
            "automatic_continuation": False,
        }
        screen._require_negative_atlas(report, target_report)
        report["bucket_treatment_screen"]["passed"] = True
        with self.assertRaises(ValueError):
            screen._require_negative_atlas(report, target_report)


if __name__ == "__main__":
    unittest.main()
