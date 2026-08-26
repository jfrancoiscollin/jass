#!/usr/bin/env python3
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src/deep_sibling_teacher.cpp"
DOC = ROOT / "docs/experiments/L3_DEEP_SEARCH_SIBLING_DISTILLATION_V1_20260826.md"


class DeepSiblingTeacherContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = SRC.read_text(encoding="utf-8")
        cls.doc = DOC.read_text(encoding="utf-8")

    def test_exact_frozen_budgets(self):
        for token in ("5'000", "50'000", "200'000", "NodeLimitMode::Exact", "MAX_PLY"):
            self.assertIn(token, self.src)
        self.assertIn("teacher A: 50,000 nodes", self.doc)
        self.assertIn("teacher B: 200,000 nodes", self.doc)

    def test_searches_are_clean_and_policy_off(self):
        for token in ("clear_tt()", "use_book(false)", "threads = 1", "JASS_TB_MOVE_ORDER_POLICY"):
            self.assertIn(token, self.src)
        self.assertIn("fresh TT / fresh search state for every sibling", self.doc)

    def test_teacher_does_not_select_labels_or_fit(self):
        for token in (
            '"stable_pairs_selected\\\": false',
            '"fits\\\": 0',
            '"strength_games\\\": 0',
            '"promotion_authorized\\\": false',
        ):
            self.assertIn(token, self.src)

    def test_parent_pov_and_direct_t_baseline_are_explicit(self):
        self.assertIn("out.parent_score = -result.score", self.src)
        self.assertIn("t_baseline_parent = -curriculum->evaluate(child)", self.src)
        self.assertIn("Q_teacher(s,m_i) = - search(child_i).score", self.doc)

    def test_semantic_sibling_order_is_score_blind(self):
        self.assertIn("std::sort(unique_moves.begin(), unique_moves.end(), semantic_less)", self.src)
        self.assertIn("Search order among siblings is canonicalized by semantic move identity", self.doc)


if __name__ == "__main__":
    unittest.main()
