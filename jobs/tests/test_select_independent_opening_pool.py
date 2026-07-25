#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/select_independent_opening_pool.py"


class IndependentOpeningSelectionTests(unittest.TestCase):
    def invoke(
        self,
        candidates: Path,
        exclude: Path,
        expected: int,
        out: Path,
        manifest: Path,
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--candidates",
                str(candidates),
                "--expected",
                str(expected),
                "--exclude",
                str(exclude),
                "--generator-seed",
                "244949",
                "--out",
                str(out),
                "--manifest",
                str(manifest),
            ],
            check=check,
            capture_output=True,
            text=True,
        )

    def test_filters_overlap_and_duplicates_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = root / "candidates.fen"
            exclude = root / "exclude.fen"
            out = root / "selected.fen"
            manifest = root / "manifest.json"
            candidates.write_text(
                "W:W31:B20\n"
                "W:W32:B19\n"
                "W:W31:B20\n"
                "W:W33:B18\n"
                "W:W34:B17\n",
                encoding="utf-8",
            )
            exclude.write_text("W:W32:B19\n", encoding="utf-8")

            self.invoke(candidates, exclude, 3, out, manifest)

            self.assertEqual(
                out.read_text(encoding="utf-8").splitlines(),
                ["W:W31:B20", "W:W33:B18", "W:W34:B17"],
            )
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["records"], 3)
            self.assertEqual(payload["unique_records"], 3)
            self.assertEqual(payload["overlap_records"], 0)
            self.assertEqual(payload["excluded_candidates_before_cutoff"], 1)
            self.assertEqual(payload["duplicate_candidates_before_cutoff"], 1)

    def test_fails_when_candidate_reserve_is_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidates = root / "candidates.fen"
            exclude = root / "exclude.fen"
            out = root / "selected.fen"
            manifest = root / "manifest.json"
            candidates.write_text("W:W31:B20\nW:W31:B20\n", encoding="utf-8")
            exclude.write_text("", encoding="utf-8")

            proc = self.invoke(
                candidates, exclude, 2, out, manifest, check=False
            )

            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("not enough independent openings", proc.stderr)


if __name__ == "__main__":
    unittest.main()
