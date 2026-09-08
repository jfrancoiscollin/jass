from __future__ import annotations
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from scipy.special import expit
from jobs.tools import ed2_value_math as m
from jobs.tools import ed2_value_pipeline as p


def toy_model(path,npat=5):
    data=struct.pack('<5I',0x57544a50,3,1000,npat,120)
    data+=np.zeros(2*(npat+120),dtype='<i4').tobytes()
    path.write_bytes(data)

class ED2MathTests(unittest.TestCase):
    def test_partial_order_keeps_only_separated_ranges(self):
        g=[dict(rows=[0,1,2],terminals=[],cell='P0_stm0',stm=0)]
        low={(0,5000):0,(0,50000):5,(1,5000):-2,(1,50000):4,(2,5000):-10,(2,50000):-10}
        point,ps=m.pair_edges(g,low,'POINT');partial,ss=m.pair_edges(g,low,'PARTIAL')
        self.assertEqual(ps['pairs'],3);self.assertEqual(ss['pairs'],2)
        self.assertNotIn((0,1),list(zip(partial[0],partial[1])))
        self.assertAlmostEqual(sum(point[2]),1);self.assertAlmostEqual(sum(partial[2]),1)
        self.assertTrue(np.all(point[3]==-1))
        low[1,50000]=0
        partial,_=m.pair_edges(g,low,'PARTIAL')
        self.assertNotIn((0,1),list(zip(partial[0],partial[1])))

    def test_empty_parent_has_zero_loss_weight_not_resampled(self):
        g=[dict(rows=[0,1],terminals=[],cell='P0_stm1',stm=1),dict(rows=[2,3],terminals=[],cell='P1_stm1',stm=1)]
        low={(0,5000):5,(0,50000):6,(1,5000):0,(1,50000):1,(2,5000):0,(2,50000):3,(3,5000):1,(3,50000):2}
        e,s=m.pair_edges(g,low,'PARTIAL')
        self.assertEqual(s['supported_parents'],1);self.assertAlmostEqual(e[2].sum(),.5)

    def test_terminal_pairs_not_fitted(self):
        g=[dict(rows=[0,1,2],terminals=[0],cell='P0_stm1',stm=1)]
        low={(r,n):10-r for r in range(3) for n in (5000,50000)}
        e,_=m.pair_edges(g,low,'POINT');self.assertEqual(list(zip(e[0],e[1])),[(1,2)])

    def test_objective_gradient_finite_difference(self):
        rng=np.random.default_rng(17);phi=rng.normal(size=(8,240));z=rng.normal(size=8)
        rx=rng.normal(size=(20,240));rz=rng.normal(size=20);y=expit(rz+.1)
        e=(np.array([0,2,4]),np.array([1,3,5]),np.array([.2,.3,.5]),np.array([1,-1,1]))
        b=rng.normal(size=240)*.01;v,grad=m.objective(b,phi,z,e,rx,rz,y)
        self.assertTrue(np.isfinite(v))
        for i in (0,19,119,120,239):
            h=np.zeros(240);h[i]=1e-6
            numerical=(m.objective(b+h,phi,z,e,rx,rz,y)[0]-m.objective(b-h,phi,z,e,rx,rz,y)[0])/2e-6
            self.assertAlmostEqual(numerical,grad[i],places=7)

    def test_one_frozen_fit_converges_without_test_targets(self):
        rng=np.random.default_rng(8);phi=rng.normal(size=(16,240))*.01;z=np.zeros(16)
        rx=rng.normal(size=(40,240))*.01;rz=np.zeros(40);y=np.full(40,.5)
        e=(np.arange(0,16,2),np.arange(1,16,2),np.full(8,1/8),np.ones(8))
        b,r=m.fit(phi,z,e,rx,rz,y)
        self.assertTrue(r['success']);self.assertEqual(b.shape,(240,))
        self.assertLess(m.objective(b,phi,z,e,rx,rz,y)[0],m.objective(np.zeros(240),phi,z,e,rx,rz,y)[0])

    def test_quantization_preserves_entire_pattern_prefix_and_zero(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);base=root/'base';toy_model(base)
            zero=root/'zero';m.quantize(base,np.zeros(240),zero)
            self.assertEqual(base.read_bytes(),zero.read_bytes())
            beta=np.linspace(-.1,.1,240);out=root/'q';report=m.quantize(base,beta,out)
            raw,off,_=m.read_model(base);new,_,w=m.read_model(out)
            self.assertEqual(raw[:off],new[:off]);self.assertGreater(report['changed_extra_coefficients'],0)
            np.testing.assert_allclose(w,np.rint(beta*1000)/1000,rtol=0,atol=0)
            with self.assertRaises(FileExistsError):m.quantize(base,beta,out)
            with self.assertRaises(ValueError):m.quantize(base,np.full(240,np.nan),root/'bad')

    def test_true_native_child_sign_tie_and_terminal_decision(self):
        g=[dict(id=1,rows=[0,1],terminals=[],cell='P0_stm1',stm=1)]
        r={(0,200000):1.,(1,200000):3.}
        a=m.decision_rows(g,r,np.array([-1,-3]));self.assertEqual(a[0]['regret'],0)
        g[0]['terminals']=[0]
        a=m.decision_rows(g,r,np.array([-1,-3]));self.assertEqual(a[0]['choice'],0)

    def test_statistics_parent_not_pair_and_wdl_cluster_support(self):
        delta=np.arange(64)/100+1;cells=['P'+str(i%4) for i in range(64)]
        a=m.bootstrap_parent(delta,cells,9);b=m.bootstrap_parent(delta,cells,9)
        self.assertEqual(a,b);self.assertGreater(a['ci95'][0],0)
        with self.assertRaises(ValueError):m.bootstrap_opening(delta,np.zeros(64),1)
        c=m.bootstrap_opening(delta,np.arange(64),1);self.assertGreater(c['ci95'][0],0)

    def test_test_worker_cannot_start_without_frozen_models(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            with self.assertRaises(FileNotFoundError):p.score_worker(root,root/'scan','test',0,root/'scores',30,root)
            self.assertFalse((root/'scores').exists())

    def test_model_seal_detects_modified_candidate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for arm in p.ARMS:toy_model(root/(arm+'.pjtw'))
            m.write_new(root/'models-sealed.json',dict(models={a:m.sha(root/(a+'.pjtw')) for a in p.ARMS},test_teacher_calls=0,base_sha256=m.BASE_SHA))
            p.verify_model_seal(root)
            with (root/'PARTIAL.pjtw').open('ab') as f:f.write(b'x')
            with self.assertRaises(ValueError):p.verify_model_seal(root)

    def test_score_consumer_rejects_missing_duplicate_and_wrong_role(self):
        g=[dict(rows=[0,1],terminals=[],id=0)]
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'scores'
            m.write_new(path,dict(row=0,budget=50000,score=1,terminal=False))
            with self.assertRaises(ValueError):p.load_scores([path],g,(50000,))
            with self.assertRaises(ValueError):p.load_scores([path,path],g,(50000,))
            with self.assertRaises(ValueError):p.load_scores([path],g,(200000,))

    def test_native_table_schema_and_nonfinite_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'v';path.write_text('header\n0\tNaN\n')
            with self.assertRaises(ValueError):m.native_table(path,1)

@unittest.skipUnless(os.environ.get('ED2_VALUE_PROBE'),'native CI probe required')
class NativeValueTests(unittest.TestCase):
    def test_native_serialized_model_roundtrip(self):
        binary=Path(os.environ['ED2_VALUE_PROBE'])
        n_pat,n_ext=map(int,subprocess.check_output([str(binary),'--layout'],text=True).split())
        self.assertEqual(n_ext,120)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);base=root/'base.pjtw';toy_model(base,n_pat)
            rows=[]
            # Fixed legal-format states, including kings and both STM orientations.
            for stm in (0,1):
                rows.append(struct.pack('<QQQQBiB',sum(1<<s for s in (30,32,37,40,44)),1<<45,
                       sum(1<<s for s in (1,3,7,10,13)),1<<18,stm,0,0))
            data=root/'d.jnnw';p.write_records(data,rows)
            x,z,cp=p.run_probe(binary,data,base,root/'a.tsv')
            zero=root/'zero.pjtw';m.quantize(base,np.zeros(240),zero)
            xx,zz,cc=p.run_probe(binary,data,zero,root/'b.tsv')
            self.assertEqual(m.sha(base),m.sha(zero));np.testing.assert_array_equal(cp,cc)
            beta=np.linspace(-.1,.1,240);out=root/'shift.pjtw';m.quantize(base,beta,out)
            _,shifted,cp2=p.run_probe(binary,data,out,root/'c.tsv')
            _,_,weights=m.read_model(out)
            np.testing.assert_allclose(shifted,x@weights,rtol=0,atol=1e-12)
            self.assertTrue(np.any(cp2!=cp))
            np.testing.assert_array_equal(x,xx)

if __name__=='__main__':unittest.main()
