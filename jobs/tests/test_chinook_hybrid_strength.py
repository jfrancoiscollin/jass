from __future__ import annotations
import unittest
from pathlib import Path
from jobs.tools import chinook_hybrid_strength as s

class ChinookHybridStrengthTests(unittest.TestCase):
    def test_frozen_gate_and_seeds(self):
        self.assertEqual((s.POOL_SEED,s.ORDER_SEED),(2026092121,2026092122))
        self.assertEqual(s.PAIRS,288)
        self.assertEqual(s.ARM_HYBRID,"CHINOOK_HYBRID")
        self.assertEqual(s.ARM_CONTROL,"CURRICULUM")
    def test_arm_model_paths(self):
        w=Path("/tmp/x")
        self.assertEqual(s.model_path(s.ARM_HYBRID,w),w/"CURRICULUM.pjtw")
        self.assertEqual(s.model_path(s.ARM_CONTROL,w),w/"CURRICULUM.pjtw")
        self.assertEqual(s.engine_env(s.ARM_HYBRID,w)["JASS_CHINOOK_HIER_MODEL"],str(w/"HIER.pjtw"))
        self.assertIsNone(s.engine_env(s.ARM_CONTROL,w)["JASS_CHINOOK_HIER_MODEL"])
if __name__=="__main__":
    unittest.main()
