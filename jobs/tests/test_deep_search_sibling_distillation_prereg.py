#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/experiments/L3_DEEP_SEARCH_SIBLING_DISTILLATION_V1_20260826.md"


class DeepSiblingPreregTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding="utf-8")

    def require(self, token: str):
        self.assertIn(token, self.text)

    def test_frozen_source_and_sample(self):
        for token in (
            "e5a6b6847a6c6e36c32e7c2dad3f8c6182a341044871a15a0cec2006f85c7334",
            "exactly **8,000 parents**",
            "30–40 pieces: 2,000",
            "20–29 pieces: 2,000",
            "12–19 pieces: 2,000",
            "9–11 pieces: 2,000",
            "at most **16 legal moves**",
        ):
            self.require(token)

    def test_teacher_is_fixed_and_counterfactual(self):
        for token in (
            "50,000 nodes",
            "200,000 nodes",
            "fresh TT / fresh search state for every sibling",
            "opening book OFF",
            "Q_teacher(s,m_i) = - search(child_i).score",
            "abs(d50) >= 10 cp",
            "abs(d200) >= 30 cp",
        ):
            self.require(token)

    def test_learner_and_gates_are_frozen(self):
        for token in (
            "Total = **126 features**",
            "L2 = 1e-3",
            "maxiter = 500",
            "gtol = 1e-6",
            "100,000 parent-cluster bootstrap resamples",
            "16 label-sign shams",
            "D holdout pairwise accuracy >= 0.58",
            "DEEP_SIBLING_RANK_SIGNAL_ESTABLISHED",
            "DEEP_SIBLING_RANK_SIGNAL_NOT_ESTABLISHED",
        ):
            self.require(token)

    def test_no_scalar_refit_or_auto_promotion(self):
        for token in (
            "No PatternEval fit",
            "no scalar refit",
            "zero automatic promotion",
            "no modification of CURRICULUM",
        ):
            self.require(token)


if __name__ == "__main__":
    unittest.main()
