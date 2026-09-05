#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b2_readout as readout
from jobs.tools import adaptive_sibling_b2_terminal_publish as publisher


class TerminalInvalidUnknownPublishTests(unittest.TestCase):
    def test_invalid_unknown_statistics_remain_support_not_established(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = root / "terminal-input.json"
            manifest.write_bytes(publisher.canonical_json_bytes({"schema": "fixture"}))
            terminal = root / "terminal"
            terminal.mkdir()
            stats = terminal / "b2-statistics-v1.json"
            progress = terminal / "progress.json"
            stats.write_bytes(publisher.canonical_json_bytes(
                {"status": "INVALID_UNKNOWN", "scientific_gates_evaluated": False}))
            progress.write_bytes(publisher.canonical_json_bytes(
                {"completed_replications": 0, "total_replications": 200_000}))
            support_flags = {
                "authentication_valid": True, "selection_valid": True,
                "teacher_valid": True, "observations_valid": True,
                "projection_invariance_valid": True, "rich_ledger_valid": True,
                "sufficient_projection_valid": True,
                "statistics_support_valid": True, "all_valid": True,
            }
            report = {
                "schema": readout.TERMINAL_SCHEMA, "code_sha": "c" * 40,
                "input_manifest_sha256": publisher.sha256_file(manifest),
                "outputs": {"statistics": publisher.descriptor(stats),
                            "progress": publisher.descriptor(progress)},
                "support": support_flags,
                "statistics": {"status": "INVALID_UNKNOWN",
                               "scientific_gates_evaluated": False,
                               "all_gates_passed": None},
                "actions": {"searches": 0, "fits": 0, "games": 0,
                            "promotions": 0, "bakes": 0,
                            "automatic_downstream_jobs": 0},
                "verdict": "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1",
            }
            (terminal / "b2-terminal-report-v1.json").write_bytes(
                publisher.canonical_json_bytes(report))
            publication = publisher.publish(
                input_manifest=manifest,
                expected_input_manifest_sha256=publisher.sha256_file(manifest),
                terminal_dir=terminal, code_sha="c" * 40,
                artifact_dir=root / "artifacts")
            self.assertEqual(publication["verdict"],
                             "B2_ADAPTIVE_SHADOW_SUPPORT_NOT_ESTABLISHED_V1")
            self.assertIsNotNone(publication["artifacts"]["statistics"])


if __name__ == "__main__":
    unittest.main()
