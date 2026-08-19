#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context3-paired-patterneval-fit-exact-extras-v2.sh"


class CorrectedCtx3PairedTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text()

    def test_uses_corrected_trainer_not_legacy_trainer(self):
        self.assertIn("pattern_jass/tools/train_stream_exact.py", self.text)
        self.assertNotIn('"$PY" pattern_jass/tools/train_stream.py', self.text)

    def test_authenticates_1426_mechanistic_gate(self):
        self.assertIn("cpx62-1426-l3-context3-exact-extras-fit-smoke-v1", self.text)
        self.assertIn("20260819T215156Z-040da98c", self.text)
        self.assertIn("JASS_CONTEXT3_EXACT_EXTRAS_FIT_CONTRACT_VERIFIED", self.text)

    def test_preserves_1418_scientific_recipe(self):
        for needle in (
            'SPLIT_SEED=577215', '--holdout-mod "$HOLDOUT_MOD"',
            '--alpha 0.30', '--fold-seed 20260811', '--shuffle-seed 2026081906',
            '--loss logistic --exact-fold --tempo-stage',
            '--prior-mean "$W/curriculum.pjtw" --prior-decay 0',
            '--l2 1e-5 --max-iter "$MAXIT"', '--lbfgs-maxcor 20 --lbfgs-gtol 1e-4',
        ):
            self.assertIn(needle, self.text)

    def test_fail_closed_safety_and_exact_extras_receipts(self):
        for needle in (
            'NO_FROZEN_READ', 'NO_AUTOMATIC_PROMOTION', 'NO_AUTOMATIC_CONTINUATION',
            'certify_exact_extras', 'exact_extras_residuals',
            'reuse_1419_force_pools_forbidden', 'STRENGTH_GAMES_PLAYED__0',
            'PROMOTION_AUTHORIZED__FALSE', 'FROZEN_READ__FALSE',
        ):
            self.assertIn(needle, self.text)


if __name__ == "__main__":
    unittest.main()
