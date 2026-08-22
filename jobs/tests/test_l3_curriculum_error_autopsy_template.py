from pathlib import Path
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-curriculum-error-autopsy-v1.sh"
).read_text(encoding="utf-8")


class CurriculumErrorAutopsyTemplateTests(unittest.TestCase):
    def test_preregistered_science_contract(self):
        for token in (
            "NOPEN=384",
            "POOL_SEED_1=2026082213",
            "POOL_SEED_2=2026082214",
            "TEACHER_DEPTH=10",
            "JUDGE_DEPTH=12",
            "--dump-games-dir",
            "--min-error-openings 64",
            "--min-confirmed-buckets 8",
            "JASS_CURRICULUM_ERROR_REGION_CONFIRMED",
        ):
            self.assertIn(token, TEMPLATE)

    def test_job_is_autopsy_only(self):
        for token in (
            "FITS__0",
            "STRENGTH_GAMES__0",
            "FROZEN_COHORTS_READ__0",
            "PROMOTION_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, TEMPLATE)
        self.assertNotIn("train_stream_exact.py", TEMPLATE)

    def test_two_complete_campaigns_feed_one_sealed_split(self):
        self.assertIn('--games-dir "$GAMES1" --games-dir "$GAMES2"', TEMPLATE)
        self.assertIn("ALL_GAMES_DUMPED__1536", TEMPLATE)
        self.assertIn("SPLIT_SEED=2026082215", TEMPLATE)


if __name__ == "__main__":
    unittest.main()
