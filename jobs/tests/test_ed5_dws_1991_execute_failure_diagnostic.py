from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from jobs.tools import ed5_dws_1991_execute_failure_diagnostic_stage as stage


class Ed5Dws1991ExecuteFailureDiagnosticTests(unittest.TestCase):
    def source_diagnostic(self) -> dict:
        # 1991 failed before StageEvidence could publish a traceback, so the bounded
        # Launch V2 diagnostic legitimately has no last_phase/error_type/frames.
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
        }

    def probe(self) -> dict:
        return {
            "schema": "jass.ed5.dws_1991_direct_script_probe.v1",
            "wrapper_rel": stage.WRAPPER_REL,
            "wrapper_git_blob_sha": stage.WRAPPER_GIT_BLOB_SHA,
            "python": "/usr/bin/python3",
            "cwd": str(stage.ROOT),
            "ed5_identity_environment_removed": True,
            "pythonpath_removed": True,
            "returncode": 1,
            "stdout": "",
            "stderr": (
                f'Traceback (most recent call last):\n  File "{stage.WRAPPER_REL}", line 12, in <module>\n'
                "    from jobs.tools import ed5_fresh_dws_disjointness_stage as barrier\n"
                "ModuleNotFoundError: No module named 'jobs'\n"
            ),
            **stage.ZERO_FIELDS,
            "scientific_verdict": None,
            "confirmation_authorized": False,
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

    def test_republishes_exact_failure_and_classifies_direct_import_with_zero_science(self):
        report = self.source_diagnostic()
        td, artifact, raw, fake_fetch_files, env = self.run_fixture(report)
        with (
            td,
            mock.patch.dict(os.environ, env, clear=False),
            mock.patch.object(stage, "fetch_files", side_effect=fake_fetch_files),
            mock.patch.object(stage, "direct_entrypoint_probe", return_value=self.probe()),
        ):
            self.assertEqual(stage.main(), 0)
            self.assertEqual((artifact / stage.LOCAL_NAME).read_bytes(), raw)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            self.assertEqual(summary["classification"], "TECHNICAL_DIAGNOSTIC_ONLY")
            self.assertEqual(summary["recovered"], report)
            self.assertFalse(summary["source_stage_evidence_available"])
            self.assertEqual(summary["proven_root_cause"], "DIRECT_SCRIPT_IMPORT_PATH")
            self.assertEqual(summary["proven_exception"], "ModuleNotFoundError: No module named 'jobs'")
            for key, expected in stage.ZERO_FIELDS.items():
                self.assertEqual(summary[key], expected)
            self.assertIsNone(summary["scientific_verdict"])
            self.assertFalse(summary["confirmation_authorized"])

    def test_direct_probe_removes_science_identity_and_pythonpath_before_execution(self):
        with tempfile.TemporaryDirectory() as td:
            completed = SimpleNamespace(returncode=1, stdout="", stderr="ModuleNotFoundError: No module named 'jobs'\n")
            env = {"ED5_FRESH_D_JOB": "must-not-leak", "PYTHONPATH": "/tmp/must-not-leak"}
            with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(stage.subprocess, "run", return_value=completed) as run:
                report = stage.direct_entrypoint_probe(Path(td))
            kwargs = run.call_args.kwargs
            self.assertNotIn("PYTHONPATH", kwargs["env"])
            self.assertFalse(any(key.startswith("ED5_FRESH_") for key in kwargs["env"]))
            self.assertEqual(kwargs["cwd"], stage.ROOT)
            self.assertEqual(run.call_args.args[0], ["/usr/bin/python3", stage.WRAPPER_REL])
            self.assertEqual(report["wrapper_git_blob_sha"], stage.WRAPPER_GIT_BLOB_SHA)
            self.assertEqual(report["target_reads"], 0)

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
        self.assertEqual(profile["evidence_outputs"], [stage.LOCAL_NAME, stage.PROBE_NAME])
        for effects in (profile["rehearsal_max_effects"], profile["production_max_effects"]):
            self.assertTrue(all(value == 0 for value in effects.values()))


if __name__ == "__main__":
    unittest.main()
