from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

from jobs.tools import cls_mirror_scale_launch_stage as launch
from jobs.tools import cls_mirror_scale_stage as stage

ROOT = Path(__file__).resolve().parents[2]


class CLSMirrorScaleV1Tests(unittest.TestCase):
    def test_source_and_science_are_hard_frozen(self):
        self.assertEqual(stage.SOURCE_JOB, "cpx62-2000-l3-cls-depth-growth-full-production-v2")
        self.assertEqual(stage.SOURCE_ATTEMPT, "20260916T083204Z-7a5f44ec")
        self.assertEqual(stage.SOURCE_CODE, "7a5f44ec1681c2471b1815f8767b4008b11e3a54")
        self.assertEqual(stage.SOURCE_RECEIPT_SHA256, "3155272745b458af68e35de06bf6921b20fdf8639913287be6d71075e3349a42")
        self.assertEqual(stage.ROOTS, 512)
        self.assertEqual(stage.ROOTS_PER_PHASE, 128)
        self.assertEqual(stage.SHALLOW_BUDGETS, (5000, 50000, 200000))
        self.assertEqual(stage.DEEP_BUDGET, 1000000)
        self.assertEqual(stage.BOOTSTRAP_REPLICATES, 100000)
        self.assertEqual(stage.BOOTSTRAP_SEED, 2026091003)

    def test_mirror_contrast_is_same_root_and_descriptive(self):
        selected = []
        deep = []
        shallow = []
        root = 0
        for phase in stage.PHASES:
            for _ in range(stage.ROOTS_PER_PHASE):
                rid = str(root)
                selected.append({"parent_id": rid, "phase": phase})
                deep.append({
                    "root_id": rid,
                    "budget": str(stage.DEEP_BUDGET),
                    "bestmove_canonical": "10-14",
                    "completed_nominal_depth": "20",
                    "nps": "100000",
                    "nodes_observed": str(stage.DEEP_BUDGET),
                })
                for budget in stage.SHALLOW_BUDGETS:
                    shallow.append({
                        "root_id": rid,
                        "budget": str(budget),
                        "engine": "JASS_PARITY",
                        "bestmove_canonical": "10-14",
                    })
                    shallow.append({
                        "root_id": rid,
                        "budget": str(budget),
                        "engine": "SCAN",
                        "bestmove_canonical": "10-14" if budget == 5000 else "11-16",
                    })
                root += 1
        aggregate, arrays = stage.aggregate(shallow, deep, selected)
        self.assertIsNone(aggregate["classification"])
        self.assertEqual(aggregate["overall"]["5000"]["mirror_agreement"], 1.0)
        self.assertEqual(aggregate["overall"]["5000"]["cross_engine_agreement"], 1.0)
        self.assertEqual(aggregate["overall"]["5000"]["mirror_excess"], 0.0)
        for budget in (50000, 200000):
            cell = aggregate["overall"][str(budget)]
            self.assertEqual(cell["mirror_agreement"], 1.0)
            self.assertEqual(cell["cross_engine_agreement"], 0.0)
            self.assertEqual(cell["mirror_excess"], 1.0)
        self.assertEqual(set(arrays), set(stage.PHASES))
        self.assertTrue(all(value.shape == (128, 9) for value in arrays.values()))

    def test_one_common_profile_covers_rehearsal_and_production(self):
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-mirror-scale-v1.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["required_phases"], launch.PHASES)
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        effects = profile["rehearsal_max_effects"]
        self.assertEqual(effects["new_jass_searches"], 512)
        self.assertEqual(effects["new_scan_searches"], 0)
        self.assertEqual(effects["test_target_reads"], 0)
        for field in ("fits", "strength_games", "selfplay_games", "promotions", "bakes"):
            self.assertEqual(effects[field], 0)

    def test_stage_keeps_diagnostic_boundary_and_exact_mode_pair(self):
        doc = (ROOT / "docs/experiments/L3_CLS_MIRROR_SCALE_V1_20260916.md").read_text()
        code = (ROOT / "jobs/tools/cls_mirror_scale_stage.py").read_text()
        cpp = (ROOT / "jobs/tools/cls_mirror_scale_jass.cpp").read_text()
        self.assertIn("DIAGNOSTIC_ONLY=true", doc)
        self.assertIn('"classification": None', code)
        self.assertIn('mode not in {"rehearsal", "production"}', code)
        self.assertIn("constexpr std::uint64_t BUDGET = 1'000'000", cpp)
        self.assertIn("run_one(root, curriculum.get(), BUDGET)", cpp)
        self.assertNotIn("go depth", code)
        self.assertNotIn("LAUNCH_MODE ==", code)

    def test_native_mirror_profiler_syntax(self):
        subprocess.run([
            "/usr/bin/c++", "-std=c++20", "-Isrc", "-Ipattern_jass/src",
            "-fsyntax-only", "jobs/tools/cls_mirror_scale_jass.cpp",
        ], cwd=ROOT, check=True, timeout=60)


if __name__ == "__main__":
    unittest.main()
