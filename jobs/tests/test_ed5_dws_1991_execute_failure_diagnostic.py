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
    def source_receipt(self, stderr_raw: bytes) -> dict:
        return {
            "schema": "jass.stage_receipt.v1",
            "campaign": "ed5-q200k-choice-k2",
            "stage": "ed5-fresh-dws-historical-disjointness-v2",
            "code_sha": stage.SOURCE_CODE_SHA,
            "state": "failed",
            "failure_class": "STAGE_EXIT_CODE",
            "failure_stage": "EXECUTE",
            "error": "stage exit 1, expected 0",
            "exit_code": 1,
            "timed_out": False,
            "inputs_authenticated": True,
            "outputs_authenticated": False,
            "stderr": {
                "local_name": "stage.stderr.log",
                "sha256": hashlib.sha256(stderr_raw).hexdigest(),
                "size_bytes": len(stderr_raw),
            },
        }

    def run_fixture(self, stderr_raw: bytes):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        result = root / "result"
        artifact = result / "artefacts"
        result.mkdir()
        artifact.mkdir()
        receipt = self.source_receipt(stderr_raw)
        receipt_raw = (json.dumps(receipt, sort_keys=True) + "\n").encode()

        def fake_fetch_files(**kwargs):
            self.assertEqual(kwargs["expected_state"], "failed")
            self.assertEqual(kwargs["prefix"], stage.SOURCE_PREFIX)
            self.assertEqual(kwargs["selections"], [
                (stage.SOURCE_RECEIPT_REMOTE, stage.RECEIPT_LOCAL),
                (stage.SOURCE_STDERR_REMOTE, stage.STDERR_LOCAL),
            ])
            out = kwargs["out_dir"]
            out.mkdir(parents=True, exist_ok=True)
            (out / stage.RECEIPT_LOCAL).write_bytes(receipt_raw)
            (out / stage.STDERR_LOCAL).write_bytes(stderr_raw)
            return {
                "job_id": stage.SOURCE_JOB,
                "attempt_id": stage.SOURCE_ATTEMPT,
                "code_sha": stage.SOURCE_CODE_SHA,
                "result_state": "failed",
                "exit_code": 2,
                "files": [
                    {
                        "path": stage.SOURCE_RECEIPT_REMOTE,
                        "local_name": stage.RECEIPT_LOCAL,
                        "sha256": hashlib.sha256(receipt_raw).hexdigest(),
                        "size_bytes": len(receipt_raw),
                    },
                    {
                        "path": stage.SOURCE_STDERR_REMOTE,
                        "local_name": stage.STDERR_LOCAL,
                        "sha256": hashlib.sha256(stderr_raw).hexdigest(),
                        "size_bytes": len(stderr_raw),
                    },
                ],
            }

        env = {
            "JASS_RESULT_DIR": str(result),
            "JASS_ARTEFACT_DIR": str(artifact),
            "LAUNCH_MODE": "rehearsal",
        }
        return td, artifact, receipt_raw, fake_fetch_files, env

    def test_republishes_authenticated_runner_evidence_and_exact_exception_with_zero_science(self):
        stderr_raw = (
            b'Traceback (most recent call last):\n'
            b'  File "/srv/jass/code/jobs/tools/ed5_fresh_dws_disjointness_stage.py", line 12, in <module>\n'
            b'    from jobs.tools import ed5_fresh_w_source_stage as util\n'
            b'ModuleNotFoundError: No module named \'jobs\'\n'
        )
        td, artifact, receipt_raw, fake_fetch_files, env = self.run_fixture(stderr_raw)
        with td, mock.patch.dict(os.environ, env, clear=False), mock.patch.object(stage, "fetch_files", side_effect=fake_fetch_files):
            self.assertEqual(stage.main(), 0)
            self.assertEqual((artifact / stage.RECEIPT_LOCAL).read_bytes(), receipt_raw)
            self.assertEqual((artifact / stage.STDERR_LOCAL).read_bytes(), stderr_raw)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            self.assertEqual(summary["classification"], "TECHNICAL_DIAGNOSTIC_ONLY")
            self.assertEqual(summary["stage_failure_class"], "STAGE_EXIT_CODE")
            self.assertEqual(summary["stage_failure_stage"], "EXECUTE")
            self.assertEqual(summary["stage_exit_code"], 1)
            self.assertEqual(summary["exception"]["error_type"], "ModuleNotFoundError")
            self.assertEqual(summary["exception"]["error_message"], "No module named 'jobs'")
            self.assertEqual(summary["exception"]["frames"][-1], {
                "file": "ed5_fresh_dws_disjointness_stage.py", "line": 12, "function": "<module>"
            })
            for key, expected in stage.ZERO_FIELDS.items():
                self.assertEqual(summary[key], expected)
            self.assertIsNone(summary["scientific_verdict"])
            self.assertFalse(summary["confirmation_authorized"])

    def test_fails_closed_if_stderr_descriptor_does_not_authenticate(self):
        stderr_raw = b'Traceback (most recent call last):\nValueError: boom\n'
        td, artifact, _receipt_raw, fake_fetch_files, env = self.run_fixture(stderr_raw)

        def corrupt_fetch(**kwargs):
            result = fake_fetch_files(**kwargs)
            path = kwargs["out_dir"] / stage.RECEIPT_LOCAL
            value = json.loads(path.read_text())
            value["stderr"]["sha256"] = "0" * 64
            path.write_text(json.dumps(value) + "\n")
            raw = path.read_bytes()
            result["files"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
            result["files"][0]["size_bytes"] = len(raw)
            return result

        with td, mock.patch.dict(os.environ, env, clear=False), mock.patch.object(stage, "fetch_files", side_effect=corrupt_fetch):
            self.assertEqual(stage.main(), 2)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            self.assertEqual(summary["classification"], "TECHNICAL")
            self.assertEqual(summary["target_reads"], 0)
            self.assertIsNone(summary["scientific_verdict"])

    def test_profile_is_read_only_and_fetches_only_runner_receipt_and_stderr(self):
        profile = json.loads((Path(__file__).resolve().parents[1] / "launch_profiles" / "ed5-dws-1991-execute-failure-diagnostic-v1.json").read_text())
        self.assertEqual(profile["stage"], "ed5-dws-1991-execute-failure-diagnostic-v2")
        self.assertEqual(profile["command"], ["/usr/bin/python3", "jobs/tools/ed5_dws_1991_execute_failure_diagnostic_stage.py"])
        self.assertEqual(profile["required_phases"], stage.PHASES)
        self.assertEqual(profile["evidence_outputs"], [stage.RECEIPT_LOCAL, stage.STDERR_LOCAL])
        self.assertEqual(stage.SOURCE_RECEIPT_REMOTE, "stage-receipt.json")
        self.assertEqual(stage.SOURCE_STDERR_REMOTE, "stage.stderr.log")
        for effects in (profile["rehearsal_max_effects"], profile["production_max_effects"]):
            self.assertTrue(all(value == 0 for value in effects.values()))


if __name__ == "__main__":
    unittest.main()
