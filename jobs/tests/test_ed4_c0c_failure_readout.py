from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from jobs.tools.ed4_c0c_failure_readout_stage import (
    SOURCE_CODE,
    bounded_text_tail,
    summarize_receipt,
)


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


if __name__ == "__main__":
    unittest.main()
