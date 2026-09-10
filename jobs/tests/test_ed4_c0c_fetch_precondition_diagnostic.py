from __future__ import annotations

# Keep an ordinary branch-authored commit after incident-register autofeed so
# the required PR checks run against the final ledger-synchronized head.
import os
import subprocess
import sys
import unittest
from pathlib import Path

from jobs.tools import ed4_c0c_fetch_precondition_diagnostic_stage as stage

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "jobs/tools/ed4_c0c_fetch_precondition_diagnostic_stage.py"


class C0CFetchPreconditionDiagnosticTests(unittest.TestCase):
    def test_zero_size_and_missing_candidates_reproduce_fetch_guard_without_payload_reads(self):
        job = "cpx62-fixture"
        attempt = "20260910T000000Z-deadbeef"
        code = "a" * 40
        c0a = {
            "sources": [{
                "job_id": job,
                "attempt_id": attempt,
                "code_sha": code,
                "result_state": "completed",
            }]
        }
        c0b = {
            "candidate_jobs": [{
                "job_id": job,
                "attempt_id": attempt,
                "candidate_files": [
                    {"path": "artefacts/good.jnnw", "kind": "jnnw", "size_bytes": 46, "sha256": "1" * 64},
                    {"path": "artefacts/empty.jnnw", "kind": "jnnw", "size_bytes": 0, "sha256": "2" * 64},
                    {"path": "artefacts/missing.fen", "kind": "fen", "size_bytes": 12, "sha256": "3" * 64},
                ],
            }]
        }
        inventories = {(job, attempt): {
            "job_id": job,
            "attempt_id": attempt,
            "code_sha": code,
            "result_state": "completed",
            "files": [
                {"path": "artefacts/good.jnnw", "size_bytes": 46, "sha256": "1" * 64},
                {"path": "artefacts/empty.jnnw", "size_bytes": 0, "sha256": "2" * 64},
            ],
        }}
        result = stage.classify_fetch_preconditions(c0a, c0b, inventories)
        self.assertEqual(result["candidate_jobs_examined"], 1)
        self.assertEqual(result["candidate_files_examined"], 3)
        self.assertEqual(result["fetch_guard_blocker_count"], 2)
        self.assertEqual(
            [row["reason"] for row in result["fetch_guard_blockers"]],
            ["ZERO_SIZE_AUTHENTICATED_CANDIDATE", "MISSING_FROM_AUTHENTICATED_INVENTORY"],
        )
        self.assertEqual(result["first_fetch_guard_blocker"]["path"], "artefacts/empty.jnnw")
        self.assertEqual(result["descriptor_drift_count"], 0)

    def test_nonempty_descriptor_drift_is_separate_from_line118_guard(self):
        job, attempt, code = "cpx62-fixture", "attempt-1", "b" * 40
        c0a = {"sources": [{"job_id": job, "attempt_id": attempt, "code_sha": code, "result_state": "failed"}]}
        c0b = {"candidate_jobs": [{"job_id": job, "attempt_id": attempt, "candidate_files": [
            {"path": "x.fen", "kind": "fen", "size_bytes": 10, "sha256": "4" * 64}
        ]}]}
        inventories = {(job, attempt): {"job_id": job, "attempt_id": attempt, "code_sha": code,
            "result_state": "failed", "files": [{"path": "x.fen", "size_bytes": 11, "sha256": "5" * 64}]}}
        result = stage.classify_fetch_preconditions(c0a, c0b, inventories)
        self.assertEqual(result["fetch_guard_blocker_count"], 0)
        self.assertEqual(result["descriptor_drift_count"], 1)

    def test_direct_entrypoint_bootstraps_repository_imports(self):
        completed = subprocess.run(
            [sys.executable, str(STAGE)],
            cwd=ROOT,
            env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("ModuleNotFoundError", completed.stderr)
        self.assertIn("JASS_ARTEFACT_DIR", completed.stderr)


if __name__ == "__main__":
    unittest.main()
