#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
POOLS = ROOT / "jobs/tools/make_imbalance2_pools.py"
COMPARE = ROOT / "jobs/tools/imbalance2_lineage_compare.py"
COMPARE_RUNNER = ROOT / "jobs/templates/l3-imbalance2-p1-compare-v1.sh"
COMPARE_WRAPPER = (
    ROOT
    / "jobs/prepared/l3-imbalance2-role-v2-20260720"
    / "cpx62-l3-imbalance2-p1-v1-v2-a64-compare.sh"
)


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

    def test_clear_v2_lead_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_manifest(root)
            out = root / "out.json"
            subprocess.run(
                [
                    sys.executable,
                    str(COMPARE),
                    "--manifest",
                    str(manifest),
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
            self.assertTrue(payload["v2_clear_lead"])
            self.assertEqual(payload["decision"], "V2_CLEAR_LEAD_AT_P1")
            self.assertFalse(payload["promotion_authorized"])
            self.assertIsNone(payload["automatic_next_job"])
            self.assertEqual(
                payload["generation_reports"]["G4"]["v2_minus_v1_failure_cost"],
                -1.0,
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


class PreparedShellSyntaxTest(unittest.TestCase):
    def test_comparison_runner_and_wrapper_parse(self):
        for path in (COMPARE_RUNNER, COMPARE_WRAPPER):
            subprocess.run(
                ["bash", "-n", str(path)],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
