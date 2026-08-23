#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    ROOT
    / "jobs/templates/l3-curriculum-error-residual-stable-subspace-screen-v1.sh"
).read_text(encoding="utf-8")


class ResidualStableSubspaceScreenTemplateTests(unittest.TestCase):
    def test_screen_is_sealed_read_only_and_cannot_continue(self) -> None:
        for marker in (
            "TRAINING_ONLY_REUSE_TARGETS:-0}",
            "DIAGNOSTIC_RESIDUAL_FITS_ALLOWED:-0}",
            "NO_NEW_ACTION_TARGETS:-0}",
            "NO_FRESH_LABEL_READ:-0}",
            "NO_FEATURE_AUDIT_READ:-0}",
            "NO_OUTER_CONFIRM_READ:-0}",
            "NO_SELFPLAY:-0}",
            "NO_PATTERNEVAL_FIT:-0}",
            "NO_PRODUCTION_FIT:-0}",
            "NO_STRENGTH_GAMES:-0}",
            "NO_FROZEN_READ:-0}",
            "NO_AUTOMATIC_PROMOTION:-0}",
            "NO_AUTOMATIC_CONTINUATION:-0}",
            "ANCHORED_REFIT_AUTHORIZED__FALSE",
            "STRENGTH_GATE_AUTHORIZED__FALSE",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_CONTINUATION__FALSE",
        ):
            self.assertIn(marker, TEMPLATE)
        for forbidden in (
            "run_match",
            "queue/pending",
            "feature-audit-v1.sh",
            "outer-confirm-atlas",
            "l3_curriculum_search_error_atlas.py atlas",
        ):
            self.assertNotIn(forbidden, TEMPLATE)

    def test_only_materialized_1508_gate_fit_data_are_fetched(self) -> None:
        self.assertIn("artefacts/gate-fit-pairs.json=gate-fit-pairs.json", TEMPLATE)
        self.assertEqual(
            TEMPLATE.count("artefacts/gate-fit-atlas-shards/shard-$shard.json"),
            1,
        )
        for forbidden in (
            "matched-pairs.json",
            "feature-audit-atlas",
            "outer-confirm-pairs",
            "fresh-pair",
        ):
            self.assertNotIn(forbidden, TEMPLATE)

    def test_tool_is_launched_as_package_module(self) -> None:
        self.assertIn(
            "python3 -m jobs.tools.l3_curriculum_error_residual_stable_subspace_screen",
            TEMPLATE,
        )

    def test_terminal_counters_are_fail_closed(self) -> None:
        for marker in (
            "NEW_ACTION_TARGETS__0",
            "FRESH_LABEL_READS__0",
            "FEATURE_AUDIT_ACTION_VALUE_READS__0",
            "OUTER_CONFIRM_ACTION_VALUE_READS__0",
            "PATTERNEVAL_FITS__0",
            "PRODUCTION_MODEL_FITS__0",
            "STRENGTH_GAMES__0",
            "NEW_SELFPLAY__0",
            "FROZEN_READS__0",
        ):
            self.assertIn(marker, TEMPLATE)


if __name__ == "__main__":
    unittest.main()
