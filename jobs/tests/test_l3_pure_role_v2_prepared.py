#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = (ROOT / "jobs/templates/l3-pure-runner-v4.sh").read_text()
ROLE = (ROOT / "jobs/templates/l3-pure-role-v2-runner-v1.sh").read_text()
TOOL = (ROOT / "jobs/tools/prepare_imbalance2_training.py").read_text()
PREP = ROOT / "jobs/prepared/l3-pure-role-v2-20260720"


class L3PureRoleV2PreparedTest(unittest.TestCase):
    def test_dedicated_runner_keeps_base_runner_frozen(self):
        for token in (
            "BASE_RUNNER=\"$JASS_CODE_DIR/jobs/templates/l3-pure-runner-v4.sh\"",
            "frozen runner dump-feature insertion point changed",
            "frozen runner train-data insertion point changed",
            "IMBALANCE2_REWEIGHT_POLICY=role-aware-v2",
            "g${generation}.weighted.jnnw",
            "g${generation}-role-v2-reweight.json",
            'manifest["lineage"] = "L3-PURE-ROLE-V2"',
            '"holdout_weighted": False',
            '"per_move_criticality_relabel": False',
        ):
            self.assertIn(token, ROLE)
        self.assertIn('"$J" --dump-eval-features "$W/g${generation}.fit.jnnw"', BASE)
        self.assertIn('--data "$W/g${generation}.fit.jnnw"', BASE)
        self.assertNotIn("IMBALANCE2_REWEIGHT_POLICY", BASE)

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
        self.assertEqual(expected, {path.name for path in PREP.glob("*.sh")})

        pairs = (
            ("ccx33", "271828", "primary"),
            ("cpx62", "161803", "replication"),
        )
        for box, seed, run_kind in pairs:
            control = (PREP / f"{box}-l3-pure-q00-control.sh").read_text()
            treatment = (PREP / f"{box}-l3-pure-q00-role-v2.sh").read_text()
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

    def test_recipe_preregisters_only_one_changed_factor(self):
        recipe = (PREP / "RECIPE.md").read_text()
        for token in (
            "paired A/B tests",
            "common seed: `271828`",
            "common seed: `161803`",
            "Only the post-split training corpus differs",
            "exactly two men of difference and equal king counts",
            "final holdout remains untouched",
        ):
            self.assertIn(token, recipe)


if __name__ == "__main__":
    unittest.main()
