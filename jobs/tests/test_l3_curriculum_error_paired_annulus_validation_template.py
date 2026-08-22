#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "jobs" / "templates" / "l3-curriculum-error-paired-annulus-validation-v1.sh").read_text()


class PairedAnnulusValidationTemplateTests(unittest.TestCase):
    def test_one_shot_validation_and_confirm_sealing_are_explicit(self):
        for token in (
            "ONE_SHOT_VALIDATION_APPROVED",
            "OUTER_CONFIRM_SEALED",
            "INNER_VALIDATION_DECISION_PAYLOAD_READS__31",
            "OUTER_CONFIRM_DECISION_PAYLOAD_READS__0",
            "DIAGNOSTIC_RESIDUAL_FITS__101",
        ):
            self.assertIn(token, TEXT)

    def test_forbidden_actions_remain_disabled(self):
        for token in (
            "NO_SELFPLAY",
            "NO_PATTERNEVAL_FIT",
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "PROMOTION_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, TEXT)
        self.assertNotIn("run_games", TEXT)
        self.assertNotIn("train_stream_exact.py", TEXT)

    def test_all_raw_inputs_and_preregistration_are_authenticated(self):
        self.assertIn("matched-pairs.json", TEXT)
        self.assertIn("atlas-shards/shard-$shard.json", TEXT)
        self.assertIn("PREREG_SOURCE_ATTEMPT", TEXT)
        self.assertIn("identity/state drift", TEXT)


if __name__ == "__main__":
    unittest.main()
