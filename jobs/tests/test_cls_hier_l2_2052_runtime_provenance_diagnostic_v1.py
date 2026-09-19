from __future__ import annotations

import inspect
import json
from pathlib import Path
import unittest

from jobs.tools import cls_hier_l2_2052_runtime_provenance_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "jobs" / "launch_profiles" / "cls-hier-l2-2052-runtime-provenance-diagnostic-v1.json"


class CLSHierL22052RuntimeProvenanceDiagnosticV1Tests(unittest.TestCase):
    def test_source_identities_and_terminal_are_frozen(self):
        self.assertEqual(diag.FAILED_JOB, "cpx62-2052-l3-cls-hier-l2-control-reproduction-rehearsal-v2")
        self.assertEqual(diag.FAILED_ATTEMPT, "20260919T004808Z-a10f9217")
        self.assertEqual(diag.FAILED_CODE, "a10f921715674eca7decfc76714637264fa4d6d2")
        self.assertEqual(diag.HIST_RUNTIME_JOB, "cpx62-1330-jass-megacorpus-smoke-fit-v1")
        self.assertEqual(diag.HIST_RUNTIME_ATTEMPT, "20260814T063409Z-80f38787")
        self.assertEqual(diag.HIST_RUNTIME_CODE, "80f3878709da5df0fa449e348f8a713b399a453e")
        self.assertEqual(diag.CURRICULUM_CODE, "18c38a33ae78c9c2e8e2df62fca266da28dacead")
        self.assertEqual(diag.VENV_PATH, "/var/tmp/jass-l3-numeric-venv-current-v1")
        self.assertEqual(diag.TERMINAL, "CLS_HIER_L2_2052_RUNTIME_PROVENANCE_DIAGNOSTIC_COMPLETE_V1")

    def test_runtime_comparison_reports_drift_without_claiming_causality(self):
        historical = {
            "schema": "jass.python_runtime.v1",
            "numpy": "2.3.2",
            "scipy": "1.16.1",
            "stack": "current-compatible-cpx",
            "venv": diag.VENV_PATH,
            "persistent_cache": True,
        }
        current = {
            "schema": "jass.cls_hier_l2_runtime_authentication.v1",
            "numpy": "2.3.3",
            "scipy": "1.16.2",
            "python": "3.x",
            "python_executable": diag.VENV_PATH + "/bin/python",
            "platform": "linux",
            "historical_recipe_code_sha": diag.CURRICULUM_CODE,
            "historical_train_stream_blob_sha": "a",
            "historical_gen_patterns_blob_sha": "b",
        }
        got = diag.compare_runtime_versions(historical, current)
        self.assertTrue(got["package_version_drift_observed"])
        self.assertFalse(got["causal_runtime_drift_proven"])
        self.assertFalse(got["comparisons"]["numpy_equal"])
        self.assertFalse(got["comparisons"]["scipy_equal"])

    def test_equal_packages_do_not_invent_runtime_cause(self):
        historical = {
            "schema": "jass.python_runtime.v1",
            "numpy": "2.3.2",
            "scipy": "1.16.1",
            "stack": "current-compatible-cpx",
            "venv": diag.VENV_PATH,
            "persistent_cache": True,
        }
        current = {
            "schema": "jass.cls_hier_l2_runtime_authentication.v1",
            "numpy": "2.3.2",
            "scipy": "1.16.1",
        }
        got = diag.compare_runtime_versions(historical, current)
        self.assertFalse(got["package_version_drift_observed"])
        self.assertFalse(got["causal_runtime_drift_proven"])

    def test_profile_is_zero_effect_and_source_is_runtime_only(self):
        code = inspect.getsource(diag)
        for forbidden in (
            "current-context30.npy.gz",
            "D-c-prior-then-current.pjtw.gz",
            "model.pjtw.gz",
            "optimizer.json",
            "fit-receipt.json",
            "logs.tar.gz",
        ):
            self.assertNotIn(forbidden, code)
        self.assertIn("artefacts/runtime-authentication.json", code)
        self.assertIn("artefacts/python-runtime.json", code)
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(profile["required_phases"], [diag.PHASE])
        self.assertEqual(
            profile["command"],
            ["/usr/bin/python3", "jobs/tools/cls_hier_l2_2052_runtime_provenance_diagnostic.py"],
        )
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(v == 0 for v in profile["rehearsal_max_effects"].values()))


if __name__ == "__main__":
    unittest.main()
