#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-c1q1-verdict-v2.sh"
PREPARED = (
    ROOT
    / "jobs/prepared/l3-c1q1-verdict-v2-20260718"
    / "cpx62-l3-c1q1-verdict-v2.sh"
)


class L3Q1VerdictPreparedTests(unittest.TestCase):
    def test_shell_is_valid_but_not_authorized_or_queued(self):
        for script in (TEMPLATE, PREPARED):
            subprocess.run(["bash", "-n", str(script)], check=True)
            self.assertNotIn("/jobs/queue/", str(script))
        wrapper = PREPARED.read_text()
        self.assertNotIn("FULL_RUN_APPROVED=1", wrapper)
        self.assertNotIn("EXPECTED_CODE_SHA=", wrapper)
        self.assertIn("Claude review + JFC go", wrapper)

    def test_reuses_the_four_immutable_g2_artifacts_without_training(self):
        text = TEMPLATE.read_text()
        for job in (
            "ccx33-0802-c1q1-q00-v2",
            "cpx62-0804-c1q1-q10-v2",
            "cpx62-0805-c1q1-q01-v2",
            "ccx33-0803-c1q1-q11-v2",
        ):
            self.assertIn(job, text)
        self.assertNotIn("--gen-data-wdl", text)
        self.assertNotIn("train_stream.py", text)

    def test_three_required_views_and_paired_verdict_are_explicit(self):
        text = TEMPLATE.read_text()
        self.assertIn('--search-params-a "$COMMON_SEARCH"', text)
        self.assertIn('--search-params-b "$COMMON_SEARCH"', text)
        self.assertIn('--search-params-a "${SEARCH[$c]}"', text)
        self.assertIn('--search-params-b "${SEARCH[Q00]}"', text)
        self.assertIn('--movetime "$NATIVE_MOVETIME"', text)
        self.assertIn('--require-position-results', text)
        self.assertIn("jobs/tools/l3_q1_verdict.py", text)
        self.assertIn("no Q2 job was launched", text)
        self.assertNotIn("qs_forcing_depth=6", text)
        self.assertNotIn("qs_promo_depth=6", text)


if __name__ == "__main__":
    unittest.main()
