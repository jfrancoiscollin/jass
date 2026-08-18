# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-intervention-mapper-screen-v1.sh"


class Context2InterventionMapperTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_corpus_activation_and_current_reference(self) -> None:
        for token in (
            "cpx62-1409-l3-context2-intervention-corpus-v1",
            "cpx62-1410-l3-context2-intervention-activation-audit-v1",
            "home-1397-l3-context2-fixed-contribution-audit-v1",
            "20260818T192156Z-3ef19179",
        ):
            self.assertIn(token, self.text)

    def test_mapper_only_protocol_is_fail_closed(self) -> None:
        for token in (
            "--group-by opening_id",
            "--row-weighting game_equal",
            "--require-convergence",
            "--fold-count 5",
            "l3_context2_fixed_contribution_audit.py",
            "l3_context2_intervention_mapper_screen.py",
            "PATTERNEVAL_FITS_RUN__0",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(token, self.text)
        self.assertNotIn("fit_pattern_eval.py", self.text)
        self.assertNotIn("jass_vs_jass", self.text)


if __name__ == "__main__":
    unittest.main()
