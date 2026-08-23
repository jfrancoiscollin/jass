import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-curriculum-error-bucket-treatment-atlas-v1.sh"


class BucketTreatmentAtlasTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_fail_closed_sources_and_cross_pool_guards(self):
        for token in (
            "verified-training-source.json",
            "verified-fresh-source.json",
            "verified-subspace-source.json",
            "verified-target-source.json",
            "FAMILYWISE_1000_SHAMS",
            "CROSS_POOL_ONLY",
            "REPLAY_1524_BIT_EXACT",
        ):
            self.assertIn(token, self.text)

    def test_forbidden_actions_remain_zero(self):
        for token in (
            "NO_NEW_EXACT_TARGETS",
            "NO_SELFPLAY",
            "NO_PATTERNEVAL_FIT",
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "ANCHORED_REFIT_AUTHORIZED__FALSE",
            "PRODUCTION_MODEL_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, self.text)

    def test_terminal_is_discovery_only(self):
        self.assertIn("NEW_FRESH_POOL_PREREGISTRATION_RECOMMENDED", self.text)
        self.assertIn("production=false", self.text)
        self.assertNotIn("strength-match", self.text)


if __name__ == "__main__":
    unittest.main()
