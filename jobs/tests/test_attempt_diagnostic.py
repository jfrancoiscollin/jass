#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools/attempt_diagnostic.py"
SPEC = importlib.util.spec_from_file_location("attempt_diagnostic", MODULE)
AD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(AD)


def manifest(state: str, exit_code: int, attempt: str) -> dict:
    return {
        "job_id": "ccx33-0769-probe-t3-adj-g1-v1",
        "attempt_id": attempt,
        "code_sha": "a" * 40,
        "host": "ubuntu-16gb-hel1-2",
        "state": state,
        "exit_code": exit_code,
    }


class AttemptDiagnosticTests(unittest.TestCase):
    def test_duplicate_failure_preserves_successful_science(self):
        result = AD.diagnose(
            manifest("completed", 0, "good"),
            manifest("failed", -1, "bad"),
        )
        self.assertTrue(result["scientific_result_preserved"])
        self.assertFalse(result["replay_science_required"])
        self.assertEqual(result["probable_cause"], "wrapper_lost_without_exit_status")

    def test_oom_evidence_takes_priority(self):
        result = AD.diagnose(
            manifest("completed", 0, "good"),
            manifest("failed", -1, "bad"),
            kernel="kernel: Out of memory: Killed process 1234 (jass)",
        )
        self.assertEqual(result["probable_cause"], "oom_kill")
        self.assertIn("oom_kill", result["evidence"])

    def test_different_job_does_not_preserve_science(self):
        failed = manifest("failed", -1, "bad")
        failed["job_id"] = "other"
        result = AD.diagnose(manifest("completed", 0, "good"), failed)
        self.assertFalse(result["scientific_result_preserved"])
        self.assertTrue(result["replay_science_required"])


if __name__ == "__main__":
    unittest.main()
