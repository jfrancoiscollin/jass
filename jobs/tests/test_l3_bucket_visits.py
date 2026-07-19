#!/usr/bin/env python3
"""Round-trip test for l3_bucket_visits: build a small valid JNNW corpus, run
the tool, assert the visit tally invariants. Runs against whatever `patterns`
geometry is on PYTHONPATH (functional check; the job pins the 8cf variant)."""
from __future__ import annotations

import importlib.util
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pattern_jass" / "tools"))

MODULE = ROOT / "jobs" / "tools" / "l3_bucket_visits.py"
SPEC = importlib.util.spec_from_file_location("l3_bucket_visits", MODULE)
BV = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(BV)


def write_corpus(path: Path, n: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    body = bytearray()
    for _ in range(n):
        wm = int(rng.integers(0, 2 ** 64, dtype=np.uint64))
        bm = int(rng.integers(0, 2 ** 64, dtype=np.uint64)) & ~wm  # disjoint = valid
        body += struct.pack("<QQQQBib", wm, 0, bm, 0, 0, 0, 0)
    path.write_bytes(b"JNNW" + struct.pack("<I", n) + bytes(body))


class BucketVisitTests(unittest.TestCase):
    def test_tally_invariants_and_json_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            write_corpus(tmp / "c.jnnw", 300, seed=13)
            out = tmp / "bv.json"
            BV.main(["--data", str(tmp / "c.jnnw"), "--out", str(out), "--chunk", "64", "--top-k", "5"])
            d = json.loads(out.read_text())
            g, c, corp = d["geometry"], d["coverage"], d["corpus"]
            TB, NP = g["trained_buckets_total"], g["num_patterns"]
            self.assertEqual(corp["total_records"], 300)
            # every record activates exactly NP pattern buckets (one per pattern)
            self.assertEqual(corp["total_bucket_visits"], 300 * NP)
            self.assertEqual(sum(p["visit_sum"] for p in d["per_pattern"]), corp["total_bucket_visits"])
            self.assertLessEqual(c["visited_buckets"], TB)
            self.assertGreater(c["visited_buckets"], 0)
            self.assertTrue(0.0 <= c["coverage_fraction"] <= 1.0)
            self.assertIn(d["capacity_heuristic"],
                          {"capacity_used_more_resolution_worth_testing",
                           "data_limited_more_capacity_not_justified"})

    def test_two_files_accumulate(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            write_corpus(tmp / "a.jnnw", 100, seed=1)
            write_corpus(tmp / "b.jnnw", 150, seed=2)
            out = tmp / "bv.json"
            BV.main(["--data", str(tmp / "a.jnnw"), str(tmp / "b.jnnw"),
                     "--out", str(out), "--chunk", "500000", "--top-k", "5"])
            d = json.loads(out.read_text())
            self.assertEqual(d["corpus"]["total_records"], 250)


if __name__ == "__main__":
    unittest.main()
