#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "split_stratified_fen.py"
SPEC = importlib.util.spec_from_file_location("split_stratified_fen", MODULE)
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(M)


class SplitStratifiedFenTests(unittest.TestCase):
    def test_splits_four_strata(self):
        lines = [
            "W:W1:B2 # margin=8 palier=p1_net",
            "W:W3:B4 # palier=p2_moyen",
            "B:W5:B6 # palier=p3_mince",
            "B:W7:B8 # palier=p4_egal",
        ]
        groups = M.split_lines(lines)
        self.assertEqual(set(groups), set(M.STRATA))
        self.assertEqual(groups["p4_egal"], ["B:W7:B8"])

    def test_missing_metadata_fails(self):
        with self.assertRaises(ValueError):
            M.split_lines([
                "W:W1:B2 # palier=p1_net",
                "W:W3:B4 # palier=p2_moyen",
                "B:W5:B6 # palier=p3_mince",
                "B:W7:B8",
            ])

    def test_empty_required_stratum_fails(self):
        with self.assertRaises(ValueError):
            M.split_lines([
                "W:W1:B2 # palier=p1_net",
                "W:W3:B4 # palier=p2_moyen",
                "B:W5:B6 # palier=p3_mince",
            ])


if __name__ == "__main__":
    unittest.main()
