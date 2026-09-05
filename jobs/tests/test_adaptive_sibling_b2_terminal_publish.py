#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b2_readout as readout
from jobs.tools import adaptive_sibling_b2_terminal_publish as publisher


CODE_SHA = "b" * 40


class TerminalPublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.input_manifest = self.root / "terminal-input-manifest.json"
        self.input_manifest.write_bytes(publisher.canonical_json_bytes({"schema": "fixture"}))
        self.terminal = self.root / "terminal"
        self.terminal.mkdir()
        self.artifacts = self.root / "artifacts"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _support(self, all_valid: bool) -> dict[str, bool]:
        keys = ["authentication_valid", "selection_valid", "teacher_valid",
                "observations_valid", "projection_invariance_valid",
                "rich_ledger_valid", "sufficient_projection_valid",
                "statistics_support_valid"]
        return {**{key: all_valid for key in keys}, "all_valid": all_valid}

    def _write_support_terminal(self) -> None:
        report = {
            "schema": readout.TERMINAL_SCHEMA, "code_sha": CODE_SHA,
            "input_manifest_sha256": publisher.sha256_file(self.input_manifest),
            "outputs": {"statistics": None, "progress": None},
            "support": self._support(False),
            "statistics": {"status": None, "scientific_gates_evaluated": False,
                           "all_gates_passed": None},
            "actions": {"searches": 0, "fits": 0, "games": 0, "promotions": 0,
                        "bakes": 0, "automatic_downstream_jobs": 0},
            "verdict": "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1",
        }
        (self.terminal / "b2-terminal-report-v1.json").write_bytes(
            publisher.canonical_json_bytes(report))

    def _write_evaluated_terminal(self, *, passed: bool) -> None:
        stats = self.terminal / "b2-statistics-v1.json"
        progress = self.terminal / "progress.json"
        stats.write_bytes(publisher.canonical_json_bytes({"status": "VALID", "fixture": True}))
        progress.write_bytes(publisher.canonical_json_bytes(
            {"completed_replications": 200_000, "total_replications": 200_000}))
        report = {
            "schema": readout.TERMINAL_SCHEMA, "code_sha": CODE_SHA,
            "input_manifest_sha256": publisher.sha256_file(self.input_manifest),
            "outputs": {"statistics": publisher.descriptor(stats),
                        "progress": publisher.descriptor(progress)},
            "support": self._support(True),
            "statistics": {"status": "VALID", "scientific_gates_evaluated": True,
                           "all_gates_passed": passed},
            "actions": {"searches": 0, "fits": 0, "games": 0, "promotions": 0,
                        "bakes": 0, "automatic_downstream_jobs": 0},
            "verdict": ("B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1" if passed
                        else "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1"),
        }
        (self.terminal / "b2-terminal-report-v1.json").write_bytes(
            publisher.canonical_json_bytes(report))

    def _publish(self) -> dict[str, object]:
        return publisher.publish(
            input_manifest=self.input_manifest,
            expected_input_manifest_sha256=publisher.sha256_file(self.input_manifest),
            terminal_dir=self.terminal, code_sha=CODE_SHA,
            artifact_dir=self.artifacts)

    def test_support_terminal_publishes_without_statistics_payload(self) -> None:
        self._write_support_terminal()
        receipt = self._publish()
        self.assertEqual(receipt["verdict"],
                         "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1")
        self.assertIsNone(receipt["artifacts"]["statistics"])
        self.assertIsNone(receipt["artifacts"]["progress"])
        self.assertFalse(receipt["promotion_authorized"])
        self.assertFalse(receipt["bake_authorized"])
        self.assertEqual(receipt["automatic_downstream_jobs"], 0)

    def test_confirmed_terminal_requires_and_copies_statistics_payloads(self) -> None:
        self._write_evaluated_terminal(passed=True)
        receipt = self._publish()
        self.assertEqual(receipt["verdict"], "B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1")
        self.assertIsNotNone(receipt["artifacts"]["statistics"])
        self.assertIsNotNone(receipt["artifacts"]["progress"])
        self.assertEqual((self.artifacts / "b2-statistics-v1.json").read_bytes(),
                         (self.terminal / "b2-statistics-v1.json").read_bytes())

    def test_gate_result_and_verdict_mismatch_is_rejected(self) -> None:
        self._write_evaluated_terminal(passed=False)
        path = self.terminal / "b2-terminal-report-v1.json"
        report = __import__("json").loads(path.read_text())
        report["verdict"] = "B2_ADAPTIVE_SHADOW_POLICY_CONFIRMED_V1"
        path.write_bytes(publisher.canonical_json_bytes(report))
        with self.assertRaises(publisher.PublishError):
            self._publish()
        self.assertFalse(self.artifacts.exists())

    def test_nonzero_downstream_action_is_rejected(self) -> None:
        self._write_support_terminal()
        path = self.terminal / "b2-terminal-report-v1.json"
        report = __import__("json").loads(path.read_text())
        report["actions"]["automatic_downstream_jobs"] = 1
        path.write_bytes(publisher.canonical_json_bytes(report))
        with self.assertRaises(publisher.PublishError):
            self._publish()
        self.assertFalse(self.artifacts.exists())


if __name__ == "__main__":
    unittest.main()
