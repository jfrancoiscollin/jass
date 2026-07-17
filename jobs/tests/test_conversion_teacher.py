#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "jobs/tools/conversion_teacher.py"
SPEC = importlib.util.spec_from_file_location("conversion_teacher", MODULE)
CT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = CT
SPEC.loader.exec_module(CT)


class ConversionTeacherTests(unittest.TestCase):
    def test_jnnw_fen_round_trip(self):
        fen = "W:W31,32,K40:B1,2,K10"
        record = CT.fen_to_record(fen, 1)
        self.assertEqual(CT.board_key(CT.record_to_fen(record)), record[:33])
        self.assertEqual(CT.signed_wdl(record), 1)

    def test_matched_b1_b2_b3_contract(self):
        parent = "W:W31,32:B1,2"
        bad = "B:W26,32:B1,2"
        good = "B:W27,31:B1,2"
        other = "B:W28,31:B1,2"
        step = CT.Step(
            source_game_id="game-1",
            trajectory_hash="t" * 64,
            parent_fen=parent,
            played_move="31-26",
            played_child_fen=bad,
            parent_wdl=1,
            child_parent_pov=0,
        )
        children = [[
            {"move": "31-26", "capture": False, "fen": bad},
            {"move": "32-27", "capture": False, "fen": good},
            {"move": "32-28", "capture": False, "fen": other},
        ]]
        # sibling oracle in STM POV: good=-1 (parent WIN), other=0.
        oracle = [CT.fen_to_record(good, -1), CT.fen_to_record(other, 0)]
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(CT, "dump_children", return_value=children), \
             mock.patch.object(CT, "oracle_records", return_value=oracle):
            root = Path(td)
            summary = CT.build_teacher(
                [step],
                jass="jass",
                work=root / "work",
                out_dir=root / "out",
                probe_tour="T3",
                engine_sha="e" * 40,
                weights_sha="w" * 64,
                depth=14,
                egdb=None,
                cache_mb=64,
                holdout_mod=5,
                max_siblings_per_parent=4,
                games_inspected=1,
            )
            self.assertEqual(summary["teacher_parents"], 1)
            self.assertEqual(summary["b2_b3_alignment"]["pairs"], 1)
            split = "holdout" if summary["split_counts"]["holdout"] else "train"
            split_root = root / "out" / split
            self.assertEqual(CT.read_jnnw(split_root / "parents.jnnw").__len__(), 1)
            self.assertEqual(CT.read_jnnw(split_root / "b2_pairs.jnnw").__len__(), 2)
            self.assertEqual((split_root / "good_moves.bin").read_bytes(), bytes([32, 27]))
            self.assertEqual((split_root / "bad_moves.bin").read_bytes(), bytes([31, 26]))

    def test_capture_parent_is_excluded(self):
        step = CT.Step("g", "t", "W:W31:B26", "31x22", "B:W22:B", 1, 0)
        children = [[
            {"move": "31x22", "capture": True, "fen": "B:W22:B"},
            {"move": "31x20", "capture": True, "fen": "B:W20:B"},
        ]]
        with tempfile.TemporaryDirectory() as td, \
             mock.patch.object(CT, "dump_children", return_value=children), \
             mock.patch.object(CT, "oracle_records", return_value=[]):
            summary = CT.build_teacher(
                [step], jass="jass", work=Path(td) / "w", out_dir=Path(td) / "o",
                probe_tour="T3", engine_sha="e", weights_sha="w", depth=14,
                egdb=None, cache_mb=64, holdout_mod=5,
                max_siblings_per_parent=4, games_inspected=1,
            )
            self.assertEqual(summary["teacher_parents"], 0)


if __name__ == "__main__":
    unittest.main()
