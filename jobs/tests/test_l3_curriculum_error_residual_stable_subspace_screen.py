#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest import mock

import numpy as np

from jobs.tests import test_l3_curriculum_error_residual_ridge_path_screen as fixtures
from jobs.tests import test_l3_curriculum_error_trace_residual_training as training_fixtures
from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_residual_stable_subspace_screen as target
from jobs.tools import l3_curriculum_error_trace_residual_training as training


def _model(coefficient: np.ndarray) -> dict:
    return {
        "coef": coefficient,
        "mean": np.zeros_like(coefficient),
        "rms": np.ones_like(coefficient),
        "alpha": target.ALPHA,
    }


class ResidualStableSubspaceScreenTests(unittest.TestCase):
    def test_analysis_selects_only_signed_repeated_low_variance_top_features(self):
        width = len(ranker.FEATURE_NAMES)
        base = np.asarray([10, 9, 8, 7, 6, 5] + [0.1] * (width - 6), dtype=float)
        folds = [_model(base * scale) for scale in (0.96, 0.98, 1.0, 1.02, 1.04)]
        result = target._analyze_models(folds, _model(base))

        self.assertEqual(result["selected_feature_indices"], list(range(6)))
        self.assertEqual(result["selected_feature_count"], 6)
        self.assertEqual(len(result["support_sha256"]), 64)
        self.assertGreaterEqual(
            result["fold_stability"]["minimum_coefficient_cosine"], 0.99
        )

    def test_sign_flip_excludes_feature(self):
        width = len(ranker.FEATURE_NAMES)
        base = np.asarray([10, 9, 8, 7, 6, 5] + [0.1] * (width - 6), dtype=float)
        coefficients = [base.copy() for _ in range(5)]
        coefficients[-1][0] *= -1
        result = target._analyze_models(
            [_model(row) for row in coefficients], _model(base)
        )

        self.assertNotIn(0, result["selected_feature_indices"])
        self.assertFalse(
            result["features"][0]["gates"][
                "same_nonzero_sign_all_folds_and_full"
            ]
        )

    def test_screen_reuses_only_sealed_1508_and_never_authorizes_refit(self):
        all_pairs = training_fixtures._pairs()
        registration = training_fixtures._preregistration(all_pairs)
        pairs, _ = training.split_profiles(all_pairs, registration)
        registration, report, model = fixtures._failed_source(all_pairs)
        width = len(ranker.FEATURE_NAMES)
        base = np.asarray([10, 9, 8, 7, 6, 5] + [0.1] * (width - 6), dtype=float)
        with mock.patch.object(target.ridge, "_fit", return_value=_model(base)):
            result = target.screen(
                registration, report, model, pairs, fixtures._shards(pairs)
            )

        self.assertEqual(result["verdict"], target.READY)
        self.assertEqual(result["diagnostic_residual_fits"], 6)
        self.assertEqual(result["new_exact_target_computations"], 0)
        self.assertEqual(result["fresh_label_reads"], 0)
        self.assertEqual(result["pattern_eval_fits"], 0)
        self.assertFalse(result["anchored_refit_authorized"])
        self.assertFalse(result["strength_gate_authorized"])
        self.assertFalse(result["automatic_continuation"])

    def test_source_with_holdout_read_fails_closed(self):
        pairs = training_fixtures._pairs()
        registration, report, model = fixtures._failed_source(pairs)
        report["outer_confirm_action_value_reads"] = 1
        with self.assertRaisesRegex(ValueError, "counter drift"):
            target.screen(registration, report, model, {}, [])


if __name__ == "__main__":
    unittest.main()
