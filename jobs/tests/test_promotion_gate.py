#!/usr/bin/env python3
"""Tests promotion inter-tours v3.2."""
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "tools" / "promotion_gate.py"
SPEC = importlib.util.spec_from_file_location("promotion_gate", MODULE)
P = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(P)


def match(rate: float, n: int) -> dict:
    wins = round(rate * n)
    return {"wins_a": wins, "draws": 0, "wins_b": n - wins}


class YoungTests(unittest.TestCase):
    def test_neutral_passes(self):
        manifest = P.young_gate(match(0.50, 600), match(0.50, 600), "T1-bis")
        self.assertEqual(manifest["promotion_decision"], "promote")
        self.assertEqual(manifest["scientific_status"], "continue_probe")

    def test_reject_if_cihigh_below_half_vs_parent(self):
        manifest = P.young_gate(match(0.40, 600), match(0.52, 600), "T2")
        self.assertEqual(manifest["vs_parent"]["decision"], "reject")
        self.assertEqual(manifest["promotion_decision"], "reject")
        self.assertEqual(manifest["scientific_status"], "stop_regression")

    def test_reject_if_cihigh_below_half_vs_fixed(self):
        manifest = P.young_gate(match(0.55, 600), match(0.40, 600), "T2")
        self.assertEqual(manifest["vs_fixed_reference"]["decision"], "reject")
        self.assertEqual(manifest["promotion_decision"], "reject")

    def test_manifest_has_both_comparisons(self):
        manifest = P.young_gate(match(0.5, 400), match(0.5, 400), "T1-bis")
        self.assertIn("vs_parent", manifest)
        self.assertIn("vs_fixed_reference", manifest)
        self.assertIn("conversion", manifest)
        self.assertIn("scientific_status", manifest)

    def test_only_probe_tours_allowed_young(self):
        manifest = P.young_gate(match(0.5, 400), match(0.5, 400), "T4")
        self.assertEqual(manifest["promotion_decision"], "reject")
        self.assertEqual(manifest["scientific_status"], "stop_technical")

    def test_t3_completes_probe(self):
        manifest = P.young_gate(match(0.52, 600), match(0.52, 600), "T3")
        self.assertEqual(manifest["scientific_status"], "complete_probe")
        self.assertEqual(manifest["promotion_decision"], "promote")

    def test_n_zero_is_technical_and_rejects(self):
        manifest = P.young_gate(
            {"rate": None, "ci_low": None, "ci_high": None, "n": 0},
            match(0.5, 400),
            "T1-bis",
        )
        self.assertEqual(manifest["vs_parent"]["decision"], "technical")
        self.assertEqual(manifest["scientific_status"], "stop_technical")
        self.assertEqual(manifest["promotion_decision"], "reject")

    def test_missing_interval_is_technical_and_rejects(self):
        manifest = P.young_gate(
            {"rate": 0.5, "ci_low": None, "ci_high": None, "n": 600},
            match(0.5, 600),
            "T2",
        )
        self.assertEqual(manifest["promotion_decision"], "reject")
        self.assertEqual(manifest["scientific_status"], "stop_technical")

    def test_missing_conversion_stays_null_not_fake_zero(self):
        manifest = P.young_gate(match(0.5, 600), match(0.5, 600), "T1-bis")
        self.assertIsNone(manifest["conversion"]["p1_net"])
        self.assertIsNone(manifest["conversion"]["p4_egal"])


class LineageTests(unittest.TestCase):
    def test_exact_weight_hashes_are_injected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            payloads = {
                "candidate.pjtw": b"candidate",
                "parent.pjtw": b"parent",
                "fixed.pjtw": b"fixed",
            }
            for name, payload in payloads.items():
                (root / name).write_bytes(payload)
            conversion = P.attach_weight_hashes({"global": 0.667}, root)
            manifest = P.young_gate(
                match(0.51, 600), match(0.51, 600), "T2", conversion
            )
            self.assertEqual(
                manifest["candidate_sha"], hashlib.sha256(b"candidate").hexdigest()
            )
            self.assertEqual(
                manifest["parent_sha"], hashlib.sha256(b"parent").hexdigest()
            )
            self.assertEqual(
                manifest["fixed_reference_sha"], hashlib.sha256(b"fixed").hexdigest()
            )

    def test_missing_weight_file_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "candidate.pjtw").write_bytes(b"candidate")
            (root / "parent.pjtw").write_bytes(b"parent")
            with self.assertRaises(RuntimeError):
                P.attach_weight_hashes({}, root)


class EstablishedTests(unittest.TestCase):
    def test_requires_conversion_window(self):
        manifest = P.established_gate(
            match(0.52, 600),
            match(0.52, 600),
            "T4",
            conversion_window=[0.66, 0.66],
            conv_min_delta=0.02,
            window=2,
        )
        self.assertEqual(manifest["promotion_decision"], "reject")

    def test_promotes_when_conversion_rises(self):
        manifest = P.established_gate(
            match(0.52, 600),
            match(0.52, 600),
            "T4",
            conversion_window=[0.64, 0.68],
            conv_min_delta=0.02,
            window=2,
        )
        self.assertEqual(manifest["promotion_decision"], "promote")

    def test_regression_blocks_established(self):
        manifest = P.established_gate(
            match(0.40, 600),
            match(0.55, 600),
            "T4",
            conversion_window=[0.60, 0.70],
            conv_min_delta=0.02,
            window=2,
        )
        self.assertEqual(manifest["promotion_decision"], "reject")
        self.assertEqual(manifest["scientific_status"], "stop_regression")

    def test_incomplete_generalist_gate_blocks_established(self):
        manifest = P.established_gate(
            {"n": 0, "rate": None, "ci_low": None, "ci_high": None},
            match(0.55, 600),
            "T4",
            conversion_window=[0.60, 0.70],
            conv_min_delta=0.02,
            window=2,
        )
        self.assertEqual(manifest["promotion_decision"], "reject")
        self.assertEqual(manifest["scientific_status"], "stop_technical")


if __name__ == "__main__":
    unittest.main()
