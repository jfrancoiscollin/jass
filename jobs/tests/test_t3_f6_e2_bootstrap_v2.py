from __future__ import annotations
import unittest
import numpy as np
from jobs.tools import t3_f6_e2_readout_v2 as readout_v2


class E2BootstrapV2Tests(unittest.TestCase):
    def test_independent_subflows_and_positive_delta(self):
        c1 = np.full(20, 0.6, dtype=np.float64)
        c2 = np.full(20, 0.6, dtype=np.float64)
        t3 = np.full(8, 200.0, dtype=np.float64)
        curriculum = np.full(8, 100.0, dtype=np.float64)
        result = readout_v2.bootstrap(c1, c2, t3, curriculum, samples=1000)
        self.assertEqual(result["subflow_derivation"], "SeedSequence(seed).spawn(3)")
        self.assertEqual(result["subflow_order"], ["C1", "C2", "E1"])
        self.assertEqual(result["invalid_replicates"], 0)
        self.assertGreater(result["slope_c2_ci95"][0], 0.0)
        self.assertGreater(result["delta_info_ci95"][0], 0.0)


if __name__ == "__main__":
    unittest.main()
