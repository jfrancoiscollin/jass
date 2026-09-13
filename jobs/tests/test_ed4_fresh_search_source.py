from __future__ import annotations
import json, unittest
from pathlib import Path
from jobs.tools import ed4_fresh_search_source_stage as s

class FreshSearchSourceTests(unittest.TestCase):
    def test_frozen_primary_and_reserve(self):
        self.assertEqual(s.PRIMARY,202609120403)
        self.assertEqual(s.RESERVE,202609120413)
        self.assertEqual(s.FORCED_SEED,s.RESERVE)

    def test_profile_is_target_free(self):
        p=Path(__file__).resolve().parents[1]/'launch_profiles/ed4-fresh-s-source-v1.json'
        obj=json.loads(p.read_text())
        self.assertEqual(obj['rehearsal_max_effects']['test_target_reads'],0)
        self.assertEqual(obj['production_max_effects']['test_target_reads'],0)
        self.assertEqual(obj['rehearsal_max_effects']['new_scan_searches'],0)
        self.assertEqual(obj['production_max_effects']['new_jass_searches'],0)
        self.assertIn('validate-and-seal',obj['required_phases'])

if __name__=='__main__': unittest.main()
