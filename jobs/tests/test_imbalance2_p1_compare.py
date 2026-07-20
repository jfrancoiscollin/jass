#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
POOLS = ROOT / "jobs/tools/make_imbalance2_pools.py"
COMPARE = ROOT / "jobs/tools/imbalance2_lineage_compare.py"
DIFFICULTY = ROOT / "jobs/tools/imbalance2_difficulty_reference.py"
COMPARE_RUNNER = ROOT / "jobs/templates/l3-imbalance2-p1-compare-v1.sh"
REFERENCE_RUNNER = ROOT / "jobs/templates/l3-imbalance2-difficulty-reference-v1.sh"
PREP = ROOT / "jobs/prepared/l3-imbalance2-role-v2-20260720"
COMPARE_WRAPPER = PREP / "cpx62-l3-imbalance2-p1-v1-v2-a64-compare.sh"
REFERENCE_WRAPPER = PREP / "cpx62-l3-imbalance2-a64-b64-difficulty-reference.sh"
REC = struct.Struct("<QQQQBiB")


class IndependentPlateauPoolsTest(unittest.TestCase):
    def run_pools(self, out: Path, plateau_seed: int) -> dict:
        subprocess.run(
            [
                sys.executable,
                str(POOLS),
                "--out-dir",
                str(out),
                "--train-per-side",
                "2",
                "--bench-per-stratum",
                "2",
                "--plateau-per-stratum",
                "4",
                "--seed",
                "271828",
                "--plateau-seed",
                str(plateau_seed),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    def test_plateau_seed_does_not_change_training_or_final_benchmark(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self.run_pools(root / "a", 161803)
            b = self.run_pools(root / "b", 314159)
            self.assertEqual(a["schema"], 2)
            self.assertEqual(a["training_seed"], 271828)
            self.assertEqual(a["plateau_seed"], 161803)
            self.assertEqual(a["plateau_records_per_pool"], 72)
            for name, meta in a["files"].items():
                if name.startswith("train-") or name.startswith("benchmark-"):
                    self.assertEqual(meta["sha256"], b["files"][name]["sha256"])
                elif name.startswith("plateau-"):
                    self.assertNotEqual(meta["sha256"], b["files"][name]["sha256"])


class PairedLineageComparisonTest(unittest.TestCase):
    @staticmethod
    def write_report(path: Path, pool: str, outcomes: list[str]) -> None:
        rows = [
            {
                "index": index,
                "stratum": f"{index % 18 + 1}v{index % 18 + 3}",
                "advantaged_side": "W" if index % 2 == 0 else "B",
                "outcome": outcome,
                "reason": "test",
            }
            for index, outcome in enumerate(outcomes)
        ]
        path.write_text(
            json.dumps(
                {
                    "schema": 3,
                    "protocol": "fixed-position-engine-selfplay",
                    "engine": "candidate",
                    "perspective": "material_up_side",
                    "pool": pool,
                    "shard": 0,
                    "nshards": 1,
                    "rows": rows,
                }
            ),
            encoding="utf-8",
        )

    def make_manifest(self, root: Path, misalign: bool = False) -> Path:
        lineages: dict[str, dict[str, list[str]]] = {"v1": {}, "v2": {}}
        for lineage in ("v1", "v2"):
            for generation in range(1, 5):
                paths = []
                for pool in ("a", "b"):
                    path = root / f"{lineage}-g{generation}-{pool}.json"
                    count = 19 if misalign and lineage == "v2" and generation == 4 and pool == "b" else 20
                    outcome = "draw" if lineage == "v1" else "win"
                    self.write_report(path, f"plateau-{pool}.jnnw", [outcome] * count)
                    paths.append(str(path))
                lineages[lineage][f"G{generation}"] = paths
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "same_pools": True,
                    "same_search_budget": True,
                    "lineages": lineages,
                }
            ),
            encoding="utf-8",
        )
        return manifest

    @staticmethod
    def write_reference(path: Path) -> None:
        strata = {}
        for n in range(1, 19):
            source = "exact_egdb_wdl" if n <= 2 else "scan_d10_selfplay_reference"
            strata[f"{n}v{n+2}"] = {
                "n": 128,
                "total_pieces": 2 * n + 2,
                "source": source,
                "rates": {"win": 0.5, "draw": 0.4, "loss": 0.1},
                "failure_cost_2loss_plus_draw": 0.6,
            }
        path.write_text(
            json.dumps(
                {
                    "protocol": "material-stratified-conversion-difficulty-reference",
                    "reference_used_for_training": False,
                    "scan_reference_is_exact": False,
                    "strata": strata,
                }
            ),
            encoding="utf-8",
        )

    def test_clear_v2_lead_is_detected_with_stratified_reference_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_manifest(root)
            reference = root / "reference.json"
            self.write_reference(reference)
            out = root / "out.json"
            subprocess.run(
                [
                    sys.executable,
                    str(COMPARE),
                    "--manifest",
                    str(manifest),
                    "--reference",
                    str(reference),
                    "--out",
                    str(out),
                    "--bootstrap",
                    "1000",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], 2)
            self.assertTrue(payload["v2_clear_lead"])
            self.assertEqual(payload["decision"], "V2_CLEAR_LEAD_AT_P1")
            self.assertFalse(payload["promotion_authorized"])
            self.assertIsNone(payload["automatic_next_job"])
            g4 = payload["generation_reports"]["G4"]
            self.assertEqual(g4["v2_minus_v1_failure_cost"], -1.0)
            self.assertEqual(len(g4["strata"]), 18)
            self.assertEqual(g4["macro_equal_stratum"]["v2_minus_v1_failure_cost"], -1.0)
            self.assertTrue(payload["difficulty_reference_used_for_reporting"])
            self.assertFalse(payload["difficulty_reference_used_in_lead_rule"])
            self.assertEqual(g4["strata"]["1v3"]["difficulty_reference"]["source"], "exact_egdb_wdl")
            self.assertEqual(
                g4["strata"]["18v20"]["difficulty_reference"]["source"],
                "scan_d10_selfplay_reference",
            )

    def test_misaligned_rows_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_manifest(root, misalign=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(COMPARE),
                    "--manifest",
                    str(manifest),
                    "--out",
                    str(root / "out.json"),
                    "--bootstrap",
                    "1000",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not perfectly paired", result.stderr)


class DifficultyReferenceToolTest(unittest.TestCase):
    @staticmethod
    def write_jnnw(path: Path, records: list[bytes]) -> None:
        path.write_bytes(b"JNNW" + struct.pack("<I", len(records)) + b"".join(records))

    def test_exact_low_strata_and_scan_high_strata_are_separated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = []
            metadata = []
            for n in range(1, 19):
                high = n + 2
                wm = (1 << high) - 1
                bm = ((1 << n) - 1) << 24
                records.append(REC.pack(wm, 0, bm, 0, 0, 0, 0))
                metadata.append(
                    {
                        "index": n - 1,
                        "stratum": f"{n}v{high}",
                        "white_men": high,
                        "black_men": n,
                        "advantaged_side": "W",
                        "stm": "W",
                    }
                )
            pool = root / "plateau-a.jnnw"
            meta = root / "plateau-a.json"
            self.write_jnnw(pool, records)
            meta.write_text(json.dumps(metadata), encoding="utf-8")

            exact_data = root / "exact.jnnw"
            exact_meta = root / "exact.json"
            high_data = root / "high.jnnw"
            high_meta = root / "high.json"
            subprocess.run(
                [sys.executable, str(DIFFICULTY), "extract", "--pool", str(pool), "--meta", str(meta),
                 "--mode", "exact", "--out-data", str(exact_data), "--out-meta", str(exact_meta)],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                [sys.executable, str(DIFFICULTY), "extract", "--pool", str(pool), "--meta", str(meta),
                 "--mode", "high", "--out-data", str(high_data), "--out-meta", str(high_meta)],
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(len(json.loads(exact_meta.read_text())), 2)
            high_items = json.loads(high_meta.read_text())
            self.assertEqual(len(high_items), 16)

            raw = bytearray(exact_data.read_bytes())
            struct.pack_into("<b", raw, 8 + 37, 0)
            struct.pack_into("<b", raw, 8 + 38 + 37, 1)
            exact_labelled = root / "exact-labelled.jnnw"
            exact_labelled.write_bytes(raw)

            scan = root / "scan.json"
            scan.write_text(
                json.dumps(
                    {
                        "engine": "scan",
                        "pool": "plateau-a.jnnw",
                        "rows": [
                            {
                                "index": index,
                                "stratum": item["stratum"],
                                "outcome": "win" if index % 2 == 0 else "draw",
                            }
                            for index, item in enumerate(high_items)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            out = root / "reference.json"
            subprocess.run(
                [
                    sys.executable, str(DIFFICULTY), "aggregate",
                    "--tb-data", str(exact_labelled), "--tb-meta", str(exact_meta),
                    "--scan-inputs", str(scan), "--out", str(out),
                ],
                check=True, capture_output=True, text=True,
            )
            payload = json.loads(out.read_text())
            self.assertEqual(payload["strata"]["1v3"]["source"], "exact_egdb_wdl")
            self.assertEqual(payload["strata"]["2v4"]["source"], "exact_egdb_wdl")
            self.assertEqual(payload["strata"]["3v5"]["source"], "scan_d10_selfplay_reference")
            self.assertEqual(payload["strata"]["18v20"]["total_pieces"], 38)
            self.assertFalse(payload["scan_reference_is_exact"])
            self.assertFalse(payload["reference_used_for_training"])


class PreparedShellSyntaxTest(unittest.TestCase):
    def test_comparison_and_reference_runners_and_wrappers_parse(self):
        for path in (COMPARE_RUNNER, COMPARE_WRAPPER, REFERENCE_RUNNER, REFERENCE_WRAPPER):
            subprocess.run(
                ["bash", "-n", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
