#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEXT = (
    ROOT
    / "jobs/templates/l3-curriculum-error-residual-power-extension-preregistration-v1.sh"
).read_text(encoding="utf-8")


class ResidualPowerExtensionPreregistrationTemplateTests(unittest.TestCase):
    def test_preregistration_is_read_only_and_stops(self):
        for marker in (
            "NO_FIT:-0}",
            "NO_NEW_TARGETS:-0}",
            "NO_HOLDOUT_READ:-0}",
            "NO_SELFPLAY:-0}",
            "NO_PATTERNEVAL_FIT:-0}",
            "NO_STRENGTH_GAMES:-0}",
            "NO_FROZEN_READ:-0}",
            "NO_AUTOMATIC_PROMOTION:-0}",
            "NO_AUTOMATIC_CONTINUATION:-0}",
            "FRESH_TARGET_RECONSTRUCTION_AUTHORIZED__FALSE",
            "HISTORICAL_HOLDOUT_READ_AUTHORIZED__FALSE",
            "PRODUCTION_RULE_AUTHORIZED__FALSE",
            "AUTOMATIC_CONTINUATION__FALSE",
        ):
            self.assertIn(marker, TEXT)
        for forbidden in ("run_match", "queue/pending", "selfplay", "feature-audit"):
            self.assertNotIn(forbidden, TEXT)

    def test_only_certified_negative_screen_and_audit_are_fetched(self):
        self.assertIn("artefacts/ridge-path-screen.json=screen.json", TEXT)
        self.assertIn("artefacts/JASS_CONTROL_SUMMARY.json=audit.json", TEXT)
        self.assertNotIn("gate-fit-atlas", TEXT)
        self.assertNotIn("matched-pairs", TEXT)
        self.assertIn(
            "python3 -m jobs.tools.l3_curriculum_error_residual_power_extension_preregistration",
            TEXT,
        )


if __name__ == "__main__":
    unittest.main()
