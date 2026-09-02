#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from jobs.tools.jfi_subset import MAX_RECORDS, main as subset_main


class JfiExecutionTemplateTests(unittest.TestCase):
    def test_boundary_template_is_bounded_and_scan_independent(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / "jobs/templates/l3-jfi-boundary-a-v1.sh").read_text()
        self.assertIn("SIZER_RECORDS=20000", text)
        self.assertIn("SIZER_MAXIT=2", text)
        self.assertIn("NEXT_BOUNDARY__GO_JFI_FIT", text)
        self.assertIn("FULL_FITS=0", text)
        self.assertEqual(text.count("fit_sizer "), 4)
        for forbidden in (
            "scan-exact", "SCAN_EXACT", "run_match", "fresh-openings",
            "GO_JFI_FIT=1", "--max-iter 2000",
        ):
            self.assertNotIn(forbidden, text)

    def test_subset_is_aligned_and_refuses_more_than_20k(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); count=7; width=2
            data=root/"data.jnnw"; feat=root/"data.feat"; targets=root/"targets.npy"
            rows=bytes(i % 251 for i in range(count*38))
            data.write_bytes(b"JNNW"+struct.pack("<I",count)+rows)
            values=np.arange(count*width,dtype="<f4")
            feat.write_bytes(b"FEAT"+struct.pack("<II",count,width)+values.tobytes())
            np.save(targets,np.linspace(.1,.9,count,dtype=np.float32),allow_pickle=False)
            manifest=root/"manifest.json"
            self.assertEqual(subset_main([
                "--data",str(data),"--feat",str(feat),"--target-values",str(targets),
                "--records","5","--holdout-count","1","--out-data",str(root/"out.jnnw"),
                "--out-feat",str(root/"out.feat"),"--out-target-values",str(root/"out.npy"),
                "--manifest",str(manifest),
            ]),0)
            doc=json.loads(manifest.read_text())
            self.assertEqual(doc["records"],5)
            self.assertEqual(doc["markers"]["SCAN_WEIGHT_READS"],0)
            with self.assertRaisesRegex(SystemExit, str(MAX_RECORDS)):
                subset_main([
                    "--data",str(data),"--feat",str(feat),"--target-values",str(targets),
                    "--records",str(MAX_RECORDS+1),"--holdout-count","1",
                    "--out-data","x","--out-feat","y","--out-target-values","z","--manifest","m",
                ])

    def test_fit_template_has_exact_seven_fit_contract_and_no_force(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / "jobs/templates/l3-jfi-factorial-l2-fit-v1.sh").read_text()
        calls = re.findall(r"^fit (?:A|B|C|D|L2_0|L2_1E6|L2_1E4) ", text, re.MULTILINE)
        self.assertEqual(len(calls), 7)
        self.assertIn("D_reused_as_l2_1e5", text)
        self.assertIn("BOOTSTRAP_SAMPLES=100000", text)
        self.assertIn("BOOTSTRAP_SEED=2026120101", text)
        self.assertIn("POST_FACTS_AUTHORIZED", text)
        self.assertIn("POS_MAXIT=6000", text)
        self.assertIn("ZERO_MAXIT=2000", text)
        self.assertIn('--max-iter "$maxit"', text)
        self.assertIn('--lbfgs-maxcor "$MAXCOR"', text)
        self.assertIn('--lbfgs-gtol "$GTOL"', text)
        self.assertIn('fit A 1e-5 "$POS_MAXIT"', text)
        self.assertIn('fit B 1e-5 "$POS_MAXIT"', text)
        self.assertIn('fit C 1e-5 "$POS_MAXIT"', text)
        self.assertIn('fit D 1e-5 "$POS_MAXIT"', text)
        self.assertIn('fit L2_0 0 "$ZERO_MAXIT"', text)
        self.assertIn('fit L2_1E6 1e-6 "$POS_MAXIT"', text)
        self.assertIn('fit L2_1E4 1e-4 "$POS_MAXIT"', text)
        self.assertIn('FIT_CHECKPOINTS__7', text)
        self.assertIn('POSITIVE_LAMBDA_MAX_ITER__6000', text)
        self.assertIn('L2_ZERO_MAX_ITER__2000', text)
        self.assertIn('A.raw.npy.gz', text)
        self.assertIn('L2_1E6.pjtw.gz', text)
        self.assertIn('--expected-max-iterations "$POS_MAXIT"', text)
        for forbidden in ("run_match", "fresh-openings", "SCAN_EXACT", "GO_JFI_FORCE"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
