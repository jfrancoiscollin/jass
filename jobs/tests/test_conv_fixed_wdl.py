#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

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

    def test_measure_records_fingerprints_and_position_outcomes(self) -> None:
        opened: list[tuple[str, str | None, str | None]] = []

        class Engine:
            def __init__(self, binary, *, pattern_path=None, search_params=None, **_):
                opened.append((binary, pattern_path, search_params))

            def close(self):
                pass

        class Referee:
            def __init__(self, binary):
                opened.append((binary, None, None))

            def close(self):
                pass

        outcomes = iter(("W", "D"))
        fake = types.ModuleType("calibrate_vs_scan")
        fake.JassEngine = Engine
        fake.Referee = Referee
        fake.play_game = lambda *_a, **_k: SimpleNamespace(outcome=next(outcomes))
        previous = sys.modules.get("calibrate_vs_scan")
        sys.modules["calibrate_vs_scan"] = fake
        try:
            with tempfile.TemporaryDirectory() as td:
                pool = Path(td) / "pool.jnnw"
                records = (
                    make_record(stm=0, wdl=1),
                    make_record(stm=1, wdl=-1),
                    make_record(stm=0, wdl=0),
                )
                pool.write_bytes(b"JNNW" + struct.pack("<I", len(records)) + b"".join(records))
                args = SimpleNamespace(
                    calibrate_tool=str(Path(td) / "calibrate_vs_scan.py"),
                    pool_jnnw=str(pool),
                    jass="jass-8cf",
                    defender_jass="jass-32cf",
                    pattern="a.pjtw",
                    defender_pattern="gen2.pjtw",
                    search_params="full-candidate",
                    defender_search_params="full-defender",
                    nshards=1,
                    shard=0,
                    movetime=None,
                    depth=10,
                    max_plies=260,
                )
                report = C.measure(args)
            self.assertEqual(
                opened[:3],
                [
                    ("jass-8cf", "a.pjtw", "full-candidate"),
                    ("jass-32cf", "gen2.pjtw", "full-defender"),
                    ("jass-8cf", None, None),
                ],
            )
            self.assertEqual(report["defender_jass"], "jass-32cf")
            self.assertEqual(report["schema"], 2)
            self.assertEqual(report["n_pos"], 2)
            self.assertEqual(report["n_win"], 1)
            self.assertEqual(report["n_draw"], 1)
            self.assertEqual(
                report["position_results"],
                [
                    {"index": 0, "result": "win"},
                    {"index": 1, "result": "draw"},
                    {"index": 2, "result": "skipped_draw_label"},
                ],
            )
            self.assertEqual(len(report["pool_sha256"]), 64)
        finally:
            if previous is None:
                sys.modules.pop("calibrate_vs_scan", None)
            else:
                sys.modules["calibrate_vs_scan"] = previous


if __name__ == "__main__":
    unittest.main()
