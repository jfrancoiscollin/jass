#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    ROOT / "jobs/templates/l3-curriculum-error-fresh-tail-autopsy-v1.sh"
).read_text(encoding="utf-8")


class FreshTailAutopsyTemplateTests(unittest.TestCase):
    def test_job_is_read_only_discovery_and_cannot_continue(self):
        for marker in (
            "READ_ONLY_TAIL_AUTOPSY:-0}", "REPLAY_1517_BIT_EXACT:-0}",
            "FIT_IMMUTABLE_1508_ONLY:-0}", "DIAGNOSTIC_RESIDUAL_FIT_ALLOWED:-0}",
            "NO_FIT_ON_FRESH:-0}", "NO_NEW_EXACT_TARGETS:-0}", "NO_SELFPLAY:-0}",
            "NO_PATTERNEVAL_FIT:-0}", "NO_STRENGTH_GAMES:-0}", "NO_FROZEN_READ:-0}",
            "NO_AUTOMATIC_PROMOTION:-0}", "NO_AUTOMATIC_CONTINUATION:-0}",
            "NEW_EXACT_TARGETS__0", "FRESH_LABEL_FITS__0", "STRENGTH_GAMES__0",
            "PRODUCTION_REFIT_AUTHORIZED__FALSE", "PROMOTION_AUTHORIZED__FALSE",
            "FRESH_1517_REUSE_FOR_VALIDATION__FORBIDDEN",
        ):
            self.assertIn(marker, TEMPLATE)
        for forbidden in (
            "run_match", "queue/pending", "l3_curriculum_search_error_atlas.py atlas",
            "fresh-powered-confirmation-v1.sh", "pattern_jass/tools/gen_patterns.py",
        ):
            self.assertNotIn(forbidden, TEMPLATE)

    def test_fetches_only_materialized_1508_1517_and_1517a_inputs(self):
        self.assertIn("artefacts/gate-fit-pairs.json=training-pairs.json", TEMPLATE)
        self.assertIn("artefacts/fresh-confirmation-pairs.json=fresh-pairs.json", TEMPLATE)
        self.assertIn("artefacts/fresh-target-cache.json=fresh-target-cache.json", TEMPLATE)
        self.assertEqual(
            TEMPLATE.count("artefacts/gate-fit-atlas-shards/shard-$shard.json"), 1
        )
        self.assertEqual(
            TEMPLATE.count("artefacts/fresh-confirmation-atlas-shards/shard-$shard.json"), 1
        )
        self.assertIn("--file artefacts/JASS_CONTROL_SUMMARY.json=final-audit.json", TEMPLATE)

    def test_tool_is_launched_as_package_module(self):
        self.assertIn(
            "python3 -m jobs.tools.l3_curriculum_error_fresh_tail_autopsy", TEMPLATE
        )


if __name__ == "__main__":
    unittest.main()
