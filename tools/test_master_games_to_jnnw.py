#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Unit test for master_games_to_jnnw.py — exercises the quiet filter + WDL
# labeling on a hand-built game via a FAKE oracle (no sqlite, no jass binary).
import logging
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from master_games_to_jnnw import emit_game, is_capture, _piece_count  # noqa: E402
from pdn_to_jnnw import _REC_STRUCT, fen_to_bitboards  # noqa: E402


class FakeOracle:
    """Replays a fixed FEN sequence; apply() always succeeds. fen() returns the
    position BEFORE the i-th move, matching JassOracle's contract."""
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


def test_quiet_filter_and_labels():
    # White-to-move on even plies. Moves: quiet/quiet/CAPTURE/CAPTURE/quiet/quiet.
    pdn = "1. 33-28 18-23 2. 28x19 14x23 3. 39-33 20-24"
    fens = [
        "W:W31,32,33:B18,19,20",  # ply0 white, quiet move    -> emit (+1)
        "B:W31,32,33:B18,19,20",  # ply1 black, quiet move    -> emit (-1)
        "W:W31,32,33:B18,19,20",  # ply2 white, CAPTURE 28x19 -> skip
        "B:W31,32,33:B18,19,20",  # ply3 black, CAPTURE 14x23 -> skip
        "W:W31,32,33:B18,19,20",  # ply4 white, quiet move    -> emit (+1)
        "B:W31,32,33:B18,19,20",  # ply5 black, quiet move    -> emit (-1)
    ]
    body = bytearray()
    log = logging.getLogger("t")
    n = emit_game(FakeOracle(fens), body, pdn, "1-0",
                  min_plies=0, skip_open=0, skip_endgame_pieces=0, log=log)

    assert n == 4, f"expected 4 quiet records, got {n}"
    wdls = [struct.unpack_from("<b", body, i * _REC_STRUCT.size + 37)[0] for i in range(n)]
    assert wdls == [1, -1, 1, -1], f"wrong STM-POV labels: {wdls}"

    # records must decode to the parsed bitboards (round-trip vs fen_to_bitboards)
    stm0, wm0, wk0, bm0, bk0 = fen_to_bitboards(fens[0])
    rwm, rwk, rbm, rbk, rstm, _sc, _wdl = _REC_STRUCT.unpack_from(body, 0)
    assert (rwm, rwk, rbm, rbk, rstm) == (wm0, wk0, bm0, bk0, stm0), "bitboard round-trip mismatch"
    print(f"[1] quiet-filter+labels OK : {n} records, wdl={wdls}")


def test_is_capture_and_piece_count():
    assert is_capture("28x19") and is_capture("32x14x3")
    assert not is_capture("33-28") and not is_capture("20-24")
    stm, wm, wk, bm, bk = fen_to_bitboards("W:W31,32,K33:B18,K19,20")
    assert _piece_count(wm, wk, bm, bk) == 6, _piece_count(wm, wk, bm, bk)
    print("[2] is_capture + piece_count OK")


def test_skip_open_and_endgame():
    pdn = "33-28 18-23 39-33 20-24"
    fens = ["W:W31,32,33:B18,19,20"] * 5
    body = bytearray()
    # skip_open=2 -> first two plies dropped; only plies 2,3 considered (both quiet)
    n = emit_game(FakeOracle(fens), body, pdn, "0-1",
                  min_plies=0, skip_open=2, skip_endgame_pieces=0, log=logging.getLogger("t"))
    assert n == 2, f"skip_open=2 should leave 2 records, got {n}"
    # skip_endgame_pieces=99 -> all positions (6 pieces) excluded
    body2 = bytearray()
    n2 = emit_game(FakeOracle(fens), body2, pdn, "0-1",
                   min_plies=0, skip_open=0, skip_endgame_pieces=99, log=logging.getLogger("t"))
    assert n2 == 0, f"endgame filter should drop all, got {n2}"
    print("[3] skip-open + endgame-piece filter OK")


if __name__ == "__main__":
    test_quiet_filter_and_labels()
    test_is_capture_and_piece_count()
    test_skip_open_and_endgame()
    print("ALL master_games_to_jnnw TESTS PASSED")
