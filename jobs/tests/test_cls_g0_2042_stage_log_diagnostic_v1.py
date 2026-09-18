from __future__ import annotations

import inspect
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_g0_2042_stage_log_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "jobs" / "launch_profiles" / "cls-g0-2042-stage-log-diagnostic-v1.json"


class CLSG02042StageLogDiagnosticV1Tests(unittest.TestCase):
    def test_failed_source_identity_and_terminal_are_frozen(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2042-l3-cls-g0-local-runtime-rehearsal-v1")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260918T113159Z-db842be0")
        self.assertEqual(diag.FAILED_CODE, "db842be0939954a59076cd2b1d8a05041a3ba661")
        self.assertEqual(diag.TERMINAL, "CLS_G0_2042_STAGE_LOG_DIAGNOSTIC_COMPLETE_V1")
        self.assertEqual(diag.PHASE, "execute-cls-g0-2042-stage-log-diagnostic")

    def test_only_runner_owned_stage_logs_are_selected_and_bounded(self):
        verified = {"files": [
            {"path": "stage.stderr.log", "size_bytes": 200},
            {"path": "stage.stdout.log", "size_bytes": 0},
            {"path": "stage-receipt.json", "size_bytes": 500},
            {"path": "work/probe.log", "size_bytes": 50},
            {"path": "artefacts/probe.tsv", "size_bytes": 50},
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
                "RuntimeError: deterministic G0 mechanical witness\n",
                encoding="utf-8",
            )
            got = diag.summarize_stage_logs(
                root, [("stage.stderr.log", "stage-logs/stage.stderr.log")]
            )
        self.assertIn("RuntimeError", got["primary_mechanical_error"])

    def test_profile_is_zero_effect_and_cannot_read_scientific_payloads(self):
        code = inspect.getsource(diag)
        for forbidden in (
            "LOCAL.pjtw.gz", "WDL.pjtw.gz", "probe.tsv", "g0-deep512.tsv",
            "g0-deep-reference.tsv", "go depth",
        ):
            self.assertNotIn(forbidden, code)
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(
            profile["command"],
            ["/usr/bin/python3", "jobs/tools/cls_g0_2042_stage_log_diagnostic.py"],
        )
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))


if __name__ == "__main__":
    unittest.main()
