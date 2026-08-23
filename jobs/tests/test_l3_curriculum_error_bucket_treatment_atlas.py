import unittest
from unittest import mock

from jobs.tools import l3_curriculum_error_bucket_treatment_atlas as atlas


def _row(pair_id, pool, sign=1.0):
    error = [0.0] * 20
    control = [0.0] * 20
    error[0] = 1.0 * sign
    control[0] = 0.2 * sign
    return {
        "pair_id": pair_id,
        "source_pool": pool,
        "paired_gain_cp": 35.0 * sign,
        "error": {
            "intervention": True,
            "gain_cp": 40.0 * sign,
            "full_vector": error,
            "phase": "middle",
            "opening_id": f"{pool}-opening-{pair_id}-e",
            "game_uid": f"{pool}-game-{pair_id}-e",
        },
        "control": {
            "intervention": True,
            "gain_cp": 5.0 * sign,
            "full_vector": control,
            "phase": "middle",
            "opening_id": f"{pool}-opening-{pair_id}-c",
            "game_uid": f"{pool}-game-{pair_id}-c",
        },
    }


class BucketTreatmentAtlasTests(unittest.TestCase):
    def test_candidate_family_is_finite_and_preregisterable(self):
        configurations = atlas._configurations([0, 8, 9, 12, 16, 17], ["early", "middle", "endgame"])
        self.assertEqual(len(configurations), 120)
        self.assertEqual(len({row["name"] for row in configurations}), 120)
        full_phase = next(row for row in configurations if row["name"] == "full20_phase__ridge_10")
        self.assertEqual(full_phase["dimension"], 60)

    def test_phase_representation_is_block_sparse(self):
        config = next(
            row for row in atlas._configurations([0], ["early", "middle", "endgame"])
            if row["name"] == "stable6_phase__ridge_1"
        )
        state = _row(1, "pool1")["error"]
        vector = atlas._vector(state, config)
        self.assertEqual(vector.shape, (3,))
        self.assertEqual(vector.tolist(), [0.0, 1.0, 0.0])

    def test_evaluation_fits_each_pool_and_tests_the_opposite_pool(self):
        rows = []
        for pool_index, pool in enumerate(("pool1", "pool2")):
            for index in range(12):
                rows.append(_row(pool_index * 100 + index, pool))
        config = next(
            row for row in atlas._configurations([0, 8, 9, 12, 16, 17], ["middle"])
            if row["name"] == "singleton_centered_score_d6__ridge_1"
        )
        evaluation = atlas._evaluate(rows, config)
        self.assertGreater(evaluation["coefficients"]["pool1"][0], 0.0)
        self.assertGreater(evaluation["coefficients"]["pool2"][0], 0.0)
        self.assertGreater(evaluation["by_pool"]["pool1"]["paired_mean_cp"], 0.0)
        self.assertGreater(evaluation["by_pool"]["pool2"]["paired_mean_cp"], 0.0)
        self.assertEqual(evaluation["combined"]["error_interventions"], 24)
        self.assertEqual(evaluation["combined"]["control_interventions"], 24)

    def test_familywise_shams_are_batched_and_finite(self):
        rows = []
        for pool_index, pool in enumerate(("pool1", "pool2")):
            for index in range(20):
                rows.append(_row(pool_index * 100 + index, pool, 1.0 if index % 2 == 0 else -1.0))
        config = next(
            row for row in atlas._configurations([0, 8, 9, 12, 16, 17], ["middle"])
            if row["name"] == "singleton_centered_score_d6__ridge_10"
        )
        evaluation = atlas._evaluate(rows, config)
        with mock.patch.object(atlas, "SHAM_REPLICATES", 16):
            maxima = atlas._sham_maxima([evaluation])
        self.assertEqual(len(maxima), 16)
        self.assertTrue(all(value == value and abs(value) < 1e9 for value in maxima))

    def test_zero_support_bucket_is_reported_ineligible_without_aborting_family(self):
        rows = []
        for pool_index, pool in enumerate(("pool1", "pool2")):
            for index in range(12):
                rows.append(_row(pool_index * 100 + index, pool))
        config = next(
            row for row in atlas._configurations([0, 8, 9, 12, 16, 17], ["middle"])
            if row["name"] == "singleton_centered_score_d7__ridge_10"
        )
        evaluation = atlas._evaluate(rows, config)
        self.assertEqual(evaluation["fits"]["pool1"]["active_pairs"], 0)
        self.assertEqual(evaluation["fits"]["pool2"]["rank"], 0)
        self.assertFalse(evaluation["eligible"])
        with mock.patch.object(atlas, "SHAM_REPLICATES", 8):
            self.assertEqual(atlas._sham_maxima([evaluation]), [0.0] * 8)

    def test_negative_target_source_is_mandatory(self):
        report = {
            "schema": atlas.TARGET_SOURCE_SCHEMA,
            "verdict": atlas.target.READY,
            "passed": True,
            "cross_pool_uplift_screen": {
                "passed": False,
                "status": "target_specificity_not_established",
            },
            "new_fresh_pool_preregistration_recommended": False,
            "production_model_authorized": False,
        }
        atlas._require_negative_target_report(report)
        report["cross_pool_uplift_screen"]["passed"] = True
        with self.assertRaises(ValueError):
            atlas._require_negative_target_report(report)


if __name__ == "__main__":
    unittest.main()
