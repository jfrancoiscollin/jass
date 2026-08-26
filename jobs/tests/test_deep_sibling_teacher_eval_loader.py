#!/usr/bin/env python3
from pathlib import Path
import os
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "src/deep_sibling_teacher_eval_loader.cpp"
TEACHER = ROOT / "src/deep_sibling_teacher.cpp"
SCAN_HPP = ROOT / "src/scan_eval.hpp"


class DeepSiblingTeacherEvalLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wrapper = WRAPPER.read_text(encoding="utf-8")
        cls.teacher = TEACHER.read_text(encoding="utf-8")
        cls.scan_hpp = SCAN_HPP.read_text(encoding="utf-8")

    def test_reproduced_failure_is_the_legacy_loader_boundary(self):
        # 1571 failed because the frozen champion carries the ScanEval
        # self-describing version word 0x203 (=515), while this legacy helper
        # accepts PJTW v1 only.  Keep this assertion so a future refactor cannot
        # silently route the production teacher back through the wrong loader.
        self.assertIn("load_pattern_jass_network(curriculum_path", self.teacher)
        self.assertIn("V_SELFDESC_BIT= 0x00000200U", self.scan_hpp)
        self.assertIn("V3_VERSION = 3U", self.scan_hpp)

    def test_wrapper_redirects_only_the_loader_call(self):
        p_bridge = self.wrapper.index('#include "pattern_jass_bridge.hpp"')
        p_scan = self.wrapper.index('#include "scan_eval.hpp"')
        p_alias = self.wrapper.index("#define load_pattern_jass_network load_eval_network")
        p_impl = self.wrapper.index('#include "deep_sibling_teacher.cpp"')
        self.assertLess(p_bridge, p_alias)
        self.assertLess(p_scan, p_alias)
        self.assertLess(p_alias, p_impl)
        self.assertIn("#undef load_pattern_jass_network", self.wrapper)

    def test_wrapper_translation_unit_is_syntax_valid(self):
        compiler = os.environ.get("CXX") or shutil.which("c++") or shutil.which("g++")
        if not compiler:
            self.skipTest("no C++ compiler available")
        proc = subprocess.run(
            [compiler, "-std=c++20", "-fsyntax-only", "-Isrc", "-Ipattern_jass/src", str(WRAPPER)],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
