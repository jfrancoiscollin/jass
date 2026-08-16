# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed static contracts for the full-Jass CTX2 fit job."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-phase-tactical-fit-v1.sh"
TOOL = ROOT / "jobs" / "tools" / "l3_conditional_targets.py"
MAIN = ROOT / "src" / "main.cpp"


class Context2PhaseTacticalProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = TEMPLATE.read_text(encoding="utf-8")
        cls.tool = TOOL.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_exact_tactical_dump_and_production_architecture_are_required(self) -> None:
        self.assertIn("--dump-conditional-context-v2", self.script)
        self.assertIn("--dump-eval-features", self.script)
        for option in (
            "-DJASS_ENDGAME_FEATURES=ON",
            "-DJASS_KING_MOBILITY=ON",
            "-DJASS_SCAN_PARITY=ON",
            "-DJASS_TEMPO_STAGE=ON",
        ):
            self.assertIn(option, self.script)
        self.assertIn("run_dump_conditional_context_v2_mode", self.main)

    def test_cross_fit_and_shuffle_are_strictly_preregistered(self) -> None:
        for token in (
            "--context-schema ctx2-phase-tactical-30",
            "--group-by opening_id",
            "--row-weighting game_equal",
            "--require-convergence",
            "--shuffle-within-wdl",
            "--shuffle-phase-bins 4",
        ):
            self.assertIn(token, self.script)
        self.assertIn("fold_local_rms", self.tool)
        self.assertIn("terminal_wdl_black_x_tempo_phase_4_bins", self.script)

    def test_only_b_and_c_are_fitted_and_a_is_reused(self) -> None:
        self.assertEqual(self.script.count('fit_arm aligned "$W/aligned.npy"'), 1)
        self.assertEqual(self.script.count('fit_arm shuffled "$W/shuffled.npy"'), 1)
        self.assertNotIn("fit_arm outcome", self.script)
        self.assertIn("reused_from':'cpx62-1340'", self.script)
        self.assertIn("primary_contrast':'B_vs_C", self.script)
        self.assertIn("secondary_contrast':'B_vs_A", self.script)

    def test_no_data_generation_frozen_read_or_automatic_promotion(self) -> None:
        forbidden = ("--self-play", "frozen_test", "--gen-data", "--gen-selfplay")
        for token in forbidden:
            self.assertNotIn(token, self.script)
        self.assertIn("new_selfplay_generated':False", self.script)
        self.assertIn("frozen_cohorts_read':0", self.script)
        self.assertIn("promotion_authorized':False", self.script)
        self.assertIn("automatic_next_job':None", self.script)
        self.assertIn("NO_AUTOMATIC_CONTINUATION", self.script)

    def test_numeric_runtime_is_persistent_and_pytorch_free(self) -> None:
        self.assertIn("/var/tmp/jass-l3-numeric-venv-current-v1", self.script)
        self.assertIn("pytorch_installed_or_required':False", self.script)
        self.assertNotIn("pip install torch", self.script)


if __name__ == "__main__":
    unittest.main()
