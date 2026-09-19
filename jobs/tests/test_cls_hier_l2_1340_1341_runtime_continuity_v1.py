from __future__ import annotations

import inspect
import json
from pathlib import Path
import unittest

from jobs.tools import cls_hier_l2_1340_1341_runtime_continuity_diagnostic as diag

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "jobs" / "launch_profiles" / "cls-hier-l2-1340-1341-runtime-continuity-v1.json"


class CLSHierL213401341RuntimeContinuityV1Tests(unittest.TestCase):
    def test_historical_identities_are_frozen(self) -> None:
        self.assertEqual(diag.ABC_JOB, "cpx62-1340-jass-megacorpus-comparative-fit-v1")
        self.assertEqual(diag.ABC_ATTEMPT, "20260814T123246Z-2ce07222")
        self.assertEqual(diag.ABC_CODE, "2ce07222f86c1468a1081fbdc53e9e17a0c5326e")
        self.assertEqual(diag.CURR_JOB, "cpx62-1341-jass-megacorpus-arm-d-fit-v1")
        self.assertEqual(diag.CURR_ATTEMPT, "20260814T191555Z-18c38a33")
        self.assertEqual(diag.CURR_CODE, "18c38a33ae78c9c2e8e2df62fca266da28dacead")
        self.assertEqual(diag.EXPECTED_NUMPY, "2.5.2")
        self.assertEqual(diag.EXPECTED_SCIPY, "1.18.0")
        self.assertEqual(diag.VENV, "/var/tmp/jass-l3-numeric-venv-current-v1")

    def test_control_first_parent_chain_is_exact(self) -> None:
        self.assertEqual(diag.CONTROL_DONE_1340, "2324bb7286d2ee90bd9e4c7d4715facba4e45540")
        self.assertEqual(diag.CONTROL_CHAIN, [
            "01da25fae2d0156fdab3f0ea4cda90022fd3b56e",
            "ebb00815e1b771c2db02a6ceed2cd1c20d3ac874",
            "44a5e3a35aec0e81f78fa18432f9ef5c3314d286",
            "deaae085df08b75852878161a2be4b647ab95098",
        ])

    def test_frozen_templates_prove_no_post_receipt_or_1341_runtime_mutator(self) -> None:
        proof = diag.authenticate_template_runtime_contracts()
        self.assertEqual(proof["venv"], diag.VENV)
        self.assertEqual(proof["1340_bootstrap_install_count_before_receipt"], 1)
        self.assertEqual(proof["1340_runtime_mutators_after_receipt"], 0)
        self.assertTrue(proof["1341_requires_preexisting_ready_runtime"])
        self.assertEqual(proof["1341_runtime_mutators"], 0)

    def test_profile_has_zero_scientific_effect_ceiling(self) -> None:
        p = json.loads(PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(p["stage"], "cls-hier-l2-1340-1341-runtime-continuity-v1")
        self.assertIn("jobs.tests.test_cls_hier_l2_1340_1341_runtime_continuity_v1", p["regressions"])
        for key in ("rehearsal_max_effects", "production_max_effects"):
            self.assertTrue(all(v == 0 for v in p[key].values()))

    def test_diagnostic_source_excludes_scientific_payloads_and_actions(self) -> None:
        code = inspect.getsource(diag)
        for forbidden in (
            "D-c-prior-then-current.pjtw.gz",
            "current_2m-context30.npy.gz",
            "logs.tar.gz",
            "--dump-eval-features",
            "strength cohort",
        ):
            self.assertNotIn(forbidden, code)
        self.assertIn("artefacts/python-runtime.json", code)
        self.assertIn("intervening_runner_jobs", code)
        self.assertIn("runner_managed_runtime_continuity_proven", code)


if __name__ == "__main__":
    unittest.main()
