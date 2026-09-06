from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b3_post_parity_audit_v2 as subject


class B3PostParityAuditV2Tests(unittest.TestCase):
    def test_indented_generic_fetch_report_is_accepted_semantically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fetch.json"
            value = {"state": "verified", "result_state": "completed", "nested": {"x": 1}}
            path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self.assertEqual(subject.read_semantic_fetch_report(path), value)

    def test_duplicate_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fetch.json"
            path.write_text('{"state":"verified","state":"wrong"}\n', encoding="utf-8")
            with self.assertRaises(subject.SemanticFetchReportError):
                subject.read_semantic_fetch_report(path)


if __name__ == "__main__":
    unittest.main()
