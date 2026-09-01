#!/usr/bin/env python3
from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main()
