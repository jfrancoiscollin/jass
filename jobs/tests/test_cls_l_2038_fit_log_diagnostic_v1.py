from __future__ import annotations

import inspect
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from jobs.tools import cls_l_2038_fit_log_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]


class CLSL2038FitLogDiagnosticTests(unittest.TestCase):
    def test_failed_source_and_terminal_are_frozen(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2038-l3-cls-l-three-arm-fit-rehearsal-v2")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260917T201315Z-d29e2c49")
        self.assertEqual(diag.FAILED_CODE, "d29e2c4985ffc77510f3fa91c51f640d89f37627")
        self.assertEqual(diag.TERMINAL, "CLS_L_2038_FIT_LOG_DIAGNOSTIC_COMPLETE_V1")

    def test_only_small_authenticated_logs_archive_is_selected(self):
        verified = {"files": [
            {"path": "artefacts/logs.tar.gz", "size_bytes": 12528},
            {"path": "artefacts/LOCAL.pjtw.gz", "size_bytes": 123},
        ]}
        self.assertEqual(diag.archive_selection(verified), ("artefacts/logs.tar.gz", "logs.tar.gz"))

    def test_extracts_only_regular_fit_log_and_surfaces_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "logs.tar.gz"
            raw = (
                "arm=LOCAL\n"
                "Traceback (most recent call last):\n"
                "RuntimeError: deterministic mechanical witness\n"
            ).encode()
            with tarfile.open(archive, "w:gz") as tf:
                info = tarfile.TarInfo("./fit.log")
                info.size = len(raw)
                tf.addfile(info, io.BytesIO(raw))
                other = b"do not read model payload"
                info = tarfile.TarInfo("./other.log")
                info.size = len(other)
                tf.addfile(info, io.BytesIO(other))
            got = diag.extract_fit_log(archive, root / "fit.log")
        self.assertEqual(got["archive_member"], "./fit.log")
        self.assertIn("RuntimeError", got["primary_mechanical_error"])

    def test_profile_is_zero_effect_and_forbids_scientific_payloads(self):
        code = inspect.getsource(diag)
        for forbidden in ("LOCAL.pjtw.gz", "WDL.pjtw.gz", "MIXED.pjtw.gz", "current.jnnw", "current-context30.npy"):
            self.assertNotIn(forbidden, code)
        profile = json.loads(
            (ROOT / "jobs/launch_profiles/cls-l-2038-fit-log-diagnostic-v1.json").read_text()
        )
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(
            profile["command"],
            ["/usr/bin/python3", "jobs/tools/cls_l_2038_fit_log_diagnostic.py"],
        )
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))


if __name__ == "__main__":
    unittest.main()
