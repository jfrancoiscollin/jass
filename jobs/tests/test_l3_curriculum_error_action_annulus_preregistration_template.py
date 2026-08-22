#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "jobs" / "templates" / "l3-curriculum-error-action-annulus-preregistration-v1.sh").read_text()


class AnnulusPreregistrationTemplateTests(unittest.TestCase):
    def test_job_is_read_only_and_sealed(self):
        for token in (
            "NO_FIT",
            "NO_SELFPLAY",
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "VALIDATION_DECISION_PAYLOAD_READS",
            "OUTER_CONFIRM_DECISION_PAYLOAD_READS",
            "DIAGNOSTIC_FITS",
            "PROMOTION_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, TEXT)
        self.assertIn("(art/f'{name}__{value}').touch()", TEXT)
        self.assertNotIn("train_stream_exact.py", TEXT)
        self.assertNotIn("run_games", TEXT)

    def test_both_sources_are_immutable_and_authenticated(self):
        for token in (
            "RANKER_SOURCE_ATTEMPT",
            "RANKER_SOURCE_CODE",
            "READOUT_SOURCE_ATTEMPT",
            "READOUT_SOURCE_CODE",
            "identity/state drift",
        ):
            self.assertIn(token, TEXT)

    def test_fixed_architecture_marker_has_no_grid(self):
        self.assertIn("FIXED__CANONICAL_EQUIVARIANT__ALPHA_100__ADV_25__MARGIN_GT50_LE100__CAP_75", TEXT)
        self.assertIn("architectures=1", TEXT)


if __name__ == "__main__":
    unittest.main()
