from __future__ import annotations

# Keep this module in the ED4 workflow so incident-register autofeed commits are
# followed by an ordinary branch commit that retriggers the required checks.
from contextlib import ExitStack
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from jobs.tools import ed4_c0c_failure_readout_stage as stage
from jobs.tools.ed4_c0c_failure_readout_stage import (
    SOURCE_CODE,
    bounded_text_tail,
    summarize_receipt,
)

ROOT = Path(__file__).resolve().parents[2]
STAGE = ROOT / "jobs/tools/ed4_c0c_failure_readout_stage.py"


class RunnerDiagnosticFixture:
    """Synthetic remote; only transport is mocked, authentication is real."""
    def __init__(self):
        self.manifest = {
            "job_id": stage.SOURCE_JOB, "attempt_id": stage.SOURCE_ATTEMPT,
            "code_sha": stage.SOURCE_CODE, "state": "failed", "exit_code": 2,
            "host": "cpx62",
        }
        self.payloads = {
            "stage-receipt.json": json.dumps({
                "schema": "jass.stage_receipt.v1", "state": "failed",
                "code_sha": stage.SOURCE_CODE, "exit_code": 1,
                "failure_stage": "EXECUTE", "inputs_authenticated": True,
                "outputs_authenticated": False,
            }).encode(),
            "stage.stdout.log": b"",
            "stage.stderr.log": b"ModuleNotFoundError: No module named 'jobs'\n",
            "artefacts/confirmation-targets.jnnw": b"DO-NOT-READ",
        }
        self.copied = []
        self.cat_paths = []
        self.rebuild()

    def rebuild(self):
        self.objects = dict(self.payloads)
        self.objects["manifest.json"] = json.dumps(self.manifest, sort_keys=True).encode()
        files = [{"path": path, "size_bytes": len(raw),
                  "sha256": hashlib.sha256(raw).hexdigest()}
                 for path, raw in sorted(self.objects.items())]
        self.objects["inventory.json"] = json.dumps({"files": files}, sort_keys=True).encode()
        self.objects["checksums.sha256"] = "".join(
            hashlib.sha256(raw).hexdigest() + "  " + path + "\n"
            for path, raw in sorted(self.objects.items())
        ).encode()
        self.objects["_FAILED"] = b"failed\n"

    def relative(self, remote):
        prefix = stage.SOURCE_PREFIX + "/"
        if not remote.startswith(prefix):
            raise AssertionError("unexpected source prefix")
        return remote[len(prefix):]

    def cat(self, argv):
        if argv[:2] != ["rclone", "cat"]:
            raise AssertionError("unexpected metadata transport")
        path = self.relative(argv[2])
        self.cat_paths.append(path)
        return self.objects[path]

    def copy(self, argv, **kwargs):
        if argv[:2] != ["rclone", "copyto"]:
            raise AssertionError("unexpected payload transport")
        path = self.relative(argv[2])
        if path not in stage.DIAGNOSTIC_PATHS:
            raise AssertionError("forbidden payload read")
        self.copied.append(path)
        if path not in self.objects:
            return subprocess.CompletedProcess(argv, 1, b"", b"not found")
        Path(argv[3]).write_bytes(self.objects[path])
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    def transport(self):
        stack = ExitStack()
        stack.enter_context(mock.patch.object(stage.fetch_result_files.base, "run_capture", self.cat))
        stack.enter_context(mock.patch.object(stage.fetch_result_files.base.subprocess, "run", self.copy))
        return stack


