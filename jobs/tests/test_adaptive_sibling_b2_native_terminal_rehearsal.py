from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tests.test_adaptive_sibling_b2_readout import terminal_pipeline_fixture
from jobs.tools import adaptive_sibling_b2_readout as readout
from jobs.tools import adaptive_sibling_b2_statistics as statistics
from jobs.tools import adaptive_sibling_b2_terminal_publish as publisher


class NativeTerminalRehearsalTests(unittest.TestCase):
    def test_native_4000_pipeline_reaches_terminal_publisher(self) -> None:
        """Exercise the real serialized B2 chain with bounded synthetic statistics.

        The native fixture + production verifier drive teacher merge semantics;
        allocation/projection/readout/terminal authentication are real. Only the
        expensive 200k bootstrap analyzer is replaced by a one-call deterministic
        bounded analyzer. The terminal publisher itself is production code.
        """
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (terminal_path, terminal_raw, terminal_manifest, runtime,
             _readout_manifest_path, _readout_manifest, merge_report) = \
                terminal_pipeline_fixture(base)

            self.assertEqual(merge_report["counters"]["parents"], 4_000)
            self.assertEqual(merge_report["counters"]["shards"], 16)
            self.assertGreaterEqual(merge_report["counters"]["groups_rows"], 8_000)

            analysis = {
                "status": "VALID",
                "scientific_gates_evaluated": True,
                "gates": {"all_passed": False},
            }
            analyzer_calls: list[int] = []

            def bounded_analyzer(rows, *, progress_callback=None):
                analyzer_calls.append(len(rows))
                if progress_callback:
                    progress_callback({
                        "completed_replications": 1,
                        "total_replications": 1,
                    })
                return analysis

            terminal_dir = base / "terminal"
            with mock.patch.object(
                    statistics, "runtime_environment",
                    return_value={**runtime, "pid": os.getpid()}), \
                    mock.patch.object(
                        statistics, "analyze_parent_stats",
                        side_effect=bounded_analyzer):
                readout.finalize_command(argparse.Namespace(
                    input_manifest=terminal_path,
                    expected_input_manifest_sha256=hashlib.sha256(terminal_raw).hexdigest(),
                    out_dir=terminal_dir,
                ))

            self.assertEqual(analyzer_calls, [4_000])
            report = json.loads(
                (terminal_dir / "b2-terminal-report-v1.json").read_text(encoding="ascii"))
            self.assertTrue(report["support"]["all_valid"], report)
            self.assertEqual(
                report["verdict"],
                "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1",
            )
            self.assertEqual(report["actions"], {
                "searches": 0,
                "fits": 0,
                "games": 0,
                "promotions": 0,
                "bakes": 0,
                "automatic_downstream_jobs": 0,
            })

            artifacts = base / "terminal-artifacts"
            publication = publisher.publish(
                input_manifest=terminal_path,
                expected_input_manifest_sha256=hashlib.sha256(terminal_raw).hexdigest(),
                terminal_dir=terminal_dir,
                code_sha=terminal_manifest["code_sha"],
                artifact_dir=artifacts,
            )
            self.assertEqual(
                publication["verdict"],
                "B2_ADAPTIVE_SHADOW_POLICY_NOT_CONFIRMED_V1",
            )
            self.assertTrue(publication["byte_roundtrip_verified"])
            self.assertEqual(publication["automatic_downstream_jobs"], 0)
            self.assertFalse(publication["promotion_authorized"])
            self.assertFalse(publication["bake_authorized"])
            self.assertTrue((artifacts / "terminal-publication-receipt.json").is_file())


if __name__ == "__main__":
    unittest.main()
