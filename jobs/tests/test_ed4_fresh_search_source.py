from __future__ import annotations
import json, re, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
STAGE=ROOT/'jobs/tools/ed4_fresh_search_source_stage.py'
PROFILE=ROOT/'jobs/launch_profiles/ed4-fresh-s-source-v1.json'

class FreshSearchSourceTests(unittest.TestCase):
    def test_frozen_primary_and_reserve(self):
        text=STAGE.read_text()
        def const(name):
            m=re.search(rf'^{name}=(\d+)$',text,re.MULTILINE)
            self.assertIsNotNone(m,name)
            return int(m.group(1))
        self.assertEqual(const('PRIMARY'),202609120403)
        self.assertEqual(const('RESERVE'),202609120413)
        self.assertIn('FORCED_SEED=RESERVE',text)
        self.assertIn('if seed!=RESERVE',text)

    def test_profile_is_target_free(self):
        obj=json.loads(PROFILE.read_text())
        self.assertEqual(obj['rehearsal_max_effects']['test_target_reads'],0)
        self.assertEqual(obj['production_max_effects']['test_target_reads'],0)
        self.assertEqual(obj['rehearsal_max_effects']['new_scan_searches'],0)
        self.assertEqual(obj['production_max_effects']['new_jass_searches'],0)
        self.assertIn('validate-and-seal',obj['required_phases'])

if __name__=='__main__': unittest.main()
