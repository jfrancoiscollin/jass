from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from jobs.tools import cls_depth_growth_scan as scan
from jobs.tools import cls_depth_growth_stage as stage
from jobs.tools import cls_depth_growth_launch_stage as launch

ROOT = Path(__file__).resolve().parents[2]


class CLSDepthGrowthV2Tests(unittest.TestCase):
    def test_frozen_contract(self):
        self.assertEqual(stage.COHORT_SHA, "478abc0fe2fe1fcd8c2157f532ba796745c645ff4f03dac8fd21c2ff851f137e")
        self.assertEqual(stage.CURRICULUM_SHA, "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1")
        self.assertEqual(stage.SCAN_COMMIT, "7aae17e7b7bfc47744601afb1ee7655e18983ce5")
        self.assertEqual(stage.BUDGETS, (5000, 50000, 200000))
        self.assertEqual(stage.REHEARSAL_SEED, 2026091001)
        self.assertEqual(stage.BOOTSTRAP_SEED, 2026091002)
        self.assertEqual(launch.PHASES, ["execute-rehearsal"])

    def test_selector_is_deterministic_8_per_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deep = root / "deep512.tsv"
            with deep.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["parent_id", "canonical_fingerprint", "phase", "subset_hash"], delimiter="\t", lineterminator="\n")
                writer.writeheader()
                idx = 0
                for phase in stage.PHASES:
                    for n in range(128):
                        writer.writerow({"parent_id": idx, "canonical_fingerprint": f"{phase}-fp-{n:03d}", "phase": phase, "subset_hash": f"x{n:03d}"})
                        idx += 1
            a = root / "a.txt"; b = root / "b.txt"
            first = stage.select_rehearsal(deep, a)
            second = stage.select_rehearsal(deep, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual([r["parent_id"] for r in first], [r["parent_id"] for r in second])
            self.assertEqual({p: sum(r["phase"] == p for r in first) for p in stage.PHASES}, {p: 8 for p in stage.PHASES})

    def test_scan_move_canonicalization(self):
        self.assertEqual(scan.canonical_move("28-32"), "28-32")
        self.assertEqual(scan.canonical_move("28x19x23x14"), "28x19|caps=14,23")

    def test_launch_profile_zero_target(self):
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-depth-growth-v2-rehearsal.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["required_phases"], launch.PHASES)
        effects = profile["rehearsal_max_effects"]
        self.assertEqual(effects["new_jass_searches"], 192)
        self.assertEqual(effects["new_scan_searches"], 96)
        self.assertEqual(effects["test_target_reads"], 0)
        for field in ("fits", "strength_games", "selfplay_games", "promotions", "bakes"):
            self.assertEqual(effects[field], 0)

    def test_depth_surrogate_is_disabled(self):
        text = (ROOT / "jobs/tools/cls_depth_growth_stage.py").read_text()
        self.assertIn('cross_engine_depth_curve_available": False', text)
        self.assertIn("fresh depth-N searches are forbidden substitutes", text)
        self.assertIn("verify_parity", text)
        self.assertNotIn("go depth", text)

    def test_native_profiler_exact_node_contract(self):
        text = (ROOT / "jobs/tools/cls_depth_growth_jass.cpp").read_text()
        self.assertIn("NodeLimitMode::Exact", text)
        self.assertIn("5'000, 50'000, 200'000", text)
        self.assertNotIn("movetime", text.lower())


if __name__ == "__main__":
    unittest.main()
