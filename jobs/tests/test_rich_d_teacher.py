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

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "jobs/tools/rich_d_teacher.py"
spec = importlib.util.spec_from_file_location("rich_d_teacher", TOOL)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

class RichDContractTests(unittest.TestCase):
    def make_records(self, n=4):
        a = np.zeros(n, dtype=mod.JNNW_DTYPE)
        a["wm"] = [1,2,4,8][:n]
        a["wk"] = [16,32,64,128][:n]
        a["bm"] = [256,512,1024,2048][:n]
        a["bk"] = [4096,8192,16384,32768][:n]
        a["stm"] = [0,1,0,1][:n]
        return a

    def make_meta(self, n=4):
        phases = ["P0","P1","P2","P3"]
        return [
            mod.StaticMeta(
                parent_id=i//2, parent_stm=i%2, phase=phases[i%4],
                pieces=40-i, legal_moves=2+i, from_sq=1+i, to_sq=10+i,
                num_captures=1+i, captured_kings=i%2, promotes=(i+1)%2,
                moving_king=i%2, t_baseline_parent=12.5-i,
            ) for i in range(n)
        ]

    def test_exact_333_static_inputs_and_order(self):
        rec = self.make_records()
        feat = np.arange(4*120,dtype=np.float64).reshape(4,120)
        meta = self.make_meta()
        x = mod.build_static_features(feat,rec,meta)
        self.assertEqual(x.shape,(4,333))
        np.testing.assert_array_equal(x[:,:120],feat)
        self.assertEqual(x[0,120],1.0)
        self.assertEqual(x[1,121],1.0)
        self.assertEqual(x[0,320],1.0)
        self.assertEqual(x[0,324],1/50)
        self.assertEqual(x[0,325],10/50)
        self.assertEqual(x[0,326],12.5)
        self.assertEqual(x[0,327],1.0)
        self.assertAlmostEqual(x[0,331],1.0)
        self.assertAlmostEqual(x[0,332],2/16)

    def test_constructor_cannot_accept_search_scores_or_wdl(self):
        sig = inspect.signature(mod.build_static_features)
        for forbidden in ("q5k","q50","q200","wdl","exact_parent_utility","source","partition"):
            self.assertNotIn(forbidden,sig.parameters)
        self.assertTrue({"q5k_parent","q50_parent","q200_parent","wdl"}.issubset(mod.FORBIDDEN_INPUT_NAMES))

    def test_jnnw_38_byte_parser(self):
        rec = self.make_records(2)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"x.jnnw"
            p.write_bytes(b"JNNW"+struct.pack("<I",2)+rec.tobytes())
            got = mod.read_jnnw(p)
            self.assertEqual(len(got),2)
            self.assertEqual(int(got[1]["wk"]),32)
            self.assertEqual(p.stat().st_size,8+2*38)

    def test_train_only_normalization(self):
        x = np.zeros((3,333),dtype=np.float64)
        x[0,0]=1; x[1,0]=3; x[2,0]=1000
        mean,std = mod.fit_normalization(x,[0,1])
        self.assertEqual(mean[0],2.0)
        self.assertEqual(std[0],1.0)

    def test_separate_banks_and_finite_backprop(self):
        b0 = mod.init_bank()
        b1 = mod.init_bank()
        self.assertIsNot(b0,b1)
        x = np.random.default_rng(3).normal(size=(5,333))
        s,c = mod.forward(b0,x)
        self.assertEqual(s.shape,(5,))
        g = mod.backward(b0,c,np.ones(5)/5)
        self.assertTrue(all(np.all(np.isfinite(v)) for v in g.values()))
        before = {k:v.copy() for k,v in b1.items()}
        b0["W0"][0,0] += 1
        for k in b1:
            np.testing.assert_array_equal(b1[k],before[k])

    def test_deterministic_forward_and_serialization_sha(self):
        b0 = mod.init_bank()
        b1 = mod.init_bank()
        x = np.random.default_rng(7).normal(size=(3,333))
        s1,_=mod.forward(b0,x); s2,_=mod.forward(mod.init_bank(),x)
        np.testing.assert_array_equal(s1,s2)
        mean=np.zeros(333); std=np.ones(333)
        payload=mod.artifact_payload(
            {"white_parent":b0,"black_parent":b1},
            {"white_parent":(mean,std),"black_parent":(mean,std)},
            {"white_parent":{"ok":True},"black_parent":{"ok":True}},
        )
        with tempfile.TemporaryDirectory() as td:
            p1=Path(td)/"a.json"; p2=Path(td)/"b.json"
            h1=mod.save_artifact(p1,payload); h2=mod.save_artifact(p2,payload)
            self.assertEqual(h1,h2)
            self.assertEqual(p1.read_bytes(),p2.read_bytes())
            self.assertEqual(h1,hashlib.sha256(p1.read_bytes()).hexdigest())

    def test_pair_cap_hash_order_is_deterministic(self):
        pairs=[mod.Pair(i,0,i,i+1) for i in range(20)]
        a=mod.cap_pairs(pairs,0,7)
        b=mod.cap_pairs(list(reversed(pairs)),0,7)
        self.assertEqual(a,b)

    def test_lr_schedule(self):
        self.assertEqual(mod.lr_for_epoch(0),1e-3)
        self.assertEqual(mod.lr_for_epoch(39),1e-3)
        self.assertAlmostEqual(mod.lr_for_epoch(40),3e-4)
        self.assertAlmostEqual(mod.lr_for_epoch(60),9e-5)

if __name__ == "__main__":
    unittest.main()
