from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from jobs.tools import cls_l_three_arm_fit as fit

ROOT = Path(__file__).resolve().parents[2]
SHELL = ROOT / "jobs" / "templates" / "l3-cls-l-valid-arms-recovery-2038-v1.sh"
PROFILE = ROOT / "jobs" / "launch_profiles" / "cls-l-valid-arms-recovery-2038-v1.json"
LAUNCH = ROOT / "jobs" / "tools" / "cls_l_valid_arms_recovery_2038_launch.py"
CONTRACT = ROOT / "docs" / "experiments" / "L3_CLS_L_OBJECTIVE_ATTRIBUTION_V1_20260916.json"


def valid_summary() -> dict:
    return {
        "terminal": fit.RECOVERY_2040_TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "failed_job_id": fit.RECOVERY_2038_JOB,
        "failed_attempt_id": fit.RECOVERY_2038_ATTEMPT,
        "primary_mechanical_error": fit.RECOVERY_2038_ERROR,
        "target_reads": 0,
        "fits": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
        "next_stage": "REPAIR_PROVEN_2038_FIT_MECHANICS_ONLY",
    }


class CLSLValidArmsRecovery2038Tests(unittest.TestCase):
    def test_recovery_is_exactly_local_wdl_and_frozen_cap_is_unchanged(self):
        self.assertEqual(fit.ARMS, ("LOCAL", "WDL", "MIXED"))
        self.assertEqual(fit.RECOVERY_ARMS, ("LOCAL", "WDL"))
        self.assertEqual(fit.MAX_ITER, 2_000)
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(contract["common_recipe"]["max_iterations"], 2000)
        self.assertFalse(contract["fit_boundary"]["retuning_after_failure"])
        self.assertTrue(contract["downstream"]["each_technically_valid_arm_runs_frozen_cls_g0"])

    def test_recovery_evidence_is_fail_closed_on_exact_2040_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text(json.dumps(valid_summary()), encoding="utf-8")
            got = fit.validate_recovery_2038_summary(path)
            self.assertEqual(got["primary_mechanical_error"], fit.RECOVERY_2038_ERROR)
            bad = valid_summary()
            bad["primary_mechanical_error"] = "different"
            path.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(fit.FitError):
                fit.validate_recovery_2038_summary(path)

    def test_recovery_shell_pins_2040_and_never_refits_mixed(self):
        text = SHELL.read_text(encoding="utf-8")
        self.assertIn('RECOVERY_JOB="cpx62-2040-l3-cls-l-2038-fit-log-diagnostic-v1"', text)
        self.assertIn('RECOVERY_ATTEMPT="20260918T063103Z-d04b96d8"', text)
        self.assertIn('RECOVERY_RECEIPT_SHA="879946b1be6dcbcd2cfdaeaa2ba524726c499f247d3153b5ba1885a7ebd84807"', text)
        self.assertIn('--recovery-2038-summary "$IN/recovery-2038-summary.json"', text)
        self.assertIn("for arm in LOCAL WDL; do", text)
        self.assertNotIn("for arm in LOCAL WDL MIXED; do", text)
        self.assertIn("MIXED remains technical-failed at frozen cap", text)
        self.assertIn("evidence.record_effect('fits',2)", text)

    def test_recovery_shell_is_bash_syntax_valid(self):
        completed = subprocess.run(
            ["/usr/bin/bash", "-n", str(SHELL)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_launch_profile_allows_two_recovery_fits_only(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(profile["stage"], "cls-l-valid-arms-recovery-2038-v1")
        self.assertEqual(profile["required_phases"], ["execute-cls-l-valid-arms-recovery"])
        for mode in ("rehearsal_max_effects", "production_max_effects"):
            effects = profile[mode]
            self.assertEqual(effects["fits"], 2)
            for key in (
                "new_scan_searches", "new_jass_searches", "strength_games",
                "selfplay_games", "promotions", "bakes", "test_target_reads",
            ):
                self.assertEqual(effects[key], 0)

    def test_direct_file_launcher_import_is_self_contained(self):
        probe = (
            "import runpy; "
            f"runpy.run_path({str(LAUNCH)!r}, run_name='cls_l_recovery_import_probe')"
        )
        completed = subprocess.run(
            ["/usr/bin/python3", "-I", "-c", probe],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
