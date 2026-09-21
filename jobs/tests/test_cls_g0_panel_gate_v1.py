from __future__ import annotations
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest import mock
from jobs.tools import cls_g0_panel_gate_v1 as gate

class PanelGateTests(unittest.TestCase):
    def fixture(self,phase='readiness'):
        profile=json.loads((gate.ROOT/'jobs/launch_profiles/cls-g0-panel-v1.json').read_text())
        plan=gate.build_plan('a'*40,gate.digest(profile))
        typed={'job_id':'cpx62-readiness','attempt_id':'attempt-1','launch_receipt_sha256':'1'*64,'publisher_manifest_sha256':'2'*64,'opening_selection_sha256':'3'*64}
        adm={'schema':gate.SCHEMA,'job_id':'cpx62-test','phase':phase,'common_plan_sha256':gate.digest(plan),'profile_sha256':gate.digest(profile)}
        deps={}
        if phase=='readiness':adm['authenticated_audit_2072']=plan['audit_2072']
        else:deps={'authenticated_readiness':typed};adm.update(deps)
        if phase=='wdl':adm.update(prebound_local_job_id='cpx62-local',prebound_local_admission_sha256='4'*64)
        adm['materialized_spec_sha256']=gate.digest(gate.materialize(plan,phase,deps))
        return profile,plan,adm

    def test_exact_frozen_three_phase_templates(self):
        profile,plan,_=self.fixture();gate.validate_profile(profile);gate.validate_plan(plan,profile)
        self.assertEqual([(gate.build_stage_spec(plan,p)['timeouts']['stage_seconds'],gate.phase_template(p)['dispatcher_seconds']) for p in gate.PHASES],[(1800,2400),(3600,4200),(3600,4200)])
        self.assertEqual([gate.build_stage_spec(plan,p)['scientific_side_effects']['strength_games'] for p in gate.PHASES],[56,576,576])
        for phase in gate.PHASES:
            from jobs.tools.run_experiment_stage import validate_spec
            validate_spec(gate.build_stage_spec(plan,phase))

    def test_every_common_identity_is_closed(self):
        profile,plan,_=self.fixture()
        changes=[('models','CURRICULUM','0'*64),('runtime_identity','workers',8),('opening_recipe','pool_seed',1),('statistics','alpha_per_contrast',.05),('budget','automatic_retries',1),('source_identities','curriculum',{}),('stage_spec_base','inputs',[{}])]
        for group,key,value in changes:
            bad=copy.deepcopy(plan);bad[group][key]=value
            with self.subTest(group=group),self.assertRaises(gate.GateError):gate.validate_plan(bad,profile)

    def test_only_five_late_fields_and_no_stale_material(self):
        profile,plan,adm=self.fixture('local');gate.validate_admission(adm,plan,profile,'a'*40)
        bad=copy.deepcopy(adm);bad['authenticated_readiness']['code_sha']='a'*40
        with self.assertRaises(gate.GateError):gate.validate_admission(bad,plan,profile,'a'*40)
        bad=copy.deepcopy(adm);bad['authenticated_readiness']['attempt_id']='attempt-2'
        with self.assertRaisesRegex(gate.GateError,'MATERIALIZED_SPEC_HASH'):gate.validate_admission(bad,plan,profile,'a'*40)

    def test_generic_spec_all_fields_and_outer_budget_bound(self):
        _,plan,adm=self.fixture();material=gate.materialize(plan,'readiness',{})
        with tempfile.TemporaryDirectory() as tmp,mock.patch.dict(os.environ,{'EXPECTED_LAUNCH_TIMEOUT_SECONDS':'2400'}):
            p=Path(tmp)/'spec.json';spec=gate.build_stage_spec(plan,'readiness')
            for change in (None,lambda x:x['resources'].update(nproc=32),lambda x:x['environment']['set'].update(PANEL_PHASE='local'),lambda x:x['scientific_side_effects'].update(fits=1),lambda x:x.update(inputs=[{}])):
                value=copy.deepcopy(spec)
                if change:change(value)
                p.write_bytes(gate.canonical(value));adm['spec_sha256']=gate.sha(p)
                if change:
                    with self.assertRaisesRegex(gate.GateError,'SPEC_PROJECTION_DRIFT'):gate.validate_external_spec(p,adm,material)
                else:gate.validate_external_spec(p,adm,material)
            p.write_bytes(gate.canonical(spec));adm['spec_sha256']=gate.sha(p)
            with mock.patch.dict(os.environ,{'EXPECTED_LAUNCH_TIMEOUT_SECONDS':'4200'}),self.assertRaisesRegex(gate.GateError,'OUTER_TIMEOUT_CONTRACT'):gate.validate_external_spec(p,adm,material)

    def test_effects_and_nonempty_regressions_fail_closed(self):
        profile,_,_=self.fixture();base={'schema':'jass.execution_evidence.v2','state':'completed','mode':'rehearsal','completed_phases':profile['required_phases'],'actual_side_effects':{k:0 for k in gate.EFFECTS}}
        base['actual_side_effects'].update(strength_games=56,new_jass_searches=168)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'evidence.json';p.write_bytes(gate.canonical(base));gate.validate_evidence(p,profile,'readiness')
            for key,value in [('fits',1),('new_jass_searches',9073),('strength_games',55)]:
                bad=copy.deepcopy(base);bad['actual_side_effects'][key]=value;p.write_bytes(gate.canonical(bad))
                with self.subTest(key=key),self.assertRaises(gate.GateError):gate.validate_evidence(p,profile,'readiness')
        with self.assertRaises(gate.GateError):gate.validate_regressions({'schema':'jass.launch_regressions.v2','passed':True,'tests':0,'skipped':0,'failures':0,'errors':0,'suites':profile['regressions']},profile)

    def test_wdl_prebind_is_mandatory(self):
        profile,plan,adm=self.fixture('wdl');gate.validate_admission(adm,plan,profile,'a'*40)
        del adm['prebound_local_admission_sha256']
        with self.assertRaises(gate.GateError):gate.validate_admission(adm,plan,profile,'a'*40)

if __name__=='__main__':unittest.main()
