from __future__ import annotations

import inspect
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_l_2025_failure_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]


class CLSL2025FailureDiagnosticTests(unittest.TestCase):
    def test_failed_source_identity_is_immutable(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2025-l3-cls-l-source-normalization-preflight-v3")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260917T072337Z-16e199f6")
        self.assertEqual(diag.FAILED_CODE, "16e199f661d266146154507c4d835883039e2488")
        self.assertEqual(diag.TERMINAL, "CLS_L_2025_TECHNICAL_DIAGNOSTIC_COMPLETE_V1")
        self.assertEqual(diag.PHASE, "execute-cls-l-2025-failure-diagnostic")

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
        self.assertEqual(got["last_abort"], "ABORT line=71 rc=2 cmd=python3 jobs/tools/fetch_result_files.py --prefix x")
        self.assertTrue(any("Traceback" in line for line in got["error_lines"]))

    def test_work_log_selection_is_allowlisted_small_and_never_scientific_payload(self):
        verified = {
            "files": [
                {"path": "work/fetch-abc.log", "size_bytes": 321, "sha256": "a" * 64},
                {"path": "work/features.log", "size_bytes": diag.WORK_LOG_MAX_BYTES + 1, "sha256": "b" * 64},
                {"path": "work/current.jnnw", "size_bytes": 999, "sha256": "c" * 64},
                {"path": "work/current-context30.npy", "size_bytes": 999, "sha256": "d" * 64},
            ]
        }
        got = diag.bounded_work_log_selections(verified)
        self.assertEqual(got, [("work/fetch-abc.log", "worklogs/fetch-abc.log")])
        selected = {remote for remote, _ in got}
        self.assertNotIn("work/current.jnnw", selected)
        self.assertNotIn("work/current-context30.npy", selected)
        self.assertNotIn("work/features.log", selected)

    def test_work_log_summary_surfaces_inner_mechanical_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "worklogs" / "normalization.log"
            path.parent.mkdir(parents=True)
            path.write_text("start\nABORT: normalization helper missing\n", encoding="utf-8")
            got = diag.summarize_work_logs(root, [("work/normalization.log", "worklogs/normalization.log")])
        self.assertIn("ABORT: normalization helper missing", got["last_abort"])
        self.assertIn("ABORT: normalization helper missing", got["primary_mechanical_error"])

    def test_diagnostic_has_zero_scientific_actions(self):
        code = inspect.getsource(diag)
        self.assertNotIn("train_stream.py --", code)
        self.assertNotIn("jass_vs_jass", code)
        self.assertNotIn("--dump-eval-features", code)
        self.assertIn('("output.log.gz", "output.log.gz")', code)
        self.assertIn("WORK_LOG_ALLOWLIST", code)
        self.assertIn('"historical_training_payloads_read": 0', code)
        self.assertIn('"confirmation_target_reads": 0', code)
        self.assertIn('"strength_games": 0', code)
        self.assertIn('"promotions": 0', code)
        self.assertIn('"bakes": 0', code)

    def test_profile_is_zero_effect_launch_v2(self):
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-l-2025-failure-diagnostic-v1.json").read_text())
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(profile["command"], ["/usr/bin/python3", "jobs/tools/cls_l_2025_failure_diagnostic.py"])
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(value == 0 for value in profile["rehearsal_max_effects"].values()))
        code = inspect.getsource(diag)
        self.assertIn("StageEvidence(art, mode)", code)
        self.assertIn("evidence.begin(PHASE)", code)
        self.assertIn("evidence.complete()", code)
        self.assertIn("evidence.finish()", code)


if __name__ == "__main__":
    unittest.main()
