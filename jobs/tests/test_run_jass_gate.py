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

BOUNDED_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_jass_gate_bounded.py"
BOUNDED_SPEC = importlib.util.spec_from_file_location("run_jass_gate_bounded", BOUNDED_PATH)
B = importlib.util.module_from_spec(BOUNDED_SPEC)
assert BOUNDED_SPEC.loader is not None
BOUNDED_SPEC.loader.exec_module(B)


class RunJassGateTests(unittest.TestCase):
    def test_aggregate_complete_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "0.log"
            b = root / "1.log"
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
            a = root / "0.log"
            b = root / "1.log"
            a.write_text("RESULT 1 0 1\n", encoding="utf-8")
            b.write_text("no result\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                M.parse_result_files([a, b], 2)

    def test_duplicate_result_line_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "0.log"
            b = root / "1.log"
            a.write_text("RESULT 1 0 1\nRESULT 1 0 1\n", encoding="utf-8")
            b.write_text("RESULT 1 0 1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                M.parse_result_files([a, b], 2)

    def _bounded_args(self, **overrides):
        values = dict(
            harness="harness.py",
            jass_a="jass-8cf",
            jass_b="jass-32cf",
            pattern_a="a.pjtw",
            pattern_b="b.pjtw",
            search_params=None,
            search_params_a="threat=1",
            search_params_b="threat=0",
            depth=9,
            movetime=None,
            pairs=1,
            max_plies=160,
            nshards=16,
            openings_file="open.fen",
        )
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_bounded_cross_arch_command_uses_two_binaries_and_fingerprints(self):
        command = B.command_for(self._bounded_args(), 3)
        self.assertEqual(command[command.index("--jass-a") + 1], "jass-8cf")
        self.assertEqual(command[command.index("--jass-b") + 1], "jass-32cf")
        self.assertEqual(command[command.index("--search-params-a") + 1], "threat=1")
        self.assertEqual(command[command.index("--search-params-b") + 1], "threat=0")
        self.assertIn("--depth", command)
        self.assertNotIn("--movetime", command)

    def test_bounded_native_command_uses_equal_movetime(self):
        command = B.command_for(self._bounded_args(movetime=0.25), 0)
        self.assertEqual(command[command.index("--movetime") + 1], "0.25")
        self.assertNotIn("--depth", command)

    def test_legacy_shared_fingerprint_is_backward_compatible(self):
        args = self._bounded_args(
            search_params="legacy=1", search_params_a=None, search_params_b=None
        )
        B.resolve_search_params(args)
        self.assertEqual(args.search_params_a, "legacy=1")
        self.assertEqual(args.search_params_b, "legacy=1")


if __name__ == "__main__":
    unittest.main()
