import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-curriculum-error-action-flip-tail-autopsy-v1.sh"


class ActionFlipTailAutopsyTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_six_sources_and_reproduction_are_fail_closed(self):
        for token in (
            "verified-training-source.json",
            "verified-fresh-source.json",
            "verified-subspace-source.json",
            "verified-target-source.json",
            "verified-bucket-source.json",
            "verified-action-source.json",
            "REPLAY_1536_BIT_EXACT",
            "POSTHOC_RULES_DIAGNOSTIC_ONLY",
        ):
            self.assertIn(token, self.text)

    def test_no_mutating_scientific_action_is_allowed(self):
        for token in (
            "NO_NEW_EXACT_TARGETS", "NO_SELFPLAY", "NO_PATTERNEVAL_FIT",
            "NO_STRENGTH_GAMES", "NO_FROZEN_READ", "NO_AUTOMATIC_PROMOTION",
            "ANCHORED_REFIT_AUTHORIZED__FALSE", "PRODUCTION_MODEL_AUTHORIZED__FALSE",
            "STRENGTH_GATE_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, self.text)

    def test_terminal_exposes_loss_and_weight_axis(self):
        for token in ("COUNTS__", "LOSS__", "DESCRIPTIVE_RULES__", "NEGATIVE_WEIGHT_AXIS__"):
            self.assertIn(token, self.text)
        self.assertNotIn("strength-match", self.text)


if __name__ == "__main__":
    unittest.main()
