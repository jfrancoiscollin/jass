#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import jfi_boundary_a


def valid_input():
    return {
        "schema": "jass.jfi.boundary_a_input.v1",
        "code_sha": "a" * 40,
        "machine": {"host": "cpx62", "nproc": 16, "avx2": True, "bmi2": True,
                    "native_build": True},
        "numeric_env": {"OMP_NUM_THREADS": "1"},
        "disk": {"code_path": "/code", "code_free_bytes": 10**11,
                 "scratch_path": "/scratch/jfi", "scratch_free_bytes": 10**11},
        "current_2m": {
            "records": 2_000_000,
            "train_records": 1_800_796,
            "holdout_records": 199_204,
            "split_seed": 577215,
            "sha256": "b" * 64,
        },
        "context30": {"sha256": "c" * 64},
        "feature_dump": {"rows": 2_000_000, "seconds": 100.0},
        "sizer": {"rows": 10_000, "iterations": 2, "seconds": 4.0,
                  "full_fit_timeout_seconds": 86400},
        "markers": dict(jfi_boundary_a.ZERO_MARKERS),
    }


class BoundaryATests(unittest.TestCase):
    def test_valid_input_stops_at_fit_boundary(self):
        facts = jfi_boundary_a.build_facts(valid_input())
        self.assertEqual(facts["verdict"], "JFI_BOUNDARY_A_READY")
        self.assertEqual(facts["next_boundary"], "GO JFI FIT")
        self.assertEqual(facts["markers"], jfi_boundary_a.ZERO_MARKERS)
        self.assertGreater(facts["sizer"]["projected_seconds_seven_physical_arms"], 0)

    def test_full_fit_marker_fails_closed(self):
        source = valid_input()
        source["markers"]["FULL_FITS"] = 1
        with self.assertRaisesRegex(ValueError, "zero markers mismatch"):
            jfi_boundary_a.build_facts(source)

    def test_sizer_volume_and_iterations_are_bounded(self):
        for field, value in (("rows", 20_001), ("iterations", 3)):
            source = copy.deepcopy(valid_input())
            source["sizer"][field] = value
            with self.assertRaisesRegex(ValueError, "sizer must be bounded"):
                jfi_boundary_a.build_facts(source)

    def test_scan_read_marker_fails_closed(self):
        source = valid_input()
        source["markers"]["SCAN_WEIGHT_READS"] = 1
        with self.assertRaisesRegex(ValueError, "zero markers mismatch"):
            jfi_boundary_a.build_facts(source)


if __name__ == "__main__":
    unittest.main()
