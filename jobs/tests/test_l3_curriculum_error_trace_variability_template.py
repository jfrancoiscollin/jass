#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "jobs/templates/l3-curriculum-error-trace-variability-screen-v1.sh").read_text()


class TraceVariabilityTemplateTests(unittest.TestCase):
    def test_read_only_target_free_guards(self):
        for token in ("NO_FIT", "NO_SELFPLAY", "NO_STRENGTH_GAMES", "NO_FROZEN_READ", "EXACT_ACTION_VALUE_READS__0", "OUTER_CONFIRM_PROFILE_ROWS_EXAMINED__0", "PROMOTION_AUTHORIZED__FALSE"):
            self.assertIn(token, TEXT)
        self.assertNotIn("train_stream_exact.py", TEXT)
        self.assertNotIn("run_games", TEXT)

    def test_immutable_failed_coverage_source(self):
        for token in ("COVERAGE_SOURCE_JOB", "COVERAGE_SOURCE_ATTEMPT", "COVERAGE_SOURCE_CODE", "coverage source identity/state drift"):
            self.assertIn(token, TEXT)


if __name__ == "__main__":
    unittest.main()
