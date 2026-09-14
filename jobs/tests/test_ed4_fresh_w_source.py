from __future__ import annotations

import json
from pathlib import Path
import struct
import tempfile
import unittest

from jobs.tools import ed4_fresh_w_source_stage as w


class FreshWSourceTests(unittest.TestCase):
    def sizing_report(self):
        return {
            "schema": "jass.ed4.fresh_w_sizing.v1",
            "terminal": "ED4_FRESH_W_SIZING_COMPLETE_V1",
            "master_seed": 202609120402,
            "records": 4096,
            "independent_games": 118,
            "independent_openings": 65,
            "game_result_parsed": False,
            "candidate_reads": 0,
            "control_evaluations": 0,
            "test_target_reads": 0,
            "fits": 0,
            "alpha_spent": 0,
            "confirmation_target_consumed": False,
            "records_per_game": {"min": 13, "p10": 23, "median": 31.0, "p90": 51},
            "records_per_opening": {"min": 24, "p10": 37, "median": 64.0, "p90": 90},
            "sanitized": {
                "jnnw_wdl_zeroed_before_publication": True,
                "jsm2_game_result_zeroed_before_publication": True,
                "raw_wdl_parsed": False,
                "raw_game_result_parsed": False,
            },
        }

    def test_mechanical_plan_is_frozen_from_target_blind_sizing(self):
        plan = w.derive_plan(self.sizing_report())
        self.assertEqual(plan["rows_per_game"], 8)
        self.assertEqual(plan["target_openings"], 512)
        self.assertEqual(plan["target_positions"], 8192)
        self.assertEqual(plan["sizing_paired_openings"], 53)
        self.assertEqual(plan["estimated_represented_openings_needed"], 628)
        self.assertEqual(plan["record_budget_initial"], 40960)
        self.assertEqual(plan["record_budget_max"], 57344)
        self.assertEqual(plan["record_budget_ladder"], [40960, 45056, 49152, 53248, 57344])
        self.assertEqual(plan["cluster_unit"], "opening_id")

    def test_sizing_target_barrier_fails_closed(self):
        report = self.sizing_report()
        report["sanitized"]["raw_game_result_parsed"] = True
        with self.assertRaisesRegex(ValueError, "sizing_target_barrier"):
            w.derive_plan(report)

    def make_jsm2(self, path: Path, openings: int, rows_per_game: int = 8):
        raw = bytearray(b"JSM2")
        count = openings * 2 * rows_per_game
        raw += struct.pack("<I", count)
        for opening in range(openings):
            for game_slot in range(2):
                game = 1000 + opening * 2 + game_slot
                for ply in range(rows_per_game):
                    outcome = 1 if game_slot == 0 else -1
                    raw += struct.pack(
                        "<QQBHHHbB",
                        game,
                        5000 + opening,
                        0,
                        ply,
                        rows_per_game + 5,
                        0xFFFF,
                        outcome,
                        0,
                    )
        path.write_bytes(raw)

    def test_jsm2_result_is_never_retained_and_selection_is_balanced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = root / "raw.jsm2"
            safe = root / "safe.jsm2"
            self.make_jsm2(raw, openings=3, rows_per_game=9)
            rows = w.parse_zero_jsm2(raw, safe)
            selected, groups, support = w.select_rows(rows, opening_target=2)
            self.assertEqual(len(selected), 32)
            self.assertEqual(support["selected_openings"], 2)
            self.assertEqual(support["selected_games"], 4)
            self.assertEqual(len({g["opening_id"] for g in groups}), 2)
            for game_id in {g["game_id"] for g in groups}:
                self.assertEqual(sum(g["game_id"] == game_id for g in groups), 8)
            safe_bytes = safe.read_bytes()
            count = struct.unpack_from("<I", safe_bytes, 4)[0]
            self.assertTrue(all(safe_bytes[8 + i * 25 + 23] == 0 for i in range(count)))
            self.assertNotIn("outcome", json.dumps(groups).lower())

    def test_support_completion_is_structural_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            raw = root / "raw.jsm2"
            safe = root / "safe.jsm2"
            self.make_jsm2(raw, openings=1, rows_per_game=8)
            rows = w.parse_zero_jsm2(raw, safe)
            with self.assertRaises(w.SupportInsufficient) as ctx:
                w.select_rows(rows, opening_target=2)
            self.assertEqual(ctx.exception.report["eligible_paired_openings"], 1)
            self.assertEqual(ctx.exception.report["required_paired_openings"], 2)

    def test_binary_selection_preserves_only_requested_zero_target_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "safe.jnnw"
            raw = bytearray(b"JNNW" + struct.pack("<I", 4))
            for i in range(4):
                rec = bytearray(38)
                rec[0:8] = struct.pack("<Q", 1 << i)
                rec[32] = i % 2
                rec[33:38] = b"\0" * 5
                raw += rec
            source.write_bytes(raw)
            dest = root / "selected.jnnw"
            w.select_binary(source, dest, [3, 1], magic=b"JNNW", rec_size=38)
            selected = dest.read_bytes()
            self.assertEqual(struct.unpack_from("<I", selected, 4)[0], 2)
            self.assertEqual(selected[8 + 33:8 + 38], b"\0" * 5)
            self.assertEqual(selected[46 + 33:46 + 38], b"\0" * 5)

    def test_constants_match_preregistration(self):
        self.assertEqual(w.SEED, 202609120402)
        self.assertEqual(w.RESERVE_SEED, 202609120412)
        self.assertEqual(w.ROWS_PER_GAME, 8)
        self.assertEqual(w.PRODUCTION_OPENINGS, 512)
        self.assertEqual(w.PRODUCTION_POSITIONS, 8192)


if __name__ == "__main__":
    unittest.main()
