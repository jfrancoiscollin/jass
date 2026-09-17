from __future__ import annotations

import inspect
import json
from pathlib import Path
import unittest

from jobs.tools import cls_l_2020_failure_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]


class CLSL2020FailureDiagnosticTests(unittest.TestCase):
    def test_failed_source_identity_is_immutable(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2020-l3-cls-l-source-normalization-preflight-v2")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260917T023839Z-68301b10")
        self.assertEqual(diag.FAILED_CODE, "68301b1027ef37e3c829eccadd42f4ba9cb86ce9")
        self.assertEqual(diag.TERMINAL, "CLS_L_2020_TECHNICAL_DIAGNOSTIC_COMPLETE_V1")
        self.assertEqual(diag.PHASE, "execute-cls-l-2020-failure-diagnostic")

    def test_bounded_parser_keeps_last_abort_and_tail(self):
        text = "\n".join([
            "start",
            "noise",
            "ABORT line=71 rc=2 cmd=python3 jobs/tools/fetch_result_files.py --prefix x",
            "Traceback: example",
            "end",
        ])
        got = diag.bounded_lines(text, limit=3)
        self.assertEqual(got["line_count"], 5)
        self.assertEqual(got["tail"], [
            "ABORT line=71 rc=2 cmd=python3 jobs/tools/fetch_result_files.py --prefix x",
            "Traceback: example",
            "end",
        ])
        self.assertEqual(
            got["last_abort"],
            "ABORT line=71 rc=2 cmd=python3 jobs/tools/fetch_result_files.py --prefix x",
        )
        self.assertTrue(any("Traceback" in line for line in got["error_lines"]))

    def test_bounded_parser_surfaces_explicit_die_abort(self):
        text = "\n".join([
            "# CLS-L source / normalization preflight",
            "ABORT: numeric venv missing",
        ])
        got = diag.bounded_lines(text)
        self.assertEqual(got["last_abort"], "ABORT: numeric venv missing")
        self.assertIn("ABORT: numeric venv missing", got["error_lines"])

    def test_diagnostic_code_has_zero_scientific_actions_and_surfaces_bounded_context(self):
        code = inspect.getsource(diag)
        self.assertNotIn("train_stream.py --", code)
        self.assertNotIn("jass_vs_jass", code)
        self.assertNotIn("--dump-eval-features", code)
        self.assertIn('("output.log.gz", "output.log.gz")', code)
        self.assertIn('"bounded_error_lines": parsed["error_lines"][-12:]', code)
        self.assertIn('"bounded_tail": parsed["tail"][-12:]', code)
        self.assertIn('"confirmation_target_reads": 0', code)
        self.assertIn('"strength_games": 0', code)
        self.assertIn('"promotions": 0', code)
        self.assertIn('"bakes": 0', code)

    def test_stage_emits_launch_v2_execution_evidence_required_by_control_spec(self):
        code = inspect.getsource(diag)
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-l-2020-failure-diagnostic-v1.json").read_text())
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(
            profile["evidence_outputs"],
            ["failure-evidence.json", "source-authentication.json", "manifest.json", "RESULTS.md", "scientific-summary.json"],
        )
        self.assertIn("StageEvidence(art, mode)", code)
        self.assertIn("evidence.begin(PHASE)", code)
        self.assertIn("evidence.complete()", code)
        self.assertIn("evidence.finish()", code)
        self.assertNotIn("execution-evidence.json", profile["evidence_outputs"])


if __name__ == "__main__":
    unittest.main()
