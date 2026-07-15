#!/usr/bin/env python3
"""Tests §11.2 — promotion (régimes young/established)."""
from __future__ import annotations
import importlib.util, unittest
from pathlib import Path

M = Path(__file__).resolve().parents[1] / "tools" / "promotion_gate.py"
spec = importlib.util.spec_from_file_location("promotion_gate", M); P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)

# helpers : construit un match à taux ~r sur n games (draws=0)
def match(r, n):
    a = round(r * n); b = n - a; return {"wins_a": a, "draws": 0, "wins_b": b}


class YoungTests(unittest.TestCase):
    def test_neutral_passes(self):
        # ~0.50 sur 600 → ci_high > 0.5 → pas de régression établie → promote
        man = P.young_gate(match(0.50, 600), match(0.50, 600), "T1-bis")
        self.assertEqual(man["promotion_decision"], "promote")
        self.assertEqual(man["scientific_status"], "continue_probe")

    def test_reject_if_cihigh_below_half_vs_parent(self):
        # ~0.40 sur 600 → ci_high ~0.44 < 0.5 → régression établie vs parent
        man = P.young_gate(match(0.40, 600), match(0.52, 600), "T2")
        self.assertEqual(man["vs_parent"]["decision"], "reject")
        self.assertEqual(man["promotion_decision"], "reject")
        self.assertEqual(man["scientific_status"], "stop_regression")

    def test_reject_if_cihigh_below_half_vs_fixed(self):
        man = P.young_gate(match(0.55, 600), match(0.40, 600), "T2")
        self.assertEqual(man["vs_fixed_reference"]["decision"], "reject")
        self.assertEqual(man["promotion_decision"], "reject")

    def test_manifest_has_both_comparisons(self):
        man = P.young_gate(match(0.5, 400), match(0.5, 400), "T1-bis")
        self.assertIn("vs_parent", man); self.assertIn("vs_fixed_reference", man)
        self.assertIn("conversion", man); self.assertIn("scientific_status", man)

    def test_only_probe_tours_allowed_young(self):
        man = P.young_gate(match(0.5, 400), match(0.5, 400), "T4")
        self.assertEqual(man["promotion_decision"], "reject")
        self.assertEqual(man["scientific_status"], "stop_technical")

    def test_t3_completes_probe(self):
        man = P.young_gate(match(0.52, 600), match(0.52, 600), "T3")
        self.assertEqual(man["scientific_status"], "complete_probe")

    def test_n_zero_is_technical(self):
        man = P.young_gate({"rate": None, "ci_low": None, "ci_high": None, "n": 0},
                           match(0.5, 400), "T1-bis")
        self.assertEqual(man["scientific_status"], "stop_technical")


class EstablishedTests(unittest.TestCase):
    def test_requires_conversion_window(self):
        # non-régressif mais conversion insuffisante → reject
        man = P.established_gate(match(0.52, 600), match(0.52, 600), "T4",
                                 conversion_window=[0.66, 0.66], conv_min_delta=0.02, window=2)
        self.assertEqual(man["promotion_decision"], "reject")

    def test_promotes_when_conversion_rises(self):
        man = P.established_gate(match(0.52, 600), match(0.52, 600), "T4",
                                 conversion_window=[0.64, 0.68], conv_min_delta=0.02, window=2)
        self.assertEqual(man["promotion_decision"], "promote")

    def test_regression_blocks_established(self):
        man = P.established_gate(match(0.40, 600), match(0.55, 600), "T4",
                                 conversion_window=[0.60, 0.70], conv_min_delta=0.02, window=2)
        self.assertEqual(man["promotion_decision"], "reject")
        self.assertEqual(man["scientific_status"], "stop_regression")


if __name__ == "__main__":
    unittest.main()
