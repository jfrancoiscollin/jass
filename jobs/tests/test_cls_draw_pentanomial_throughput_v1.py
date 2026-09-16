from __future__ import annotations

import json
from pathlib import Path
import unittest

import numpy as np

from jobs.tools import cls_draw_pentanomial_throughput_launch_stage as launch
from jobs.tools import cls_draw_pentanomial_throughput_stage as stage

ROOT = Path(__file__).resolve().parents[2]


class CLSDrawPentanomialThroughputV1Tests(unittest.TestCase):
    def test_historical_sources_and_bootstrap_are_frozen(self):
        self.assertEqual(stage.POOL1_JOB, "cpx62-1568-l3-tb-policy-move-ordering-force-pool1-v1")
        self.assertEqual(stage.POOL1_ATTEMPT, "20260825T234756Z-146f3464")
        self.assertEqual(stage.POOL2_JOB, "cpx62-1569-l3-tb-policy-move-ordering-force-pool2-v1")
        self.assertEqual(stage.POOL2_ATTEMPT, "20260826T061618Z-146f3464")
        self.assertEqual(stage.SOURCE_CODE, "146f34647dae489c6d2817748fd767aa65b93d87")
        self.assertEqual(stage.CURRICULUM_SHA, "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1")
        self.assertEqual(stage.SOURCE_NATIVE_FILE_SIZES, (36739, 36775))
        self.assertEqual(stage.SOURCE_BOOTSTRAP_SEEDS, (2026083011, 2026083021))
        self.assertEqual(stage.MOVETIME_SECONDS, 0.1)
        self.assertEqual(stage.NATIVE_GAMES, 12000)
        self.assertEqual(stage.NATIVE_PAIRS, 6000)
        self.assertEqual(stage.BOOTSTRAP_REPLICATES, 100000)
        self.assertEqual(stage.BOOTSTRAP_SEED, 2026091005)

    def test_pentanomial_counts_use_two_game_pair_points(self):
        scores = np.asarray([0.0, 0.25, 0.5, 0.75, 1.0, 0.5], dtype=np.float64)
        self.assertEqual(
            stage.canonical_counts(scores),
            {"0": 1, "0.5": 1, "1": 2, "1.5": 1, "2": 1},
        )

    def test_search_throughput_uses_frozen_parallelism(self):
        telemetry = {"a": {"wall_seconds": 1800.0}, "b": {"wall_seconds": 1800.0}}
        out = stage.search_throughput(3000, 8, telemetry)
        self.assertAlmostEqual(out["aggregate_engine_search_wall_seconds"], 3600.0)
        self.assertAlmostEqual(out["serial_engine_search_seconds_per_pair"], 1.2)
        self.assertAlmostEqual(out["parallelized_search_wall_seconds_estimate"], 450.0)
        self.assertAlmostEqual(out["cpx62_search_capacity_pairs_per_hour"], 24000.0)

    def test_launch_profile_is_read_only_and_common(self):
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-draw-pentanomial-throughput-v1.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["required_phases"], launch.PHASES)
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(value == 0 for value in profile["rehearsal_max_effects"].values()))

    def test_stage_quarantines_historical_strength_verdict_and_final_cls_classification(self):
        doc = (ROOT / "docs/experiments/L3_CLS_DRAW_PENTANOMIAL_THROUGHPUT_V1_20260916.md").read_text()
        code = (ROOT / "jobs/tools/cls_draw_pentanomial_throughput_stage.py").read_text()
        self.assertIn("strength_games=0", doc)
        self.assertIn("Historical candidate identity", doc)
        self.assertNotIn("run_jass_gate_bounded", code)
        self.assertNotIn("jass_vs_jass", code)
        self.assertIn('"final_bottleneck_classification": None', code)
        self.assertIn('"classification": None', code)
        self.assertIn('"strength_games": 0', code)
        self.assertIn("sprt_boundaries_frozen_here", code)


if __name__ == "__main__":
    unittest.main()
