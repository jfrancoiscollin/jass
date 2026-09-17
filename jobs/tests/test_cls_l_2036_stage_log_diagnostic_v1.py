from __future__ import annotations

import inspect
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_l_2036_stage_log_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]


class CLSL2036StageLogDiagnosticTests(unittest.TestCase):
    def test_failed_source_identity_and_terminal_are_frozen(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2036-l3-cls-l-three-arm-fit-rehearsal-v1")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260917T183209Z-4b46d3fc")
        self.assertEqual(diag.FAILED_CODE, "4b46d3fc37c631ec46b4b3173ead4c7f719e31ff")
        self.assertEqual(diag.TERMINAL, "CLS_L_2036_STAGE_LOG_DIAGNOSTIC_COMPLETE_V1")
        self.assertEqual(diag.PHASE, "execute-cls-l-2036-stage-log-diagnostic")

    def test_only_runner_owned_stage_logs_are_selected_and_bounded(self):
        verified = {"files": [
            {"path": "stage.stderr.log", "size_bytes": 200},
            {"path": "stage.stdout.log", "size_bytes": 0},
            {"path": "stage-receipt.json", "size_bytes": 500},
            {"path": "work/fit.log", "size_bytes": 50},
            {"path": "artefacts/LOCAL.pjtw.gz", "size_bytes": 50},
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

    def test_profile_is_zero_effect_and_cannot_read_fit_payloads(self):
        code = inspect.getsource(diag)
        self.assertNotIn("LOCAL.pjtw.gz", code)
        self.assertNotIn("WDL.pjtw.gz", code)
        self.assertNotIn("MIXED.pjtw.gz", code)
        self.assertNotIn("train_stream.py --", code)
        self.assertNotIn("jass_vs_jass", code)
        self.assertIn('"historical_training_payloads_read": 0', code)
        self.assertIn('"fitted_model_payloads_read": 0', code)
        self.assertIn('"confirmation_target_reads": 0', code)
        profile = json.loads(
            (ROOT / "jobs/launch_profiles/cls-l-2036-stage-log-diagnostic-v1.json").read_text()
        )
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(
            profile["command"],
            ["/usr/bin/python3", "jobs/tools/cls_l_2036_stage_log_diagnostic.py"],
        )
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))


if __name__ == "__main__":
    unittest.main()
