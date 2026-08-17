# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-context2-fixed-contribution-audit-v1.sh"


class Context2FixedContributionTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = TEMPLATE.read_text(encoding="utf-8")

    def test_pins_exact_current2m_ctx2_source(self) -> None:
        for token in (
            "home-1373-l3-context2-phase-tactical-fit-v1",
            "20260816T214312Z-9e224d6e",
            "9e224d6ec7583d3c041755a35559bf559d380f8f",
            "ctx2-context.feat.gz",
            "ctx2-aligned-target.npy.gz",
            "conditional-targets.json",
            "cmp \"$ART/split.json\" \"$IN/source-split.json\"",
        ):
            self.assertIn(token, self.script)

    def test_replays_strict_fixed_position_protocol(self) -> None:
        for token in (
            "l3_context2_fixed_contribution_audit.py",
            "same_fixed_positions",
            "fold_local_oof_coefficients_replayed",
            "row_weighting",
            "game_equal",
            "prediction_recovery_max_absolute_error",
            "EXPECTED_RECORDS=2000000",
            "EXPECTED_HOLDOUT=199204",
        ):
            self.assertIn(token, self.script)

    def test_is_read_only_and_uses_persistent_runtime(self) -> None:
        for forbidden in (
            "--gen-data-wdl",
            "train_stream.py",
            "l3_conditional_targets.py \\",
            "pip install",
            "--dump-conditional-context-v2",
            "--force",
        ):
            self.assertNotIn(forbidden, self.script)
        self.assertIn("persistent numeric runtime absent; do not reinstall", self.script)
        self.assertIn("new_selfplay_generated':False", self.script)
        self.assertIn("'fits_run':0", self.script)
        self.assertIn("'promotion_authorized':False", self.script)

    def test_publishes_mechanistic_markers(self) -> None:
        for token in (
            "BASECOMP__RANK_",
            "RAWCOMP__RANK_",
            "PHASESHARE__MID_PPM_",
            "CONCENTRATION__TOP1_PPM_",
            "COEFFICIENT_SIGN_FLIPS__COUNT_",
            "HIGH_CORRELATION_PAIRS_GE_090__COUNT_",
            "TARGET_SHIFT__MEANABS_PPB_",
            "VERDICT__JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDITED",
        ):
            self.assertIn(token, self.script)


if __name__ == "__main__":
    unittest.main()
