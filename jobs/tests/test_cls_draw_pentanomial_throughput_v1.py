from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from jobs.tools import cls_draw_pentanomial_throughput_launch_stage as launch
from jobs.tools import cls_draw_pentanomial_throughput_stage as legacy
from jobs.tools import cls_draw_pentanomial_throughput_stage_v2 as repaired
from jobs.tools import cls_bottleneck_classification_stage as clsdiag

ROOT = Path(__file__).resolve().parents[2]


def legacy_native_payload(seed: int) -> dict:
    scores = [0.5] * legacy.OPENINGS_PER_POOL
    return {
        "complete": True,
        "n": legacy.GAMES_PER_POOL,
        "wins_a": 2000,
        "draws": 2000,
        "wins_b": 2000,
        "rate": 0.5,
        "pairs": 1,
        "nshards": 8,
        "max_parallel": legacy.MAX_PARALLEL,
        "movetime": legacy.MOVETIME_SECONDS,
        "depth": None,
        "paired_opening": {
            "method": "paired_colour_opening_cluster_bootstrap",
            "n_openings": legacy.OPENINGS_PER_POOL,
            "games_per_opening": 2,
            "bootstrap_samples": 200000,
            "seed": seed,
            "error_draws": 0,
            "rate": 0.5,
            "per_opening_scores": scores,
        },
    }


