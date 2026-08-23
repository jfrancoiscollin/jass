from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-curriculum-error-loss-first-crossfit-v1.sh"


class LossFirstCrossfitTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_fail_closed_identity_and_host_contracts(self) -> None:
        for token in (
            "EXPECTED_CODE_SHA", "EXPECTED_JOB_ID", "LABEL_JOB", "LABEL_ATTEMPT",
            "LABEL_CODE", "hostname", "nproc", "git merge-base --is-ancestor",
        ):
            self.assertIn(token, self.text)

    def test_exact_preregistered_resampling(self) -> None:
        self.assertRegex(self.text, r"--bootstrap-samples 200000")
        self.assertRegex(self.text, r"--bootstrap-seed 2026082345")
        self.assertRegex(self.text, r"--sham-replicates 1000")
        self.assertRegex(self.text, r"--sham-seed 2026082346")

    def test_no_production_fit_or_games(self) -> None:
        for guard in (
            "CROSS_FIT_SCREEN_ONLY", "NO_PATTERNEVAL_FIT", "NO_STRENGTH_GAMES",
            "NO_SELFPLAY", "NO_FROZEN_READ", "NO_AUTOMATIC_PROMOTION",
            "NO_AUTOMATIC_CONTINUATION",
        ):
            self.assertIn(guard, self.text)
        self.assertIn("PATTERNEVAL_FITS__0", self.text)
        self.assertIn("STRENGTH_GAMES__0", self.text)
        self.assertIn("PRODUCTION_MODEL_AUTHORIZED__FALSE", self.text)

    def test_only_pass_can_authorize_next_refit_design(self) -> None:
        block = re.search(r"if report\['passed'\]:.*?else:", self.text, re.S)
        self.assertIsNotNone(block)
        self.assertIn("ANCHORED_LOCAL_REFIT_AUTHORIZED__TRUE", block.group(0))


if __name__ == "__main__":
    unittest.main()
