from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-pure-hard-replay-readout-v1.sh"


class HardReplayReadoutTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_source_and_model_identity_are_pinned(self) -> None:
        for literal in (
            "EXPECTED_SOURCE_ATTEMPT",
            "EXPECTED_SOURCE_CODE_SHA",
            "EXPECTED_UNIFORM_MODEL_SHA",
            "EXPECTED_HARD_MODEL_SHA",
            "artefacts/control.pjtw.gz=UNIFORM_REPLAY.pjtw.gz",
            "artefacts/treatment.pjtw.gz=HARD_REPLAY.pjtw.gz",
            'optimizer", {}).get("success")',
        ):
            self.assertIn(literal, self.text)

    def test_force_is_powered_paired_two_view_and_disjoint(self) -> None:
        for literal in (
            'NOPEN="${NOPEN:-2500}"',
            'OPENING_SEED="${OPENING_SEED:-1069001}"',
            "--exclude data/dilf_combinations.fen",
            '--exclude "$IN/prior-1024-openings.fen"',
            "for view in q00 native",
            "--pairs 1",
            '--depth "$FORCE_DEPTH"',
            '--movetime "$MOVETIME"',
            "HARD_REPLAY-vs-UNIFORM_REPLAY",
        ):
            self.assertIn(literal, self.text)

    def test_conversion_is_paired_and_uses_corrected_defender(self) -> None:
        for literal in (
            'FIXED_DEFENDER_CODE_SHA="9c1d1e8eaaa5b9bbd86105f7f9807a3033784186"',
            "for stratum in p3_mince p4_egal",
            "for arm in UNIFORM_REPLAY HARD_REPLAY",
            "--require-position-results",
            '--defender-jass "$J32FIXED"',
            '--defender-pattern "$W/GEN2.pjtw"',
        ):
            self.assertIn(literal, self.text)

    def test_no_automatic_promotion_or_chaining(self) -> None:
        for literal in (
            "NO_AUTOMATIC_CONTINUATION",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
            "promotion=false automatic_next_job=null",
        ):
            self.assertIn(literal, self.text)
        self.assertNotIn("git push", self.text)


if __name__ == "__main__":
    unittest.main()
