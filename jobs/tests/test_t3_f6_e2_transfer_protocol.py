from __future__ import annotations
import unittest
import numpy as np
from jobs.tools import t3_f6_e2_pool as pool
from jobs.tools import t3_f6_e2_readout as readout

class E2ProtocolTests(unittest.TestCase):
    def test_frozen_geometry(self):
        self.assertEqual(pool.CANDIDATES, 30000)
        self.assertEqual(pool.OPENINGS, 1350)
        self.assertEqual(pool.SELECT_SEED, 2026100102)
        self.assertEqual(pool.EXEC_SEED, 2026100104)
        self.assertEqual(pool.CELLS, (("C1", 750), ("C2", 400), ("C3", 200)))
        self.assertEqual(pool.rank_key(pool.SELECT_SEED, "x"), pool.rank_key(pool.SELECT_SEED, "x"))

    def test_elo_sign(self):
        self.assertGreater(readout.elo(0.6), 0.0)
        self.assertLess(readout.elo(0.4), 0.0)
        self.assertAlmostEqual(readout.elo(0.5), 0.0, places=12)

    def test_joint_bootstrap_order_and_positive_delta(self):
        c1=np.full(20,0.6,dtype=np.float64)
        c2=np.full(20,0.6,dtype=np.float64)
        t=np.full(8,200.0,dtype=np.float64)
        c=np.full(8,100.0,dtype=np.float64)
        b=readout.bootstrap(c1,c2,t,c,samples=2000,seed=readout.BOOTSTRAP_SEED)
        self.assertEqual(b['subflow_order'], ['C1','C2','E1'])
        self.assertEqual(b['invalid_replicates'], 0)
        self.assertGreater(b['slope_c2_ci95'][0], 0.0)
        self.assertGreater(b['delta_info_ci95'][0], 0.0)

if __name__ == '__main__':
    unittest.main()
