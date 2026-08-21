#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-exploratory-replay-force-resume-v3.sh"


class ReplayForceResumeV3TemplateTest(unittest.TestCase):
    def test_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(TEMPLATE)], check=True)

    def test_failed_source_is_fetched_directly(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for token in (
            "2c681159e8eeb84882b35c93cd03b2acb47e8244",
            "fetch_result_files.py --prefix",
            "--expected-state failed",
            '--report "$ART/verified-1449-models.json"',
            "models_reused':4",
            "'refits':0",
            "scientific_force_protocol_changed':False",
        ):
            self.assertIn(token, text)
        self.assertIn("completed-state helper still used for failed source", text)
        self.assertIn("l3-exploratory-replay-force-resume-v3", text)


if __name__ == "__main__":
    unittest.main()
