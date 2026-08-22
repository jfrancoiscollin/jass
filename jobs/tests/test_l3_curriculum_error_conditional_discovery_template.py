from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-curriculum-error-conditional-discovery-screen-v1.sh"
SPEC = ROOT / "docs/experiments/L3_CURRICULUM_ERROR_CONDITIONAL_DISCOVERY_SCREEN_V1_20260822.md"


class CurriculumErrorConditionalDiscoveryTemplateTests(unittest.TestCase):
    def test_template_pins_negative_source_and_forbidden_actions(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for needle in (
            'SOURCE_JOB="cpx62-1486-l3-curriculum-error-residual-atlas-v1"',
            'SOURCE_ATTEMPT="20260822T193326Z-2e028428"',
            'SOURCE_CODE="2e0284287657ca6b9325cb76e12e28376c873b0c"',
            'NO_SELFPLAY', 'NO_FIT', 'NO_STRENGTH_GAMES', 'NO_FROZEN_READ',
            'NO_AUTOMATIC_PROMOTION', 'NO_AUTOMATIC_CONTINUATION',
            'outer_confirm_pairs_read_for_selection_or_evaluation',
            '--split-seed 2026082226', '--bootstrap-seed 2026082227',
            '--bootstrap-samples 10000', '--total-buckets "$TOTAL_BUCKETS"',
            'JASS_CURRICULUM_ERROR_CONDITIONAL_DISCOVERY_SCREEN_READY',
            'FIT_AUTHORIZED__FALSE', 'OUTER_CONFIRM_READS__0',
            'CANDIDATE_POPULATIONS_CONSIDERED__', 'candidate_preflight',
        ):
            self.assertIn(needle, text)

    def test_spec_requires_fresh_confirmation_before_fit(self) -> None:
        text = SPEC.read_text(encoding="utf-8")
        for needle in ("confirm est désormais consommé", "inner-fit", "entièrement fraîche", "n'autorise aucun refit"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
