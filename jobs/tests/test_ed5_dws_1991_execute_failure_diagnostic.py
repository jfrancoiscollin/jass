from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tools import ed5_dws_1991_execute_failure_diagnostic_stage as stage


class Ed5Dws1991ExecuteFailureDiagnosticTests(unittest.TestCase):
    def source_diagnostic(self) -> dict:
        return {
            "schema": "jass.launch_failure.v2",
            "classification": "TECHNICAL",
            "state": "failed",
            "failure_code": "STAGE_FAILED:EXECUTE",
            "scientific_verdict": None,
            "job_id": stage.SOURCE_JOB,
            "attempt_id": stage.SOURCE_ATTEMPT,
            "snapshot_at": "2026-09-15T17:39:20+00:00",
            "next_stage": None,
            "last_phase": "authenticate-seals",
            "error_type": "ValueError",
            "frames": [
                {"file": "ed5_fresh_dws_disjointness_stage.py", "line": 91, "function": "fetch_ds"}
            ],
        }

    def run_fixture(self, report: dict):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        result = root / "result"
        artifact = result / "artefacts"
        result.mkdir()
        artifact.mkdir()
        raw = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()

        def fake_fetch_files(**kwargs):
            self.assertEqual(kwargs["expected_state"], "failed")
            self.assertEqual(kwargs["prefix"], stage.SOURCE_PREFIX)
            self.assertEqual(kwargs["selections"], [(stage.SOURCE_REMOTE_PATH, stage.LOCAL_NAME)])
            out = kwargs["out_dir"]
            out.mkdir(parents=True, exist_ok=True)
            (out / stage.LOCAL_NAME).write_bytes(raw)
            return {
                "job_id": stage.SOURCE_JOB,
                "attempt_id": stage.SOURCE_ATTEMPT,
                "code_sha": stage.SOURCE_CODE_SHA,
                "result_state": "failed",
                "exit_code": 2,
                "files": [{
                    "path": stage.SOURCE_REMOTE_PATH,
                    "local_name": stage.LOCAL_NAME,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }],
            }

        env = {
            "JASS_RESULT_DIR": str(result),
            "JASS_ARTEFACT_DIR": str(artifact),
            "LAUNCH_MODE": "rehearsal",
        }
        return td, artifact, raw, fake_fetch_files, env

    def test_republishes_exact_bounded_failure_evidence_with_zero_science(self):
        report = self.source_diagnostic()
        td, artifact, raw, fake_fetch_files, env = self.run_fixture(report)
        with td, mock.patch.dict(os.environ, env, clear=False), mock.patch.object(stage, "fetch_files", side_effect=fake_fetch_files):
            self.assertEqual(stage.main(), 0)
            self.assertEqual((artifact / stage.LOCAL_NAME).read_bytes(), raw)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            self.assertEqual(summary["classification"], "TECHNICAL_DIAGNOSTIC_ONLY")
            self.assertEqual(summary["recovered"], report)
            for key, expected in stage.ZERO_FIELDS.items():
                self.assertEqual(summary[key], expected)
            self.assertIsNone(summary["scientific_verdict"])
            self.assertFalse(summary["confirmation_authorized"])

    def test_fails_closed_if_source_is_not_execute_failure(self):
        report = self.source_diagnostic()
        report["failure_code"] = "SOMETHING_ELSE"
        td, artifact, _raw, fake_fetch_files, env = self.run_fixture(report)
        with td, mock.patch.dict(os.environ, env, clear=False), mock.patch.object(stage, "fetch_files", side_effect=fake_fetch_files):
            self.assertEqual(stage.main(), 2)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            self.assertEqual(summary["classification"], "TECHNICAL")
            self.assertEqual(summary["target_reads"], 0)
            self.assertIsNone(summary["scientific_verdict"])

    def test_profile_is_read_only_and_binds_this_stage(self):
        profile = json.loads((Path(__file__).resolve().parents[1] / "launch_profiles" / "ed5-dws-1991-execute-failure-diagnostic-v1.json").read_text())
        self.assertEqual(stage.SOURCE_REMOTE_PATH, "artefacts/attempt-diagnostic.json")
        self.assertEqual(profile["command"], ["/usr/bin/python3", "jobs/tools/ed5_dws_1991_execute_failure_diagnostic_stage.py"])
        self.assertEqual(profile["required_phases"], stage.PHASES)
        self.assertEqual(profile["evidence_outputs"], [stage.LOCAL_NAME])
        for effects in (profile["rehearsal_max_effects"], profile["production_max_effects"]):
            self.assertTrue(all(value == 0 for value in effects.values()))


if __name__ == "__main__":
    unittest.main()
