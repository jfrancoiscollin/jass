#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

MODULE = Path(__file__).resolve().parents[1] / "tools" / "run_jass_gate.py"
SPEC = importlib.util.spec_from_file_location("run_jass_gate", MODULE)
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(M)

BOUNDED_PATH = (
    Path(__file__).resolve().parents[1] / "tools" / "run_jass_gate_bounded.py"
)
BOUNDED_SPEC = importlib.util.spec_from_file_location("run_jass_gate_bounded", BOUNDED_PATH)
B = importlib.util.module_from_spec(BOUNDED_SPEC)
assert BOUNDED_SPEC.loader is not None
BOUNDED_SPEC.loader.exec_module(B)


class RunJassGateTests(unittest.TestCase):
    def test_aggregate_complete_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "0.log"; b = root / "1.log"
            a.write_text("noise\nRESULT 10 5 5\n", encoding="utf-8")
            b.write_text("RESULT 8 4 8\n", encoding="utf-8")
            result = M.parse_result_files([a, b], 2)
            self.assertEqual(result["n"], 40)
            self.assertEqual(result["wins_a"], 18)
            self.assertTrue(result["complete"])

    def test_missing_log_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "0.log"
            a.write_text("RESULT 1 0 1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                M.parse_result_files([a], 2)

    def test_missing_result_line_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "0.log"; b = root / "1.log"
            a.write_text("RESULT 1 0 1\n", encoding="utf-8")
            b.write_text("no result\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                M.parse_result_files([a, b], 2)

    def test_duplicate_result_line_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "0.log"; b = root / "1.log"
            a.write_text("RESULT 1 0 1\nRESULT 1 0 1\n", encoding="utf-8")
            b.write_text("RESULT 1 0 1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                M.parse_result_files([a, b], 2)

    def test_bounded_cross_arch_command_uses_two_binaries(self):
        args = SimpleNamespace(
            harness="harness.py",
            jass_a="jass-8cf",
            jass_b="jass-32cf",
            pattern_a="a.pjtw",
            pattern_b="b.pjtw",
            search_params="qs=1",
            depth=9,
            pairs=1,
            max_plies=160,
            nshards=16,
            openings_file="open.fen",
        )
        command = B.command_for(args, 3)
        self.assertEqual(command[command.index("--jass-a") + 1], "jass-8cf")
        self.assertEqual(command[command.index("--jass-b") + 1], "jass-32cf")


if __name__ == "__main__":
    unittest.main()
