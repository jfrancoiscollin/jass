from __future__ import annotations

import json
from pathlib import Path
import unittest

from jobs.tools import cls_search_profile_launch_stage as launch
from jobs.tools import cls_search_profile_stage as stage

ROOT = Path(__file__).resolve().parents[2]


class CLSSearchProfileV1Tests(unittest.TestCase):
    def test_sources_and_bootstrap_are_frozen(self):
        self.assertEqual(stage.DEPTH_JOB, "cpx62-2000-l3-cls-depth-growth-full-production-v2")
        self.assertEqual(stage.DEPTH_ATTEMPT, "20260916T083204Z-7a5f44ec")
        self.assertEqual(stage.DEPTH_RECEIPT, "3155272745b458af68e35de06bf6921b20fdf8639913287be6d71075e3349a42")
        self.assertEqual(stage.MIRROR_JOB, "cpx62-2008-l3-cls-mirror-scale-production-v3")
        self.assertEqual(stage.MIRROR_ATTEMPT, "20260916T161938Z-92984c1f")
        self.assertEqual(stage.MIRROR_RECEIPT, "2ac13b1e61dffc7d73217a8daba111aed9028b7a006020d081ebd6aa3480b004")
        self.assertEqual(stage.ROOTS, 512)
        self.assertEqual(stage.ROOTS_PER_PHASE, 128)
        self.assertEqual(stage.BUDGETS, (5000, 50000, 200000))
        self.assertEqual(stage.DEEP_BUDGET, 1000000)
        self.assertEqual(stage.BOOTSTRAP_REPLICATES, 100000)
        self.assertEqual(stage.BOOTSTRAP_SEED, 2026091004)

    def test_jass_search_counter_summary_is_descriptive(self):
        rows = [
            {
                "nodes_observed": "100", "qnodes": "20", "eval_calls": "40", "cutoffs": "30",
                "first_move_cutoffs": "15", "pvs_researches": "5", "moves_searched": "60",
                "nps": "1000", "completed_nominal_depth": "10", "tt_hit_rate": "0.25", "wall_ms": "100",
            },
            {
                "nodes_observed": "100", "qnodes": "30", "eval_calls": "50", "cutoffs": "20",
                "first_move_cutoffs": "10", "pvs_researches": "10", "moves_searched": "40",
                "nps": "2000", "completed_nominal_depth": "12", "tt_hit_rate": "0.75", "wall_ms": "50",
            },
        ]
        out = stage.summarize_jass(rows)
        self.assertEqual(out["rows"], 2)
        self.assertAlmostEqual(out["mean_nps"], 1500.0)
        self.assertAlmostEqual(out["mean_completed_nominal_depth"], 11.0)
        self.assertAlmostEqual(out["qnodes_per_node"], 0.25)
        self.assertAlmostEqual(out["eval_calls_per_node"], 0.45)
        self.assertAlmostEqual(out["tt_hit_rate"], 0.5)
        self.assertAlmostEqual(out["cutoffs_per_node"], 0.25)
        self.assertAlmostEqual(out["first_move_cutoff_share"], 0.5)
        self.assertAlmostEqual(out["pvs_researches_per_move"], 0.15)
        self.assertAlmostEqual(out["moves_searched_per_node"], 0.5)
        self.assertAlmostEqual(out["wall_ms_sum"], 150.0)

    def test_root_vector_preserves_paired_runtime_and_ordering_metrics(self):
        jass = {
            "nps": "2000", "completed_nominal_depth": "12", "nodes_observed": "100",
            "qnodes": "20", "eval_calls": "40", "tt_hit_rate": "0.5", "cutoffs": "25",
            "first_move_cutoffs": "10", "pvs_researches": "4", "moves_searched": "50",
        }
        scan = {"nps": "1000", "completed_nominal_depth": "10"}
        vector = stage.root_vector(jass, scan)
        self.assertAlmostEqual(vector[0], __import__("math").log(2.0))
        self.assertEqual(vector[1], 2.0)
        self.assertAlmostEqual(vector[2], 0.2)
        self.assertAlmostEqual(vector[3], 0.4)
        self.assertAlmostEqual(vector[4], 0.5)
        self.assertAlmostEqual(vector[5], 0.25)
        self.assertAlmostEqual(vector[6], 0.4)
        self.assertAlmostEqual(vector[7], 0.08)
        self.assertAlmostEqual(vector[8], 0.5)

    def test_launch_profile_is_zero_effect_and_common(self):
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-search-profile-v1.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["required_phases"], launch.PHASES)
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(value == 0 for value in profile["rehearsal_max_effects"].values()))

    def test_no_nodes_to_depth_surrogate_or_engine_execution(self):
        doc = (ROOT / "docs/experiments/L3_CLS_SEARCH_PROFILE_V1_20260916.md").read_text()
        code = (ROOT / "jobs/tools/cls_search_profile_stage.py").read_text()
        self.assertIn("nodes_to_depth_available=false", doc)
        self.assertIn("Fresh depth-N searches", doc)
        self.assertIn('"available": False', code)
        self.assertNotIn("subprocess", code)
        self.assertNotIn("run_jass", code)
        self.assertNotIn("run_scan", code)
        self.assertIn("classification\": None", code)


if __name__ == "__main__":
    unittest.main()
