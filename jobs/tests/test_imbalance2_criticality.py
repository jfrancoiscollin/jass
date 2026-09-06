#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/imbalance2_criticality.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("imbalance2_criticality", TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def bits(*squares: int) -> int:
    out = 0
    for square in squares:
        out |= 1 << (square - 1)
    return out


def record(wm: tuple[int, ...], wk: tuple[int, ...], bm: tuple[int, ...], bk: tuple[int, ...],
           stm: int, score: int, wdl: int) -> bytes:
    return struct.pack("<QQQQBiB", bits(*wm), bits(*wk), bits(*bm), bits(*bk),
                       stm, score, wdl & 0xFF)


class FenCodecTest(unittest.TestCase):
    def test_round_trip_supports_ranges_and_kings(self):
        tool = load_tool()
        row = tool.fen_to_record("B:W10-12,K20:B1,3,K40")
        fen = tool.record_to_fen(row)
        self.assertEqual(fen, "B:W10,11,12,K20:B1,3,K40")
        self.assertEqual(tool.fen_to_record(fen), row)


class ParentSelectionTest(unittest.TestCase):
    def test_excludes_holdout_tb_locked_and_out_of_domain(self):
        tool = load_tool()
        rows = [
            # Eligible: 5 men vs 3, total 8.
            record((20, 21, 22, 23, 24), (), (1, 2, 3), (), 0, -1, -1),
            # TB locked: 3 vs 1, total 4.
            record((20, 21, 22), (), (1,), (), 1, 0, 0),
            # Out of domain: only one man difference.
            record((20, 21, 22, 23), (), (1, 2, 3), (), 0, 1, 1),
            # Holdout, otherwise eligible.
            record((20, 21, 22, 23, 24), (), (1, 2, 3), (), 1, 0, 0),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tool.write_jnnw(tmp_path / "fit.jnnw", rows)
            subprocess.run([
                sys.executable, str(TOOL), "make-parents",
                "--input", str(tmp_path / "fit.jnnw"),
                "--holdout-count", "1", "--max-parents", "0",
                "--tb-lock-pieces", "6", "--seed", "9",
                "--out-fen", str(tmp_path / "parents.fen"),
                "--out-index", str(tmp_path / "parents.json"),
            ], check=True, capture_output=True, text=True)
            payload = json.loads((tmp_path / "parents.json").read_text())
            self.assertEqual(payload["eligible_parents"], 1)
            self.assertEqual(payload["record_indices"], [0])
            self.assertEqual(len((tmp_path / "parents.fen").read_text().splitlines()), 1)


class FlattenAndReweightTest(unittest.TestCase):
    def test_unique_defensive_choice_gets_capped_weight_and_holdout_is_exact(self):
        tool = load_tool()
        rows = [
            # Current STM is the disadvantaged side and ultimately wins.
            record((20, 21, 22, 23, 24), (), (1, 2, 3), (), 1, -1, 1),
            # Current STM is advantaged; terminal draw.
            record((20, 21, 22, 23, 24), (), (1, 2, 3), (), 0, 0, 0),
            # Out of exact +2 domain: V1 base weight only.
            record((20, 21, 22, 23), (), (1, 2, 3), (), 0, 1, 1),
            # Holdout sentinel.
            record((30, 31, 32, 33, 34), (), (5, 6, 7), (), 1, 0, -1),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tool.write_jnnw(tmp_path / "fit.jnnw", rows)
            parent_index = {
                "schema": 1,
                "record_indices": [0, 1],
            }
            (tmp_path / "parents.json").write_text(json.dumps(parent_index))
            children = [
                [
                    {"move": "1-2", "fen": "W:W20,21,22,23,24:B1,2,3"},
                    {"move": "1-3", "fen": "W:W20,21,22,23,24:B1,2,4"},
                    {"move": "1-4", "fen": "W:W20,21,22,23,24:B1,3,4"},
                ],
                [
                    {"move": "20-15", "fen": "B:W15,21,22,23,24:B1,2,3"},
                    {"move": "21-16", "fen": "B:W16,20,22,23,24:B1,2,3"},
                    {"move": "22-17", "fen": "B:W17,20,21,23,24:B1,2,3"},
                ],
            ]
            (tmp_path / "children.jsonl").write_text("\n".join(json.dumps(row) for row in children) + "\n")
            subprocess.run([
                sys.executable, str(TOOL), "flatten-children",
                "--parent-index", str(tmp_path / "parents.json"),
                "--children-jsonl", str(tmp_path / "children.jsonl"),
                "--out-data", str(tmp_path / "children.jnnw"),
                "--out-index", str(tmp_path / "children-index.json"),
            ], check=True, capture_output=True, text=True)
            child_rows = tool.read_jnnw(tmp_path / "children.jnnw")
            # Child search scores are child-STM POV; the profiler negates them.
            # Parent 0: [300, 0, -20] => one clearly preserving move.
            # Parent 1: [100, 80, 70] => all moves within the 50-point margin.
            child_scores = [-300, 0, 20, -100, -80, -70]
            for row, score in zip(child_rows, child_scores, strict=True):
                struct.pack_into("<i", row, 33, score)
            tool.write_jnnw(tmp_path / "children-scored.jnnw", child_rows)

            subprocess.run([
                sys.executable, str(TOOL), "reweight",
                "--input", str(tmp_path / "fit.jnnw"),
                "--scored-children", str(tmp_path / "children-scored.jnnw"),
                "--child-index", str(tmp_path / "children-index.json"),
                "--output", str(tmp_path / "weighted.jnnw"),
                "--holdout-count", "1", "--seed", "17",
                "--report", str(tmp_path / "report.json"),
                "--profile-report", str(tmp_path / "profiles.json"),
            ], check=True, capture_output=True, text=True)

            report = json.loads((tmp_path / "report.json").read_text())
            self.assertEqual(report["profile_bucket_counts"]["unique"], 1)
            self.assertEqual(report["profile_bucket_counts"]["broad"], 1)
            self.assertEqual(report["effective_weight_histogram"]["8"], 1)
            self.assertEqual(report["effective_weight_histogram"]["2"], 1)
            self.assertEqual(report["effective_weight_histogram"]["1"], 1)
            self.assertEqual(report["holdout_body_sha256_before"], report["holdout_body_sha256_after"])
            weighted = tool.read_jnnw(tmp_path / "weighted.jnnw")
            self.assertEqual(weighted[-1], bytearray(rows[-1]))


if __name__ == "__main__":
    unittest.main()
