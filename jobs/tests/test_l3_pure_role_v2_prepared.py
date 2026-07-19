#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "jobs/templates/l3-pure-runner-v4.sh"
ROLE_PATH = ROOT / "jobs/templates/l3-pure-role-v2-runner-v1.sh"
PATCHER = ROOT / "jobs/tools/patch_l3_pure_role_v2_runner.py"
BASE = BASE_PATH.read_text()
ROLE = ROLE_PATH.read_text()
PATCHER_TEXT = PATCHER.read_text()
TOOL = (ROOT / "jobs/tools/prepare_imbalance2_training.py").read_text()
PREP = ROOT / "jobs/prepared/l3-pure-role-v2-20260720"
DOC = (ROOT / "docs/L3_ROLE_V2_DUAL_LINEAGE_PLAN.md").read_text()


class L3PureRoleV2PreparedTest(unittest.TestCase):
    def test_dedicated_runner_keeps_base_runner_frozen(self):
        for token in (
            "BASE_RUNNER=\"$JASS_CODE_DIR/jobs/templates/l3-pure-runner-v4.sh\"",
            "patch_l3_pure_role_v2_runner.py",
            "g*-role-v2-reweight.json",
            'manifest["lineage"] = "L3-PURE-ROLE-V2"',
            '"holdout_weighted": False',
            '"per_move_criticality_relabel": False',
        ):
            self.assertIn(token, ROLE)
        self.assertIn('"$J" --dump-eval-features "$W/g${generation}.fit.jnnw"', BASE)
        self.assertIn('--data "$W/g${generation}.fit.jnnw"', BASE)
        self.assertNotIn("IMBALANCE2_REWEIGHT_POLICY", BASE)

    def test_patcher_produces_a_valid_role_aware_derivative(self):
        for token in (
            "frozen runner dump-feature insertion point changed",
            "frozen runner train-data insertion point changed",
            "IMBALANCE2_REWEIGHT_POLICY=role-aware-v2",
            "g${generation}.weighted.jnnw",
            "g${generation}-role-v2-reweight.json",
        ):
            self.assertIn(token, PATCHER_TEXT)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "patched.sh"
            subprocess.run(
                [sys.executable, str(PATCHER), "--input", str(BASE_PATH), "--output", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            patched = output.read_text()
            self.assertIn("IMBALANCE2_REWEIGHT_POLICY=role-aware-v2", patched)
            self.assertIn('TRAIN_DATA="$W/g${generation}.weighted.jnnw"', patched)
            self.assertIn('--data "$TRAIN_DATA"', patched)
            self.assertIn('--input "$W/g${generation}.fit.jnnw"', patched)
            subprocess.run(["bash", "-n", str(output)], check=True)

    def test_tool_is_compatible_with_zero_score_l3_pure_records(self):
        for token in (
            '"score_field_used_for_weighting": False',
            '"wdl_field_semantics": "side_to_move_pov_-1_0_1"',
            "abs(nwm - nbm) != 2 or nwk != nbk",
        ):
            self.assertIn(token, TOOL)

    def test_two_hardware_pairs_are_exactly_matched_within_box(self):
        expected = {
            "ccx33-l3-pure-q00-control.sh",
            "ccx33-l3-pure-q00-role-v2.sh",
            "cpx62-l3-pure-q00-control.sh",
            "cpx62-l3-pure-q00-role-v2.sh",
        }
        wrappers = {path.name for path in PREP.glob("*.sh")}
        self.assertEqual(expected, wrappers)

        pairs = (
            ("ccx33", "271828", "primary"),
            ("cpx62", "161803", "replication"),
        )
        for box, seed, run_kind in pairs:
            control_path = PREP / f"{box}-l3-pure-q00-control.sh"
            treatment_path = PREP / f"{box}-l3-pure-q00-role-v2.sh"
            control = control_path.read_text()
            treatment = treatment_path.read_text()
            for token in (
                "L3_VARIANT=Q00_CAPTURE",
                "NGEN=2 FRESH=150000 NSHARDS=8 PAR_GEN=8",
                f"BASE_SEED={seed}",
                "SHARD_TIMEOUT=21600 JASS_BUILD_JOBS=8",
            ):
                self.assertIn(token, control)
                self.assertIn(token, treatment)
            self.assertIn("l3-pure-runner-v4.sh", control)
            self.assertNotIn("L3_ROLE_V2_BOX", control)
            self.assertIn("l3-pure-role-v2-runner-v1.sh", treatment)
            self.assertIn(f"L3_ROLE_V2_BOX={box}", treatment)
            self.assertIn(f"L3_ROLE_V2_RUN_KIND={run_kind}", treatment)
            subprocess.run(["bash", "-n", str(control_path)], check=True)
            subprocess.run(["bash", "-n", str(treatment_path)], check=True)
        subprocess.run(["bash", "-n", str(ROLE_PATH)], check=True)

    def test_recipe_preregisters_only_one_changed_factor(self):
        recipe = (PREP / "RECIPE.md").read_text()
        for token in (
            "paired A/B tests",
            "comparison jobs, not promotion jobs",
            "common seed: `271828`",
            "common seed: `161803`",
            "Only the post-split training corpus differs",
            "exactly two men of difference and equal king counts",
            "final holdout remains untouched",
            "G1 self-play is directly matched",
            "separate reviewed evaluation/gate",
        ):
            self.assertIn(token, recipe)

    def test_dual_lineage_doc_keeps_decisions_separate(self):
        for token in (
            "do not share runners, manifests or promotion decisions",
            "jobs/templates/l3-imbalance2-runner-v2.sh",
            "jobs/templates/l3-pure-role-v2-runner-v1.sh",
            "comparison jobs, not promotion jobs",
            "ccx33 primary pair",
            "cpx62 replication pair",
            "From G2 onward, trajectories may diverge",
            "separate reviewed evaluation/gate",
            "do not launch a later phase or external gate automatically",
        ):
            self.assertIn(token, DOC)


if __name__ == "__main__":
    unittest.main()
