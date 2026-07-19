#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "l3_screen_verdict.py"
SPEC = importlib.util.spec_from_file_location("l3_screen_verdict", MODULE)
V = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(V)

FP = ",".join(f"{k}=0" for k in V.REQUIRED_SEARCH_KEYS)


class Fixture:
    def __init__(self, root: Path, wins: dict, p3_regression: bool = False):
        self.root = root
        self.cells = list(wins)
        self.spec = {
            "schema": 2, "experiment": "L3-PURE-C3-MF", "baseline": "CONTROL",
            "common_search_params": FP, "conversion_delta_threshold": 0.02,
            "bootstrap": {"replicates": 300, "seed": 7}, "cells": {},
        }
        for cell, w in wins.items():
            conv = {}
            for stratum in V.STRATA:
                ww = 3 if (p3_regression and cell == "MF_L2LO" and stratum == "p3_mince") else w
                p = root / f"{cell}-{stratum}.json"
                self._conv(p, stratum, ww)
                conv[stratum] = p.name
            cs = {"search_params": FP, "conversion": conv, "meta": {"l2": cell}}
            if cell != "CONTROL":
                cg, ng = root / f"c-{cell}.json", root / f"n-{cell}.json"
                self._gate(cg, native=False)
                self._gate(ng, native=True)
                cs["common_gate"], cs["native_gate"] = cg.name, ng.name
            self.spec["cells"][cell] = cs
        self.spec_path = root / "spec.json"
        self.spec_path.write_text(json.dumps(self.spec))

    def _conv(self, path, stratum, wins):
        n = 20
        path.write_text(json.dumps({
            "schema": 2, "complete": True, "stratum": stratum, "expected_records": n,
            "n_pos": n, "n_win": wins, "n_draw": 0, "n_loss": n - wins, "n_errors": 0,
            "conversion": wins / n, "depth": 10, "movetime": None, "defender_jass": "j32",
            "defender_pattern": "gen2", "search_params": FP, "defender_search_params": FP,
            "pool_sha256": str(V.STRATA.index(stratum) + 1) * 64,
            "position_results": [{"index": i, "result": "win" if i < wins else "loss"} for i in range(n)],
        }))

    @staticmethod
    def _gate(path, *, native):
        path.write_text(json.dumps({
            "complete": True, "n": 600, "rate": 0.5, "ci_low": 0.44, "ci_high": 0.56, "elo": 0,
            "depth": None if native else 9, "movetime": 0.1 if native else None,
            "pairs": 1, "openings_file": "open.fen", "search_params_a": FP, "search_params_b": FP,
        }))


class ScreenVerdictTests(unittest.TestCase):
    def test_leading_challenger_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp), {"CONTROL": 10, "MF_L2LO": 13, "MF_L2HI": 10})
            r1 = V.build_report(fx.spec, fx.spec_path)
            r2 = V.build_report(fx.spec, fx.spec_path)
            self.assertEqual(r1, r2)
            self.assertEqual(r1["technical_status"], "complete")
            self.assertEqual(r1["scientific_verdict"], "screen_lead_mf_l2lo")
            self.assertEqual(r1["selected_lead"], "MF_L2LO")
            self.assertTrue(r1["screen"]["MF_L2LO"]["advance_to_confirmation"])
            self.assertGreaterEqual(r1["screen"]["MF_L2LO"]["paired_conversion"]["global"]["estimate"], 0.02)

    def test_flat_sweep_no_lead(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp), {"CONTROL": 10, "MF_L2LO": 10, "MF_L2HI": 10})
            r = V.build_report(fx.spec, fx.spec_path)
            self.assertEqual(r["scientific_verdict"], "screen_no_lead")
            self.assertEqual(r["eligible_leads"], [])

    def test_p3_regression_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp), {"CONTROL": 10, "MF_L2LO": 13, "MF_L2HI": 10}, p3_regression=True)
            r = V.build_report(fx.spec, fx.spec_path)
            self.assertFalse(r["screen"]["MF_L2LO"]["p3_non_regression"])
            self.assertFalse(r["screen"]["MF_L2LO"]["advance_to_confirmation"])
            self.assertEqual(r["scientific_verdict"], "screen_no_lead")

    def test_divergent_fingerprint_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = Fixture(Path(tmp), {"CONTROL": 10, "MF_L2LO": 13, "MF_L2HI": 10})
            fx.spec["cells"]["MF_L2HI"]["search_params"] = FP.replace("nmp_min_depth=0", "nmp_min_depth=1")
            with self.assertRaisesRegex(ValueError, "shared common-search"):
                V.build_report(fx.spec, fx.spec_path)


if __name__ == "__main__":
    unittest.main()
