from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path

from jobs.tools import ed5_fresh_decision_source_stage as s


class Ed5FreshDecisionSourceTests(unittest.TestCase):
    def test_preregistered_seeds(self):
        self.assertEqual(s.MASTER, 202609140501)
        self.assertEqual(s.RESERVE, 202609140511)
        s.validate_seed(s.MASTER)
        s.validate_seed(s.RESERVE)
        with self.assertRaises(ValueError):
            s.validate_seed(202609140502)

    def test_target_boundary_rejects_nonzero_target_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.jnnw"
            rec = bytearray(38)
            struct.pack_into("<Q", rec, 0, 1)
            rec[32] = 0
            rec[37] = 1
            p.write_bytes(b"JNNW" + struct.pack("<I", 1) + rec)
            with self.assertRaises(ValueError):
                s.base.records(p)

    def test_profile_is_zero_target_and_zero_search(self):
        profile = Path(__file__).resolve().parents[1] / "launch_profiles/ed5-fresh-d-source-v1.json"
        obj = json.loads(profile.read_text())
        for mode in ("rehearsal_max_effects", "production_max_effects"):
            self.assertEqual(obj[mode]["test_target_reads"], 0)
            self.assertEqual(obj[mode]["new_scan_searches"], 0)
            self.assertEqual(obj[mode]["new_jass_searches"], 0)
            self.assertEqual(obj[mode]["fits"], 0)


if __name__ == "__main__":
    unittest.main()
