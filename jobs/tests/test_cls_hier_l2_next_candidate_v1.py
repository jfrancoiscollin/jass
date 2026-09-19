from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
SHELL = ROOT / "jobs" / "templates" / "l3-cls-hier-l2-next-candidate-v1.sh"
PROFILE = ROOT / "jobs" / "launch_profiles" / "cls-hier-l2-next-candidate-v1.json"
LAUNCH = ROOT / "jobs" / "tools" / "cls_hier_l2_next_candidate_launch.py"
CONTRACT = ROOT / "docs" / "experiments" / "L3_CLS_HIER_L2_NEXT_CANDIDATE_V1_20260918.md"
CURRICULUM = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
HISTORICAL_CODE = "18c38a33ae78c9c2e8e2df62fca266da28dacead"
HISTORICAL_TRAIN_STREAM_BLOB = "12ed5f0f743dadc07ebaab6de1dd9a837297b6c0"


class CLSHierL2NextCandidateV1Tests(unittest.TestCase):
    def test_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(SHELL)], check=True)

    def test_contract_freezes_one_factor_and_parent(self) -> None:
        text = CONTRACT.read_text()
        self.assertIn(CURRICULUM, text)
        self.assertIn("CONTROL: `hier_l2 = 0`", text)
        self.assertIn("HIER: `hier_l2 = 1e-5`", text)
        self.assertIn("ordinary `l2 = 1e-5`", text)
        self.assertIn("No automatic promotion, bake or scale-up", text)
        self.assertIn("missing receipt in either arm = hard G0-C FAIL", text)

    def test_stage_reproduces_historical_curriculum_recipe(self) -> None:
        text = SHELL.read_text()
        for literal in (
            'CURRICULUM_SHA="' + CURRICULUM + '"',
            'CURRICULUM_CODE="' + HISTORICAL_CODE + '"',
            'HIST_TRAIN_STREAM_BLOB="' + HISTORICAL_TRAIN_STREAM_BLOB + '"',
            'ABC_ATTEMPT="20260814T123246Z-2ce07222"',
            'CURRICULUM_ATTEMPT="20260814T191555Z-18c38a33"',
            'HOLDOUT_MOD=10; SPLIT_SEED=577215',
            'MAXIT=2000; CHUNK=20000; L2="1e-5"; HIER_L2="1e-5"',
            '--target external --target-values "$W/current-context30.npy"',
            '--loss logistic --exact-fold --tempo-stage',
            '--prior-mean "$W/C.pjtw" --prior-decay 0',
            '--lbfgs-maxcor 20 --lbfgs-gtol 1e-4 --prune',
        ):
            self.assertIn(literal, text)

    def test_historical_recipe_mechanics_are_fail_closed(self) -> None:
        text = SHELL.read_text()
        self.assertIn('git archive --format=tar "$CURRICULUM_CODE"', text)
        self.assertIn('git rev-parse "$CURRICULUM_CODE:pattern_jass/tools/train_stream.py"', text)
        self.assertIn('python3 "$HIST/tools/selfplay_frontier.py" split', text)
        self.assertIn('cmake -S "$HIST" -B "$W/build"', text)
        self.assertIn('"$PY" "$HIST/pattern_jass/tools/train_stream.py"', text)
        self.assertIn('PYTHONPATH="$GEOM:$HIST/pattern_jass/tools:$HIST"', text)
        self.assertNotIn("current-code production feature geometry", text)
        self.assertIn("historical_recipe_code_sha", text)
        self.assertIn("runtime-authentication.json", text)

    def test_control_is_byte_exact_and_hier_is_gated(self) -> None:
        text = SHELL.read_text()
        self.assertIn('CONTROL_BYTE_IDENTITY_MISMATCH', text)
        self.assertIn('[ "$MODEL_SHA" != "$CURRICULUM_SHA" ]', text)
        self.assertIn(': "${CLS_HIER_CONTROL_ROOT:?HIER requires authenticated CONTROL production root}"', text)
        self.assertIn("CLS_HIER_CONTROL_REPRODUCTION_READY_V1", text)
        self.assertIn('HIER_ARGS=(--hier-l2 "$HIER_L2")', text)
        self.assertNotIn('--hier-l2 0', text)

    def test_zero_strength_side_effect_boundary(self) -> None:
        text = SHELL.read_text()
        for literal in (
            "'strength_games':0",
            "'alpha_spent':0",
            "'promotions':0",
            "'bakes':0",
            "'new_jass_searches':0",
            "'new_scan_searches':0",
        ):
            self.assertIn(literal, text)

    def test_launch_profile_is_fail_closed(self) -> None:
        p = json.loads(PROFILE.read_text())
        self.assertEqual(p["schema"], "jass.launch_profile.v2")
        self.assertEqual(p["stage"], "cls-hier-l2-next-candidate-v1")
        self.assertEqual(p["command"], ["/usr/bin/python3", "jobs/tools/cls_hier_l2_next_candidate_launch.py"])
        self.assertIn("jobs.tests.test_cls_hier_l2_next_candidate_v1", p["regressions"])
        for mode in ("rehearsal_max_effects", "production_max_effects"):
            effects = p[mode]
            self.assertEqual(effects["fits"], 1)
            self.assertEqual(effects["strength_games"], 0)
            self.assertEqual(effects["new_jass_searches"], 0)
            self.assertEqual(effects["new_scan_searches"], 0)
            self.assertEqual(effects["promotions"], 0)
            self.assertEqual(effects["bakes"], 0)

    def test_launch_entrypoint_uses_authenticated_sha_and_numeric_runtime(self) -> None:
        text = LAUNCH.read_text()
        self.assertIn("authenticated_code_sha()", text)
        self.assertIn("ensure_numeric_runtime()", text)
        self.assertIn("os.execv", text)


if __name__ == "__main__":
    unittest.main()
