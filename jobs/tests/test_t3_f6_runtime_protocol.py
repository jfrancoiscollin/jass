from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from jobs.tools.run_jass_gate_bounded import command_for, paired_opening_report
from jobs.tools.t3_f6_strength_readout import (
    CURRICULUM_SHA,
    MODEL_SHA,
    game_stats,
    load_gate,
)


ROOT = Path(__file__).resolve().parents[2]
R0 = ROOT / "jobs/templates/l3-t3-f6-runtime-r0-v1.sh"
POOL1 = ROOT / "jobs/templates/l3-t3-f6-runtime-strength-pool1-v1.sh"
POOL2 = ROOT / "jobs/templates/l3-t3-f6-runtime-strength-pool2-v1.sh"
EXCLUSIONS = ROOT / "jobs/templates/t3-f6-runtime-exclusions-v1.sh"


class T3F6RuntimeProtocolTest(unittest.TestCase):
    def test_templates_freeze_seeds_budgets_and_sequential_gate(self):
        r0 = R0.read_text(encoding="utf-8")
        p1 = POOL1.read_text(encoding="utf-8")
        p2 = POOL2.read_text(encoding="utf-8")
        for value in ("2026090901", "2026090902", "2026090903", "2026090904"):
            self.assertIn(value, r0)
        for value in ("2026091001", "2026091002", "2026091003", "2026091004"):
            self.assertIn(value, p1)
        for value in ("2026091101", "2026091102", "2026091103", "2026091104",
                      "2026091201", "2026091202"):
            self.assertIn(value, p2)
        self.assertIn("R0_PRODUCTION_LEAF_CONTRACT_PASS", r0)
        self.assertIn("T3_F6_POOL1_POSITIVE_POOL2_AUTHORIZED", p2)
        self.assertIn("CANDIDATES=30000", p1)
        self.assertIn("OPENINGS=3000", p1)
        self.assertIn("GAMES=6000", p1)
        self.assertIn("BOOTSTRAP=200000", p1)
        self.assertNotIn("--game-timeout", p1)
        self.assertNotIn("--game-timeout", p2)
        self.assertIn("--fail-on-game-error --enforce-no-book", p1)
        self.assertIn("--fail-on-game-error --enforce-no-book", p2)
        self.assertIn("POOL3_AUTHORIZED__FALSE", p2)
        self.assertIn("PROMOTION_AUTHORIZED__FALSE", p1)
        self.assertIn("BAKE__FALSE", p2)

    def test_exclusion_catalog_has_all_frozen_sources(self):
        text = EXCLUSIONS.read_text(encoding="utf-8")
        for token in ("cpx62-1617", "cpx62-1628c", "cpx62-1633", "cpx62-1638",
                      "cpx62-1360", "cpx62-1361", "cpx62-1568", "cpx62-1569",
                      "cpx62-1584"):
            self.assertIn(token, text)
        identity_block, force_block = text.split("T3_F6_FORCE_EXCLUDE_SPECS=", 1)
        self.assertEqual(identity_block.count("|r2:"), 10)
        self.assertEqual(force_block.count("|r2:"), 24)

    def test_force_command_wires_candidate_only_and_book_off(self):
        args = SimpleNamespace(
            harness="harness.py", jass_a="jass", jass_b="jass",
            pattern_a="curriculum", pattern_b="curriculum",
            search_params_a="q00", search_params_b="q00", pairs=1,
            max_plies=160, nshards=12, openings_file="pool.fen",
            work_dir="work", paired_bootstrap_samples=200000,
            dump_games_dir=None, t3_f6_model_a="t3.json", t3_f6_model_b=None,
            fail_on_game_error=True, enforce_no_book=True,
            movetime=0.1, depth=9, game_timeout=None,
        )
        command = command_for(args, 0)
        self.assertIn("--t3-f6-model-a", command)
        self.assertNotIn("--t3-f6-model-b", command)
        self.assertIn("--fail-on-game-error", command)
        self.assertIn("--enforce-no-book", command)
        self.assertNotIn("--game-timeout", command)

    def test_paired_report_includes_colour_and_depth_distribution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            scores = (1.0, 0.0, 0.5, 1.0)
            for index, score in enumerate(scores):
                rows.append({
                    "game_index": index, "opening_index": index // 2,
                    "pair_index": 0, "a_is_white": index % 2 == 0,
                    "score_a": score, "error": None, "error_side": None,
                    "telemetry_a": {"searches": 2, "depth_sum": 15, "nodes": 100,
                                    "eval_calls": 25, "wall_seconds": 0.2,
                                    "depth_histogram": {"7": 1, "8": 1}},
                    "telemetry_b": {"searches": 2, "depth_sum": 13, "nodes": 80,
                                    "eval_calls": 20, "wall_seconds": 0.2,
                                    "depth_histogram": {"6": 1, "7": 1}},
                })
            (root / "games.0.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            report = paired_opening_report(
                [root / "games.0.jsonl"], expected_shards=1,
                expected_openings=2, pairs=1, bootstrap_samples=1000, seed=9,
            )
            self.assertEqual(report["score_by_candidate_colour"]["white"]["games"], 2)
            self.assertAlmostEqual(
                report["score_by_candidate_colour"]["white"]["score_rate"], 0.75
            )
            self.assertEqual(report["telemetry"]["a"]["depth_histogram"], {"7": 4, "8": 4})
            self.assertEqual(report["telemetry"]["a"]["depth_quantiles"]["p50"], 7.5)

    def test_gate_authentication_checks_exact_runtime_contract(self):
        gate = {
            "complete": True, "n": 6000, "wins_a": 2400, "draws": 1800,
            "wins_b": 1800, "rate": 0.55,
            "paired_opening": {
                "n_openings": 3000, "games_per_opening": 2,
                "bootstrap_samples": 200000, "seed": 2026091003,
                "error_draws": 0, "errors_by_arm": {"a": 0, "b": 0, "unknown": 0},
                "per_opening_scores": [0.75] * 600 + [0.5] * 2400,
                "rate": 0.55,
                "wins_a": 2400, "draws": 1800, "wins_b": 1800,
                "score_by_candidate_colour": {
                    "white": {"games": 3000}, "black": {"games": 3000}
                },
            },
            "jass_a": "jass", "jass_b": "jass",
            "pattern_a": "curr", "pattern_b": "curr",
            "search_params_a": "q00", "search_params_b": "q00",
            "t3_f6_model_a": "t3", "t3_f6_model_b": None,
            "fail_on_game_error": True, "book_disabled": True,
            "jass_a_sha256": "e" * 64, "jass_b_sha256": "e" * 64,
            "pattern_a_sha256": CURRICULUM_SHA, "pattern_b_sha256": CURRICULUM_SHA,
            "t3_f6_model_a_sha256": MODEL_SHA, "t3_f6_model_b_sha256": None,
            "openings_file_sha256": "p" * 64, "pairs": 1, "max_plies": 160,
            "game_timeout": None, "movetime": 0.1, "depth": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate.json"
            path.write_text(json.dumps(gate), encoding="utf-8")
            loaded = load_gate(path, seed=2026091003, view="native",
                               executable_sha="e" * 64, openings_sha="p" * 64,
                               search_params="q00")
            self.assertAlmostEqual(game_stats(loaded)[0], 0.55)
            gate["book_disabled"] = False
            path.write_text(json.dumps(gate), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "book-OFF"):
                load_gate(path, seed=2026091003, view="native",
                          executable_sha="e" * 64, openings_sha="p" * 64,
                          search_params="q00")


if __name__ == "__main__":
    unittest.main()
