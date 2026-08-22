#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "jobs" / "templates" / "l3-curriculum-error-action-ranker-readout-v1.sh").read_text()


class ActionRankerReadoutTemplateTests(unittest.TestCase):
    def test_readout_is_strictly_read_only_and_sealed(self):
        for token in (
            "NO_FIT",
            "NO_SELFPLAY",
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "VALIDATION_DECISION_PAYLOAD_READS__0",
            "OUTER_CONFIRM_DECISION_PAYLOAD_READS__0",
            "DIAGNOSTIC_FITS__0",
        ):
            self.assertIn(token, TEXT)
        self.assertNotIn("train_stream_exact.py", TEXT)
        self.assertNotIn("run_games", TEXT)

    def test_nomenclature_and_source_identity_are_pinned(self):
        self.assertIn("action-ranker-readout-v1$", TEXT)
        self.assertIn("RANKER_SOURCE_ATTEMPT", TEXT)
        self.assertIn("source identity mismatch", TEXT)

    def test_failure_logs_are_published_for_auditable_diagnosis(self):
        self.assertIn("for log in tests fetch autopsy", TEXT)
        self.assertIn('cp "$W/$log.log" "$ART/$log.log"', TEXT)
        for name in ("tests", "fetch", "autopsy"):
            self.assertIn(f'$W/{name}.log', TEXT)


if __name__ == "__main__":
    unittest.main()
