from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tools import run_experiment_stage_status_bridge as bridge


class StageStatusBridgeTests(unittest.TestCase):
    def receipt(self, *, state="failed", failure_class="STAGE_EXIT_CODE",
                failure_stage="EXECUTE", next_stage=None):
        return {
            "campaign": "infra",
            "stage": "full-rehearsal",
            "code_sha": "a" * 40,
            "spec_sha256": "b" * 64,
            "state": state,
            "failure_class": failure_class,
            "failure_stage": failure_stage,
            "error": "stage exit 4, expected 0" if state == "failed" else None,
            "exit_code": 4 if state == "failed" else 0,
            "timed_out": False,
            "inputs_authenticated": True,
            "outputs_authenticated": state == "completed",
            "declared_scientific_side_effects": {
                "fits": 0, "strength_games": 0, "promotions": 0, "bakes": 0,
            },
            "next_stage": next_stage,
        }

    def test_compact_summary_contains_closed_diagnostic_fields(self):
        with mock.patch.dict(os.environ, {
            "JASS_JOB_ID": "job-1", "JASS_ATTEMPT_ID": "attempt-1",
        }, clear=False):
            summary = bridge.compact_summary(self.receipt())
        self.assertEqual(summary["schema"], bridge.SUMMARY_SCHEMA)
        self.assertEqual(summary["job_id"], "job-1")
        self.assertEqual(summary["failure_class"], "STAGE_EXIT_CODE")
        self.assertEqual(summary["failure_stage"], "EXECUTE")
        self.assertIsNone(summary["scientific_verdict"])
        self.assertEqual(summary["declared_scientific_side_effects"]["fits"], 0)

    def test_write_new_never_overwrites_stage_owned_summary(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "scientific-summary.json"
            path.write_text('{"owned":"stage"}\n', encoding="ascii")
            bridge.write_new(path, {"owned": "bridge"})
            self.assertEqual(json.loads(path.read_text()), {"owned": "stage"})

    def test_failed_stage_writes_allowlisted_summary_and_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = root / "result"
            artifact = root / "artifact"
            artifact.mkdir()
            spec = root / "spec.json"
            spec.write_text("{}\n", encoding="ascii")
            receipt = self.receipt()
            with mock.patch.object(bridge.core, "run_stage", return_value=(2, receipt)), \
                    mock.patch.dict(os.environ, {
                        "JASS_JOB_ID": "job-fail",
                        "JASS_ATTEMPT_ID": "attempt-fail",
                    }, clear=False):
                rc = bridge.main([
                    "--spec", str(spec),
                    "--repo-root", str(root),
                    "--result-dir", str(result),
                    "--artifact-dir", str(artifact),
                ])
            self.assertEqual(rc, 2)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            diagnostic = json.loads((artifact / "attempt-diagnostic.json").read_text())
            self.assertEqual(summary["failure_stage"], "EXECUTE")
            self.assertEqual(diagnostic["classification"], "stage_runner_failure")
            self.assertEqual(diagnostic["job_id"], "job-fail")

    def test_success_writes_summary_with_next_stage_and_no_diagnostic(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            result = root / "result"
            artifact = root / "artifact"
            artifact.mkdir()
            spec = root / "spec.json"
            spec.write_text("{}\n", encoding="ascii")
            receipt = self.receipt(
                state="completed", failure_class=None, failure_stage=None,
                next_stage="B3_INFRASTRUCTURE_READY",
            )
            with mock.patch.object(bridge.core, "run_stage", return_value=(0, receipt)):
                rc = bridge.main([
                    "--spec", str(spec),
                    "--repo-root", str(root),
                    "--result-dir", str(result),
                    "--artifact-dir", str(artifact),
                ])
            self.assertEqual(rc, 0)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            self.assertEqual(summary["state"], "completed")
            self.assertEqual(summary["next_stage"], "B3_INFRASTRUCTURE_READY")
            self.assertFalse((artifact / "attempt-diagnostic.json").exists())


if __name__ == "__main__":
    unittest.main()
