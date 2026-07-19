#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "jobs/tools/make_imbalance2_pools.py"
GATE = ROOT / "jobs/tools/imbalance2_scan_gate.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ImbalancePoolsTest(unittest.TestCase):
    def test_all_18_strata_and_two_independent_pools(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, str(GEN), "--out-dir", tmp,
                            "--train-per-stratum", "4", "--bench-per-stratum", "4",
                            "--seed", "271828"], check=True, capture_output=True, text=True)
            manifest = json.loads((Path(tmp) / "manifest.json").read_text())
            self.assertEqual(manifest["strata"], [f"{n}v{n+2}" for n in range(1, 19)])
            self.assertEqual(manifest["files"]["benchmark-a.jnnw"]["records"], 72)
            self.assertEqual(manifest["files"]["benchmark-b.jnnw"]["records"], 72)
            self.assertNotEqual(manifest["files"]["benchmark-a.jnnw"]["sha256"],
                                manifest["files"]["benchmark-b.jnnw"]["sha256"])
            for n in range(1, 19):
                self.assertEqual(manifest["files"][f"train-{n:02d}v{n+2:02d}.jnnw"]["records"], 4)

    def test_record_contract(self):
        gen = load(GEN, "imbalance_gen")
        records, meta = gen.build_pool(2, 7)
        gen.validate(records, meta)
        self.assertEqual(len(records), 36)
        for item in meta:
            self.assertEqual(item["high"] - item["low"], 2)


class GateAggregationTest(unittest.TestCase):
    def test_identical_wdl_vectors_pass(self):
        rows = []
        for n in range(1, 19):
            for i in range(24):
                outcome = ("win", "draw", "loss")[i % 3]
                rows.append({"index": len(rows), "stratum": f"{n}v{n+2}",
                             "candidate": outcome, "scan": outcome})
        with tempfile.TemporaryDirectory() as tmp:
            shard = Path(tmp) / "shard.json"
            out = Path(tmp) / "decision.json"
            shard.write_text(json.dumps({"rows": rows}))
            subprocess.run([sys.executable, str(GATE), "aggregate", "--inputs", str(shard),
                            "--out", str(out), "--bootstrap", "200", "--min-per-stratum", "20"],
                           check=True, capture_output=True, text=True)
            payload = json.loads(out.read_text())
            self.assertTrue(payload["pass"])
            self.assertEqual(payload["decision"], "scan_equivalent")


if __name__ == "__main__":
    unittest.main()
