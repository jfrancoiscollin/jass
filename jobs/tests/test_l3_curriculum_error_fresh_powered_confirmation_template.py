from pathlib import Path
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-curriculum-error-fresh-powered-confirmation-v1.sh"
)


class FreshPoweredConfirmationTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_fixed_hypothesis_and_power_are_explicit(self) -> None:
        for token in (
            "pairs=300 alpha=300 cap=100 mode=strict_both_change threshold=10",
            "FIRST_VALID_300_ONLY",
            "TARGET_STATES_PER_ROUND=256",
            "MAX_ROUNDS=32",
            "fresh-powered-confirmation.json",
        ):
            self.assertIn(token, self.text)

    def test_fresh_games_are_subset_fetched_and_moves_normalized(self) -> None:
        for token in (
            "fetch_result_subset.py",
            "required-games.txt",
            "lossless-historical-move-normalization",
            "fresh-confirmation-catalog.json",
        ):
            self.assertIn(token, self.text)

    def test_exact_targets_are_batched_then_repacked(self) -> None:
        self.assertIn("l3_curriculum_search_error_atlas.py atlas", self.text)
        self.assertIn("exact-label-first-300-valid-pairs-in-frozen-order", self.text)
        self.assertIn("finalize-repacked-authenticated-fresh-atlas", self.text)
        self.assertIn("fresh-confirmation-atlas-shards", self.text)

    def test_fit_and_continuation_guards_are_fail_closed(self) -> None:
        for token in (
            "FIT_IMMUTABLE_1508_ONLY",
            "NO_FIT_ON_FRESH",
            "NO_PATTERNEVAL_FIT",
            "NO_STRENGTH_GAMES",
            "NO_NEW_SELFPLAY",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "NO_AUTOMATIC_CONTINUATION",
        ):
            self.assertIn(token, self.text)


if __name__ == "__main__":
    unittest.main()
