from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (
    ROOT
    / "jobs"
    / "templates"
    / "l3-pure-failed-conversion-weights-causal-ab-v1.sh"
)


class FailedConversionWeightsCausalAbTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = TEMPLATE.read_text(encoding="utf-8")

    def test_immutable_turnover_and_f2m_sources_are_authenticated(self) -> None:
        for literal in (
            "EXPECTED_SOURCE_ATTEMPT",
            "EXPECTED_SOURCE_CODE_SHA",
            "SOURCE_CORPUS_SHA",
            "SOURCE_META_SHA",
            "SOURCE_MODEL_SHA",
            "EXPECTED_M1_ATTEMPT",
            "EXPECTED_M1_CODE_SHA",
            "F2M_MODEL_SHA",
            "artefacts/turnover1to1.jnnw.gz=turnover.jnnw.gz",
            "artefacts/turnover1to1.jsm.gz=turnover.jsm.gz",
            "artefacts/f2m.pjtw.gz=f2m.pjtw.gz",
            "TURNOVER split reproduction drift",
        ):
            self.assertIn(literal, self.text)

    def test_only_factor_is_failed_conversion_weight(self) -> None:
        for literal in (
            "FAILED_WEIGHT=2",
            "fit-only DOE",
            "SOURCE_ONLY_IMMUTABLE_TURNOVER",
            "ONE_FACTOR_ONLY",
            "NO_SELFPLAY_GENERATION",
            "EXTERNAL_TEACHER_INPUTS",
            "--failed-weight",
            "--sample-weights",
            "--weight-normalization mean-train-1",
            "--weight-min 1",
            "--weights-report",
            '"single_factor": "train_failed_conversion_weight"',
            '"oversampling": False',
        ):
            self.assertIn(literal, self.text)
        self.assertNotIn("--gen-data", self.text)
        self.assertNotIn("--topk", self.text.lower())
        self.assertNotIn("--prior-mean", self.text)

    def test_split_features_and_fit_are_common(self) -> None:
        self.assertEqual(
            self.text.count(
                '"$J" --dump-eval-features "$W/turnover.fit.jnnw" '
                '"$W/turnover.feat"'
            ),
            1,
        )
        for literal in (
            "HOLDOUT_MOD=10",
            "SPLIT_SEED=577215",
            "L2=3e-5",
            "MAXIT=1000",
            "LBFGS_MAXCOR=20",
            "LBFGS_GTOL=1e-3",
            "CHUNK=20000",
            '--data "$W/turnover.fit.jnnw"',
            '--feat "$W/turnover.feat"',
            '--warm-start "$W/F2M.pjtw"',
            '--holdout-count "$HOLDOUT"',
        ):
            self.assertIn(literal, self.text)

    def test_control_is_a_strict_historical_reproduction_gate(self) -> None:
        for literal in (
            "uniform_after_normalization",
            "sw_all_used",
            "CONTROL did not take exact legacy unweighted path",
            "all-ones CONTROL failed byte-level TURNOVER reproduction",
            "CONTROL reproduces historical TURNOVER model byte-for-byte",
        ):
            self.assertIn(literal, self.text)
        self.assertLess(
            self.text.index("fit_arm control 1"),
            self.text.index("fit_arm treatment"),
        )
        self.assertLess(
            self.text.index(
                "all-ones CONTROL failed byte-level TURNOVER reproduction"
            ),
            self.text.index("fit_arm treatment"),
        )

    def test_certificate_cannot_promote_or_chain(self) -> None:
        for literal in (
            "L3_PURE_FAILED_CONVERSION_WEIGHTS_CAUSAL_AB_ARMS_READY",
            '"scientific_result": False',
            '"promotion_authorized": False',
            '"automatic_next_job": None',
            "PROMOTION_AUTHORIZED__FALSE",
            "AUTOMATIC_NEXT_JOB__NULL",
        ):
            self.assertIn(literal, self.text)
        self.assertNotIn("git push", self.text)

    def test_embedded_python_is_syntax_valid(self) -> None:
        blocks = re.findall(r"<<'PY'\n(.*?)\nPY", self.text, flags=re.S)
        self.assertGreaterEqual(len(blocks), 7)
        for block in blocks:
            ast.parse(block)


if __name__ == "__main__":
    unittest.main()
