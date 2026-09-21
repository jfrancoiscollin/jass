from __future__ import annotations

import inspect
import json
import unittest
from unittest import mock

from jobs.tools import chinook_error_mining_stage as s


class ChinookStageTests(unittest.TestCase):
    def test_source_identities_are_frozen(self):
        self.assertEqual(s.REFERENCE_JOB, "cpx62-2065-l3-cls-hier-scan-reference-diagnostic-v1")
        self.assertEqual(s.REFERENCE_CODE, "7b789a0c675ce08868fe4a8fcef0becaa4193286")
        self.assertEqual(s.SELECTION[0], "home-1651-l3-scan-ceiling-selection-v1")
        self.assertEqual(s.SELECTION[1], "20260829T133348Z-28e12fba")

    def test_unique_completed_attempt_fail_closed(self):
        good = {
            "job_id": s.REFERENCE_JOB,
            "attempt_id": "a",
            "result_state": "completed",
            "exit_code": 0,
        }
        proc = mock.Mock(stdout="a/\nb/\n", stderr="")
        with mock.patch.object(s.subprocess, "run", return_value=proc),              mock.patch.object(s.fetch, "inspect_result_inventory", side_effect=[good, RuntimeError("bad")]):
            self.assertEqual(s.unique_completed_attempt(s.REFERENCE_JOB), "a")

        with mock.patch.object(s.subprocess, "run", return_value=proc),              mock.patch.object(s.fetch, "inspect_result_inventory", side_effect=[good, dict(good, attempt_id="b")]):
            with self.assertRaises(ValueError):
                s.unique_completed_attempt(s.REFERENCE_JOB)

    def test_direct_script_import_bootstrap_precedes_jobs_imports(self):
        source = inspect.getsource(s)
        bootstrap = 'sys.path.insert(0, str(ROOT))'
        first_jobs_import = 'from jobs.tools import chinook_error_mining as miner'
        self.assertIn(bootstrap, source)
        self.assertLess(source.index(bootstrap), source.index(first_jobs_import))

    def test_profile_is_zero_effect(self):
        path = s.Path(__file__).resolve().parents[1] / "launch_profiles" / "chinook-error-mining-v1.json"
        profile = json.loads(path.read_text())
        self.assertEqual(profile["required_phases"], s.PHASES)
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))
        self.assertIn("chinook-error-patterns-v1.csv", profile["evidence_outputs"])


if __name__ == "__main__":
    unittest.main()
