# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-intervention-activation-audit-v1.sh"


class Context2InterventionActivationTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_authenticates_all_fixed_sources(self) -> None:
        for token in (
            "cpx62-1409-l3-context2-intervention-corpus-v1",
            "home-1395-l3-context2-knob-attribution-v1",
            "home-1397-l3-context2-fixed-contribution-audit-v1",
            "cpx62-1408-l3-context2-intervention-plan-v1",
            "20260818T184956Z-3465ec72",
        ):
            self.assertIn(token, self.text)

    def test_runs_realized_screen_without_fit_or_force(self) -> None:
        for token in (
            "--dump-conditional-context-v2",
            "l3_context2_activation_census.py analyze",
            "l3_context2_intervention_activation_audit.py",
            "FITS_RUN__0",
            "FORCE_GAMES_PLAYED__0",
            "FROZEN_READ__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(token, self.text)
        self.assertNotIn("--fit-pattern-eval", self.text)
        self.assertNotIn("--frozen", self.text)


if __name__ == "__main__":
    unittest.main()
