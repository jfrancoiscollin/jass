import unittest
from unittest import mock

import numpy as np

from jobs.tools import l3_curriculum_error_target_specificity_autopsy as target


class TargetSpecificityAutopsyTests(unittest.TestCase):
    def test_fit_uplift_recovers_positive_direction(self):
        rows = []
        for index in range(20):
            vector = np.asarray([1.0 + index / 20.0, 0.5, 0.0])
            rows.append({
                "pair_vector": vector.tolist(),
                "paired_gain_cp": float(4.0 * vector[0] + vector[1]),
            })
        fit = target._fit_uplift(rows)
        self.assertGreater(float(fit["coefficient"][0]), 0.0)
        self.assertGreaterEqual(fit["rank"], 1)
        self.assertEqual(fit["active_pairs"], 20)

    def test_apply_gate_uses_opposite_pool_model(self):
        rows = [{
            "pair_id": 1,
            "source_pool": "pool1",
            "error": {"vector": [2.0], "intervention": True, "gain_cp": 30.0},
            "control": {"vector": [-1.0], "intervention": True, "gain_cp": 20.0},
        }]
        adjusted, scores = target._apply_gate(
            rows, {"pool1": np.asarray([1.0]), "pool2": np.asarray([-1.0])}
        )
        self.assertTrue(adjusted[0]["error"]["retained"])
        self.assertFalse(adjusted[0]["control"]["retained"])
        self.assertEqual(adjusted[0]["error"]["adjusted_gain_cp"], 30.0)
        self.assertEqual(adjusted[0]["control"]["adjusted_gain_cp"], 0.0)
        self.assertEqual(scores, [2.0, -1.0])

    def test_split_identity_detects_no_overlap(self):
        def pair(pair_id, pool, prefix):
            role = lambda suffix: {
                "profile": {"source": {
                    "opening_id": f"{prefix}-opening-{suffix}",
                    "game_uid": f"{prefix}-game-{suffix}",
                }}
            }
            return {
                "pair_id": pair_id,
                "source_pool": pool,
                "error": role("e"),
                "control": role("c"),
            }
        training = [pair(0, "train", "training")]
        fresh = [pair(1, "pool1", "one"), pair(2, "pool2", "two")]
        report = target._split_identity(training, fresh)
        self.assertEqual(report["pool_opening_overlap"], 0)
        self.assertEqual(report["pool_game_overlap"], 0)
        self.assertEqual(report["training_fresh_opening_overlap"], 0)
        self.assertEqual(report["training_fresh_game_overlap"], 0)

    def test_cross_pool_screen_is_oof_and_never_authorizes_production(self):
        rows = []
        for pool_index, pool in enumerate(("pool1", "pool2")):
            for index in range(24):
                sign = 1.0 if index % 2 == 0 else -1.0
                error_vector = [sign, 0.2 + pool_index * 0.01]
                control_vector = [-sign, -0.2 - pool_index * 0.01]
                error_gain = 80.0 if sign > 0 else -20.0
                control_gain = -5.0 if sign < 0 else 10.0
                rows.append({
                    "pair_id": pool_index * 100 + index,
                    "source_pool": pool,
                    "pair_vector": (np.asarray(error_vector) - np.asarray(control_vector)).tolist(),
                    "paired_gain_cp": error_gain - control_gain,
                    "error": {"vector": error_vector, "intervention": True, "gain_cp": error_gain},
                    "control": {"vector": control_vector, "intervention": True, "gain_cp": control_gain},
                })
        with mock.patch.object(target, "BOOTSTRAP_SAMPLES", 2000), mock.patch.object(target, "SHAM_REPLICATES", 20):
            report = target._cross_pool_screen(rows, ["a", "b"])
        self.assertEqual(report["training_direction"]["pool1"], "tests_model_fit_on_pool2")
        self.assertFalse(report["production_authorized"])
        self.assertTrue(report["fresh_1524_reuse_for_confirmation_forbidden"])
        self.assertEqual(report["sham"]["replicates"], 20)


if __name__ == "__main__":
    unittest.main()
