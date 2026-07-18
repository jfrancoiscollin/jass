#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "l3_q1_verdict.py"
SPEC = importlib.util.spec_from_file_location("l3_q1_verdict", MODULE)
V = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(V)


def fingerprint(threat: int, sacs: int) -> str:
    values = {key: 0 for key in V.REQUIRED_SEARCH_KEYS}
    values.update(
        qs_threat_ext=threat,
        qs_sacs=sacs,
        qs_sacs_depth0_only=1,
        qs_forcing_depth=0,
        qs_promo_depth=0,
    )
    return ",".join(f"{key}={values[key]}" for key in V.REQUIRED_SEARCH_KEYS)


class VerdictFixture:
    def __init__(self, root: Path, p3_regression: bool = False):
        self.root = root
        self.search = {
            "Q00": fingerprint(0, 0),
            "Q10": fingerprint(1, 0),
            "Q01": fingerprint(0, 1),
            "Q11": fingerprint(1, 1),
        }
        self.spec = {
            "schema": 2,
            "baseline": "Q00",
            "common_search_params": self.search["Q00"],
            "conversion_delta_threshold": 0.02,
            "bootstrap": {"replicates": 300, "seed": 42},
            "cells": {},
        }
        for cell in V.CELLS:
            conversion = {}
            for stratum in V.STRATA:
                wins = 10
                if cell == "Q10":
                    wins = 5 if p3_regression and stratum == "p3_mince" else (14 if p3_regression else 12)
                path = root / f"{cell}-{stratum}.json"
                self.write_conversion(path, cell, stratum, wins)
                conversion[stratum] = path.name
            cell_spec = {"search_params": self.search[cell], "conversion": conversion}
            if cell != "Q00":
                common = root / f"common-{cell}.json"
                native = root / f"native-{cell}.json"
                self.write_gate(common, self.search["Q00"], self.search["Q00"], native=False)
                established = cell == "Q10"
                self.write_gate(
                    native,
                    self.search[cell],
                    self.search["Q00"],
                    native=True,
                    established=established,
                )
                cell_spec.update(common_gate=common.name, native_gate=native.name)
            self.spec["cells"][cell] = cell_spec
        self.spec_path = root / "spec.json"
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")

    def write_conversion(self, path: Path, cell: str, stratum: str, wins: int):
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
            "search_params": self.search["Q00"],
            "defender_search_params": self.search["Q00"],
            "pool_sha256": str(V.STRATA.index(stratum) + 1) * 64,
            "position_results": [
                {"index": index, "result": "win" if index < wins else "loss"}
                for index in range(n)
            ],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def write_gate(
        path: Path,
        search_a: str,
        search_b: str,
        *,
        native: bool,
        established: bool = False,
    ):
        rate = 0.60 if established else 0.50
        payload = {
            "complete": True,
            "n": 600,
            "rate": rate,
            "ci_low": 0.51 if established else 0.44,
            "ci_high": 0.69 if established else 0.56,
            "elo": 0,
            "depth": None if native else 9,
            "movetime": 0.1 if native else None,
            "pairs": 1,
            "openings_file": "open.fen",
            "search_params_a": search_a,
            "search_params_b": search_b,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")


class L3Q1VerdictTests(unittest.TestCase):
    def test_verdict_fingerprint_keys_track_the_engine_parser(self):
        source = (Path(__file__).resolve().parents[2] / "src/search_params.hpp").read_text()
        parser_keys = re.findall(r'key == "([^"]+)"', source)
        self.assertEqual(len(parser_keys), 63)
        self.assertEqual(set(V.REQUIRED_SEARCH_KEYS), set(parser_keys))

    def test_complete_contract_selects_one_lead_and_classifies_search_gain(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = VerdictFixture(Path(tmp))
            first = V.build_report(fixture.spec, fixture.spec_path)
            second = V.build_report(fixture.spec, fixture.spec_path)
            self.assertEqual(first, second)
            self.assertEqual(first["technical_status"], "complete")
            self.assertEqual(first["scientific_verdict"], "q1_lead_q10")
            self.assertEqual(first["selected_lead"], "Q10")
            self.assertEqual(first["screen"]["Q10"]["gain_classification"], "search_gain")
            self.assertTrue(first["screen"]["Q10"]["advance_to_confirmation"])
            self.assertFalse(first["screen"]["Q10"]["cost_branch"]["available"])
            self.assertIsNone(first["automatic_next_job"])
            self.assertEqual(first["search_contract"]["parameter_count"], 63)

    def test_established_p3_regression_blocks_an_otherwise_positive_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = VerdictFixture(Path(tmp), p3_regression=True)
            report = V.build_report(fixture.spec, fixture.spec_path)
            q10 = report["screen"]["Q10"]
            self.assertGreaterEqual(
                q10["paired_conversion"]["global"]["estimate"], 0.02
            )
            self.assertFalse(q10["p3_non_regression"])
            self.assertFalse(q10["advance_to_confirmation"])
            self.assertEqual(report["scientific_verdict"], "q1_no_lead")

    def test_incomplete_search_fingerprint_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = VerdictFixture(Path(tmp))
            broken = fixture.search["Q00"].split(",", 1)[1]
            fixture.spec["common_search_params"] = broken
            with self.assertRaisesRegex(ValueError, "exactly 63"):
                V.build_report(fixture.spec, fixture.spec_path)

    def test_native_gate_must_use_the_cell_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = VerdictFixture(Path(tmp))
            path = Path(tmp) / "native-Q10.json"
            payload = json.loads(path.read_text())
            payload["search_params_a"] = fixture.search["Q00"]
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "side-A"):
                V.build_report(fixture.spec, fixture.spec_path)


if __name__ == "__main__":
    unittest.main()
