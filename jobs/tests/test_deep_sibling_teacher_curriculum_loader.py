#!/usr/bin/env python3
from pathlib import Path
import os
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src/deep_sibling_teacher.cpp"
SHIM = ROOT / "src/deep_sibling_teacher_curriculum_loader.hpp"
SCAN = ROOT / "src/scan_eval.hpp"


class DeepSiblingTeacherCurriculumLoaderTests(unittest.TestCase):
    def test_shim_routes_legacy_call_to_unified_production_loader(self):
        shim = SHIM.read_text(encoding="utf-8")
        src = SRC.read_text(encoding="utf-8")
        scan = SCAN.read_text(encoding="utf-8")
        self.assertIn("load_pattern_jass_network(curriculum_path", src)
        self.assertIn("#define load_pattern_jass_network load_eval_network", shim)
        self.assertIn("std::unique_ptr<INetwork> load_eval_network", scan)
        self.assertIn("V_SELFDESC_BIT", scan)
        self.assertIn("V3_VERSION", scan)

    def test_teacher_translation_unit_compiles_with_loader_shim(self):
        compiler = os.environ.get("CXX") or shutil.which("c++") or shutil.which("g++")
        if not compiler:
            self.skipTest("no C++ compiler available")
        proc = subprocess.run(
            [compiler, "-std=c++20", "-fsyntax-only",
             "-Isrc", "-Ipattern_jass/src",
             "-include", "src/deep_sibling_teacher_curriculum_loader.hpp",
             str(SRC)],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
