import unittest
from unittest import mock

import numpy as np

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_fresh_tail_autopsy as autopsy
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge


class FreshTailAutopsyTests(unittest.TestCase):
    def test_distribution_and_loss_concentration_expose_catastrophic_tail(self):
        values = [-1200.0, -600.0, 100.0, 200.0]
        distribution = autopsy._distribution(values)
        self.assertEqual(distribution["n"], 4)
        self.assertEqual(distribution["threshold_counts"]["-500"], 2)
        concentration = autopsy._loss_concentration(
            [{"improvement_cp": value} for value in values]
        )
        self.assertAlmostEqual(concentration["top_1_share"], 2.0 / 3.0)
        self.assertEqual(concentration["events_for_80pct_loss"], 2)

    def test_detail_recomposes_raw_feature_contributions(self):
        width = len(ranker.FEATURE_NAMES)
        model = {
            "mean": np.zeros(width), "rms": np.ones(width),
            "coef": np.asarray([10.0] + [0.0] * (width - 1)),
        }
        state = {
            "profile": {"source": {}},
            "features": {
                "31-26": np.zeros(width),
                "32x27": np.asarray([2.0] + [0.0] * (width - 1)),
            },
            "original_scores": {"31-26": 0.0, "32x27": -5.0},
            "image_scores": {"31-26": 0.0, "32x27": -5.0},
            "values": {"31-26": 0.0, "32x27": 500.0},
        }
        with mock.patch.object(
            autopsy.variability, "_profile_values",
            return_value={autopsy.prereg.SELECTED_PROXY: 100.0},
        ):
            decision = ridge._decision(
                state, model, cap_cp=100.0, threshold_cp=10.0,
                mode="strict_both_change",
            )
        self.assertTrue(decision["intervention"])
        metadata = {
            "phase": "mid", "piece_count": 20, "king_count": 0,
            "stm_material_balance": 0, "ply": 20, "legal_moves": 8,
            "capture_historical": False, "outcome": "loss", "opening_id": "o",
            "game_uid": "g", "exact_state_key": "s",
        }
        with (
            mock.patch.object(autopsy.variability, "_profile_values", return_value={autopsy.prereg.SELECTED_PROXY: 100.0}),
            mock.patch.object(autopsy, "_piece_metadata", return_value=metadata),
        ):
            detail = autopsy._detail(
                state, model, decision, role="error", pair_id=7, source_pool="pool1"
            )
        self.assertEqual(detail["dominant_feature"], ranker.FEATURE_NAMES[0])
        self.assertAlmostEqual(sum(detail["feature_contributions_cp"].values()), 20.0)
        self.assertAlmostEqual(detail["raw_correction_delta_cp"], 20.0)
        self.assertAlmostEqual(detail["guard_margin_cp"], 5.0)

    def test_pool_stable_risk_factor_is_discovery_only(self):
        rows = []
        for pool in ("pool1", "pool2"):
            for index in range(10):
                inside = index < 6
                rows.append({
                    "source_pool": pool,
                    "improvement_cp": -500.0 if inside else 0.0,
                    "predicted_advantage_cp": 15.0 if inside else 30.0,
                    "guard_margin_cp": 8.0,
                    "correction_clipped": False,
                    "anchor_disagreement": False,
                    "proposed_capture": False,
                    "proxy_cp": 80.0,
                })
        candidates = autopsy._risk_candidates(rows)
        selected = next(row for row in candidates if row["name"] == "predicted_advantage_lt_20cp")
        self.assertTrue(selected["descriptively_pool_stable"])
        self.assertTrue(selected["fresh_1517_reuse_for_validation_forbidden"])

    def test_source_authentication_rejects_positive_or_unaudited_source(self):
        summary = {
            "schema": autopsy.SOURCE_TERMINAL_SCHEMA,
            "verdict": autopsy.fresh.READY,
            "passed": True,
        }
        with self.assertRaisesRegex(ValueError, "negative 1517"):
            autopsy._require_source(summary, {}, {})


if __name__ == "__main__":
    unittest.main()
