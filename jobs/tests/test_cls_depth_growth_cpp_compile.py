from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CLSDepthGrowthCppCompileTests(unittest.TestCase):
    def test_native_profiler_syntax(self):
        subprocess.run([
            "/usr/bin/c++", "-std=c++20", "-Isrc", "-Ipattern_jass/src",
            "-fsyntax-only", "jobs/tools/cls_depth_growth_jass.cpp",
        ], cwd=ROOT, check=True, timeout=60)


if __name__ == "__main__":
    unittest.main()
