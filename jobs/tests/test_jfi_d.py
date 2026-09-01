from __future__ import annotations

import gc
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

from jobs.tools import jfi_active4_materialize as materialize
from jobs.tools import jfi_candidate_universe as universe


def write_counted(path, magic, rows):
    Path(path).write_bytes(magic + struct.pack("<I", len(rows)) + rows.tobytes())


def write_feat(path, rows):
    rows = np.asarray(rows, dtype="<f4")
    Path(path).write_bytes(b"FEAT" + struct.pack("<II", *rows.shape) + rows.tobytes())


class JfiDTests(unittest.TestCase):
    def test_active4_materialization_is_post_freeze_and_keeps_dev_tail(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = np.zeros(6, dtype=universe.JNNW_DTYPE)
            source["wm"] = np.arange(1, 7); source["score"] = np.arange(10, 16)
            candidate = source.copy(); candidate["score"] = 0; candidate["wdl"] = 0
            meta = np.zeros(6, dtype=universe.JSM1_DTYPE)
            meta["game_id"] = np.arange(6); meta["opening_id"] = np.arange(6) // 2
            source_data=root/"source.jnnw"; source_meta=root/"source.jsm"
            candidate_data=root/"candidate.jnnw"; candidate_meta=root/"candidate.jsm"
            write_counted(source_data,b"JNNW",source); write_counted(source_meta,b"JSM1",meta)
            write_counted(candidate_data,b"JNNW",candidate); write_counted(candidate_meta,b"JSM1",meta)
            feat=root/"candidate.feat"; write_feat(feat,np.arange(12,dtype=np.float32).reshape(6,2))
            origin=root/"origin.npy"; np.save(origin,np.arange(6,dtype=np.uint32))
            active=root/"active.npy"; np.save(active,np.asarray([1,3],dtype=np.uint32))
            cm=root/"candidate.json"
            cm.write_text(json.dumps({"schema":"jass.jfi.candidate_universe.v1",
                "source":{"data_sha256":universe.sha256_file(source_data),"meta_sha256":universe.sha256_file(source_meta)},
                "files":{"data":{"sha256":universe.sha256_file(candidate_data)},
                         "meta":{"sha256":universe.sha256_file(candidate_meta)},
                         "origin_indices":{"sha256":universe.sha256_file(origin)}}}))
            sm=root/"selection.json"
            sm.write_text(json.dumps({"schema":"jass.jfi.d_active_selection.v1",
                "guards":{"TARGET_READS_BEFORE_MANIFEST_FREEZE":0},
                "inputs":{"candidate_manifest":{"sha256":universe.sha256_file(cm)},
                          "candidate_data":{"sha256":universe.sha256_file(candidate_data)},
                          "candidate_feat":{"sha256":universe.sha256_file(feat)},
                          "origin_indices":{"sha256":universe.sha256_file(origin)}},
                "files":{"active_indices":{"sha256":universe.sha256_file(active)}}}))
            args=SimpleNamespace(candidate_data=str(candidate_data),candidate_meta=str(candidate_meta),
                candidate_feat=str(feat),candidate_manifest=str(cm),origin_indices=str(origin),
                source_data=str(source_data),source_meta=str(source_meta),selection_manifest=str(sm),
                active_indices=str(active),train_count=4,out_data=str(root/"out.jnnw"),
                out_meta=str(root/"out.jsm"),out_feat=str(root/"out.feat"),manifest=str(root/"report.json"),
                chunk=2,production=False)
            report=materialize.materialize(args)
            rows,_=universe.open_counted(args.out_data,{b"JNNW":universe.JNNW_DTYPE})
            np.testing.assert_array_equal(rows["score"],source["score"][[1,3,4,5]])
            self.assertEqual(report["counts"],{"active_train":2,"dev_eval":2})
            self.assertTrue(report["guards"]["selection_manifest_verified_before_source_label_access"])
            del rows; gc.collect()

    def test_d_templates_preserve_target_blind_selection_and_one_fit(self):
        templates=Path(__file__).resolve().parents[1]/"templates"
        select=(templates/"l3-jfi-d-active4-select-v1.sh").read_text()
        fit=(templates/"l3-jfi-d-active4-fit-v1.sh").read_text()
        self.assertIn("--stage d",select); self.assertIn("--count 4000000",select)
        self.assertIn("TARGET_READS_TOTAL__0",select)
        self.assertNotIn("l3_conditional_targets.py",select)
        self.assertNotIn("train_stream.py",select)
        self.assertIn("jfi_active4_materialize.py",fit)
        self.assertIn("JASS_NATIVE_ACTIVE_V1",fit)
        self.assertEqual(fit.count("pattern_jass/tools/train_stream.py"),1)
        self.assertNotIn("--prior-mean",fit)
        self.assertNotIn("run_jass_gate_bounded.py",fit)


if __name__ == "__main__":
    unittest.main()
