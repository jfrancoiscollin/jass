from pathlib import Path
import unittest


TEXT = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-curriculum-error-action-ranker-screen-v1.sh"
).read_text(encoding="utf-8")


class ActionRankerTemplateTests(unittest.TestCase):
    def test_source_is_fresh_authenticated_and_pattern_buckets_stay_closed(self):
        for token in (
            "ACTION_SOURCE_JOB",
            "JASS_CURRICULUM_ERROR_ACTION_SOURCE_READY",
            "pool_seeds')!=[2026082231,2026082232]",
            "split_seed')!=2026082233",
            "pattern_bucket_aggregate_reads",
            "PATTERNEVAL_FITS__0",
        ):
            self.assertIn(token, TEXT)

    def test_ranker_protocol_is_fixed_before_source_result(self):
        for token in (
            "l3_curriculum_error_action_ranker.py",
            "--bootstrap-samples \"$BOOTSTRAP\"",
            "pairwise-ridge-inner-oof-then-outer-confirm-if-authorized",
            "OUTER_CONFIRM_PAIRS_READ__",
            "PRODUCTION_RULE_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, TEXT)

    def test_no_training_or_force_or_frozen_path(self):
        self.assertNotIn("train_stream_exact.py", TEXT)
        self.assertNotIn("run_jass_gate_bounded.py", TEXT)
        for guard in (
            "NO_SELFPLAY",
            "NO_PATTERNEVAL_FIT",
            "NO_STRENGTH_GAMES",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
        ):
            self.assertIn(guard, TEXT)


if __name__ == "__main__":
    unittest.main()
