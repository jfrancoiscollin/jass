from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
TOOL=ROOT/"jobs/tools/t2_phase_specialist.py"
spec=importlib.util.spec_from_file_location("t2_phase_specialist_ci",TOOL); assert spec and spec.loader
m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)


def _records():
    a=np.zeros(4,dtype=m.JNNW_DTYPE)
    bits=(10,7,4,2)
    for i,b in enumerate(bits):
        mask=(1<<b)-1; a["wm"][i]=mask; a["wk"][i]=mask<<10; a["bm"][i]=mask<<20; a["bk"][i]=mask<<30
    a["stm"]=[0,1,0,1]
    return a


def _meta():
    return [m.StaticMeta(i//2,i%2,("P0","P1","P2","P3")[i],10.0+i) for i in range(4)]


def test_exact_state_only_contract_and_phase_routing():
    feat=np.arange(480,dtype=np.float64).reshape(4,120); x,t0,ph=m.build_state_features(feat,_records(),_meta())
    assert x.shape==(4,326); np.testing.assert_array_equal(x[:,:120],feat); np.testing.assert_array_equal(t0,[-10.,-11.,-12.,-13.]); np.testing.assert_array_equal(ph,[0,1,2,3])
    assert np.all(x[:,322:326].sum(axis=1)==1)
    sig=inspect.signature(m.build_state_features)
    for forbidden in ("from_sq","to_sq","num_captures","d1","q1000","q50","q200","wdl","q1"):
        assert forbidden not in sig.parameters
    assert {"from","to","num_captures","d1","q1000","q50","q200","wdl","q1_metric"}.issubset(m.FORBIDDEN_INPUT_NAMES)


def test_hard_phase_heads_parent_pov_and_shared_colour_network():
    model=m.init_model()
    for k in model: model[k].fill(0)
    for p in range(4): model[f"H{p}b1"][0]=p+1
    x=np.zeros((4,326)); ph=np.array([0,1,2,3],dtype=np.int8); r,_=m.forward_residual(model,x,ph)
    np.testing.assert_array_equal(r,[1.,2.,3.,4.])
    for k in model: model[k].fill(0)
    np.testing.assert_array_equal(m.parent_scores(model,np.zeros((2,326)),np.array([5.,-7.]),np.array([0,0],dtype=np.int8)),[-5.,7.])
    assert not any("white" in k or "black" in k for k in model)


def test_equal_cell_weighting_and_determinism():
    pairs=[m.Pair(i,0,"P0",i,i+1) for i in range(10)]+[m.Pair(i,1,"P1",i,i+1) for i in range(10,12)]
    ps,w,counts=m.cap_and_weight_pairs(pairs,100); assert counts=={"P0_white":10,"P1_black":2}
    sums={}
    for p,ww in zip(ps,w): sums[m.pair_cell(p)]=sums.get(m.pair_cell(p),0.0)+ww
    assert abs(sums[("P0",0)]-.5)<1e-12 and abs(sums[("P1",1)]-.5)<1e-12
    a=m.cap_and_weight_pairs(list(reversed(pairs)),3)[0]; b=m.cap_and_weight_pairs(pairs,3)[0]; assert a==b
    m1=m.init_model(); m2=m.init_model()
    for k in m1: np.testing.assert_array_equal(m1[k],m2[k])


def test_finite_backprop_and_artifact_roundtrip(tmp_path):
    rng=np.random.default_rng(9); model=m.init_model(); x=rng.normal(size=(8,326)); ph=np.array([0,1,2,3,0,1,2,3],dtype=np.int8)
    _,cache=m.forward_residual(model,x,ph); g=m.backward_residual(model,cache,np.ones(8)/8); assert all(np.all(np.isfinite(v)) for v in g.values())
    payload=m.artifact_payload(model,np.zeros(326),np.ones(326),{"pairs":0,"cell_counts":{},"history":[]}); p=tmp_path/"t2.json"; sha=m.save_artifact(p,payload); j,restored,mu,sd=m.load_artifact(p)
    assert j["input_width"]==326 and len(sha)==64; np.testing.assert_array_equal(mu,np.zeros(326)); np.testing.assert_array_equal(sd,np.ones(326))
    for k in model: np.testing.assert_array_equal(model[k],restored[k])
