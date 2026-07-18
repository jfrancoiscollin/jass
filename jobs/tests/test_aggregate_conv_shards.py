#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "aggregate_conv_shards.py"
SPEC = importlib.util.spec_from_file_location("aggregate_conv_shards", MODULE)
M = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(M)


def payload(shard: int, nshards: int = 2, *, pos: int = 3, errors: int = 0) -> dict:
    outcomes = ["win"] * pos + ["skipped_draw_label"] + ["error"] * errors
    return {
        "schema": 2,
        "shard": shard,
        "nshards": nshards,
        "n_pos": pos,
        "n_win": pos,
        "n_draw": 0,
        "n_loss": 0,
        "n_skipped_draw_label": 1,
        "n_errors": errors,
        "n_restarts": 0,
        "errors": [],
        "depth": 10,
        "movetime": None,
        "jass": "j8",
        "defender_jass": "j32",
        "pattern": "candidate.pjtw",
        "defender_pattern": "gen2.pjtw",
        "search_params": "full-common",
        "defender_search_params": "full-common",
        "pool_jnnw": "pool.jnnw",
        "pool_sha256": "a" * 64,
        "position_results": [
            {"index": shard + offset * nshards, "result": outcome}
            for offset, outcome in enumerate(outcomes)
        ],
    }


class AggregateConvTests(unittest.TestCase):
    def write(self, root: Path, name: str, data: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_complete_set_aggregates_position_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = [
                self.write(root, "0.json", payload(0)),
                self.write(root, "1.json", payload(1)),
            ]
            result = M.aggregate(
                files,
                expected_shards=2,
                expected_records=8,
                require_position_results=True,
            )
            self.assertTrue(result["complete"])
            self.assertEqual(result["schema"], 2)
            self.assertEqual(result["n_pos"], 6)
            self.assertEqual(result["accounted_records"], 8)
            self.assertEqual(result["conversion"], 1.0)
            self.assertEqual([row["index"] for row in result["position_results"]], list(range(8)))
            self.assertEqual(result["search_params"], "full-common")

    def test_missing_file_count_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            only = self.write(root, "0.json", payload(0))
            with self.assertRaises(ValueError):
                M.aggregate([only], expected_shards=2)

    def test_duplicate_shard_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = [
                self.write(root, "a.json", payload(0)),
                self.write(root, "b.json", payload(0)),
            ]
            with self.assertRaises(ValueError):
                M.aggregate(files, expected_shards=2)

    def test_accounting_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = [
                self.write(root, "0.json", payload(0)),
                self.write(root, "1.json", payload(1)),
            ]
            with self.assertRaises(ValueError):
                M.aggregate(files, expected_shards=2, expected_records=9)

    def test_error_threshold_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = [
                self.write(root, "0.json", payload(0, pos=2, errors=2)),
                self.write(root, "1.json", payload(1, pos=2, errors=2)),
            ]
            with self.assertRaises(ValueError):
                M.aggregate(
                    files,
                    expected_shards=2,
                    expected_records=10,
                    max_error_rate=0.08,
                )

    def test_wdl_accounting_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = payload(0)
            bad["n_win"] = 2
            files = [
                self.write(root, "0.json", bad),
                self.write(root, "1.json", payload(1)),
            ]
            with self.assertRaises(ValueError):
                M.aggregate(files, expected_shards=2)

    def test_required_position_trace_cannot_be_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = payload(0)
            second = payload(1)
            del second["position_results"]
            files = [
                self.write(root, "0.json", first),
                self.write(root, "1.json", second),
            ]
            with self.assertRaisesRegex(ValueError, "position_results"):
                M.aggregate(files, 2, require_position_results=True)

    def test_fingerprint_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            second = payload(1)
            second["search_params"] = "different"
            files = [
                self.write(root, "0.json", payload(0)),
                self.write(root, "1.json", second),
            ]
            with self.assertRaisesRegex(ValueError, "search_params"):
                M.aggregate(files, 2)


if __name__ == "__main__":
    unittest.main()
