#!/usr/bin/env python3
"""Tests §11.1 — labels et draw-band."""
from __future__ import annotations
import importlib.util, unittest
from pathlib import Path

M = Path(__file__).resolve().parents[1] / "tools" / "oracle_cert.py"
spec = importlib.util.spec_from_file_location("oracle_cert", M); O = importlib.util.module_from_spec(spec); spec.loader.exec_module(O)


def cert(**kw):
    base = dict(oracle_tier="ON_POLICY", proof_type="none", proof_validated=False,
                blocks_draw_band=False, tb_reached=False, result_wdl=1)
    base.update(kw); return base


class LabelTests(unittest.TestCase):
    def test_tb_exact_blocks_and_survives(self):
        c = cert(oracle_tier="TB_EXACT", proof_type="tb_direct", tb_reached=True, blocks_draw_band=True)
        ok, r = O.validate_certificate(c); self.assertTrue(ok, r)
        self.assertTrue(O.can_block_draw_band(c))
        res = O.resolve_label(c, on_policy_wdl=0, draw_band_wdl=0)
        self.assertEqual(res["source"], "TB_EXACT"); self.assertTrue(res["blocks_draw_band"])
        self.assertEqual(res["wdl"], 1)   # résultat exact conservé malgré draw-band=0

    def test_cert_proof_verified_blocks(self):
        c = cert(oracle_tier="CERT_PROOF", proof_type="pv_to_tb", proof_validated=True, blocks_draw_band=True)
        self.assertTrue(O.can_block_draw_band(c))
        self.assertEqual(O.resolve_label(c, 0, 0)["source"], "CERT_PROOF")

    def test_cert_proof_unverified_rejected(self):
        c = cert(oracle_tier="CERT_PROOF", proof_type="pv_to_tb", proof_validated=False, blocks_draw_band=True)
        ok, r = O.validate_certificate(c)
        self.assertFalse(ok); self.assertFalse(O.can_block_draw_band(c))
        # déclassé : ne bloque pas → draw-band appliqué
        self.assertFalse(O.resolve_label(c, on_policy_wdl=1, draw_band_wdl=0)["blocks_draw_band"])

    def test_search_stable_cannot_block(self):
        c = cert(oracle_tier="SEARCH_STABLE", proof_type="search_stable", blocks_draw_band=True)
        ok, r = O.validate_certificate(c)
        self.assertFalse(ok)                          # incohérent : SEARCH_STABLE + blocks
        c2 = cert(oracle_tier="SEARCH_STABLE", proof_type="search_stable", blocks_draw_band=False)
        self.assertTrue(O.validate_certificate(c2)[0])
        self.assertFalse(O.can_block_draw_band(c2))
        self.assertFalse(O.resolve_label(c2, 0, 0)["blocks_draw_band"])   # draw-band reste autorisé

    def test_resolution_identical_parent_child_sibling(self):
        c = cert(oracle_tier="TB_EXACT", proof_type="tb_direct", tb_reached=True, result_wdl=-1)
        # même certificat → même résolution quel que soit le rôle
        r_parent = O.resolve_label(c, 1, 1); r_child = O.resolve_label(dict(c), 1, 1); r_sib = O.resolve_label(dict(c), 0, 0)
        self.assertEqual(r_parent, r_child); self.assertEqual(r_parent["wdl"], -1); self.assertEqual(r_sib["wdl"], -1)

    def test_tip_survival_counters_and_invariants(self):
        recs = [
            dict(oracle_tier="TB_EXACT", survived=True, strata="p4_egal", provenance="gen", tour="T1-bis", cert_valid=True),
            dict(oracle_tier="CERT_PROOF", survived=True, strata="p3_mince", provenance="gen", tour="T1-bis", cert_valid=True),
            dict(oracle_tier="SEARCH_STABLE", survived=False, strata="p1_net", provenance="gen", tour="T1-bis", cert_valid=True),
            dict(oracle_tier="ON_POLICY", survived=True, strata="p2_moyen", provenance="gen", tour="T1-bis", cert_valid=True),
        ]
        rep = O.tip_survival(recs)
        self.assertEqual(rep["by_tier"]["TB_EXACT"]["rate"], 1.0)
        self.assertEqual(rep["tip_total"]["total"], 4)
        self.assertEqual(rep["invalid_blocking"], 0)

    def test_tip_survival_invariant_violation_raises(self):
        recs = [dict(oracle_tier="TB_EXACT", survived=False, cert_valid=True)]   # un TB tué = violation
        with self.assertRaises(AssertionError):
            O.tip_survival(recs)

    def test_invalid_cert_blocking_raises(self):
        recs = [dict(oracle_tier="ON_POLICY", survived=True, blocks_draw_band=True, cert_valid=False)]
        with self.assertRaises(AssertionError):
            O.tip_survival(recs)


if __name__ == "__main__":
    unittest.main()
