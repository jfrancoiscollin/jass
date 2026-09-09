from __future__ import annotations
import unittest
from unittest.mock import patch
import numpy as np
from jobs.tools import ed4_choice_math as m
from jobs.tools.ed4_choice_fixtures import fixture

class ChoiceMath(unittest.TestCase):
 def test_fixture_design_and_normalizers(self):
  d,meta=fixture(); self.assertEqual(d['normalizer'],24); self.assertEqual(meta['future_production_normalizer'],512)
  self.assertEqual([g['A'] for g in d['groups'][:4]],[[0],[4,5],[8,9,10,11],[]])
 def test_fd_and_stable_logits(self):
  d,_=fixture(); b=np.linspace(-.001,.001,240); v,g,h=m.derivatives(b,d); self.assertLessEqual(np.max(abs(h-h.T)),1e-10)
  for i in (0,49,100,104,120,220,239):
   e=np.zeros(240);e[i]=1e-7; self.assertLessEqual(abs((m.derivatives(b+e,d)[0]-m.derivatives(b-e,d)[0])/(2e-7)-g[i]),1e-6); self.assertTrue(np.allclose((m.derivatives(b+e,d)[1]-m.derivatives(b-e,d)[1])/(2e-7),h[:,i],rtol=1e-5,atol=1e-5))
  self.assertTrue(np.isfinite(v))
 def test_extreme_logits_and_malformed_reject(self):
  phi=np.zeros((24,240)); z=np.zeros(24); z[:3]=[-1000,0,1000]
  gs=[{'id':0,'stm':1,'rows':[0,1,2],'V':[0,1,2],'A':[2],'edges':[]}]+[{'id':i,'stm':0,'rows':[i+2],'V':[i+2],'A':[i+2],'edges':[]} for i in range(1,22)]+[{'id':22,'stm':0,'rows':[],'V':[],'A':[],'edges':[]},{'id':23,'stm':0,'rows':[],'V':[],'A':[],'edges':[]}]
  d=m.design(phi,z,gs,np.zeros((1,240)),np.zeros(1),np.array([.5])); self.assertTrue(np.isfinite(m.derivatives(np.zeros(240),d)[0]))
  bad=[dict(x) for x in gs]; bad[1]['stm']=2
  with self.assertRaises(ValueError):m.design(phi,z,bad,np.zeros((1,240)),np.zeros(1),np.array([.5]))
 def test_edges_and_failclosed(self):
  gs=[{'id':0,'stm':1,'rows':[0,1,2],'terminals':[]}]; low={(0,5000):2,(0,50000):2,(1,5000):2,(1,50000):2,(2,5000):0,(2,50000):0}
  x=m.groups_from_labels(gs,low)[0]; self.assertEqual(x['edges'],[(0,2),(1,2)]); self.assertEqual(x['A'],[0,1])
  with self.assertRaises(ValueError):m.design(np.zeros((24,240)),np.zeros(24),[{'id':i,'stm':0,'rows':([0] if i==0 else []),'V':([0] if i==0 else []),'A':[],'edges':[]} for i in range(24)],np.zeros((1,240)),np.zeros(1),np.array([.5]))
 def test_saddle_rejected_by_mock_success(self):
  phi=np.zeros((3,240));phi[:,0]=[-10,10,0]; groups=[{'id':0,'stm':1,'rows':[0,1,2],'V':[0,1,2],'A':[0,1],'edges':[]}]+[{'id':i,'stm':0,'rows':[],'V':[],'A':[],'edges':[]} for i in range(1,512)]
  d=m.design(phi,np.zeros(3),groups,np.zeros((1,240)),np.zeros(1),np.array([.5]))
  class R: success=True;x=np.zeros(240);message='mock'
  with patch.object(m,'minimize',return_value=R()):
   with self.assertRaises(m.NumericalFailure):m.fit(d)
 def test_bad_beta(self):
  d,_=fixture()
  with self.assertRaises(ValueError):m.derivatives(np.zeros(2),d)
 def test_unsupported_is_exact_zero(self):
  phi=np.zeros((24,240)); z=np.zeros(24); gs=[{'id':i,'stm':i%2,'rows':[i],'V':[i],'A':[i],'edges':[]} for i in range(24)]
  d=m.design(phi,z,gs,np.zeros((1,240)),np.zeros(1),np.array([.5])); v,g,h=m.derivatives(np.zeros(240),d)
  self.assertEqual(v,float(np.log(2))); self.assertTrue(np.array_equal(g,np.zeros(240))); self.assertTrue(np.array_equal(h,.001*np.eye(240)))
 def test_parent_sign_affects_ordered_utility(self):
  phi=np.zeros((24,240)); phi[0,0]=1; phi[1,0]=-1; z=np.zeros(24)
  def make(stm): return [{'id':0,'stm':stm,'rows':[0,1],'V':[0,1],'A':[0],'edges':[]}]+[{'id':i,'stm':0,'rows':[i+1],'V':[i+1],'A':[i+1],'edges':[]} for i in range(1,23)]+[{'id':23,'stm':0,'rows':[],'V':[],'A':[],'edges':[]}]
  beta=np.zeros(240); beta[0]=1
  a=m.design(phi,z,make(1),np.zeros((1,240)),np.zeros(1),np.array([.5])); b=m.design(phi,z,make(0),np.zeros((1,240)),np.zeros(1),np.array([.5]))
  self.assertNotEqual(m.derivatives(beta,a)[0],m.derivatives(beta,b)[0])
if __name__=='__main__':unittest.main()
