#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"jobs/tools/t2_phase_specialist.py"
spec=importlib.util.spec_from_file_location("t2_phase_specialist",TOOL); assert spec and spec.loader
mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)

class T2ContractTests(unittest.TestCase):
    def records(self,n=4):
        a=np.zeros(n,dtype=mod.JNNW_DTYPE)
        # piece counts 40,25,15,8 while keeping four planes disjoint enough for contract tests
        masks=[(1<<10)-1,(1<<7)-1,(1<<4)-1,(1<<2)-1]
        for i in range(n):
            m=masks[i]
            a["wm"][i]=m; a["wk"][i]=m<<10; a["bm"][i]=m<<20; a["bk"][i]=m<<30
        a["stm"]=[0,1,0,1][:n]
        return a
    def meta(self,n=4):
        phases=["P0","P1","P2","P3"]
        return [mod.StaticMeta(i//2,i%2,phases[i],10.0+i) for i in range(n)]

    def test_exact_326_state_only_inputs(self):
        rec=self.records(); feat=np.arange(4*120,dtype=np.float64).reshape(4,120); meta=self.meta()
        x,t0,ph=mod.build_state_features(feat,rec,meta)
        self.assertEqual(x.shape,(4,326)); np.testing.assert_array_equal(x[:,:120],feat)
        self.assertEqual(x[0,120],1.0); self.assertEqual(x[0,320],-10.0); self.assertEqual(x[1,321],1.0)
        np.testing.assert_array_equal(ph,np.array([0,1,2,3],dtype=np.int8))
        for i in range(4): self.assertEqual(x[i,322+i],1.0); self.assertEqual(float(x[i,322:326].sum()),1.0)
        np.testing.assert_array_equal(t0,np.array([-10.,-11.,-12.,-13.]))

    def test_constructor_has_no_forbidden_data_arguments(self):
        sig=inspect.signature(mod.build_state_features)
        for k in ("from_sq","to_sq","num_captures","d1","q1000","q50","q200","wdl","q1"):
            self.assertNotIn(k,sig.parameters)
        self.assertTrue({"from","to","num_captures","d1","q1000","q50","q200","wdl","q1_metric"}.issubset(mod.FORBIDDEN_INPUT_NAMES))

    def test_jnnw_parser_and_piece_phase(self):
        rec=self.records(2)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x.jnnw"; p.write_bytes(b"JNNW"+struct.pack("<I",2)+rec.tobytes())
            got=mod.read_jnnw(p); self.assertEqual(len(got),2); self.assertEqual(p.stat().st_size,8+2*38)
        self.assertEqual(mod.phase_from_pieces(40),0); self.assertEqual(mod.phase_from_pieces(29),1); self.assertEqual(mod.phase_from_pieces(12),2); self.assertEqual(mod.phase_from_pieces(0),3)

    def test_hard_phase_routing(self):
        m=mod.init_model(); x=np.zeros((4,326)); ph=np.array([0,1,2,3],dtype=np.int8)
        # Zero all parameters, then unique phase biases prove hard routing.
        for k in m: m[k].fill(0)
        for p in range(4): m[f"H{p}b1"][0]=float(p+1)
        r,_=mod.forward_residual(m,x,ph); np.testing.assert_array_equal(r,np.array([1.,2.,3.,4.]))

    def test_parent_pov_is_negative_child_t2(self):
        m=mod.init_model();
        for k in m: m[k].fill(0)
        xn=np.zeros((2,326)); t0=np.array([5.,-7.]); ph=np.array([0,0],dtype=np.int8)
        s=mod.parent_scores(m,xn,t0,ph); np.testing.assert_array_equal(s,np.array([-5.,7.]))

    def test_equal_phase_colour_cell_weighting_and_cap_order(self):
        pairs=[]
        # deliberately very unequal cell sizes
        for i in range(10): pairs.append(mod.Pair(i,0,"P0",i,i+1))
        for i in range(10,12): pairs.append(mod.Pair(i,1,"P1",i,i+1))
        ps,w,counts=mod.cap_and_weight_pairs(pairs,cap=100)
        self.assertEqual(counts,{"P0_white":10,"P1_black":2})
        sums={}
        for p,ww in zip(ps,w): sums[p.parent_phase,p.parent_stm]=sums.get((p.parent_phase,p.parent_stm),0)+ww
        self.assertAlmostEqual(sums["P0",0],0.5,places=14); self.assertAlmostEqual(sums["P1",1],0.5,places=14)
        a=mod.cap_and_weight_pairs(list(reversed(pairs)),cap=3)[0]; b=mod.cap_and_weight_pairs(pairs,cap=3)[0]; self.assertEqual(a,b)

    def test_finite_backprop_and_shared_network(self):
        rng=np.random.default_rng(7); m=mod.init_model(); x=rng.normal(size=(8,326)); ph=np.array([0,1,2,3,0,1,2,3],dtype=np.int8)
        r,c=mod.forward_residual(m,x,ph); self.assertEqual(r.shape,(8,)); g=mod.backward_residual(m,c,np.ones(8)/8)
        self.assertTrue(all(np.all(np.isfinite(v)) for v in g.values()))
        self.assertFalse(any("white" in k or "black" in k for k in m))

    def test_deterministic_init_serialization_and_roundtrip(self):
        m1=mod.init_model(); m2=mod.init_model()
        for k in m1: np.testing.assert_array_equal(m1[k],m2[k])
        mean=np.zeros(326); std=np.ones(326); payload=mod.artifact_payload(m1,mean,std,{"cell_counts":{},"pairs":0,"history":[]})
        with tempfile.TemporaryDirectory() as td:
            p1=Path(td)/"a.json"; p2=Path(td)/"b.json"; h1=mod.save_artifact(p1,payload); h2=mod.save_artifact(p2,payload)
            self.assertEqual(h1,h2); self.assertEqual(p1.read_bytes(),p2.read_bytes()); self.assertEqual(h1,hashlib.sha256(p1.read_bytes()).hexdigest())
            j,m3,mu,sd=mod.load_artifact(p1); self.assertEqual(j["input_width"],326); np.testing.assert_array_equal(mu,mean); np.testing.assert_array_equal(sd,std)
            for k in m1: np.testing.assert_array_equal(m1[k],m3[k])

    def test_lr_schedule(self):
        self.assertEqual(mod.lr_for_epoch(39),1e-3); self.assertAlmostEqual(mod.lr_for_epoch(40),3e-4); self.assertAlmostEqual(mod.lr_for_epoch(60),9e-5)

if __name__=="__main__": unittest.main()
