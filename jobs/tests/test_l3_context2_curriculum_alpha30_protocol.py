# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed contracts for the CTX2 alpha=0.30 Curriculum A/B/C refit."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    ROOT / "jobs" / "templates" / "l3-context2-curriculum-alpha30-abc-fit-v1.sh"
)


class Context2CurriculumAlpha30ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = TEMPLATE.read_text(encoding="utf-8")

    def test_reuses_certified_pure_teacher_and_recomposes_alpha30(self) -> None:
        for token in (
            "cpx62-1384-l3-context2-curriculum-full-relabel-fit-v1",
            "l3_context2_recompose_targets.py",
            "--pure-context-target",
            "--alpha 0.30",
            "--fold-count 5",
            "--fold-seed 20260811",
            "--shuffle-seed 20260812",
            "--shuffle-phase-bins 4",
            "teacher_refits':0",
        ):
            self.assertIn(token, self.script)
        self.assertNotIn("--dump-conditional-context-v2", self.script)
        self.assertNotIn("--alpha 1.00", self.script)

    def test_reproduces_both_curriculum_stages_and_four_fits(self) -> None:
        for token in (
            "home-0977-l3-pure-turnover1to1-train-v1",
            "home-1044-l3-pure-hard-replay-large-source-v1",
            "SAMPLE_SEED=20260814",
            "HOLDOUT_MOD=10",
            "SPLIT_SEED=577215",
            'fit_stage B-mega mega_full_4m',
            'fit_stage C-mega mega_full_4m',
            'fit_stage B-current current_2m',
            'fit_stage C-current current_2m',
            '"$W/B-mega.pjtw"',
            '"$W/C-mega.pjtw"',
        ):
            self.assertIn(token, self.script)

    def test_a_is_authenticated_and_never_refitted(self) -> None:
        self.assertIn("cpx62-1341-jass-megacorpus-arm-d-fit-v1", self.script)
        self.assertIn('CURRICULUM_SHA="319d174f', self.script)
        self.assertIn("baseline_reused_without_refit':True", self.script)
        self.assertNotIn("fit_stage A-", self.script)

    def test_exact_training_recipe_and_scale_guards(self) -> None:
        for token in (
            "--loss logistic",
            "--exact-fold",
            "--tempo-stage",
            "--prior-decay 0",
            "--l2 1e-5",
            "--lbfgs-maxcor 20",
            "--lbfgs-gtol 1e-4",
            "0.95 <= ref[key] <= 1.05",
            "0.80 <= ratio <= 1.20",
            "validate-current-target-recomposition-against-original-alpha30-fit",
            "dtype='<i4'",
            "dtype=np.float64)/scale",
        ):
            self.assertIn(token, self.script)

    def test_pre_registered_hierarchy_and_no_unauthorized_actions(self) -> None:
        self.assertIn(
            "primary_contrast':'B_vs_C_native_0.1s_on_two_fresh_disjoint_pools",
            self.script,
        )
        self.assertIn(
            "secondary_contrast':'B_vs_A_only_if_B_vs_C_is_established_positive",
            self.script,
        )
        for token in ("--self-play", "frozen_test", "--gen-selfplay"):
            self.assertNotIn(token, self.script)
        self.assertIn("strength_games_played':0", self.script)
        self.assertIn("promotion_authorized':False", self.script)
        self.assertIn("automatic_next_job':None", self.script)

    def test_persistent_runtime_is_reused(self) -> None:
        self.assertIn("/var/tmp/jass-l3-numeric-venv-current-v1", self.script)
        self.assertIn("persistent numeric runtime absent; do not reinstall", self.script)
        self.assertNotIn("pip install", self.script)


if __name__ == "__main__":
    unittest.main()
