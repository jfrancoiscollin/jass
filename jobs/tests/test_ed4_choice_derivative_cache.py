"""Prove the P1 mechanical evaluation reuse against the frozen P0 formula."""
import unittest
from unittest.mock import patch
import numpy as np
from scipy.special import expit
from jobs.tools import ed4_choice_math as m
from jobs.tools.ed4_choice_fixtures import fixture


def p0_reference(beta, d):
    # Literal P0 operation order before hoisting the identical x@beta call.
    x,z=d['phi'],d['z']; value=0.; grad=np.zeros(240); H=np.zeros((240,240))
    for g in d['groups']:
        V,A=g['V'],g['A']
        if not V or A==V: continue
        sign=1. if g['stm']==1 else -1.; u=sign*(z+x@beta)
        lv,gv,hv=m._term(u,x,V); la,ga,ha=m._term(u,x,A)
        value+=lv-la; grad+=sign*(gv-ga); H+=hv-ha
    value/=d['normalizer']; grad/=d['normalizer']; H/=d['normalizer']
    zz=d['replay_z']+d['replay_x']@beta; p=expit(zz)
    value+=float(np.mean(np.logaddexp(0,zz)-d['y']*zz)); grad+=d['replay_x'].T@(p-d['y'])/len(zz); H+=(d['replay_x'].T*p*(1-p))@d['replay_x']/len(zz)
    value+=.0005*float(beta@beta); grad+=.001*beta; H+=.001*np.eye(240)
    return float(value),grad,H


class DerivativeReuse(unittest.TestCase):
    def test_precomputed_logits_preserve_exact_p0_results(self):
        design,_=fixture()
        for beta in (np.zeros(240), np.linspace(-.001,.001,240)):
            reference=p0_reference(beta,design)
            actual=m.derivatives(beta,design)
            for a,b in zip(actual,reference):
                self.assertEqual(np.asarray(a).tobytes(),np.asarray(b).tobytes())

    def test_identical_requests_are_cached_and_changed_bytes_recomputed(self):
        groups=[{'id':i,'stm':0,'rows':[],'V':[],'A':[]} for i in range(512)]
        design=m.design(np.zeros((0,240)),np.zeros(0),groups,np.zeros((1,240)),np.zeros(1),np.array([.5]))
        original=m.derivatives
        def mock_minimize(fun, x, jac, hess, **kwargs):
            fun(x);jac(x);hess(x)
            changed=x.copy();changed[0]=1.
            self.assertNotEqual(fun(changed),fun(x))
            class Result:
                success=True
                message='mocked API sequence, zero optimizer invocations'
            result=Result();result.x=x
            return result
        with patch.object(m,'derivatives',wraps=original) as calls, patch.object(m,'minimize',side_effect=mock_minimize):
            m.fit(design)
            # initial, first zero, changed, zero again, final gate
            self.assertEqual(calls.call_count,5)


if __name__=='__main__':unittest.main()
