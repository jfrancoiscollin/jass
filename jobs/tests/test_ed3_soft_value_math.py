from __future__ import annotations
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np
from scipy.special import expit
from jobs.tools import ed3_soft_value_math as m


def fixture(seed=910):
    rng=np.random.default_rng(seed)
    # Deliberately heterogeneous, sparse, correlated scales (unlike ED2's
    # all-small iid Gaussian smoke): PSTs, counts, mobility, skew, and MG/EG.
    n=96; nr=192
    raw=rng.integers(0,2,size=(n+nr,120)).astype(float)
    raw[:,:100] *= rng.random((n+nr,100))<.05
    raw[:,100:] *= np.tile([1,20,60,150,2],4)
    raw[:,101]=raw[:,100]*2
    phase=rng.choice([0,.05,.2,.65,1.0],n+nr)
    x=np.hstack((raw*phase[:,None],raw*(1-phase[:,None])))
    phi,rx=x[:n],x[n:]
    z=rng.normal(size=n); rz=rng.normal(size=nr)
    w=np.arange(0,n,2);l=w+1
    edges=(w,l,np.full(len(w),1/len(w)),rng.choice([-1.,1.],len(w)),rng.integers(1,500,len(w)))
    y=expit(rz+rng.normal(size=nr)*.1)
    return phi,z,edges,rx,rz,y


class SoftMathTests(unittest.TestCase):
    def test_tau_weighted_median_and_target_interpretation(self):
        tau=m.train_temperature(np.array([100.,2.,7.]),np.array([.1,.2,.7]))
        self.assertAlmostEqual(tau,7/np.log(3))
        self.assertAlmostEqual(expit(7/tau),.75)
        for gap,weight in [(np.array([]),np.array([])),(np.array([0.]),np.array([1.])),
                           (np.array([1.]),np.array([0.])),(np.array([np.nan]),np.array([1.]))]:
            with self.assertRaises(ValueError):m.train_temperature(gap,weight)

    def test_gradient_and_hessian_finite_differences_realistic_scales(self):
        data=fixture();tau=m.train_temperature(data[2][4],data[2][2]);args=m.design(*data,tau)
        beta=np.linspace(-.001,.001,240);_,g,h=m.derivatives(beta,*args)
        for i in (0,49,100,104,120,220,239):
            step=np.zeros(240);step[i]=1e-7
            up=m.derivatives(beta+step,*args);lo=m.derivatives(beta-step,*args)
            self.assertAlmostEqual((up[0]-lo[0])/2e-7,g[i],places=6)
            np.testing.assert_allclose((up[1]-lo[1])/2e-7,h[:,i],rtol=1e-5,atol=1e-5)
        np.testing.assert_allclose(h,h.T,rtol=0,atol=1e-10)
        self.assertGreaterEqual(np.linalg.eigvalsh(h).min(),m.RIDGE-1e-9)

    def test_real_240_coordinate_solve_and_certificate(self):
        data=fixture();tau=m.train_temperature(data[2][4],data[2][2])
        beta,report=m.fit(*data,tau)
        self.assertTrue(report['success']);self.assertLessEqual(report['gradient_l2'],1e-6)
        self.assertLessEqual(report['objective_gap_upper_bound'],5e-10)
        self.assertGreater(np.linalg.norm(beta),0)

    def test_soft_pressure_vanishes_at_finite_target_margin(self):
        p=.75;d=np.log(p/(1-p))
        force=(1-p)*expit(d)-p*expit(-d)
        self.assertAlmostEqual(force,0,places=14)
        self.assertLess(-expit(-d),0)  # hard label still pushes the gap upward

    def test_hard_limit_matches_analytical_old_loss_gradient_hessian(self):
        data=fixture();a=list(m.design(*data,1.0));a[3]=np.ones_like(a[3]);b=np.zeros(240)
        value,g,h=m.derivatives(b,*a);dx,d,wt,_,rx,rz,y=a
        expected=float(wt@np.logaddexp(0,-d)+np.mean(np.logaddexp(0,rz)-y*rz))
        self.assertEqual(value,expected)
        np.testing.assert_allclose(g,dx.T@(-wt*expit(-d))+rx.T@(expit(rz)-y)/len(y),rtol=0,atol=1e-12)
        self.assertTrue(np.isfinite(h).all())

    def test_large_teacher_gaps_and_logits_remain_finite(self):
        data=list(fixture());data[1]=np.full(len(data[1]),1000.);data[4]=np.full(len(data[4]),-1000.)
        a=list(m.design(*data,1e-8));out=m.derivatives(np.zeros(240),*a)
        self.assertTrue(all(np.isfinite(v).all() for v in out))

    def test_invalid_data_rejected_before_optimizer(self):
        data=list(fixture());data[5][0]=np.nan
        with patch.object(m,'minimize',side_effect=AssertionError('must not execute')):
            with self.assertRaises(ValueError):m.fit(*data,100.)

    def test_frozen_solver_reports_failure_before_export(self):
        from types import SimpleNamespace
        result=SimpleNamespace(x=np.zeros(240),success=False,status=1,nit=500,nfev=510,nhev=500)
        data=fixture()
        with tempfile.TemporaryDirectory() as td,patch.object(m,'minimize',return_value=result):
            dest=Path(td)/'solver.json'
            with self.assertRaises(m.NumericalFailure):m.fit(*data,100.,report_path=dest)
            self.assertTrue(dest.is_file())

if __name__=='__main__':unittest.main()
