from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from jobs.tools import validate_launch_contracts as v
from jobs.tools import make_launch_bundle as b
from jobs.tools.launch_runtime_v2 import EFFECTS

class LaunchContractPreflightV3Tests(unittest.TestCase):
    def profile(self,root:Path):
        p=root/'jobs/launch_profiles/x.json'; p.parent.mkdir(parents=True)
        t=root/'jobs/tools/stage.py'; t.parent.mkdir(parents=True); t.write_text('print(1)\n')
        obj={'schema':'jass.launch_profile.v2','campaign':'c','stage':'s','command':['/python','jobs/tools/stage.py'],'evidence_outputs':['out.json'],'production_max_effects':{k:0 for k in EFFECTS},'rehearsal_max_effects':{k:0 for k in EFFECTS},'regressions':['jobs.tests.test_launch_gate_v2','jobs.tests.test_launch_gate_pipeline_v2'],'required_phases':['a','b']}
        p.write_text(json.dumps(obj)); return p,obj
    def test_missing_regressions_fails_before_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p,obj=self.profile(root); del obj['regressions']; p.write_text(json.dumps(obj))
            with patch.object(v,'ROOT',root):
                with self.assertRaisesRegex(v.ContractError,'profile_fields'): v.validate_profile(p)
    def test_missing_entrypoint_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p,obj=self.profile(root); obj['command'][1]='jobs/tools/missing.py'; p.write_text(json.dumps(obj))
            with patch.object(v,'ROOT',root):
                with self.assertRaisesRegex(v.ContractError,'entrypoint'): v.validate_profile(p)
    def test_bundle_hashes_exact_written_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p,obj=self.profile(root)
            spec=root/'spec.json'; spec.write_text(json.dumps({'environment':{'set':{}},'timeouts':{'stage_seconds':120},'outputs':[{'path':'out.json','required':True,'nonempty':True,'scope':'artifact'},{'path':'execution-evidence.json','required':True,'nonempty':True,'scope':'artifact'},{'path':'scientific-summary.json','required':True,'nonempty':True,'scope':'artifact'}]}))
            with patch.object(v,'ROOT',root), patch.object(b,'ROOT',root), patch.object(b,'validate_profile',lambda x: obj):
                sb,ab,sh=b.build('cpx62-test','a'*40,p,spec)
            adm=json.loads(ab); import hashlib
            self.assertEqual(adm['profile'],'jobs/launch_profiles/x.json')
            self.assertEqual(adm['spec_sha256'],hashlib.sha256(sb).hexdigest())
            self.assertEqual(adm['profile_sha256'],hashlib.sha256(p.read_bytes()).hexdigest())
            self.assertIn('EXPECTED_LAUNCH_TIMEOUT_SECONDS="720"',sh)
    def test_base_regressions_are_mandatory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p,obj=self.profile(root); obj['regressions']=['jobs.tests.test_launch_gate_v2']; p.write_text(json.dumps(obj))
            with patch.object(v,'ROOT',root):
                with self.assertRaisesRegex(v.ContractError,'regressions'): v.validate_profile(p)
    def test_bundle_rejects_profile_outside_repo(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); p,obj=self.profile(root)
            spec=root/'spec.json'; spec.write_text(json.dumps({'environment':{'set':{}},'timeouts':{'stage_seconds':120},'outputs':[{'path':'out.json','required':True,'nonempty':True,'scope':'artifact'},{'path':'execution-evidence.json','required':True,'nonempty':True,'scope':'artifact'},{'path':'scientific-summary.json','required':True,'nonempty':True,'scope':'artifact'}]}))
            with patch.object(b,'validate_profile',lambda x: obj):
                with self.assertRaisesRegex(v.ContractError,'profile_outside_repo'): b.build('cpx62-test','a'*40,p,spec)

if __name__=='__main__': unittest.main()
