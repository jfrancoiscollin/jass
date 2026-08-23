#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    ROOT
    / "jobs/templates/l3-curriculum-error-anchored-local-refit-preregistration-v1.sh"
).read_text(encoding="utf-8")


class AnchoredLocalRefitPreregistrationTemplateTests(unittest.TestCase):
    def test_no_compute_preregistration_is_fail_closed(self) -> None:
        for marker in (
            "JOINT_PASS_REQUIRED:-0}",
            "NO_OOS_READ:-0}",
            "NO_NEW_TARGETS:-0}",
            "NO_FIT:-0}",
            "NO_SELFPLAY:-0}",
            "NO_STRENGTH_GAMES:-0}",
            "NO_FROZEN_READ:-0}",
            "NO_PROMOTION:-0}",
            "NO_AUTOMATIC_CONTINUATION:-0}",
            "OOS_READS__0",
            "PATTERNEVAL_FITS__0",
            "PRODUCTION_MODEL_FITS__0",
            "STRENGTH_GAMES__0",
            "ANCHORED_LOCAL_REFIT_AUTHORIZED__TRUE",
            "OOS_CAMPAIGN_AUTHORIZED__FALSE",
            "STRENGTH_GATE_AUTHORIZED__FALSE",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_CONTINUATION__FALSE",
        ):
            self.assertIn(marker, TEMPLATE)
        for forbidden in (
            "run_match",
            "queue/pending",
            "fresh-confirmation-pairs.json",
            "gate-fit-pairs.json",
            "build-l3",
        ):
            self.assertNotIn(forbidden, TEMPLATE)

    def test_fetches_only_two_terminal_summaries(self) -> None:
        self.assertEqual(
            TEMPLATE.count("--file artefacts/JASS_CONTROL_SUMMARY.json="), 2
        )
        self.assertNotIn("exact-target", TEMPLATE)
        self.assertNotIn("atlas-shard", TEMPLATE)

    def test_tool_is_launched_as_module(self) -> None:
        self.assertIn(
            "python3 -m jobs.tools.l3_curriculum_error_anchored_local_refit_preregistration",
            TEMPLATE,
        )


if __name__ == "__main__":
    unittest.main()
