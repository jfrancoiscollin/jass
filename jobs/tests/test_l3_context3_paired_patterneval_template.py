import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-context3-paired-patterneval-fit-v1.sh"


class Context3PairedPatternEvalTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_mapper_corpus_and_parent(self) -> None:
        self.assertIn("20260819T072356Z-999091b3", self.text)
        self.assertIn("20260818T184956Z-3465ec72", self.text)
        self.assertIn("20260814T191555Z-18c38a33", self.text)
        self.assertIn("JASS_CONTEXT3_EXACT_TANH_MAPPER_SCREEN_PASSED", self.text)
        self.assertIn("CURRICULUM_SHA", self.text)

    def test_paired_protocol_differs_only_by_target(self) -> None:
        self.assertEqual(self.text.count("fit_arm aligned"), 1)
        self.assertEqual(self.text.count("fit_arm shuffled"), 1)
        self.assertIn("--alpha 0.30", self.text)
        self.assertIn("--prior-mean \"$W/curriculum.pjtw\" --prior-decay 0", self.text)
        self.assertIn("--l2 1e-5 --max-iter \"$MAXIT\"", self.text)
        self.assertIn("--lbfgs-maxcor 20 --lbfgs-gtol 1e-4", self.text)
        self.assertIn("same_parent=CURRICULUM", self.text)

    def test_no_expansive_actions(self) -> None:
        for marker in (
            "SELFPLAY_GENERATED__FALSE",
            "STRENGTH_GAMES_PLAYED__0",
            "FROZEN_READ__FALSE",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(marker, self.text)
        self.assertNotRegex(self.text, re.compile(r"frozen_test|--selfplay|--force", re.I))


if __name__ == "__main__":
    unittest.main()
