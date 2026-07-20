#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "jobs/tools/imbalance2_symmetric_exclusion.py"
PROGRESS = ROOT / "jobs/tools/imbalance2_phase_progress.py"
RUNNER = ROOT / "jobs/templates/l3-imbalance2-p2-consolidate-v1.sh"
PREP = ROOT / "jobs/prepared/l3-imbalance2-role-v2-20260720"
CPX = PREP / "cpx62-l3-imbalance2-p2-consolidate.sh"
CCX = PREP / "alternate-box/ccx33-l3-imbalance2-p2-consolidate.sh"


class P2ConsolidationTest(unittest.TestCase):
    @staticmethod
    def rows(outcome: str, error_index: int | None = None) -> list[dict[str, object]]:
        rows = []
        for index in range(36):
            n = index // 2 + 1
            row: dict[str, object] = {
                "index": index,
                "stratum": f"{n}v{n+2}",
                "advantaged_side": "W" if index % 2 == 0 else "B",
                "outcome": outcome,
                "reason": "test",
            }
            if error_index == index:
                row.pop("outcome")
                row["error"] = "candidate-W: no match in 60.0s"
            rows.append(row)
        return rows

    @staticmethod
    def write_report(path: Path, pool: str, rows: list[dict[str, object]]) -> None:
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

    def make_manifest(self, root: Path, second_error: bool = False) -> Path:
        outcomes = {"G4": "loss", "G5": "draw", "G6": "draw", "G7": "win", "G8": "win"}
        report_sets: dict[str, list[str]] = {}
        for generation, outcome in outcomes.items():
            paths = []
            for pool in ("a", "b"):
                path = root / f"{generation}-{pool}.json"
                error_index = 0 if generation == "G8" and pool == "a" else None
                if second_error and generation == "G7" and pool == "b":
                    error_index = 1
                self.write_report(
                    path,
                    f"plateau-{pool}.jnnw",
                    self.rows(outcome, error_index),
                )
                paths.append(str(path))
            report_sets[generation] = paths
        manifest = root / "raw-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "same_pools": True,
                    "same_search_budget": True,
                    "report_sets": report_sets,
                }
            ),
            encoding="utf-8",
        )
        return manifest

    @staticmethod
    def write_reference(path: Path) -> None:
        strata = {}
        for n in range(1, 19):
            strata[f"{n}v{n+2}"] = {
                "n": 128,
                "total_pieces": 2 * n + 2,
                "source": "exact_egdb_wdl" if n <= 2 else "scan_d10_selfplay_reference",
                "rates": {"win": 0.5, "draw": 0.4, "loss": 0.1},
                "failure_cost_2loss_plus_draw": 0.6,
            }
        path.write_text(
            json.dumps(
                {
                    "protocol": "material-stratified-conversion-difficulty-reference",
                    "reference_used_for_training": False,
                    "reference_used_for_weighting": False,
                    "scan_reference_is_exact": False,
                    "strata": strata,
                }
            ),
            encoding="utf-8",
        )

    def test_one_allowed_error_is_removed_from_all_generations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_manifest(root)
            clean_manifest = root / "clean-manifest.json"
            exclusions = root / "exclusions.json"
            subprocess.run(
                [
                    sys.executable,
                    str(CLEAN),
                    "--manifest",
                    str(manifest),
                    "--out-dir",
                    str(root / "clean"),
                    "--out-manifest",
                    str(clean_manifest),
                    "--report",
                    str(exclusions),
                    "--expected-per-stratum",
                    "2",
                    "--max-excluded-positions",
                    "1",
                    "--max-excluded-fraction",
                    "0.02",
                    "--allow-error-substring",
                    "no match in 60.0s",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(exclusions.read_text())
            self.assertEqual(report["excluded_distinct_positions"], 1)
            self.assertEqual(report["rows_dropped_by_set"], {g: 1 for g in ("G4", "G5", "G6", "G7", "G8")})
            cleaned = json.loads(clean_manifest.read_text())
            for paths in cleaned["report_sets"].values():
                row_count = sum(len(json.loads(Path(path).read_text())["rows"]) for path in paths)
                self.assertEqual(row_count, 71)

            reference = root / "reference.json"
            self.write_reference(reference)
            out = root / "progress.json"
            subprocess.run(
                [
                    sys.executable,
                    str(PROGRESS),
                    "--manifest",
                    str(clean_manifest),
                    "--reference",
                    str(reference),
                    "--exclusions",
                    str(exclusions),
                    "--out",
                    str(out),
                    "--bootstrap",
                    "1000",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(out.read_text())
            self.assertEqual(payload["decision"], "P2_CLEAR_BROAD_IMPROVEMENT")
            self.assertTrue(payload["clear_broad_improvement"])
            self.assertFalse(payload["p3_authorized"])
            self.assertFalse(payload["promotion_authorized"])
            self.assertTrue(payload["difficulty_reference_used_for_reporting"])
            macro = payload["comparisons"]["G4_to_G8"]["macro_equal_stratum"]
            self.assertEqual(macro["nonworse_strata"], 18)
            self.assertEqual(macro["last_minus_first_failure_cost"], -2.0)

    def test_exclusion_cap_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_manifest(root, second_error=True)
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLEAN),
                    "--manifest",
                    str(manifest),
                    "--out-dir",
                    str(root / "clean"),
                    "--out-manifest",
                    str(root / "clean.json"),
                    "--report",
                    str(root / "exclusions.json"),
                    "--expected-per-stratum",
                    "2",
                    "--max-excluded-positions",
                    "1",
                    "--max-excluded-fraction",
                    "0.05",
                    "--allow-error-substring",
                    "no match in 60.0s",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("exceeds cap", result.stderr)

    def test_runner_and_box_wrappers_are_shell_valid_and_equivalent(self):
        for path in (RUNNER, CPX, CCX):
            subprocess.run(["bash", "-n", str(path)], check=True, capture_output=True, text=True)
        cpx_exports = [line for line in CPX.read_text().splitlines() if line.startswith("export ")]
        ccx_exports = [line for line in CCX.read_text().splitlines() if line.startswith("export ")]
        self.assertEqual(cpx_exports, ccx_exports)
        self.assertIn("MAX_EXCLUDED_POSITIONS=2", CPX.read_text())
        self.assertIn("MIN_NONWORSE_STRATA=12", CPX.read_text())
        self.assertIn("l3-imbalance2-p2-consolidate-v1.sh", CPX.read_text())


if __name__ == "__main__":
    unittest.main()
