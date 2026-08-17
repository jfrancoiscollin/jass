# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed contracts for the CTX2 alpha=1 Curriculum refit."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-curriculum-full-relabel-fit-v1.sh"


class Context2CurriculumFullRelabelProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = TEMPLATE.read_text(encoding="utf-8")

    def test_reproduces_both_certified_curriculum_corpora(self) -> None:
        for token in (
            "home-0977-l3-pure-turnover1to1-train-v1",
            "home-1044-l3-pure-hard-replay-large-source-v1",
            "cpx62-1340-jass-megacorpus-comparative-fit-v1",
            "game_hash_mod",
            "modulus':10",
            "SAMPLE_SEED=20260814",
            "HOLDOUT_MOD=10",
            "SPLIT_SEED=577215",
            "reproduced mega manifest drift",
            "reproduced current manifest drift",
        ):
            self.assertIn(token, self.script)

    def test_ctx2_is_aligned_complete_and_leakage_resistant_on_both_stages(self) -> None:
        for token in (
            "--dump-conditional-context-v2",
            "--context-schema ctx2-phase-tactical-30",
            "--group-by opening_id",
            "--row-weighting game_equal",
            "--require-convergence",
            "--alpha 1.00",
            "--fold-count 5",
            "--shuffle-within-wdl",
            "--shuffle-phase-bins 4",
        ):
            self.assertIn(token, self.script)
        self.assertEqual(self.script.count("--alpha 1.00"), 1)
        self.assertIn("for arm in mega_full_4m current_2m", self.script)

    def test_exact_curriculum_objectives_are_replayed(self) -> None:
        self.assertIn('fit_stage mega_full_4m "$W/l2low.pjtw"', self.script)
        self.assertIn('fit_stage current_2m "$W/mega_full_4m.pjtw"', self.script)
        for token in (
            "--loss logistic",
            "--exact-fold",
            "--tempo-stage",
            "--prior-decay 0",
            "--l2 1e-5",
            "--lbfgs-maxcor 20",
            "--lbfgs-gtol 1e-4",
        ):
            self.assertIn(token, self.script)

    def test_champion_is_authenticated_and_not_refitted(self) -> None:
        self.assertIn("cpx62-1341-jass-megacorpus-arm-d-fit-v1", self.script)
        self.assertIn("CURRICULUM_SHA=\"319d174f", self.script)
        self.assertNotIn("fit_stage curriculum", self.script)
        self.assertIn("baseline_reused_without_refit':True", self.script)

    def test_no_games_frozen_or_automatic_promotion(self) -> None:
        for token in ("--self-play", "frozen_test", "--gen-selfplay"):
            self.assertNotIn(token, self.script)
        self.assertIn("strength_games_played':0", self.script)
        self.assertIn("frozen_cohorts_read':0", self.script)
        self.assertIn("promotion_authorized':False", self.script)
        self.assertIn("automatic_next_job':None", self.script)

    def test_persistent_numeric_runtime_is_reused(self) -> None:
        self.assertIn("/var/tmp/jass-l3-numeric-venv-current-v1", self.script)
        self.assertIn("persistent numeric runtime absent; do not reinstall", self.script)
        self.assertNotIn("pip install", self.script)


if __name__ == "__main__":
    unittest.main()
