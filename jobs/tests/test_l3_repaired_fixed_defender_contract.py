#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPAIRED_DEFENDER_SHA = "9c1d1e8eaaa5b9bbd86105f7f9807a3033784186"
PRE_DRAWN_ROOT_FIX_SHA = "038a2001854f2805bc0045acd56c617826e5ff15"
TEMPLATES = (
    "l3-pure-m2-eval-v1.sh",
    "l3-pure-replay25-eval-v1.sh",
    "l3-pure-turnover-l2-eval-v1.sh",
    "l3-pure-turnover-succession-gate-v1.sh",
    "l3-pure-volume8m-eval-v1.sh",
)


class RepairedFixedDefenderContractTests(unittest.TestCase):
    def test_active_templates_pin_first_fully_repaired_defender(self) -> None:
        for name in TEMPLATES:
            with self.subTest(template=name):
                text = (ROOT / "jobs" / "templates" / name).read_text(
                    encoding="utf-8"
                )
                self.assertIn(
                    f'FIXED_DEFENDER_CODE_SHA="{REPAIRED_DEFENDER_SHA}"',
                    text,
                )
                self.assertNotIn(
                    f'FIXED_DEFENDER_CODE_SHA="{PRE_DRAWN_ROOT_FIX_SHA}"',
                    text,
                )
                self.assertIn(
                    'grep -q "root_is_drawn" '
                    '"$W/fixed-defender-code/src/search.cpp"',
                    text,
                )
                self.assertIn('--defender-jass "$J32FIXED"', text)


if __name__ == "__main__":
    unittest.main()
