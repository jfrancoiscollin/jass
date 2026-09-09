from __future__ import annotations
import unittest
import numpy as np
from jobs.tools import ed3_transfer_diagnostic as t


class TransferDiagnosticContracts(unittest.TestCase):
    def setUp(self):
        # Fixed 512-parent denominator is part of the published estimand.
        self.g=[{'id':0,'cell':'P0_stm0','rows':[0,1,2],'terminals':[]}]
        self.q={0:3.,1:2.,2:1.}
        self.h=np.array([-3,-2,-1]); self.s=np.array([-2,-3,-1])
        self.z=np.array([3.,2.,1.]); self.sz=np.array([2.,3.,1.])

    def test_orientation_ties_and_full_parent_weight(self):
        pairs,parents,info=t.analyse_population(self.g,self.q,self.h,self.h,self.s,self.z,self.z,self.sz,population='TRAIN',terminals_priority=False)
        self.assertEqual(len(pairs),3); self.assertEqual(info['supported_parents'],1)
        self.assertAlmostEqual(sum(x['full_parent_mass'] for x in pairs),1/512)
        self.assertEqual(pairs[0]['hard_state'],'correct')
        self.assertEqual(pairs[0]['soft_state'],'wrong')
        self.assertEqual(parents[0]['hard_choice'],0); self.assertEqual(parents[0]['soft_choice'],1)
        self.assertIsNone(parents[0]['raw_margin_equivalent_to_production_choice_rule'])
        self.assertEqual(parents[0]['choice_rule'],'nonterminal_argmax_diagnostic')

    def test_terminal_priority_beats_scores_and_logit_sensitivity(self):
        g=[{'id':0,'cell':'P0_stm0','rows':[0,1],'terminals':[1]}]
        pairs,parents,_=t.analyse_population(g,{0:2.,1:1.},np.array([-100,0]),np.array([-100,0]),np.array([-100,0]),np.array([100.,0.]),np.array([100.,0.]),np.array([100.,0.]),population='CONFIRMATION',terminals_priority=True)
        self.assertEqual(parents[0]['hard_choice'],1)
        self.assertEqual(parents[0]['hard_logit_choice'],1)
        self.assertTrue(parents[0]['terminal_priority_parent'])
        self.assertFalse(parents[0]['raw_margin_equivalent_to_production_choice_rule'])
        self.assertTrue(pairs[0]['terminal_involving'])

    def test_summary_uses_linear_quantile_and_rejects_nonfinite(self):
        self.assertEqual(t._summary([0.,10.])['quantiles']['0.5'],5.)
        with self.assertRaises(ValueError): t._summary([float('nan')])

    def test_integer_tie_and_unrounded_logit_have_distinct_choices(self):
        g=[{'id':0,'cell':'P0_stm0','rows':[2,5],'terminals':[]}]
        cp=np.zeros(6,dtype=int);z=np.zeros(6);z[2]=.001;z[5]=.009
        pairs,parents,_=t.analyse_population(g,{2:1.,5:2.},cp,cp,cp,z,z,z,
                                           population='CONFIRMATION',terminals_priority=True)
        self.assertEqual(parents[0]['hard_choice'],2)
        self.assertEqual(parents[0]['hard_logit_choice'],5)
        self.assertEqual(pairs[0]['hard_state'],'tie')
        self.assertEqual(pairs[0]['hard_logit_state'],'correct')

    def test_components_keep_primary_weights(self):
        rows=[{'hard_state':'correct','soft_state':'correct','full_parent_mass':1/1536,'terminal_involving':True},
              {'hard_state':'correct','soft_state':'wrong','full_parent_mass':1/1536,'terminal_involving':False}]
        allm=t._matrix(rows,t.STATES,'hard_state','soft_state')['full_parent_mass']
        tm=t._matrix(rows[:1],t.STATES,'hard_state','soft_state')['full_parent_mass']
        nm=t._matrix(rows[1:],t.STATES,'hard_state','soft_state')['full_parent_mass']
        self.assertTrue(np.array_equal(np.asarray(allm),np.asarray(tm)+np.asarray(nm)))


if __name__=='__main__': unittest.main()
