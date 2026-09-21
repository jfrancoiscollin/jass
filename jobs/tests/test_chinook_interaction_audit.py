from __future__ import annotations
import unittest
from jobs.tools import chinook_interaction_audit as a

class InteractionAuditTests(unittest.TestCase):
    def test_fixed_interactions_are_exact(self):
        f = {
            "phase":"P2","legal_moves":"5-8","stm_material_status":"behind",
            "white_men":"5","black_men":"6",
        }
        got = a.fixed_interactions(f)
        self.assertTrue(got["CORE"])
        self.assertTrue(got["CORE_MEN_4_7"])
        self.assertTrue(got["PHASE_MOBILITY"])
        self.assertTrue(got["MOBILITY_BEHIND"])
        self.assertTrue(got["PHASE_BEHIND"])
        self.assertTrue(got["P2_CORE"])
        self.assertFalse(got["P3_CORE"])

    def test_no_automatic_causal_authority(self):
        self.assertEqual(a.TERMINAL, "CHINOOK_INTERACTION_AUDIT_COMPLETE_V1")

if __name__ == "__main__":
    unittest.main()
