#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import unittest
from unittest import mock

import numpy as np

from jobs.tests import test_l3_curriculum_error_trace_residual_training as fixtures
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as target
from jobs.tools import l3_curriculum_error_trace_residual_training as training
from jobs.tools import l3_curriculum_search_error_atlas as atlas


def _failed_source(pairs: dict) -> tuple[dict, dict, dict]:
    registration = fixtures._preregistration(pairs)
    report = {
        "schema": training.SCHEMA,
        "verdict": training.NOT_ESTABLISHED,
        "passed": False,
        "selected_threshold": None,
        "sham": None,
        "champion_sha256": "champion",
        "jass_sha256": "jass",
        "search_params_sha256": "search",
        "feature_audit_action_value_reads": 0,
        "outer_confirm_action_value_reads": 0,
        "pattern_eval_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }
    model = {
        "schema": training.MODEL_SCHEMA,
        "authorized_for_feature_audit": False,
        "authorized_for_production": False,
        "promotion_authorized": False,
        "aligned_model": None,
        "shuffled_model": None,
        "champion_sha256": "champion",
        "jass_sha256": "jass",
        "search_params_sha256": "search",
    }
    return registration, report, model


def _shards(pairs: dict) -> list[dict]:
    digest = hashlib.sha256(target._canonical(pairs)).hexdigest()
    rows = []
    for pair in pairs["pairs"]:
        rows.append(
            {
                "pair_id": pair["pair_id"],
                "split": pair["split"],
                "error": {
                    "action_values": {
                        fixtures.QUIET: {"root_cp": 0.0},
                        fixtures.CAPTURE: {"root_cp": 100.0},
                    }
                },
                "control": {
                    "action_values": {
                        fixtures.QUIET: {"root_cp": 0.0},
                        fixtures.CAPTURE: {"root_cp": 0.0},
                    }
                },
            }
        )
    return [
        {
            "schema": atlas.SCHEMA_ATLAS_SHARD,
            "pairs_sha256": digest,
            "champion_sha256": "champion",
            "jass_sha256": "jass",
            "search_params_sha256": "search",
            "shard": shard,
            "nshards": 16,
            "max_pairs": 0,
            "rows": [row for row in rows if int(row["pair_id"]) % 16 == shard],
        }
        for shard in range(16)
    ]


class ResidualRidgePathScreenTests(unittest.TestCase):
    def test_at_least_one_change_accepts_one_orientation_already_correct(self):
        profile = fixtures._profile(1, max_spread=100.0)
        features, original, image = training._paired_features(profile)
        delta = features[fixtures.CAPTURE] - features[fixtures.QUIET]
        coefficient = 50.0 * delta / float(delta @ delta)
        model = {
            "mean": np.zeros_like(delta),
            "rms": np.ones_like(delta),
            "coef": coefficient,
        }
        image[fixtures.CAPTURE] = 10.0
        image[fixtures.QUIET] = 0.0
        state = {
            "profile": profile,
            "features": features,
            "original_scores": original,
            "image_scores": image,
            "values": {fixtures.QUIET: 0.0, fixtures.CAPTURE: 100.0},
        }

        strict = target._decision(
            state,
            model,
            cap_cp=75.0,
            threshold_cp=0.0,
            mode="strict_both_change",
        )
        relaxed = target._decision(
            state,
            model,
            cap_cp=75.0,
            threshold_cp=0.0,
            mode="at_least_one_change",
        )

        self.assertFalse(strict["intervention"])
        self.assertTrue(relaxed["intervention"])
        self.assertGreater(relaxed["improvement_cp"], 0.0)

    def test_small_grid_uses_only_gate_fit_and_keeps_holdouts_sealed(self):
        all_pairs = fixtures._pairs()
        registration = fixtures._preregistration(all_pairs)
        pairs, _ = training.split_profiles(all_pairs, registration)
        registration, report, model = _failed_source(all_pairs)
        with (
            mock.patch.object(target, "ALPHAS", (0.3, 1.0)),
            mock.patch.object(target, "CAPS_CP", (50.0, 75.0)),
            mock.patch.object(target, "MODES", ("strict_both_change", "at_least_one_change")),
            mock.patch.object(target, "THRESHOLDS_CP", (0.0, 5.0)),
            mock.patch.object(target, "SHAM_REPLICATES", 3),
        ):
            result = target.screen(
                registration, report, model, pairs, _shards(pairs)
            )

        self.assertEqual(result["grid"]["candidates"], 16)
        self.assertEqual(result["feature_audit_profile_rows_examined"], 0)
        self.assertEqual(result["feature_audit_action_value_reads"], 0)
        self.assertEqual(result["outer_confirm_action_value_reads"], 0)
        self.assertEqual(result["pattern_eval_fits"], 0)
        self.assertEqual(result["production_model_fits"], 0)
        self.assertFalse(result["feature_audit_authorized"])
        self.assertFalse(result["production_rule_authorized"])
        self.assertEqual(result["diagnostic_fits"], 10 + (15 if result["selected"] else 0))

    def test_source_with_any_holdout_read_fails_closed(self):
        pairs = fixtures._pairs()
        registration, report, model = _failed_source(pairs)
        report["feature_audit_action_value_reads"] = 1
        with self.assertRaisesRegex(ValueError, "counter drift"):
            target.screen(registration, report, model, {}, [])


if __name__ == "__main__":
    unittest.main()
