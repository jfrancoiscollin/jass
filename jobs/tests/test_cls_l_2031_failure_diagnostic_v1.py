from __future__ import annotations

import inspect
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_l_2031_failure_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]


class CLSL2031FailureDiagnosticTests(unittest.TestCase):
    def test_failed_source_identity_is_immutable(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2031-l3-cls-l-source-normalization-preflight-v6")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260917T131839Z-1088c921")
        self.assertEqual(diag.FAILED_CODE, "1088c921c93fd35f71276e57fd40b1abb22eb5e4")
        self.assertEqual(diag.TERMINAL, "CLS_L_2031_TECHNICAL_DIAGNOSTIC_COMPLETE_V1")
        self.assertEqual(diag.PHASE, "execute-cls-l-2031-failure-diagnostic")

    def test_parser_and_worklogs_are_bounded(self):
        got = diag.bounded_lines("start\nABORT: helper failed\nend", 2)
        self.assertEqual(got["last_abort"], "ABORT: helper failed")
        self.assertEqual(got["tail"], ["ABORT: helper failed", "end"])
        verified = {"files": [
            {"path": "work/normalization.log", "size_bytes": 42},
            {"path": "work/current.jnnw", "size_bytes": 42},
            {"path": "work/features.log", "size_bytes": diag.WORK_LOG_MAX_BYTES + 1},
        ]}
        self.assertEqual(diag.work_log_selections(verified), [("work/normalization.log", "worklogs/normalization.log")])

    def test_work_log_summary_surfaces_inner_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / "worklogs" / "normalization.log"
            p.parent.mkdir(parents=True)
            p.write_text("x\nABORT: exact mechanical cause\n", encoding="utf-8")
            got = diag.summarize_work_logs(root, [("work/normalization.log", "worklogs/normalization.log")])
        self.assertIn("exact mechanical cause", got["primary_mechanical_error"])

    def test_zero_scientific_actions_and_launch_profile(self):
        code = inspect.getsource(diag)
        self.assertNotIn("train_stream.py --", code)
        self.assertNotIn("jass_vs_jass", code)
        self.assertNotIn("--dump-eval-features", code)
        self.assertIn('"historical_training_payloads_read": 0', code)
        self.assertIn('"confirmation_target_reads": 0', code)
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-l-2031-failure-diagnostic-v1.json").read_text())
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(profile["command"], ["/usr/bin/python3", "jobs/tools/cls_l_2031_failure_diagnostic.py"])
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))
        self.assertIn("StageEvidence(art, mode)", code)


if __name__ == "__main__":
    unittest.main()
