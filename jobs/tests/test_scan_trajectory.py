#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/scan_selfplay_gen.py"
SPEC = importlib.util.spec_from_file_location("scan_selfplay_gen", MODULE)
SG = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = SG
SPEC.loader.exec_module(SG)


class TrajectoryTests(unittest.TestCase):
    def test_record_is_stable_and_replayable(self):
        kwargs = dict(
            game_index=4,
            shard=2,
            opening="W:W31-50:B1-20",
            seed_source="ONP",
            outcome="D",
            reason="ply cap",
            fens=["W:W31-50:B1-20", "B:W26,32-50:B1-20"],
            moves=["31-26"],
        )
        first = SG.trajectory_record(**kwargs)
        second = SG.trajectory_record(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(len(first["trajectory_hash"]), 64)
        self.assertEqual(len(first["source_game_id"]), 24)
        self.assertEqual(len(first["fens"]), len(first["moves"]) + 1)


if __name__ == "__main__":
    unittest.main()
