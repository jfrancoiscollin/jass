import unittest
import numpy as np

from jobs.tools.rich_d_phase_c_readout import Sibling, stable_relation, parent_metrics


def sib(pid, idx, q50, q200, exact=2):
    return Sibling(idx,pid,0,1,2,1,0,0,0,exact,0.0,0.0,float(q50),float(q200))


class RichDReadoutTests(unittest.TestCase):
    def test_stable_relation_thresholds(self):
        a=sib(0,0,20,50); b=sib(0,1,0,0)
        self.assertEqual(stable_relation(a,b),1)
        self.assertEqual(stable_relation(sib(0,0,9,50),b),0)
        self.assertEqual(stable_relation(sib(0,0,20,-50),b),0)

    def test_exact_precedence(self):
        a=sib(0,0,0,0,1); b=sib(0,1,0,0,0)
        self.assertEqual(stable_relation(a,b),1)

    def test_parent_metrics(self):
        score=np.asarray([3.0,2.0,1.0])
        pair,top=parent_metrics([0,1,2],[(0,1),(0,2),(1,2)],score)
        self.assertEqual(pair,1.0); self.assertEqual(top,1.0)
        score2=np.asarray([1.0,3.0,2.0])
        pair2,top2=parent_metrics([0,1,2],[(0,1),(0,2),(1,2)],score2)
        self.assertLess(pair2,1.0); self.assertEqual(top2,0.0)


if __name__ == '__main__': unittest.main()
