from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs/templates/l3-curriculum-error-root-trajectory-screen-v1.sh"
SPEC = ROOT / "docs/experiments/L3_CURRICULUM_ERROR_ROOT_TRAJECTORY_SCREEN_V1_20260822.md"


class CurriculumErrorRootTrajectoryTemplateTests(unittest.TestCase):
    def test_template_pins_source_and_zero_node_contract(self) -> None:
        text = TEMPLATE.read_text(encoding="utf-8")
        for needle in (
            'SOURCE_JOB="cpx62-1476-l3-curriculum-search-error-atlas-v1"',
            'SOURCE_ATTEMPT="20260822T170608Z-92a7f393"',
            'SOURCE_CODE="92a7f393e26d41a1047e6660bee8724a9a64a5aa"',
            'NO_SELFPLAY', 'NO_FIT', 'NO_STRENGTH_GAMES', 'NO_FROZEN_READ',
            'NO_AUTOMATIC_PROMOTION', 'NO_AUTOMATIC_CONTINUATION',
            '--split-seed 2026082228', '--bootstrap-seed 2026082229',
            '--bootstrap-samples 10000', 'OUTER_CONFIRM_READS__0',
            'ADDITIONAL_SEARCH_NODES__0', 'PRODUCTION_RULE_AUTHORIZED__FALSE',
            'JASS_CURRICULUM_ERROR_ROOT_TRAJECTORY_SCREEN_READY',
        ):
            self.assertIn(needle, text)

    def test_spec_forbids_production_before_fresh_confirmation(self) -> None:
        text = SPEC.read_text(encoding="utf-8")
        for needle in (
            "douze candidats", "outer-confirm 1476 est consommé", "zéro nœud additionnel",
            "n’autorise aucune règle de production", "campagne entièrement fraîche",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
