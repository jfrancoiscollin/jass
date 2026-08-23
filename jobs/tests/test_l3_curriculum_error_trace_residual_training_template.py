#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "jobs/templates/l3-curriculum-error-trace-residual-training-v1.sh").read_text()


class TraceResidualTrainingTemplateTests(unittest.TestCase):
    def test_training_is_strictly_isolated_from_sealed_splits_and_force(self):
        for marker in (
            'TRAINING_ONLY:-0}',
            'NO_FEATURE_AUDIT_TARGETS:-0}',
            'NO_OUTER_CONFIRM_TARGETS:-0}',
            'NO_SELFPLAY:-0}',
            'NO_PATTERNEVAL_FIT:-0}',
            'NO_STRENGTH_GAMES:-0}',
            'NO_FROZEN_READ:-0}',
            'NO_AUTOMATIC_PROMOTION:-0}',
            'NO_AUTOMATIC_CONTINUATION:-0}',
        ):
            self.assertIn(marker, TEMPLATE)
        self.assertNotIn("run_match", TEMPLATE)

    def test_exact_targets_use_only_materialized_gate_fit_pairs(self):
        atlas_calls = TEMPLATE.count("l3_curriculum_search_error_atlas.py atlas")
        self.assertEqual(atlas_calls, 2)
        # Two exact-atlas passes (preflight/full) plus the trainer consume only
        # the already-materialized gate-fit subset.
        self.assertEqual(TEMPLATE.count('--pairs "$ART/gate-fit-pairs.json"'), 3)
        self.assertNotIn('--pairs "$IN/matched-pairs.json" --jass', TEMPLATE)
        self.assertIn("materialize-sealed-gate-fit-split-without-targets", TEMPLATE)
        self.assertIn("FEATURE_AUDIT_ACTION_VALUE_READS__0", TEMPLATE)
        self.assertIn("OUTER_CONFIRM_ACTION_VALUE_READS__0", TEMPLATE)

    def test_curriculum_and_source_identities_are_pinned(self):
        self.assertIn('CURRICULUM_JOB="cpx62-1341-jass-megacorpus-arm-d-fit-v1"', TEMPLATE)
        self.assertIn('CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"', TEMPLATE)
        self.assertIn('CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"', TEMPLATE)
        self.assertIn("pre-registration/pairs byte identity drift", TEMPLATE)

    def test_no_automatic_continuation_after_training_pass(self):
        self.assertIn("automatic_continuation':False", TEMPLATE)
        self.assertIn("PRODUCTION_RULE_AUTHORIZED__FALSE", TEMPLATE)
        self.assertNotIn("feature-audit-v1.sh", TEMPLATE)
        self.assertNotIn("queue/pending", TEMPLATE)


if __name__ == "__main__":
    unittest.main()
