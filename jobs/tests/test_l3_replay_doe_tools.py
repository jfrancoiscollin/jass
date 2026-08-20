#!/usr/bin/env python3
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from jobs.tools.l3_replay_doe_force_readout import classify
from jobs.tools.l3_replay_doe_static_readout import _balanced_cluster_bootstrap


class ReplayDoeForceReadoutTests(unittest.TestCase):
    def test_native_classification_is_fail_closed(self):
        positive = {
            "pool_rates": [0.51, 0.52],
            "inter_pool_compatible_95": True,
            "ci_low": 0.503,
            "ci_high": 0.527,
            "probability_rate_gt_half": 0.99,
        }
        negative = {
            "pool_rates": [0.49, 0.48],
            "inter_pool_compatible_95": True,
            "ci_low": 0.473,
            "ci_high": 0.497,
            "probability_rate_gt_half": 0.01,
        }
        inconclusive = dict(positive, ci_low=0.499)
        self.assertEqual(classify(positive), "ESTABLISHED_POSITIVE")
        self.assertEqual(classify(negative), "ESTABLISHED_NEGATIVE")
        self.assertEqual(classify(inconclusive), "NOT_ESTABLISHED")


class ReplayDoeStaticReadoutTests(unittest.TestCase):
    def test_balanced_bootstrap_gives_equal_cohort_mass(self):
        old = np.asarray([1.0, 1.0, -1.0, -1.0])
        new = np.asarray([0.5, 0.5, 0.5, 0.5, 0.5, 0.5])
        old_clusters = np.asarray([1, 1, 2, 2])
        new_clusters = np.asarray([10, 10, 11, 11, 12, 12])
        report = _balanced_cluster_bootstrap(
            old, old_clusters, new, new_clusters, samples=1000, seed=7
        )
        self.assertAlmostEqual(report["effect"], 0.25)
        self.assertEqual(report["cohort_mass"], {"OLD": 0.5, "NEW": 0.5})
        self.assertEqual(report["OLD_opening_clusters"], 2)
        self.assertEqual(report["NEW_opening_clusters"], 3)


class ReplayDoeTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = Path(
            "jobs/templates/l3-exploratory-replay-four-arm-doe-v1.sh"
        ).read_text(encoding="utf-8")

    def test_immutable_sources_and_scientific_arms_are_locked(self):
        for token in (
            "20260818T184956Z-3465ec72",
            "20260820T215456Z-4652cdc4",
            "20260814T191555Z-18c38a33",
            "REPLAY_SEED=2026082106",
            "SPLIT_SEED=577215",
            "HOLDOUT_MOD=10",
            'fit_arm A "$DATA/A-current.jnnw"',
            'fit_arm B "$DATA/BC-replay25.jnnw"',
            'fit_arm C "$DATA/BC-replay25.jnnw"',
            'fit_arm D "$DATA/D-full-history.jnnw"',
            '"primary_contrast": "B_vs_A"',
        ):
            self.assertIn(token, self.text)

    def test_force_budget_and_safety_guards_are_locked(self):
        for token in (
            "NOPEN=1500",
            "BOOTSTRAP=100000",
            "MOVETIME=0.1",
            "FORCE_DEPTH=9",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "FORCE_GAMES_PLAYED__36000",
            "CTX4_VERDICT_UNCHANGED__FAILED",
        ):
            self.assertIn(token, self.text)

    def test_no_automatic_promotion_or_continuation(self):
        self.assertNotIn("promotion_authorized\": true", self.text.lower())
        self.assertIn("AUTOMATIC_NEXT_JOB__NULL", self.text)


if __name__ == "__main__":
    unittest.main()
