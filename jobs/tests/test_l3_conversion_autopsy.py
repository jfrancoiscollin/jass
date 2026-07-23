#!/usr/bin/env python3
from __future__ import annotations

import gzip
import importlib.util
import io
import json
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/l3_conversion_autopsy.py"
spec = importlib.util.spec_from_file_location("l3_conversion_autopsy", TOOL)
autopsy = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(autopsy)


def write_pjtw(path: Path, values: list[int]) -> None:
    n_pat, n_ext = 8, 2
    weights = np.asarray(values, dtype="<i4")
    assert weights.size == 2 * (n_pat + n_ext)
    raw = b"PJTW" + struct.pack("<IIII", 515, 1000, n_pat, n_ext) + weights.tobytes()
    path.write_bytes(gzip.compress(raw, mtime=0))


def write_matrix(path: Path, *, pure: bool) -> None:
    rows = []
    outcomes = {
        "g0_g0": ("W", "W"),
        "scan_scan": ("W", "W"),
        "g4_g0": ("L", "W"),
        "g0_g4": ("W", "L"),
        "g4_scan": ("L", "W"),
        "scan_g4": ("W", "W"),
        "g4_g4": ("L", "W"),
    }
    for arm, (specialist, treatment) in outcomes.items():
        for index in range(2):
            rows.append({
                "arm": arm,
                "position_id": f"p{index}",
                "fen": f"W:W{index + 1}:B{index + 3}",
                "cell": "16v18|adv=B|stm=W",
                "stratum": "16v18",
                "advantaged": "B",
                "outcome_plus2": treatment if pure else specialist,
                "plies": 20,
                "hashes": {"pool_sha256": "pool"},
            })
    with tarfile.open(path, "w:gz") as archive:
        payload = "".join(json.dumps(row) + "\n" for row in rows).encode()
        info = tarfile.TarInfo("matrix/all/s0.jsonl")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))


class ConversionAutopsyTests(unittest.TestCase):
    def test_model_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pure = root / "pure.pjtw.gz"
            specialist = root / "specialist.pjtw.gz"
            write_pjtw(pure, list(range(20)))
            write_pjtw(specialist, [value + (value % 2) for value in range(20)])
            report = autopsy.compare_models(pure, specialist)
            self.assertEqual(report["pure"]["n_pat"], 8)
            self.assertEqual(report["banks"]["pattern_mg"]["changed"], 4)
            self.assertEqual(len(report["pattern_blocks"]["pattern_mg"]), 8)

    def test_exact_pairing_and_role_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specialist = root / "specialist.tar.gz"
            pure = root / "pure.tar.gz"
            write_matrix(specialist, pure=False)
            write_matrix(pure, pure=True)
            report = autopsy.compare_matrices(specialist, pure)
            self.assertEqual(report["paired_rows"], 14)
            self.assertTrue(report["same_pool_hash"])
            self.assertEqual(report["controls"]["g0_g0"]["identical_outcomes"], 2)
            self.assertEqual(
                report["arms"]["g4_g0"]["g4_role_effect_pure_minus_specialist"]["improved_positions"],
                2,
            )
            self.assertEqual(
                report["arms"]["g0_g4"]["g4_role_effect_pure_minus_specialist"]["improved_positions"],
                2,
            )


if __name__ == "__main__":
    unittest.main()