class CLSDrawPentanomialThroughputV1Tests(unittest.TestCase):
    def test_historical_sources_and_bootstrap_are_frozen(self):
        self.assertEqual(legacy.POOL1_JOB, "cpx62-1568-l3-tb-policy-move-ordering-force-pool1-v1")
        self.assertEqual(legacy.POOL1_ATTEMPT, "20260825T234756Z-146f3464")
        self.assertEqual(legacy.POOL2_JOB, "cpx62-1569-l3-tb-policy-move-ordering-force-pool2-v1")
        self.assertEqual(legacy.POOL2_ATTEMPT, "20260826T061618Z-146f3464")
        self.assertEqual(legacy.SOURCE_CODE, "146f34647dae489c6d2817748fd767aa65b93d87")
        self.assertEqual(legacy.CURRICULUM_SHA, "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1")
        self.assertEqual(legacy.SOURCE_NATIVE_FILE_SIZES, (36739, 36775))
        self.assertEqual(legacy.SOURCE_BOOTSTRAP_SEEDS, (2026083011, 2026083021))
        self.assertEqual(legacy.MOVETIME_SECONDS, 0.1)
        self.assertEqual(legacy.NATIVE_GAMES, 12000)
        self.assertEqual(legacy.NATIVE_PAIRS, 6000)
        self.assertEqual(legacy.BOOTSTRAP_REPLICATES, 100000)
        self.assertEqual(legacy.BOOTSTRAP_SEED, 2026091005)

    def test_pentanomial_counts_use_two_game_pair_points(self):
        scores = np.asarray([0.0, 0.25, 0.5, 0.75, 1.0, 0.5], dtype=np.float64)
        self.assertEqual(
            legacy.canonical_counts(scores),
            {"0": 1, "0.5": 1, "1": 2, "1.5": 1, "2": 1},
        )

    def test_legacy_schema_repair_accepts_only_fields_the_producer_serialized(self):
        raw = legacy_native_payload(legacy.SOURCE_BOOTSTRAP_SEEDS[0])
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "force-native.json"
            path.write_bytes(b"x" * 123)
            scores, summary = repaired.validate_native(raw, source_seed=legacy.SOURCE_BOOTSTRAP_SEEDS[0], expected_size=123, path=path)
        self.assertEqual(scores.shape, (legacy.OPENINGS_PER_POOL,))
        self.assertEqual(summary["pentanomial_counts"], {"0": 0, "0.5": 0, "1": 3000, "1.5": 0, "2": 0})
        self.assertFalse(summary["throughput"]["primary_native_search_wall_telemetry_available"])
        self.assertIsNone(summary["throughput"]["cpx62_search_capacity_pairs_per_hour"])

    def test_legacy_schema_repair_fails_closed_if_unexpected_invocation_fields_appear(self):
        raw = legacy_native_payload(legacy.SOURCE_BOOTSTRAP_SEEDS[0])
        raw["max_plies"] = legacy.MAX_PLIES
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "force-native.json"
            path.write_bytes(b"x" * 123)
            with self.assertRaisesRegex(repaired.StageError, "legacy_serialization_contract_drift:max_plies"):
                repaired.validate_native(raw, source_seed=legacy.SOURCE_BOOTSTRAP_SEEDS[0], expected_size=123, path=path)

    def test_legacy_schema_repair_never_invents_missing_search_wall_telemetry(self):
        raw = legacy_native_payload(legacy.SOURCE_BOOTSTRAP_SEEDS[0])
        raw["paired_opening"]["telemetry"] = {"a": {"wall_seconds": 1.0}, "b": {"wall_seconds": 1.0}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "force-native.json"
            path.write_bytes(b"x" * 123)
            with self.assertRaisesRegex(repaired.StageError, "legacy_serialization_contract_drift:telemetry"):
                repaired.validate_native(raw, source_seed=legacy.SOURCE_BOOTSTRAP_SEEDS[0], expected_size=123, path=path)
        code = (ROOT / "jobs/tools/cls_draw_pentanomial_throughput_stage_v2.py").read_text()
        self.assertIn('"future_sprt_sizing_inputs_ready": False', code)
        self.assertIn("UNAVAILABLE_LEGACY_SOURCE_NO_SEARCH_WALL_TELEMETRY", code)

    def test_launch_profile_is_read_only_and_common_and_uses_repair(self):
        profile = json.loads((ROOT / "jobs/launch_profiles/cls-draw-pentanomial-throughput-v1.json").read_text())
        self.assertEqual(profile["campaign"], "cls-v1")
        self.assertEqual(profile["required_phases"], launch.PHASES)
        self.assertEqual(profile["rehearsal_max_effects"], profile["production_max_effects"])
        self.assertTrue(all(value == 0 for value in profile["rehearsal_max_effects"].values()))
        self.assertIs(launch.stage, repaired)

    def test_stage_quarantines_historical_strength_verdict_and_final_cls_classification(self):
        doc = (ROOT / "docs/experiments/L3_CLS_DRAW_PENTANOMIAL_THROUGHPUT_V1_20260916.md").read_text()
        code = (ROOT / "jobs/tools/cls_draw_pentanomial_throughput_stage_v2.py").read_text()
        self.assertIn("strength_games=0", doc)
        self.assertIn("Historical candidate identity", doc)
        self.assertIn("Authenticated technical correction after 2011", doc)
        self.assertNotIn("subprocess", code)
        self.assertNotIn("jass_vs_jass", code)
        self.assertIn('"final_bottleneck_classification": None', code)
        self.assertIn('"classification": None', code)
        self.assertIn('"strength_games": 0', code)
        self.assertIn("sprt_boundaries_frozen_here", code)

    def test_terminal_classifier_is_wired_into_existing_ci(self):
        self.assertEqual(clsdiag.BUDGET, 200000)
        search = {"q025": -2.0, "median": -1.0, "q975": -0.1}
        decision = {"q025": 0.01, "median": 0.05, "q975": 0.1}
        neutral = {"q025": -0.1, "median": 0.0, "q975": 0.1}
        label, supported, reason = clsdiag.classify(search_ci=search, decision_ci=decision, cost_ci=neutral)
        self.assertEqual(label, "mixed")
        self.assertEqual(supported, ["SEARCH", "DECISION-EVAL"])
        self.assertEqual(reason, "MULTIPLE_SUPPORTED_AXES")


if __name__ == "__main__":
    unittest.main()
