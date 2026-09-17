from __future__ import annotations

import inspect
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_l_2031_stage_log_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]


class CLSL2031StageLogDiagnosticTests(unittest.TestCase):
    def test_failed_source_identity_and_terminal_are_frozen(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2031-l3-cls-l-source-normalization-preflight-v6")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260917T131839Z-1088c921")
        self.assertEqual(diag.FAILED_CODE, "1088c921c93fd35f71276e57fd40b1abb22eb5e4")
        self.assertEqual(diag.TERMINAL, "CLS_L_2031_STAGE_LOG_DIAGNOSTIC_COMPLETE_V1")
        self.assertEqual(diag.PHASE, "execute-cls-l-2031-stage-log-diagnostic")

    def test_only_runner_owned_stage_logs_are_selected_and_bounded(self):
        verified = {"files": [
            {"path": "stage.stderr.log", "size_bytes": 200},
            {"path": "stage.stdout.log", "size_bytes": 0},
            {"path": "stage-receipt.json", "size_bytes": 500},
            {"path": "work/normalization.log", "size_bytes": 50},
            {"path": "stage.huge.log", "size_bytes": diag.MAX_BYTES + 1},
        ]}
        self.assertEqual(
            diag.stage_log_selections(verified),
            [
                ("stage.stderr.log", "stage-logs/stage.stderr.log"),
                ("stage-receipt.json", "stage-logs/stage-receipt.json"),
            ],
        )

    def test_stage_stderr_surfaces_exact_mechanical_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "stage-logs" / "stage.stderr.log"
            path.parent.mkdir(parents=True)
            path.write_text(
                "Traceback (most recent call last):\n"
                "subprocess.CalledProcessError: Command failed with exit status 1\n",
                encoding="utf-8",
            )
            got = diag.summarize_stage_logs(
                root, [("stage.stderr.log", "stage-logs/stage.stderr.log")]
            )
        self.assertIn("CalledProcessError", got["primary_mechanical_error"])

    def test_profile_is_zero_effect_and_uses_stage_log_tool(self):
        code = inspect.getsource(diag)
        self.assertNotIn("train_stream.py --", code)
        self.assertNotIn("jass_vs_jass", code)
        self.assertNotIn("--dump-eval-features", code)
        self.assertIn('"historical_training_payloads_read": 0', code)
        self.assertIn('"confirmation_target_reads": 0', code)
        profile = json.loads(
            (ROOT / "jobs/launch_profiles/cls-l-2031-stage-log-diagnostic-v2.json").read_text()
        )
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(
            profile["command"],
            ["/usr/bin/python3", "jobs/tools/cls_l_2031_stage_log_diagnostic.py"],
        )
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))


if __name__ == "__main__":
    unittest.main()
