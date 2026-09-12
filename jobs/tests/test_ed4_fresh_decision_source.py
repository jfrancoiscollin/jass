from __future__ import annotations
import json, struct, tempfile, unittest
from pathlib import Path
from jobs.tools import ed4_fresh_decision_source_stage as s

class FreshDecisionSourceTests(unittest.TestCase):
    def test_frozen_seeds(self):
        self.assertEqual(s.MASTER,202609120401)
        self.assertEqual(s.RESERVE,202609120411)
        self.assertEqual([s.MASTER+i for i in range(3)],[202609120401,202609120402,202609120403])

    def test_target_bytes_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.jnnw'
            r=bytearray(38); r[32]=0; r[33]=1
            p.write_bytes(b'JNNW'+struct.pack('<I',1)+bytes(r))
            with self.assertRaises(ValueError): s.records(p)

    def test_profile_has_zero_target_budget(self):
        p=Path(__file__).resolve().parents[1]/'launch_profiles/ed4-fresh-d-source-v1.json'
        obj=json.loads(p.read_text())
        self.assertEqual(obj['rehearsal_max_effects']['test_target_reads'],0)
        self.assertEqual(obj['production_max_effects']['test_target_reads'],0)
        self.assertIn('validate-and-seal',obj['required_phases'])

if __name__=='__main__': unittest.main()
