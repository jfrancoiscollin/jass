from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "l3-pure-explore-topk-fit-resume-v1.sh"
)


class TopkFitResumeTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_reuses_failed_1017_corpora_without_selfplay(self):
        self.assertIn("--expected-state failed", self.text)
        self.assertIn("artefacts/uniform.jnnw.gz=uniform.jnnw.gz", self.text)
        self.assertIn("artefacts/topk3.jnnw.gz=topk3.jnnw.gz", self.text)
        self.assertNotIn("--gen-data-wdl", self.text)

    def test_source_identity_and_all_four_hashes_are_required(self):
        for name in (
            "EXPECTED_SOURCE_JOB",
            "EXPECTED_SOURCE_ATTEMPT",
            "EXPECTED_SOURCE_CODE_SHA",
            "UNIFORM_JNNW_GZ_SHA",
            "UNIFORM_JSM_GZ_SHA",
            "TOPK3_JNNW_GZ_SHA",
            "TOPK3_JSM_GZ_SHA",
        ):
            self.assertIn(f'${{{name}:?}}', self.text)
        self.assertIn('report.get("result_state") != "failed"', self.text)
        self.assertIn('report.get("exit_code") != 1', self.text)

    def test_splits_are_reproduced_and_counts_are_not_forced_equal(self):
        self.assertIn("deterministic split reproduction drift", self.text)
        self.assertIn(
            'for key in ("split_unit", "holdout_mod", "seed", "tail_is_holdout")',
            self.text,
        )
        self.assertIn('"opening_counts_are_treatment_outcomes": True', self.text)

    def test_fit_recipe_is_identical_for_both_arms(self):
        self.assertIn("for arm in uniform topk3; do", self.text)
        for literal in (
            "--target wdl --loss logistic --color-fold --tempo-stage",
            '--warm-start "$W/PARENT.pjtw"',
            '--l2 "$L2" --max-iter "$MAXIT" --chunk "$CHUNK"',
            '--optimizer-report "$ART/$arm-optimizer.json"',
        ):
            self.assertIn(literal, self.text)
        self.assertIn("L2=3e-5", self.text)
        self.assertIn("MAXIT=1000", self.text)
        self.assertIn("CHUNK=20000", self.text)

    def test_fail_closed_and_no_automatic_promotion(self):
        self.assertIn('die "$arm optimiser did not converge"', self.text)
        self.assertIn('"promotion_authorized": False', self.text)
        self.assertIn('"automatic_next_job": None', self.text)

    def test_embedded_python_parses(self):
        blocks = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY(?:\n|$)", self.text, re.S)
        self.assertEqual(len(blocks), 5)
        for block in blocks:
            ast.parse(block)


if __name__ == "__main__":
    unittest.main()
