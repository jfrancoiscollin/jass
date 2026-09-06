from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from jobs.tools import adaptive_sibling_b3_teacher_source as subject

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "src/deep_sibling_teacher.cpp"
TOOL = ROOT / "jobs/tools/adaptive_sibling_b3_teacher_source.py"


class B3TeacherSourceTests(unittest.TestCase):
    def test_render_carries_confirmed_policy_and_removes_full_ladder(self):
        rendered = subject.render(BASE.read_text(encoding="utf-8"))
        self.assertIn("B3_M5_CP = 100", rendered)
        self.assertIn("B3_M50_CP = 60", rendered)
        self.assertIn("B3_MIN_SURVIVORS = 2", rendered)
        self.assertIn("jass.adaptive_sibling_b3_teacher_extract.v1", rendered)
        self.assertIn("searched5", rendered)
        self.assertIn("searched50", rendered)
        self.assertIn("searched200", rendered)
        self.assertIn("survived5", rendered)
        self.assertIn("survived50", rendered)
        self.assertIn("selected", rendered)
        self.assertIn("SOLE_UNRESOLVED_BEFORE_Q200", rendered)
        self.assertEqual(rendered.count("= run_fresh_search("), 3)
        self.assertNotIn("const SearchObs s5 = run_fresh_search", rendered)
        self.assertNotIn("const SearchObs s50 = run_fresh_search", rendered)
        self.assertNotIn("const SearchObs s200 = run_fresh_search", rendered)

    def test_q200_search_is_structurally_after_s50_seal(self):
        rendered = subject.render(BASE.read_text(encoding="utf-8"))
        seal = rendered.index("const auto s50 = top_with_margin")
        q200 = rendered.index("action.s200 = run_fresh_search", seal)
        self.assertLess(seal, q200)
        self.assertIn("for (std::size_t index : s50)", rendered[seal:q200 + 200])

    def test_direct_cli_render_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "b3.cpp"
            receipt = Path(tmp) / "receipt.json"
            completed = subprocess.run(
                [sys.executable, str(TOOL), "render", "--source", str(BASE),
                 "--output", str(output), "--receipt", str(receipt)],
                cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output.is_file())
            value = json.loads(receipt.read_text(encoding="ascii"))
            self.assertEqual(value["schema"], subject.SCHEMA)
            self.assertEqual(value["policy"], {"M5": 100, "M50": 60, "minimum_survivors": 2})
            self.assertEqual(value["budgets_nodes"], [5000, 50000, 200000])
            self.assertTrue(value["fresh_engine_each_search"])
            self.assertFalse(value["q200_used_before_s50_seal"])
            self.assertFalse(value["search_decision_trace_affects_allocation"])

    def test_existing_output_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "b3.cpp"
            receipt = Path(tmp) / "receipt.json"
            output.write_text("occupied", encoding="utf-8")
            with self.assertRaises(ValueError):
                subject.render_file(BASE, output, receipt)


if __name__ == "__main__":
    unittest.main()
