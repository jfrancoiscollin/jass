from __future__ import annotations

import inspect
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_hier_l2_2050_stage_log_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "jobs" / "launch_profiles" / "cls-hier-l2-2050-stage-log-diagnostic-v1.json"


class CLSHierL22050StageLogDiagnosticV1Tests(unittest.TestCase):
    def test_failed_source_identity_and_terminal_are_frozen(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2050-l3-cls-hier-l2-control-reproduction-rehearsal-v1")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260918T201651Z-1c8de5ca")
        self.assertEqual(diag.FAILED_CODE, "1c8de5cae04f92e53cb15f0de394be2e2bdb3085")
        self.assertEqual(diag.TERMINAL, "CLS_HIER_L2_2050_STAGE_LOG_DIAGNOSTIC_COMPLETE_V1")
        self.assertEqual(diag.PHASE, "execute-cls-hier-l2-2050-stage-log-diagnostic")

    def test_only_runner_owned_stage_logs_are_selected_and_bounded(self):
        verified = {"files": [
            {"path": "stage.stderr.log", "size_bytes": 200},
            {"path": "stage.stdout.log", "size_bytes": 0},
            {"path": "stage-receipt.json", "size_bytes": 500},
            {"path": "artefacts/logs.tar.gz", "size_bytes": 100},
            {"path": "artefacts/model.pjtw.gz", "size_bytes": 100},
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
                "RuntimeError: deterministic HIER-L2 mechanical witness\n",
                encoding="utf-8",
            )
            got = diag.summarize_stage_logs(
                root, [("stage.stderr.log", "stage-logs/stage.stderr.log")]
            )
        self.assertIn("RuntimeError", got["primary_mechanical_error"])

    def test_profile_is_zero_effect_and_cannot_read_scientific_payloads(self):
        code = inspect.getsource(diag)
        for forbidden in (
            "model.pjtw.gz", "logs.tar.gz", "fit-receipt.json", "optimizer.json",
            "current-context30.npy.gz", "D-c-prior-then-current.pjtw.gz",
        ):
            self.assertNotIn(forbidden, code)
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(
            profile["command"],
            ["/usr/bin/python3", "jobs/tools/cls_hier_l2_2050_stage_log_diagnostic.py"],
        )
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))


if __name__ == "__main__":
    unittest.main()
