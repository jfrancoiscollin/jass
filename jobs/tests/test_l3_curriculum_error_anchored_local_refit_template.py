#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    ROOT / "jobs/templates/l3-curriculum-error-anchored-local-refit-v1.sh"
).read_text(encoding="utf-8")


class AnchoredLocalRefitTemplateTests(unittest.TestCase):
    def test_single_fit_is_anchored_and_seals_oos(self) -> None:
        for marker in (
            "PREREGISTERED_SINGLE_FIT:-0}",
            "CONFIRMED_600_TRAINING_ONLY:-0}",
            "NO_OOS_READ:-0}",
            "NO_NEW_TARGETS:-0}",
            "NO_HYPERPARAMETER_SEARCH:-0}",
            "PATTERNEVAL_BYTE_IDENTICAL:-0}",
            "OUTSIDE_SUPPORT_BYTE_IDENTICAL:-0}",
            "NO_SELFPLAY:-0}",
            "NO_STRENGTH_GAMES:-0}",
            "NO_FROZEN_READ:-0}",
            "NO_PROMOTION:-0}",
            "NO_AUTOMATIC_CONTINUATION:-0}",
            "MODEL_CANDIDATES_FIT__1",
            "PATTERNEVAL_FITS__0",
            "OOS_READS__0",
            "STRENGTH_GAMES__0",
            "STRENGTH_GATE_AUTHORIZED__FALSE",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_CONTINUATION__FALSE",
        ):
            self.assertIn(marker, TEMPLATE)
        for forbidden in ("run_match", "queue/pending", "oos-pairs.json", "selfplay --"):
            self.assertNotIn(forbidden, TEMPLATE)

    def test_fetches_only_training_and_confirmed_training_inputs(self) -> None:
        self.assertIn("artefacts/gate-fit-pairs.json=historical-pairs.json", TEMPLATE)
        self.assertIn("artefacts/fresh-confirmation-pairs.json=confirmed-pairs.json", TEMPLATE)
        self.assertIn("fresh-confirmation-atlas-shards", TEMPLATE)
        self.assertNotIn("outer-confirm", TEMPLATE)
        self.assertNotIn("feature-audit", TEMPLATE)

    def test_tool_is_launched_as_module(self) -> None:
        self.assertIn(
            "python3 -m jobs.tools.l3_curriculum_error_anchored_local_refit",
            TEMPLATE,
        )


if __name__ == "__main__":
    unittest.main()
