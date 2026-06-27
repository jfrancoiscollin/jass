#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Unit test for build_ballots.py — colour-mirror correctness (the subtle part)
# and the ply-window extraction (via a FAKE oracle).
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_ballots import (  # noqa: E402
    mirror50, color_swap_mirror, collect_game, material_imbalance, _popcount,
)
from pdn_to_jnnw import fen_to_bitboards  # noqa: E402


class FakeOracle:
    def __init__(self, fens):
        self.fens = fens
        self.i = 0

    def reset(self):
        self.i = 0

    def apply(self, move):
        self.i += 1
        return True

    def fen(self):
        return self.fens[self.i]


def test_mirror50():
    # square 1 (bit 0) -> square 50 (bit 49) ; square 50 -> square 1
    assert mirror50(1 << 0) == (1 << 49)
    assert mirror50(1 << 49) == (1 << 0)
    assert mirror50(1 << 24) == (1 << 25)   # square 25 <-> 26
    # involution + popcount preserved over a few patterns
    for bb in (0, 1, 0b1011, (1 << 0) | (1 << 49) | (1 << 7), (1 << 50) - 1):
        assert mirror50(mirror50(bb)) == bb, f"not involution for {bb}"
        assert _popcount(mirror50(bb)) == _popcount(bb)
    print("[1] mirror50 OK (square map, involution, popcount-preserving)")


def test_color_swap_mirror():
    stm, wm, wk, bm, bk = fen_to_bitboards("W:W31,32,K33:B18,19,K20")
    m = color_swap_mirror(wm, wk, bm, bk, stm)
    # colours swapped + stm flipped
    assert m[4] == 1 - stm
    # white men/king counts of the mirror == black men/king counts of original
    assert _popcount(m[0]) == _popcount(bm) and _popcount(m[1]) == _popcount(bk)
    assert _popcount(m[2]) == _popcount(wm) and _popcount(m[3]) == _popcount(wk)
    # applying twice returns the original position exactly
    m2 = color_swap_mirror(*m)
    assert m2 == (wm, wk, bm, bk, stm), f"double-mirror != identity: {m2}"
    # material imbalance is preserved (symmetry)
    assert material_imbalance(*m[:4]) == material_imbalance(wm, wk, bm, bk)
    print("[2] color_swap_mirror OK (swap, involution, imbalance-preserving)")


def test_collect_window():
    # 8 quiet plies ; positions distinguished by a black man on square 10+ply.
    moves = "31-26 20-25 32-28 19-23 33-29 18-22 34-30 17-21".split()
    pdn = " ".join(moves)
    fens = [f"{'W' if p % 2 == 0 else 'B'}:W31,32,33:B{10 + p},48,49" for p in range(len(moves))]
    got = collect_game(FakeOracle(fens), pdn, ply_lo=3, ply_hi=6,
                       min_imbalance=0, log=logging.getLogger("t"))
    assert len(got) == 4, f"window [3,6] should yield 4 positions, got {len(got)}"
    # the black 'marker' man must be on squares 13,14,15,16 for plies 3..6
    markers = sorted({(b & -b).bit_length() for (_wm, _wk, b, _bk, _stm) in got})
    assert markers == [13, 14, 15, 16], f"wrong plies collected: {markers}"
    print("[3] collect_game ply-window OK (plies 3..6 selected)")


def test_imbalance_filter():
    # equal material position ; min_imbalance=1 must drop it
    moves = "31-26 20-25 32-28 19-23".split()
    fens = ["W:W31,32,33:B18,19,20"] * len(moves)
    got = collect_game(FakeOracle(fens), " ".join(moves), ply_lo=0, ply_hi=3,
                       min_imbalance=1, log=logging.getLogger("t"))
    assert got == [], f"balanced positions should be filtered, got {len(got)}"
    print("[4] imbalance filter OK")


if __name__ == "__main__":
    test_mirror50()
    test_color_swap_mirror()
    test_collect_window()
    test_imbalance_filter()
    print("ALL build_ballots TESTS PASSED")
