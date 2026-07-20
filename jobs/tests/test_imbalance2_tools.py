#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "jobs/tools/make_imbalance2_pools.py"
PREP = ROOT / "jobs/tools/prepare_imbalance2_training.py"
GATE = ROOT / "jobs/tools/imbalance2_scan_gate.py"
PLATEAU = ROOT / "jobs/tools/imbalance2_plateau.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ImbalancePoolsTest(unittest.TestCase):
    def test_all_18_strata_split_by_advantaged_colour(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([
                sys.executable, str(GEN), "--out-dir", tmp,
                "--train-per-side", "4", "--bench-per-stratum", "4", "--plateau-per-stratum", "2",
                "--seed", "271828",
            ], check=True, capture_output=True, text=True)
            manifest = json.loads((Path(tmp) / "manifest.json").read_text())
            self.assertEqual(manifest["schema"], 2)
            self.assertEqual(manifest["strata"], [f"{n}v{n+2}" for n in range(1, 19)])
            self.assertEqual(manifest["files"]["benchmark-a.jnnw"]["records"], 72)
            self.assertEqual(manifest["files"]["plateau-a.jnnw"]["records"], 36)
            self.assertNotEqual(
                manifest["files"]["benchmark-a.jnnw"]["sha256"],
                manifest["files"]["benchmark-b.jnnw"]["sha256"],
            )
            for n in range(1, 19):
                for side in ("W", "B"):
                    key = f"train-{n:02d}v{n+2:02d}-up{side}.jnnw"
                    self.assertEqual(manifest["files"][key]["records"], 4)
                    self.assertEqual(manifest["files"][key]["advantaged_side"], side)

    def test_static_tb_source_is_restricted_below_seven_pieces(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([
                sys.executable, str(PREP), "static", "--low", "2", "--high", "4",
                "--advantaged-side", "W", "--count", "20", "--seed", "7",
                "--out-data", f"{tmp}/data.jnnw", "--out-meta", f"{tmp}/data.jsm",
                "--report", f"{tmp}/report.json",
            ], check=True, capture_output=True, text=True)
            report = json.loads(Path(f"{tmp}/report.json").read_text())
            self.assertEqual(report["records"], 20)
            self.assertEqual(report["total_pieces"], 6)
            self.assertTrue(report["requires_egdb_relabel"])


class OutcomeWeightTest(unittest.TestCase):
    def test_material_up_outcome_code_and_weight_order(self):
        prep = load(PREP, "imbalance_prepare")
        with tempfile.TemporaryDirectory() as tmp:
            records = []
            # Up side W. Encode one up-win, one draw and one up-loss, repeated.
            for wdl in (1, 0, -1) * 10:
                records.append(bytearray(struct.pack("<QQQQBi", 1, 0, 6, 0, 0, 0) + struct.pack("<b", wdl)))
            prep.write_jnnw(Path(tmp) / "in.jnnw", records)
            subprocess.run([
                sys.executable, str(PREP), "encode", "--input", f"{tmp}/in.jnnw",
                "--output", f"{tmp}/coded.jnnw", "--advantaged-side", "W",
                "--report", f"{tmp}/coded.json",
            ], check=True, capture_output=True, text=True)
            v1_env = dict(os.environ)
            v1_env.pop("IMBALANCE2_REWEIGHT_POLICY", None)
            subprocess.run([
                sys.executable, str(PREP), "reweight", "--input", f"{tmp}/coded.jnnw",
                "--output", f"{tmp}/weighted.jnnw", "--holdout-count", "3",
                "--win-weight", "1", "--draw-weight", "2", "--loss-weight", "4",
                "--seed", "11", "--report", f"{tmp}/weighted.json",
            ], check=True, capture_output=True, text=True, env=v1_env)
            report = json.loads(Path(f"{tmp}/weighted.json").read_text())
            self.assertEqual(report["weights_material_up_pov"], {"win": 1.0, "draw": 2.0, "loss": 4.0})
            sampled = report["resampled_training_counts"]
            self.assertGreater(sampled["loss"], sampled["draw"])
            self.assertGreater(sampled["draw"], sampled["win"])
            self.assertEqual(report["holdout_records_untouched"], 3)

    def test_role_aware_v2_rewards_conversion_failures_and_defensive_successes(self):
        prep = load(PREP, "imbalance_prepare_role_v2")

        def bb(*squares: int) -> int:
            value = 0
            for square in squares:
                value |= 1 << (square - 1)
            return value

        def rec(stm: int, wdl: int, wm: int, bm: int, wk: int = 0, bk: int = 0) -> bytearray:
            return bytearray(struct.pack("<QQQQBi", wm, wk, bm, bk, stm, 0) + struct.pack("<b", wdl))

        # White is currently +2 men in the six in-domain buckets.
        prototypes = [
            rec(0, 1, bb(10, 11, 12), bb(30)),
            rec(0, 0, bb(10, 11, 12), bb(30)),
            rec(0, -1, bb(10, 11, 12), bb(30)),
            rec(1, -1, bb(10, 11, 12), bb(30)),
            rec(1, 0, bb(10, 11, 12), bb(30)),
            rec(1, 1, bb(10, 11, 12), bb(30)),
            rec(0, 1, bb(10, 11), bb(30, 31)),
        ]
        expected_buckets = [
            "up_win", "up_draw", "up_loss", "down_loss", "down_draw", "down_win",
            "anchor_outside_exact_2men_equal_kings",
        ]
        self.assertEqual([prep.record_role_bucket(item) for item in prototypes], expected_buckets)
        self.assertEqual(
            [prep.role_bucket_weight(bucket, 1.0, 2.0, 4.0) for bucket in expected_buckets],
            [1.0, 2.0, 4.0, 1.0, 2.0, 4.0, 1.0],
        )

        with tempfile.TemporaryDirectory() as tmp:
            records = [bytearray(item) for item in prototypes for _ in range(80)]
            holdout = 7
            source = Path(tmp) / "coded.jnnw"
            prep.write_jnnw(source, records)
            env = dict(os.environ, IMBALANCE2_REWEIGHT_POLICY="role-aware-v2")
            command = [
                sys.executable, str(PREP), "reweight", "--input", str(source),
                "--output", f"{tmp}/weighted-a.jnnw", "--holdout-count", str(holdout),
                "--win-weight", "1", "--draw-weight", "2", "--loss-weight", "4",
                "--seed", "19", "--report", f"{tmp}/weighted-a.json",
            ]
            subprocess.run(command, check=True, capture_output=True, text=True, env=env)
            command[command.index(f"{tmp}/weighted-a.jnnw")] = f"{tmp}/weighted-b.jnnw"
            command[command.index(f"{tmp}/weighted-a.json")] = f"{tmp}/weighted-b.json"
            subprocess.run(command, check=True, capture_output=True, text=True, env=env)

            report = json.loads(Path(f"{tmp}/weighted-a.json").read_text())
            self.assertEqual(report["mode"], "deterministic_role_domain_resample")
            self.assertEqual(report["policy"], "role-aware-v2")
            self.assertEqual(report["domain"]["men_gap"], 2)
            self.assertTrue(report["domain"]["equal_king_counts"])
            self.assertFalse(report["score_field_used_for_weighting"])
            self.assertFalse(report["per_move_criticality_relabel"])
            self.assertEqual(report["holdout_records_untouched"], holdout)
            self.assertEqual(
                report["weight_semantics"]["matrix_side_to_move_pov"],
                {
                    "up": {"win": 1.0, "draw": 2.0, "loss": 4.0},
                    "down": {"win": 4.0, "draw": 2.0, "loss": 1.0},
                },
            )
            sampled = report["resampled_training_buckets"]
            expected_total = sampled["up_win"] + sampled["down_loss"]
            draw_total = sampled["up_draw"] + sampled["down_draw"]
            upset_total = sampled["up_loss"] + sampled["down_win"]
            self.assertGreater(upset_total, draw_total)
            self.assertGreater(draw_total, expected_total)
            self.assertEqual(Path(f"{tmp}/weighted-a.jnnw").read_bytes(), Path(f"{tmp}/weighted-b.jnnw").read_bytes())
            weighted = prep.read_jnnw(Path(f"{tmp}/weighted-a.jnnw"))
            self.assertEqual(weighted[-holdout:], records[-holdout:])


class GateAggregationTest(unittest.TestCase):
    def test_scan_equal_and_above_gen2_passes(self):
        engines = {"candidate": [], "gen2": [], "scan": []}
        for n in range(1, 19):
            for i in range(24):
                index = len(engines["candidate"])
                target = ("win", "draw", "loss")[i % 3]
                gen2 = "loss" if i % 4 == 0 else target
                for engine, outcome in (("candidate", target), ("scan", target), ("gen2", gen2)):
                    engines[engine].append({"index": index, "stratum": f"{n}v{n+2}", "outcome": outcome})
        with tempfile.TemporaryDirectory() as tmp:
            paths = {}
            for engine, rows in engines.items():
                path = Path(tmp) / f"{engine}.json"
                path.write_text(json.dumps({"engine": engine, "rows": rows}))
                paths[engine] = path
            out = Path(tmp) / "decision.json"
            subprocess.run([
                sys.executable, str(GATE), "aggregate",
                "--candidate-inputs", str(paths["candidate"]),
                "--gen2-inputs", str(paths["gen2"]),
                "--scan-inputs", str(paths["scan"]),
                "--out", str(out), "--bootstrap", "200", "--min-per-stratum", "20",
            ], check=True, capture_output=True, text=True)
            payload = json.loads(out.read_text())
            self.assertTrue(payload["pass"])
            self.assertEqual(payload["decision"], "scan_equivalent_above_gen2")
            self.assertTrue(payload["gen2_lower_reference_pass"])


class PlateauTest(unittest.TestCase):
    def test_flat_candidate_only_window_confirms_plateau(self):
        with tempfile.TemporaryDirectory() as tmp:
            generations = {}
            for generation in range(1, 5):
                paths = []
                for pool in ("a", "b"):
                    path = Path(tmp) / f"g{generation}-{pool}.json"
                    rows = []
                    for index in range(36):
                        rows.append({"index": index, "stratum": f"{index % 18 + 1}v{index % 18 + 3}",
                                     "outcome": ("win", "draw", "loss")[index % 3]})
                    path.write_text(json.dumps({"engine": "candidate",
                                                "pool": f"/x/plateau-{pool}.jnnw", "rows": rows}))
                    paths.append(str(path))
                generations[f"G{generation}"] = paths
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"same_search_budget": True, "generations": generations}))
            out = Path(tmp) / "plateau.json"
            subprocess.run([sys.executable, str(PLATEAU), "--manifest", str(manifest),
                            "--out", str(out), "--bootstrap", "200"],
                           check=True, capture_output=True, text=True)
            payload = json.loads(out.read_text())
            self.assertTrue(payload["plateau_confirmed"])
            self.assertEqual(payload["decision"], "PLATEAU_CONFIRMED")


if __name__ == "__main__":
    unittest.main()
