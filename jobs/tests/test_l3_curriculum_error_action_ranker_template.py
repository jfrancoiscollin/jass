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
            'EXPECTED_SOURCE_POOL_SEED_1="${EXPECTED_SOURCE_POOL_SEED_1:-2026082231}"',
            'EXPECTED_SOURCE_POOL_SEED_2="${EXPECTED_SOURCE_POOL_SEED_2:-2026082232}"',
            'EXPECTED_SOURCE_SPLIT_SEED="${EXPECTED_SOURCE_SPLIT_SEED:-2026082233}"',
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

    def test_coverage_mode_stops_before_action_values_or_ranker_fit(self):
        for token in (
            'COVERAGE_ONLY="${COVERAGE_ONLY:-0}"',
            'BUDGET_ROWS_PER_SPLIT="${BUDGET_ROWS_PER_SPLIT:-1024}"',
            "l3_curriculum_error_paired_coverage_screen.py",
            "paired-image-feature-only-relative-coverage-screen",
            "EXACT_ACTION_VALUE_READS__0",
            "OUTER_CONFIRM_PROFILE_ROWS_EXAMINED__0",
            "RESIDUAL_FIT_AUTHORIZED__FALSE",
            "source-exclude-1492-pool1.json",
            "source-exclude-1492-pool2.json",
        ):
            self.assertIn(token, TEXT)
        coverage_block = TEXT.split('if [ "$COVERAGE_ONLY" = 1 ]; then', 2)[-1].split(
            "stage atlas-cost-preflight", 1
        )[0]
        self.assertIn("exit 0", coverage_block)


if __name__ == "__main__":
    unittest.main()
