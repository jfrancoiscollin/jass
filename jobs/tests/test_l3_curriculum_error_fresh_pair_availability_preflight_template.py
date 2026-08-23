from pathlib import Path
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-curriculum-error-fresh-pair-availability-preflight-v1.sh"
)


class FreshPairAvailabilityTemplateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_target_free_scope_and_cardinality_are_explicit(self) -> None:
        for token in (
            "NOPEN=1920",
            "games_dumped=%s/7680",
            "NO_EXACT_ACTION_TARGETS",
            "FRESH_TRAJECTORY_MINING_ONLY",
            "NEW_TARGETS__0",
            "EXACT_ACTION_VALUE_READS__0",
            "NEW_SELFPLAY__7680",
        ):
            self.assertIn(token, self.text)

    def test_fresh_pools_exclude_discovery_sources(self) -> None:
        for token in (
            "cpx62-1492-l3-curriculum-error-autopsy-v1",
            "cpx62-1504-l3-curriculum-error-autopsy-v1",
            "--exclude data/dilf_combinations.fen",
            "POOL_SEED_1=2026082264",
            "POOL_SEED_2=2026082265",
        ):
            self.assertIn(token, self.text)

    def test_only_root_profiles_are_computed(self) -> None:
        self.assertIn("l3_curriculum_search_error_atlas.py profile", self.text)
        self.assertNotIn("l3_curriculum_search_error_atlas.py atlas", self.text)
        self.assertNotIn("l3_curriculum_error_learning.py worker", self.text)
        self.assertNotIn("--judge-depth", self.text)
        self.assertNotIn("train --", self.text)

    def test_no_force_frozen_or_promotion(self) -> None:
        for token in (
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "NO_AUTOMATIC_CONTINUATION",
            "PROMOTION_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
