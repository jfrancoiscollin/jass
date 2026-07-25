from pathlib import Path
from types import ModuleType, SimpleNamespace
import struct
import sys
import tempfile
import unittest

from jobs.tools.conv_scan_fixed_wdl import measure


def record(*, stm: int, wdl: int) -> bytes:
    payload = bytearray(38)
    struct.pack_into("<QQQQ", payload, 0, 1 << 30, 0, 1, 0)
    payload[32] = stm
    struct.pack_into("<b", payload, 37, wdl)
    return bytes(payload)


class FakeEngine:
    def __init__(self, *args, label="", **kwargs):
        self.label = label

    def close(self):
        return None


class ScanFixedWDLTests(unittest.TestCase):
    def test_scan_always_plays_certified_winning_side(self):
        module = ModuleType("calibrate_vs_scan")
        module.ScanEngine = FakeEngine
        module.JassEngine = FakeEngine
        module.Referee = FakeEngine

        def play_game(white, black, referee, fen, **kwargs):
            del referee, kwargs
            if fen.startswith("W"):
                self.assertTrue(white.label.startswith("Scan-d"))
                return SimpleNamespace(outcome="W")
            self.assertTrue(black.label.startswith("Scan-d"))
            return SimpleNamespace(outcome="L")

        module.play_game = play_game
        previous = sys.modules.get("calibrate_vs_scan")
        sys.modules["calibrate_vs_scan"] = module
        try:
            with tempfile.TemporaryDirectory() as tmp:
                pool = Path(tmp) / "pool.jnnw"
                records = record(stm=0, wdl=1) + record(stm=1, wdl=1)
                pool.write_bytes(b"JNNW" + struct.pack("<I", 2) + records)
                args = SimpleNamespace(
                    calibrate_tool="jobs/tools/calibrate_vs_scan.py",
                    pool_jnnw=str(pool),
                    scan="scan",
                    scan_depth=12,
                    scan_runtime_sha256="runtime",
                    jass="jass",
                    defender_pattern="gen2.pjtw",
                    defender_search_params="q00",
                    defender_depth=10,
                    max_plies=260,
                    game_timeout=600.0,
                    nshards=1,
                    shard=0,
                )
                result = measure(args)
        finally:
            if previous is None:
                sys.modules.pop("calibrate_vs_scan", None)
            else:
                sys.modules["calibrate_vs_scan"] = previous

        self.assertEqual(result["n_pos"], 2)
        self.assertEqual(result["n_win"], 2)
        self.assertEqual(result["n_draw"], 0)
        self.assertEqual(result["n_loss"], 0)
        self.assertEqual(
            result["position_results"],
            [{"index": 0, "result": "win"}, {"index": 1, "result": "win"}],
        )
        self.assertEqual(result["depth"], 12)
        self.assertEqual(result["defender_depth"], 10)


if __name__ == "__main__":
    unittest.main()