class C0CFailureReadoutTests(unittest.TestCase):
    def test_receipt_summary_preserves_only_technical_failure_fields(self):
        value = {
            "schema": "jass.stage_receipt.v1",
            "state": "failed",
            "failure_class": "STAGE_EXIT_CODE",
            "failure_stage": "EXECUTE",
            "error": "stage exit 2, expected 0",
            "exit_code": 2,
            "timed_out": False,
            "duration_seconds": 12.5,
            "inputs_authenticated": True,
            "outputs_authenticated": False,
            "stage": "ed4-c0c-exclusion-union-v1",
            "code_sha": SOURCE_CODE,
            "inputs": [{"should_not": "leak"}],
        }
        summary = summarize_receipt(value)
        self.assertEqual(summary["failure_stage"], "EXECUTE")
        self.assertEqual(summary["error"], "stage exit 2, expected 0")
        self.assertNotIn("inputs", summary)

    def test_receipt_summary_rejects_wrong_code(self):
        value = {
            "schema": "jass.stage_receipt.v1",
            "state": "failed",
            "code_sha": "0" * 40,
        }
        with self.assertRaisesRegex(RuntimeError, "stage_receipt_code_identity"):
            summarize_receipt(value)

    def test_tail_is_bounded_and_decodes_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.log"
            path.write_bytes(b"prefix-" + b"a" * 50 + b"\xfftail")
            text = bounded_text_tail(path, 8)
            self.assertLessEqual(len(text.encode("utf-8")), 12)
            self.assertTrue(text.endswith("tail"))

    def test_direct_stage_entrypoint_bootstraps_repo_imports_without_pythonpath(self):
        env = {"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run(
            [sys.executable, str(STAGE)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        # No runner-owned environment is supplied here on purpose.  Reaching the
        # expected JASS_ARTEFACT_DIR lookup proves that direct-path startup got
        # past the jobs.tools imports under the same no-PYTHONPATH condition as
        # run_experiment_stage.
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("ModuleNotFoundError", completed.stderr)
        self.assertIn("JASS_ARTEFACT_DIR", completed.stderr)

    def test_empty_stdout_reproduces_generic_rejection_but_diagnostic_verifies_it(self):
        remote = RunnerDiagnosticFixture()
        with tempfile.TemporaryDirectory() as td, remote.transport():
            with self.assertRaisesRegex(RuntimeError, "missing/empty result file: stage.stdout.log"):
                stage.fetch_result_files.fetch_files(
                    rclone="rclone", prefix=stage.SOURCE_PREFIX, expected_state="failed",
                    selections=[(name, name) for name in stage.DIAGNOSTIC_PATHS],
                    out_dir=Path(td) / "generic",
                )
            remote.copied.clear()
            report = stage.fetch_runner_diagnostics(Path(td) / "diagnostic")
            self.assertEqual(remote.copied, list(stage.DIAGNOSTIC_PATHS))
            self.assertEqual([item["path"] for item in report["files"]], list(stage.DIAGNOSTIC_PATHS))
            self.assertEqual((Path(td) / "diagnostic/stage.stdout.log").read_bytes(), b"")
            self.assertEqual(report["files"][1]["sha256"], hashlib.sha256(b"").hexdigest())
            self.assertEqual(set(remote.cat_paths), {"_FAILED", "manifest.json", "inventory.json", "checksums.sha256"})

    def test_both_empty_logs_are_downloaded_and_verified(self):
        remote = RunnerDiagnosticFixture()
        remote.payloads["stage.stderr.log"] = b""
        remote.rebuild()
        with tempfile.TemporaryDirectory() as td, remote.transport():
            stage.fetch_runner_diagnostics(Path(td))
            self.assertEqual(remote.copied, list(stage.DIAGNOSTIC_PATHS))
            self.assertEqual((Path(td) / "stage.stderr.log").read_bytes(), b"")

    def test_missing_required_file_is_not_treated_as_empty(self):
        for name in stage.DIAGNOSTIC_PATHS:
            with self.subTest(name=name):
                remote = RunnerDiagnosticFixture()
                del remote.payloads[name]
                remote.rebuild()
                with tempfile.TemporaryDirectory() as td, remote.transport():
                    with self.assertRaisesRegex(RuntimeError, "missing/invalid runner diagnostic"):
                        stage.fetch_runner_diagnostics(Path(td))
                    self.assertEqual(remote.copied, [])

    def test_empty_receipt_remains_forbidden(self):
        remote = RunnerDiagnosticFixture()
        remote.payloads["stage-receipt.json"] = b""
        remote.rebuild()
        with tempfile.TemporaryDirectory() as td, remote.transport():
            with self.assertRaisesRegex(RuntimeError, "empty runner stage receipt"):
                stage.fetch_runner_diagnostics(Path(td))
            self.assertEqual(remote.copied, [])

    def test_empty_log_cannot_be_synthesized_if_remote_object_is_missing(self):
        remote = RunnerDiagnosticFixture()
        del remote.objects["stage.stdout.log"]
        with tempfile.TemporaryDirectory() as td, remote.transport():
            with self.assertRaisesRegex(RuntimeError, "download failed"):
                stage.fetch_runner_diagnostics(Path(td))
            self.assertFalse((Path(td) / "stage.stdout.log").exists())

    def test_changed_empty_log_bytes_fail_size_and_digest_verification(self):
        remote = RunnerDiagnosticFixture()
        remote.objects["stage.stdout.log"] = b"tampered"
        with tempfile.TemporaryDirectory() as td, remote.transport():
            with self.assertRaisesRegex(RuntimeError, "download verification failed"):
                stage.fetch_runner_diagnostics(Path(td))
            self.assertFalse((Path(td) / "stage.stdout.log").exists())

    def test_inconsistent_inventory_digest_aborts_before_downloads(self):
        remote = RunnerDiagnosticFixture()
        remote.objects["inventory.json"] += b" "
        with tempfile.TemporaryDirectory() as td, remote.transport():
            with self.assertRaisesRegex(RuntimeError, "inventory.json digest differs"):
                stage.fetch_runner_diagnostics(Path(td))
            self.assertEqual(remote.copied, [])

    def test_wrong_source_code_aborts_before_payload_downloads(self):
        remote = RunnerDiagnosticFixture()
        remote.manifest["code_sha"] = "0" * 40
        remote.rebuild()
        with tempfile.TemporaryDirectory() as td, remote.transport():
            with self.assertRaisesRegex(RuntimeError, "failed_attempt_identity"):
                stage.fetch_runner_diagnostics(Path(td))
            self.assertEqual(remote.copied, [])

    def test_generic_empty_scientific_payload_policy_is_unchanged(self):
        remote = RunnerDiagnosticFixture()
        remote.payloads["artefacts/confirmation-targets.jnnw"] = b""
        remote.rebuild()
        with tempfile.TemporaryDirectory() as td, remote.transport():
            with self.assertRaisesRegex(RuntimeError, "missing/empty result file"):
                stage.fetch_result_files.fetch_files(
                    rclone="rclone", prefix=stage.SOURCE_PREFIX, expected_state="failed",
                    selections=[("artefacts/confirmation-targets.jnnw", "forbidden")],
                    out_dir=Path(td),
                )
            self.assertEqual(remote.copied, [])

    def test_full_synthetic_readout_preserves_zero_scientific_effects(self):
        remote = RunnerDiagnosticFixture()
        with tempfile.TemporaryDirectory() as td, remote.transport():
            artifact = Path(td) / "artifact"
            with mock.patch.dict(os.environ, {
                "JASS_ARTEFACT_DIR": str(artifact), "JASS_RESULT_DIR": str(Path(td) / "result"),
                "LAUNCH_MODE": "rehearsal",
            }):
                self.assertEqual(stage.main(), 0)
            summary = json.loads((artifact / "scientific-summary.json").read_text())
            self.assertEqual(summary["source_attempt_id"], stage.SOURCE_ATTEMPT)
            self.assertEqual(summary["stdout_size_bytes"], 0)
            self.assertFalse(summary["confirmation_authorized"])
            self.assertFalse(summary["automatic_continuation"])
            self.assertIsNone(summary["scientific_verdict"])
            for key in ("scientific_payload_reads", "target_reads", "score_reads", "wdl_reads",
                        "qvalue_reads", "model_reads", "teacher_calls", "search_calls", "fits",
                        "games", "alpha_spent"):
                self.assertEqual(summary[key], 0, key)
            evidence = json.loads((artifact / "execution-evidence.json").read_text())
            self.assertEqual(evidence["state"], "completed")
            self.assertEqual(evidence["completed_phases"], stage.PHASES)
            self.assertTrue(all(value == 0 for value in evidence["actual_side_effects"].values()))
            self.assertEqual(remote.copied, list(stage.DIAGNOSTIC_PATHS))


if __name__ == "__main__":
    unittest.main()
