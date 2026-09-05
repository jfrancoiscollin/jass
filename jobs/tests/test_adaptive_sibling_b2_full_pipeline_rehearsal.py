from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from jobs.tools import adaptive_sibling_b2_full_pipeline_rehearsal as rehearsal


class FullPipelineRehearsalContractTests(unittest.TestCase):
    def test_failure_receipt_never_claims_b3_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            receipt = base / "receipt.json"
            log = base / "log.txt"
            with mock.patch.object(
                rehearsal,
                "run_full",
                side_effect=rehearsal.FullRehearsalError("synthetic failure"),
            ):
                rc = rehearsal.main([
                    "--work-dir", str(base / "work"),
                    "--receipt", str(receipt),
                    "--log", str(log),
                ])
            self.assertEqual(rc, 4)
            value = json.loads(receipt.read_text(encoding="ascii"))
            self.assertEqual(value["verdict"], "FULL_PIPELINE_REHEARSAL_FAIL")
            self.assertFalse(value["full_pipeline_rehearsal_pass"])
            self.assertEqual(value["b3_infrastructure_gate"], "BLOCKED")
            self.assertEqual(value["scientific_scope"], {
                "fresh_data_reads": 0,
                "teacher_searches": 0,
                "fits": 0,
                "strength_games": 0,
                "promotions": 0,
                "bakes": 0,
                "scientific_verdict": None,
            })

    def test_success_receipt_requires_run_full_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            receipt = base / "receipt.json"
            log = base / "log.txt"
            outcome = {
                "actual_runtime": {"nproc": 16},
                "native_build": {"ok": True},
                "population": {"parents": 4000, "shards": 16, "teacher_rows": 8000},
                "statistics": {
                    "replications": 200000, "seed": 2026110717,
                    "accepted_draws": 800000000, "status": "VALID"},
                "terminal": {"support_all_valid": True},
                "publication": {"byte_roundtrip_verified": True},
            }
            with mock.patch.object(rehearsal, "run_full", return_value=outcome):
                rc = rehearsal.main([
                    "--work-dir", str(base / "work"),
                    "--receipt", str(receipt),
                    "--log", str(log),
                ])
            self.assertEqual(rc, 0)
            value = json.loads(receipt.read_text(encoding="ascii"))
            self.assertEqual(value["verdict"], "FULL_PIPELINE_REHEARSAL_PASS")
            self.assertTrue(value["full_pipeline_rehearsal_pass"])
            self.assertEqual(value["b3_infrastructure_gate"], "READY")


if __name__ == "__main__":
    unittest.main()
