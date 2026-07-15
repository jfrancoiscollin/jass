#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import struct
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "conv_fixed_wdl.py"
SPEC = importlib.util.spec_from_file_location("conv_fixed_wdl", MODULE_PATH)
assert SPEC and SPEC.loader
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


def make_record(*, stm: int, wdl: int) -> bytes:
    wm = (1 << 0) | (1 << 4)
    wk = 1 << 9
    bm = 1 << 19
    bk = 1 << 29
    return struct.pack("<QQQQBib", wm, wk, bm, bk, stm, 0, wdl)


class ConvFixedWdlTests(unittest.TestCase):
    def test_winner_from_stm_pov(self) -> None:
        self.assertEqual(C.winning_side(make_record(stm=0, wdl=1)), "W")
        self.assertEqual(C.winning_side(make_record(stm=0, wdl=-1)), "B")
        self.assertEqual(C.winning_side(make_record(stm=1, wdl=1)), "B")
        self.assertEqual(C.winning_side(make_record(stm=1, wdl=-1)), "W")
        self.assertIsNone(C.winning_side(make_record(stm=1, wdl=0)))

    def test_record_to_fen(self) -> None:
        fen = C.record_to_fen(make_record(stm=1, wdl=1))
        self.assertEqual(fen, "B:W1,5,K10:B20,K30")


if __name__ == "__main__":
    unittest.main()
