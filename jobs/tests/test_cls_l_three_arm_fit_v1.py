from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIT = ROOT / "jobs" / "tools" / "cls_l_three_arm_fit.py"
LAUNCH = ROOT / "jobs" / "tools" / "cls_l_three_arm_fit_launch.py"
SHELL = ROOT / "jobs" / "templates" / "l3-cls-l-three-arm-fit-v1.sh"
PROFILE = ROOT / "jobs" / "launch_profiles" / "cls-l-three-arm-fit-v1.json"
RUNTIME = ROOT / "jobs" / "tools" / "launch_runtime_v2.py"


class ClsLThreeArmFitContractTest(unittest.TestCase):
    def test_frozen_scientific_constants_and_exact_three_arms(self):
        text = FIT.read_text(encoding="utf-8")
        self.assertIn('ARMS = ("LOCAL", "WDL", "MIXED")', text)
        self.assertIn("TRAIN_RECORDS = 1_800_796", text)
        self.assertIn("HOLDOUT_RECORDS = 199_204", text)
        self.assertIn("EXTRAS = 120", text)
        self.assertIn("CHUNK = 20_000", text)
        self.assertIn("L2 = 1e-5", text)
        self.assertIn("MAX_ITER = 2_000", text)
        self.assertIn("MAXCOR = 20", text)
        self.assertIn("GTOL = 1e-4", text)
        self.assertIn('FOLD = "exact"', text)
        self.assertIn("PRUNE_MIN_VISITS = 1", text)
        self.assertIn("EXPECTED_PARENT_SHA256 = \"319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1\"", text)
        self.assertIn('"MIXED": objective.mixed_terms(local, wdl_targets, norms)', text)
        self.assertNotIn('"FOURTH"', text)

    def test_frozen_normalization_is_required_and_holdout_cannot_normalize(self):
        text = FIT.read_text(encoding="utf-8")
        self.assertIn('receipt.get("normalization_scope") != "TRAIN_ONLY"', text)
        self.assertIn('receipt.get("holdout_rows_used_for_normalization") != 0', text)
        self.assertIn('receipt.get("lambda_normalized_gradient") != objective.FROZEN_LAMBDA', text)
        self.assertIn('set(norms) != {"LOCAL", "WDL"}', text)
        self.assertIn('"coordinate_identity_sha256": coordinate_sha', text)
        self.assertIn('"inputs": {', text)
        self.assertIn('objective.FROZEN_LAMBDA * local_holdout / norms["LOCAL"]', text)
        self.assertIn('"selection_authorized": False', text)

    def test_launch_profile_allows_only_three_fits_and_no_downstream_effects(self):
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(profile["stage"], "cls-l-three-arm-fit-v1")
        self.assertEqual(profile["required_phases"], ["execute-cls-l-three-arm-fit"])
        for mode in ("rehearsal_max_effects", "production_max_effects"):
            effects = profile[mode]
            self.assertEqual(effects["fits"], 3)
            for key in (
                "new_scan_searches", "new_jass_searches", "strength_games",
                "selfplay_games", "promotions", "bakes", "test_target_reads",
            ):
                self.assertEqual(effects[key], 0, (mode, key))
        self.assertEqual(
            profile["regressions"][-1], "jobs.tests.test_cls_l_three_arm_fit_v1"
        )

    def test_stage_is_pinned_to_green_2035_and_common_rehearsal_production_spec(self):
        text = SHELL.read_text(encoding="utf-8")
        self.assertIn('PREFLIGHT_JOB="cpx62-2035-l3-cls-l-source-normalization-preflight-v8"', text)
        self.assertIn('PREFLIGHT_ATTEMPT="20260917T172555Z-13f1c748"', text)
        self.assertIn('PREFLIGHT_CODE="13f1c748fc088ff4bef5c4779eb3d8733c817041"', text)
        self.assertIn('case "$LAUNCH_MODE" in rehearsal|production)', text)
        self.assertIn('HOLDOUT_MOD=10; SPLIT_SEED=577215', text)
        self.assertIn('CURRICULUM_SHA="319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"', text)
        self.assertIn("execute-cls-l-three-arm-fit", text)
        self.assertIn("evidence.record_effect('fits',3)", text)
        self.assertIn("no search, strength, alpha, promotion or bake", text)

    def test_direct_file_launcher_bootstraps_jobs_package_without_running_stage(self):
        probe = (
            "import runpy; "
            f"runpy.run_path({str(LAUNCH)!r}, run_name='cls_l_three_arm_fit_import_probe')"
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

    def test_launch_evidence_has_validated_effect_recorder(self):
        text = RUNTIME.read_text(encoding="utf-8")
        self.assertIn("def record_effect(self, name: str, count: int = 1):", text)
        self.assertIn("if name not in EFFECTS:", text)
        self.assertIn("if type(count) is not int or count < 0:", text)
        self.assertIn("self.value['actual_side_effects'][name] += count", text)
        self.assertIn("self.save()", text)


if __name__ == "__main__":
    unittest.main()
