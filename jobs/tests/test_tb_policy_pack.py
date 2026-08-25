#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/tb_policy_pack.py"
spec = importlib.util.spec_from_file_location("tb_policy_pack", TOOL)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def payload() -> dict:
    return {
        "schema": "jass.tb_move_order_policy.v1",
        "usable": True,
        "eval_feature_width": 120,
        "move_feature_names": list(mod.MOVE_FEATURES),
        "score_convention": "higher_is_better_for_parent",
        "weights": {
            "white_parent": [float(i) / 10.0 for i in range(126)],
            "black_parent": [-float(i) / 7.0 for i in range(126)],
        },
        "training": {},
    }


class PolicyPackTests(unittest.TestCase):
    def test_pack_is_deterministic_and_preserves_126_weights_per_colour(self):
        p = payload()
        a = mod.pack(p)
        b = mod.pack(json.loads(json.dumps(p)))
        self.assertEqual(a, b)
        lines = a.decode("ascii").splitlines()
        self.assertEqual(lines[0], mod.MAGIC)
        self.assertEqual(lines[1], "120 6")
        self.assertEqual(len(lines[2].split()), 126)
        self.assertEqual(len(lines[3].split()), 126)
        self.assertEqual(float(lines[2].split()[125]), p["weights"]["white_parent"][125])
        self.assertEqual(float(lines[3].split()[125]), p["weights"]["black_parent"][125])

    def test_rejects_feature_order_or_width_drift(self):
        p = payload(); p["eval_feature_width"] = 119
        with self.assertRaises(ValueError): mod.pack(p)
        p = payload(); p["move_feature_names"] = list(reversed(mod.MOVE_FEATURES))
        with self.assertRaises(ValueError): mod.pack(p)
        p = payload(); p["weights"]["white_parent"] = [0.0] * 125
        with self.assertRaises(ValueError): mod.pack(p)


if __name__ == "__main__":
    unittest.main()
