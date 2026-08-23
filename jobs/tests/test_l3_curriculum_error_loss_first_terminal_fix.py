import unittest
from unittest import mock

from jobs.tools import l3_curriculum_error_loss_first_sibling_labels as base
from jobs.tools import l3_curriculum_error_loss_first_sibling_labels_terminal_fix as fix


class LossFirstTerminalFixTests(unittest.TestCase):
    def setUp(self):
        fix._TERMINAL_FENS.clear()

    @mock.patch.object(fix.ctx, "_search")
    def test_accepts_exact_terminal_child_at_any_teacher_depth(self, search):
        search.return_value = (mock.Mock(), {"depth": 0, "nodes": 0, "score": -30000})
        fen = "W:W31:B1"
        result = fix._search_leaf(mock.Mock(), fen, 12)
        self.assertTrue(result["terminal_exact"])
        self.assertEqual(result["requested_depth"], 12)
        self.assertEqual(result["pv_leaf_fen"], fen)
        extractor = fix.ExactFeatureExtractor.__new__(fix.ExactFeatureExtractor)
        vector, meta = extractor.vector(fen)
        self.assertEqual(vector, {})
        self.assertEqual(meta["pattern_eval_jacobian"], "zero")

    @mock.patch.object(fix.ctx, "_search")
    def test_rejects_nonterminal_incomplete_depth(self, search):
        search.return_value = (
            mock.Mock(),
            {"depth": 9, "nodes": 1000, "score": 42, "pv_leaf_fen": "W:W31:B1"},
        )
        with self.assertRaisesRegex(ValueError, "fixed-depth"):
            fix._search_leaf(mock.Mock(), "W:W31:B1", 10)

    def test_install_changes_only_label_adapter_hooks(self):
        original_main = base.main
        fix.install()
        self.assertIs(base._search_leaf, fix._search_leaf)
        self.assertIs(base.ExactFeatureExtractor, fix.ExactFeatureExtractor)
        self.assertIs(base.main, original_main)


if __name__ == "__main__":
    unittest.main()
