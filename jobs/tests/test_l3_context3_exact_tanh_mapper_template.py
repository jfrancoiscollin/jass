import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-context3-exact-tanh-mapper-screen-v1.sh"


class Context3ExactTanhMapperTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_immutable_sources(self) -> None:
        self.assertIn("cpx62-1409-l3-context2-intervention-corpus-v1", self.text)
        self.assertIn("20260819T070756Z-95059c8e", self.text)
        self.assertIn("JASS_CONTEXT3_INDEPENDENT_INFORMATION_SCREEN_PASSED", self.text)
        self.assertIn("split drift", self.text)

    def test_exact_three_mapper_protocol_is_fixed(self) -> None:
        self.assertIn("mapper_fits=18", self.text)
        self.assertIn("--fold-seed 20260811", self.text)
        self.assertIn("--shuffle-seed 2026081903", self.text)
        self.assertIn("--bootstrap-replicates 5000", self.text)
        self.assertIn("len(r.get('guards',{}))!=11", self.text)

    def test_forbidden_actions_remain_zero(self) -> None:
        for marker in (
            "SELFPLAY_GENERATED__FALSE",
            "PATTERNEVAL_FITS_RUN__0",
            "FORCE_GAMES_PLAYED__0",
            "FROZEN_READ__FALSE",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(marker, self.text)
        self.assertNotRegex(self.text, re.compile(r"--frozen|frozen_test", re.I))


if __name__ == "__main__":
    unittest.main()
