#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "l3_x1_verdict.py"
SPEC = importlib.util.spec_from_file_location("l3_x1_verdict", MODULE)
V = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(V)


def fingerprint() -> str:
    # X1 shares one game search across all cells.
    values = {key: 0 for key in V.REQUIRED_SEARCH_KEYS}
    return ",".join(f"{key}={values[key]}" for key in V.REQUIRED_SEARCH_KEYS)


class VerdictFixture:
    """Synthetic five-cell X1 spec with a real write->read round-trip.

    ``wins`` per cell/stratum drives the paired conversion; the lead corner is
    X_HLL (+0.15 vs CONTROL), the centre also gains but must never lead.
    """

    def __init__(self, root: Path, p3_regression: bool = False):
        self.root = root
        self.search = fingerprint()
        self.spec = {
            "schema": 2,
            "baseline": V.CONTROL,
            "common_search_params": self.search,
            "conversion_delta_threshold": 0.02,
            "bootstrap": {"replicates": 300, "seed": 42},
            "cells": {},
        }
        base_wins = {V.CONTROL: 10, "X_LLH": 10, "X_HLL": 13, "X_LHL": 10, V.CENTER: 13}
        for cell in V.CELLS:
            conversion = {}
            for stratum in V.STRATA:
                wins = base_wins[cell]
                if p3_regression and cell == "X_HLL" and stratum == "p3_mince":
                    wins = 4  # establish a P3 regression on the otherwise-leading corner
                path = root / f"{cell}-{stratum}.json"
                self.write_conversion(path, stratum, wins)
                conversion[stratum] = path.name
            cell_spec = {"search_params": self.search, "conversion": conversion}
            if cell != V.CONTROL:
                common = root / f"common-{cell}.json"
                native = root / f"native-{cell}.json"
                self.write_gate(common, native=False)
                self.write_gate(native, native=True)
                cell_spec.update(common_gate=common.name, native_gate=native.name)
            self.spec["cells"][cell] = cell_spec
        self.spec_path = root / "spec.json"
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")

    def write_conversion(self, path: Path, stratum: str, wins: int):
        n = 20
        payload = {
            "schema": 2,
            "complete": True,
            "stratum": stratum,
            "expected_records": n,
            "n_pos": n,
            "n_win": wins,
            "n_draw": 0,
            "n_loss": n - wins,
            "n_errors": 0,
            "conversion": wins / n,
            "depth": 10,
            "movetime": None,
            "defender_jass": "j32",
            "defender_pattern": "gen2.pjtw",
            "search_params": self.search,
            "defender_search_params": self.search,
            "pool_sha256": str(V.STRATA.index(stratum) + 1) * 64,
            "position_results": [
                {"index": index, "result": "win" if index < wins else "loss"}
                for index in range(n)
            ],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def write_gate(self, path: Path, *, native: bool):
        payload = {
            "complete": True,
            "n": 600,
            "rate": 0.50,
            "ci_low": 0.44,
            "ci_high": 0.56,
            "elo": 0,
            "depth": None if native else 9,
            "movetime": 0.1 if native else None,
            "pairs": 1,
            "openings_file": "open.fen",
            "search_params_a": self.search,
            "search_params_b": self.search,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")


class L3X1VerdictTests(unittest.TestCase):
    def test_fingerprint_keys_track_the_engine_parser(self):
        source = (Path(__file__).resolve().parents[2] / "src/search_params.hpp").read_text()
        parser_keys = re.findall(r'key == "([^"]+)"', source)
        self.assertEqual(len(parser_keys), 63)
        self.assertEqual(set(V.REQUIRED_SEARCH_KEYS), set(parser_keys))

    def test_complete_contract_selects_the_leading_corner(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = VerdictFixture(Path(tmp))
            first = V.build_report(fixture.spec, fixture.spec_path)
            second = V.build_report(fixture.spec, fixture.spec_path)
            self.assertEqual(first, second)  # deterministic round-trip
            self.assertEqual(first["technical_status"], "complete")
            self.assertEqual(first["scientific_verdict"], "x1_lead_x_hll")
            self.assertEqual(first["selected_lead"], "X_HLL")
            self.assertTrue(first["screen"]["X_HLL"]["advance_to_confirmation"])
            self.assertGreaterEqual(
                first["screen"]["X_HLL"]["paired_conversion"]["global"]["estimate"], 0.02
            )
            self.assertIsNone(first["automatic_next_job"])

    def test_center_gains_but_is_never_a_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = VerdictFixture(Path(tmp))
            report = V.build_report(fixture.spec, fixture.spec_path)
            center = report["screen"][V.CENTER]
            self.assertFalse(center["lead_candidate"])
            self.assertGreaterEqual(
                center["paired_conversion"]["global"]["estimate"], 0.02
            )
            self.assertFalse(center["advance_to_confirmation"])
            self.assertNotIn(V.CENTER, report["eligible_leads"])
            # curvature is reported (centre vs mean of four corners)
            self.assertIn("curvature_global", report)

    def test_established_p3_regression_blocks_the_leading_corner(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = VerdictFixture(Path(tmp), p3_regression=True)
            report = V.build_report(fixture.spec, fixture.spec_path)
            hll = report["screen"]["X_HLL"]
            self.assertFalse(hll["p3_non_regression"])
            self.assertFalse(hll["advance_to_confirmation"])
            self.assertEqual(report["scientific_verdict"], "x1_no_lead")

    def test_divergent_cell_fingerprint_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = VerdictFixture(Path(tmp))
            # perturb one key on X_LLH's search -> must be rejected as non-shared
            broken = fixture.search.replace("nmp_min_depth=0", "nmp_min_depth=1")
            fixture.spec["cells"]["X_LLH"]["search_params"] = broken
            with self.assertRaisesRegex(ValueError, "shared common-search"):
                V.build_report(fixture.spec, fixture.spec_path)

    def test_missing_cell_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = VerdictFixture(Path(tmp))
            del fixture.spec["cells"][V.CENTER]
            with self.assertRaisesRegex(ValueError, "exactly the five"):
                V.build_report(fixture.spec, fixture.spec_path)


if __name__ == "__main__":
    unittest.main()
