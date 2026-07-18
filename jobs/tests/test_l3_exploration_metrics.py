#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "jobs/tools/aggregate_l3_exploration.py"
SPEC = importlib.util.spec_from_file_location("aggregate_l3_exploration", MODULE)
METRICS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(METRICS)


def line(*, random_open=8, eps=8, decay=60, openings=10, games=20,
         random_moves=80, play_plies=1000, events=40, changed=30,
         games_with_eps=15) -> str:
    return (
        "EXPLORATION "
        f"random_open_plies={random_open} explore_eps={eps} decay_plies={decay} "
        f"openings={openings} games={games} random_open_moves={random_moves} "
        f"play_plies={play_plies} eps_events={events} "
        f"eps_changed_best={changed} games_with_eps={games_with_eps}\n"
    )


class ExplorationMetricsTests(unittest.TestCase):
    def test_aggregates_counts_and_rates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a, b = root / "a.log", root / "b.log"
            a.write_text(line(), encoding="utf-8")
            b.write_text(line(openings=5, games=10, random_moves=40,
                              play_plies=500, events=20, changed=10,
                              games_with_eps=8), encoding="utf-8")
            payload = METRICS.build_payload(
                [a, b], expected_random_open=8, expected_eps=8, expected_decay=60)
            self.assertEqual(payload["shards"], 2)
            self.assertEqual(payload["counts"]["play_plies"], 1500)
            self.assertEqual(payload["counts"]["eps_events"], 60)
            self.assertAlmostEqual(payload["rates"]["epsilon_event_per_play_ply"], 0.04)
            self.assertTrue(payload["activation_proven"])

    def test_rejects_configuration_drift(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.log"
            path.write_text(line(eps=4), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "configured exploration"):
                METRICS.build_payload(
                    [path], expected_random_open=8, expected_eps=8, expected_decay=60)

    def test_rejects_missing_or_duplicate_activation_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.log"
            path.write_text("no counters\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                METRICS.parse_log(path)
            path.write_text(line() + line(), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exactly one"):
                METRICS.parse_log(path)


if __name__ == "__main__":
    unittest.main()
