#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs" / "tools" / "check_retirement_readiness.py"
SPEC = importlib.util.spec_from_file_location("check_retirement_readiness", TOOL)
assert SPEC and SPEC.loader
GUARD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GUARD
SPEC.loader.exec_module(GUARD)


class RetirementReadinessPatternTests(unittest.TestCase):
    def test_legacy_clone_match_requires_a_path_boundary(self):
        pattern = GUARD.patterns()["hardcoded_legacy_clone"]
        self.assertIsNotNone(pattern.search("cd /root/jass"))
        self.assertIsNotNone(pattern.search("cd /root/jass/jobs"))
        self.assertIsNone(pattern.search("cd /root/jass-scan"))
        self.assertIsNone(pattern.search("cd /root/jass-control"))
        self.assertIsNone(pattern.search("cd /root/jass2"))


if __name__ == "__main__":
    unittest.main()
