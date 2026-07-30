from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "jobs" / "templates" / "l3-pure-reverse-seed-readout-v1.sh"


class ReverseSeedReadoutTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_source_and_models_are_authenticated(self) -> None:
        for literal in (
            "EXPECTED_SOURCE_ATTEMPT",
            "EXPECTED_SOURCE_CODE_SHA",
            "EXPECTED_CONTROL_MODEL_SHA",
            "EXPECTED_TREATMENT_MODEL_SHA",
            "artefacts/control.pjtw.gz=CONTROL.pjtw.gz",
            "artefacts/treatment.pjtw.gz=TREATMENT.pjtw.gz",
            "L3_PURE_REVERSE_SEED_CAUSAL_AB_ARMS_READY",
            'fit", {}).get("converged")',
        ):
            self.assertIn(literal, self.text)

    def test_force_is_paired_two_view_and_preregistered_power(self) -> None:
        for literal in (
            'NOPEN="${NOPEN:-1500}"',
            'OPENING_SEED="${OPENING_SEED:-1087001}"',
            "GAMES_PER_VIEW=$((NOPEN * 2))",
            "for view in q00 native",
            "--pairs 1",
            '--depth "$FORCE_DEPTH"',
            '--movetime "$MOVETIME"',
            "TREATMENT-vs-CONTROL",
        ):
            self.assertIn(literal, self.text)

    def test_openings_are_fresh_against_prior_readouts(self) -> None:
        for literal in (
            "--exclude data/dilf_combinations.fen",
            '--exclude "$IN/prior-topk-openings.fen"',
            '--exclude "$IN/prior-hard-openings.fen"',
            "EXPECTED_TOPK_OPENINGS_ATTEMPT",
            "EXPECTED_HARD_OPENINGS_ATTEMPT",
            "overlap_records",
        ):
            self.assertIn(literal, self.text)

    def test_scale4m_has_distinct_training_and_opening_contracts(self) -> None:
        for literal in (
            'READOUT_STAGE="${READOUT_STAGE:-base2m}"',
            "scale4m)",
            "L3_PURE_REVERSE_SEED_SCALE4M_CAUSAL_AB_ARMS_READY",
            "EXPECTED_TRAINING_RECORDS=4000000",
            "EXPECTED_OPENING_SEED=1113001",
            'OPENING_STEM="reverse-seed-scale4m-readout-openings"',
            "EXPECTED_REVERSE_OPENINGS_ATTEMPT",
            "EXPECTED_FAILED_X2_OPENINGS_ATTEMPT",
            "EXPECTED_BLEND_OPENINGS_ATTEMPT",
            '--exclude "$IN/prior-reverse-openings.fen"',
            '--exclude "$IN/prior-failed-x2-openings.fen"',
            '--exclude "$IN/prior-blend-openings.fen"',
            '--experiment-stage "$READOUT_STAGE"',
            '--expected-records-per-arm "$EXPECTED_TRAINING_RECORDS"',
        ):
            self.assertIn(literal, self.text)

    def test_no_promotion_or_automatic_chaining(self) -> None:
        for literal in (
            "NO_AUTOMATIC_CONTINUATION",
            "SCIENTIFIC_RESULT__TRUE",
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
            "scientific_result=true promotion=false automatic_next_job=null",
        ):
            self.assertIn(literal, self.text)
        self.assertNotIn("git push", self.text)

    def test_embedded_python_is_syntax_valid(self) -> None:
        blocks = re.findall(r"<<'PY'\n(.*?)\nPY", self.text, flags=re.S)
        self.assertGreaterEqual(len(blocks), 2)
        for block in blocks:
            ast.parse(block)


if __name__ == "__main__":
    unittest.main()
