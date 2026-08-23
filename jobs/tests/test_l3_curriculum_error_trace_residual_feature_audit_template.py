#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "jobs/templates/l3-curriculum-error-trace-residual-feature-audit-v1.sh").read_text()


class TraceResidualFeatureAuditTemplateTests(unittest.TestCase):
    def test_one_shot_oos_guards_and_no_refit(self):
        for marker in (
            "ONE_SHOT_FEATURE_AUDIT",
            "NO_RESIDUAL_REFIT",
            "NO_OUTER_CONFIRM_TARGETS",
            "NO_SELFPLAY",
            "NO_PATTERNEVAL_FIT",
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "NO_AUTOMATIC_CONTINUATION",
            "RESIDUAL_FITS__0",
        ):
            self.assertIn(marker, TEMPLATE)
        self.assertNotIn(" trace-residual-training.py train", TEMPLATE)
        self.assertNotIn("queue/pending", TEMPLATE)

    def test_exact_targets_are_generated_only_once_on_feature_audit(self):
        self.assertEqual(TEMPLATE.count("l3_curriculum_search_error_atlas.py atlas"), 1)
        self.assertEqual(TEMPLATE.count('--pairs "$ART/feature-audit-pairs.json"'), 2)
        self.assertNotIn('--pairs "$IN/matched-pairs.json" --jass', TEMPLATE)
        self.assertNotIn("max-pairs", TEMPLATE)
        self.assertIn("exact-targets-on-feature-audit-once", TEMPLATE)

    def test_training_split_model_and_curriculum_are_authenticated(self):
        for marker in (
            "TRAINING_SOURCE_ATTEMPT",
            "PREREG_SOURCE_ATTEMPT",
            "PAIRS_SOURCE_ATTEMPT",
            "verified-training-source.json",
            "sealed-audit-manifest.json",
            "gate-fit-pairs.json",
            'CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"',
        ):
            self.assertIn(marker, TEMPLATE)

    def test_output_never_authorizes_production_or_promotion(self):
        self.assertIn("PRODUCTION_RULE_AUTHORIZED__FALSE", TEMPLATE)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", TEMPLATE)
        self.assertIn("automatic_continuation':False", TEMPLATE)


if __name__ == "__main__":
    unittest.main()
