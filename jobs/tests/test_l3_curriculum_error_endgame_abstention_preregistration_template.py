#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "jobs/templates/l3-curriculum-error-endgame-abstention-preregistration-v1.sh").read_text(encoding="utf-8")


class EndgameAbstentionPreregistrationTemplateTests(unittest.TestCase):
    def test_read_only_one_hypothesis_contract(self):
        for marker in (
            "READ_ONLY_PREREGISTRATION:-0}", "ONE_HYPOTHESIS_ONLY:-0}",
            "NO_TARGETS:-0}", "NO_FITS:-0}", "NO_SELFPLAY:-0}",
            "NO_STRENGTH_GAMES:-0}", "NO_FROZEN_READ:-0}",
            "NO_AUTOMATIC_PROMOTION:-0}", "NO_AUTOMATIC_CONTINUATION:-0}",
            "HYPOTHESES__1", "FRESH_PAIRS__600", "PHASE_RULE__ABSTAIN_ENDGAME",
            "NEW_TARGETS__0", "FITS__0", "STRENGTH_GAMES__0",
            "PRODUCTION_REFIT_AUTHORIZED__FALSE", "PROMOTION_AUTHORIZED__FALSE",
        ):
            self.assertIn(marker, TEMPLATE)
        for forbidden in ("run_match", "queue/pending", "l3_curriculum_search_error_atlas.py atlas"):
            self.assertNotIn(forbidden, TEMPLATE)


if __name__ == "__main__":
    unittest.main()
