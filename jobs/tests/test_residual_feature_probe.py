#!/usr/bin/env python3
import json
import shutil
import subprocess
import unittest
from pathlib import Path

import numpy as np

from jobs.tools import residual_feature_probe as rf


class ResidualFeatureProbeContractTest(unittest.TestCase):
    def test_exact_family_width_and_order(self):
        self.assertEqual([len(rf.FAMILY_NAMES[x]) for x in ("F1","F2","F3","F4","F5","F6")],
                         [12,14,12,16,12,66])
        self.assertEqual(rf.FAMILY_NAMES["F6"],
                         rf.FAMILY_NAMES["F1"]+rf.FAMILY_NAMES["F2"]+rf.FAMILY_NAMES["F3"]+rf.FAMILY_NAMES["F4"]+rf.FAMILY_NAMES["F5"])
        self.assertEqual(rf.FAMILY_SLICES["F1"], slice(0,12))
        self.assertEqual(rf.FAMILY_SLICES["F5"], slice(54,66))

    def test_forbidden_feature_input_guard(self):
        for names in rf.FAMILY_NAMES.values():
            lowered=" ".join(names).lower()
            for token in rf.FORBIDDEN_FEATURE_TOKENS:
                self.assertNotIn(token, lowered)

    def test_parent_sign_sham_is_cluster_deterministic(self):
        a=rf.sham_sign("canonical-parent","TRAIN-A",7)
        b=rf.sham_sign("canonical-parent","TRAIN-A",7)
        self.assertEqual(a,b)
        self.assertIn(a,(-1.0,1.0))
        signs=[rf.sham_sign(f"p{i}","DEV-B",3) for i in range(128)]
        self.assertIn(-1.0,signs); self.assertIn(1.0,signs)

    def test_d1_is_fixed_one_no_intercept_and_roundtrips(self):
        x=np.zeros((8,12),dtype=np.float64)
        x[:,0]=[4,0,3,0,2,0,1,0]
        d1=np.asarray([.2,.2,-.3,-.3,.1,.1,0.,0.],dtype=np.float64)
        pairs=[rf.PairRef(f"p{k}",2*k,2*k+1) for k in range(4)]
        model=rf.fit_probe(x,d1,pairs,"F1")
        self.assertEqual(model["d1_coefficient"],1.0)
        self.assertEqual(model["intercept"],0.0)
        score=rf.score_probe(model,x,d1)
        for k in range(4): self.assertGreater(score[2*k],score[2*k+1])
        raw=rf.artifact_bytes(model)
        replay=json.loads(raw)
        np.testing.assert_array_equal(score,rf.score_probe(replay,x,d1))
        self.assertEqual(raw,rf.artifact_bytes(replay))

    def test_pair_cap_deterministic_sha_order(self):
        pairs=[rf.PairRef(f"p{i%17}",i,i+1) for i in range(200)]
        a=rf.cap_pairs(pairs,31); b=rf.cap_pairs(list(reversed(pairs)),31)
        self.assertEqual(a,b); self.assertEqual(len(a),31)

    def test_probe_selftest(self):
        self.assertEqual(rf.self_test(),0)

    def test_cpp_extractor_source_contract_and_syntax(self):
        root=Path(__file__).resolve().parents[2]
        src=root/"jobs/tools/residual_feature_dump.cpp"
        text=src.read_text(encoding="utf-8")
        self.assertIn("TOTAL_WIDTH == 66",text)
        self.assertIn("CENTRAL16",text)
        self.assertIn("generate_legal_moves",text)
        self.assertIn("Bytes [33..37] hold historical score/WDL. They are never read.",text)
        # No search-engine/TT header is linked into the extractor.
        self.assertNotIn('#include "search.hpp"',text)
        self.assertNotIn('#include "tt.hpp"',text)
        cxx=shutil.which("c++") or shutil.which("g++")
        if cxx:
            subprocess.run([cxx,"-std=c++20","-Isrc","-fsyntax-only",str(src)],cwd=root,check=True,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)


if __name__ == "__main__":
    unittest.main()
