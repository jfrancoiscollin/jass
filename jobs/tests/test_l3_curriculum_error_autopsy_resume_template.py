from pathlib import Path
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-curriculum-error-autopsy-resume-v1.sh"
).read_text(encoding="utf-8")


class CurriculumErrorAutopsyResumeTemplateTests(unittest.TestCase):
    def test_reuses_exact_sealed_selection_without_replaying_campaign(self):
        for token in (
            'SOURCE_JOB="cpx62-1468-l3-curriculum-error-autopsy-v1"',
            'SOURCE_ATTEMPT="20260822T134756Z-746421c7"',
            "selection.get('decisions')!=79110",
            "exact_state_components_sha256_parity",
            "CAMPAIGN_REPLAYED__FALSE",
            "NEW_SELFPLAY__0",
        ):
            self.assertIn(token, TEMPLATE)
        self.assertNotIn("run_jass_gate_bounded.py", TEMPLATE)

    def test_preserves_original_science_and_lossless_capture_guard(self):
        for token in (
            "TEACHER_DEPTH=10",
            "JUDGE_DEPTH=12",
            "MAX_PROJECTED_MINUTES=480",
            "--min-error-openings 64",
            "--min-confirmed-buckets 8",
            "historical_endpoint_only_captures_resolved",
            "successor_state_validated",
            "dump_legal_endpoints_and_authenticated_successor_state",
            '--transitions "$ART/error-transitions.json"',
            'GAME_SPECS',
            "rel.replace('/', '__')",
            "source-games-flat",
            "os.link(source,destination)",
            "resolution.get('ambiguous')!=0",
            "JASS_CURRICULUM_ERROR_REGION_CONFIRMED",
        ):
            self.assertIn(token, TEMPLATE)

    def test_scope_guards_forbid_fit_frozen_and_promotion(self):
        for token in (
            "NO_SELFPLAY",
            "NO_FROZEN_READ",
            "NO_AUTOMATIC_PROMOTION",
            "FITS__0",
            "FROZEN_COHORTS_READ__0",
            "PROMOTION_AUTHORIZED__FALSE",
        ):
            self.assertIn(token, TEMPLATE)
        self.assertNotIn("train_stream_exact.py", TEMPLATE)


if __name__ == "__main__":
    unittest.main()
