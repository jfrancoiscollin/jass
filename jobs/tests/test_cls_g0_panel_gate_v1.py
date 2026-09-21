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

    def test_both_main_admissions_and_specs_are_sealed_before_local(self):
        profile,plan,local=self.fixture('local');_,_,wdl=self.fixture('wdl')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);local['job_id']='cpx62-local';wdl['job_id']='cpx62-wdl'
            activation={'schema':'jass.cls_panel_main_activation.v1','common_plan_sha256':gate.digest(plan),'code_sha':plan['code_sha'],'profile_sha256':plan['profile_sha256']}
            for phase,record in (('local',local),('wdl',wdl)):
                sp=root/(phase+'.json');sp.write_bytes(gate.canonical(gate.build_stage_spec(plan,phase)));record['spec_sha256']=gate.sha(sp)
                if phase=='wdl':record['prebound_local_admission_sha256']=activation['local']['admission_sha256']
                ap=root/(phase+'.admission.json');ap.write_bytes(gate.canonical(record))
                activation[phase]={'admission':ap.name,'admission_sha256':gate.sha(ap),'spec':sp.name,'materialized_spec_sha256':record['materialized_spec_sha256']}
            act=root/'main-activation.json';act.write_bytes(gate.canonical(activation))
            gate.validate_main_activation(act,plan,local,activation['local']['admission_sha256'],root)
            wdl_path=root/'wdl.admission.json';wdl_path.write_bytes(wdl_path.read_bytes()+b' ')
            with self.assertRaisesRegex(gate.GateError,'MAIN_ACTIVATION_HASH'):
                gate.validate_main_activation(act,plan,local,activation['local']['admission_sha256'],root)

    def test_local_technical_resolution_requires_prebound_receipt_without_outcome_parse(self):
        profile,plan,_=self.fixture('wdl')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'panel-admission-receipt.json').write_text('{}');games=root/'stage-games.json.gz';games.write_bytes(b'synthetic raw data')
            proof={'receipt':{'phase':'local','admission_sha256':'a'*64,'main_activation_sha256':'b'*64,'materialized_spec_sha256':'c'*64},'evidence':{'actual_side_effects':{'strength_games':576}},'games_path':games}
            with mock.patch.object(gate,'fetch_panel_proof',return_value=proof) as fetch:
                result=gate.local_technical_from_r2({'job_id':'cpx62-local','attempt_id':'attempt-1'},plan,profile,root,'cpx62-local','a'*64,'b'*64,'c'*64)
                self.assertTrue(fetch.call_args.kwargs['technical_only']);self.assertIsNone(result['scientific_verdict'])
                with self.assertRaisesRegex(gate.GateError,'LOCAL_TECHNICAL_IDENTITY'):
                    gate.local_technical_from_r2({'job_id':'cpx62-local','attempt_id':'attempt-1'},plan,profile,root,'cpx62-local','d'*64,'b'*64,'c'*64)

    def test_wdl_prebind_is_mandatory(self):
        profile,plan,adm=self.fixture('wdl');gate.validate_admission(adm,plan,profile,'a'*40)
        del adm['prebound_local_admission_sha256']
        with self.assertRaises(gate.GateError):gate.validate_admission(adm,plan,profile,'a'*40)


class ExplicitReadinessAdmissionTests(unittest.TestCase):
    successor = dict(job_id='cpx62-2074-readiness-v2', attempt_id='20260921T120000Z-abcdef12', code_sha='b'*40)
    predecessor = dict(zip(('job_id','attempt_id','code_sha'), gate._READINESS_2073))

    def history_case(self, histories, *, exception=True, phase='readiness', duplicate=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'specs').mkdir()
            binding={'path':'specs/exception.json','sha256':'e'*64}
            adm={'schema':gate.SCHEMA,'phase':phase,'job_id':self.successor['job_id']}
            if exception: adm['prior_attempt_exception']=binding
            all_rows={self.successor['job_id']: []}
            all_rows.update(histories)
            for i, (job, rows) in enumerate(all_rows.items()):
                row=adm if job==self.successor['job_id'] else {'schema':gate.SCHEMA,'phase':phase,'job_id':job}
                (root/'specs'/f'{i}.admission.json').write_bytes(gate.canonical(row))
            if duplicate:
                dup=copy.deepcopy(adm);dup['prior_attempt_exception']['path']='specs/another-copy.json'
                (root/'specs/duplicate.admission.json').write_bytes(gate.canonical(dup))
            def history(argv, **kwargs):
                if 'log' in argv:
                    job=Path(argv[-1]).stem
                    return ''.join(str(i)+'\n' for i in range(len(all_rows[job])))
                if 'show' in argv:
                    commit, name=argv[-1].split(':',1)
                    return gate.canonical(all_rows[Path(name).stem][int(commit)])
                self.fail('unexpected git command')
            value={**binding,'record':{}} if exception else None
            with mock.patch.dict(os.environ,{'JASS_JOB_ID':self.successor['job_id'],'JASS_ATTEMPT_ID':self.successor['attempt_id']}), \
                 mock.patch.object(gate,'_readiness_exception',return_value=value), \
                 mock.patch.object(gate.subprocess,'check_output',side_effect=history):
                return gate.reject_prior_attempts(root,adm,self.successor['code_sha'],repo_root=root,proof_dir=root/'proof')

    def test_full_history_accepts_only_pinned_prior_and_current_tuple(self):
        rows={self.predecessor['job_id']:[dict(self.predecessor,state='running'),dict(self.predecessor,state='failed')],
              self.successor['job_id']:[dict(self.successor,state='running')]}
        self.assertEqual(self.history_case(rows)['sha256'],'e'*64)

    def test_history_rejects_unknown_or_second_attempt_and_duplicate_digest(self):
        base={self.predecessor['job_id']:[self.predecessor]}
        cases=[({},False),
               ({**base,'unknown-job':[dict(self.predecessor,job_id='unknown-job')]},False),
               ({**base,self.successor['job_id']:[dict(self.successor,attempt_id='earlier-attempt')]},False),
               ({**base,self.successor['job_id']:[dict(self.successor,code_sha='c'*40)]},False),
               ({self.predecessor['job_id']:[dict(self.predecessor,attempt_id='unknown-attempt')]},False),
               (base,True)]
        for rows, duplicate in cases:
            with self.subTest(rows=rows,duplicate=duplicate),self.assertRaisesRegex(gate.GateError,gate._NO_RETRY):
                self.history_case(rows,duplicate=duplicate)

    def test_without_exception_original_current_tuple_and_no_retry_remain(self):
        self.assertIsNone(self.history_case({self.successor['job_id']:[self.successor]},exception=False))
        with self.assertRaisesRegex(gate.GateError,gate._NO_RETRY):
            self.history_case({self.predecessor['job_id']:[self.predecessor]},exception=False)

    def exception_case(self, mutate=None, *, proof_error=False):
        """Exercise real wrapper/source checks; mock only already-separated R2 proof boundary."""
        amendment=json.loads((gate.ROOT/gate._AMENDMENT_V2).read_text())
        raw_amend=gate.canonical(amendment)
        profile_hash=amendment['frozen_contract']['launch_profile_raw_git_object_bytes_sha256']
        old=gate.build_plan(self.predecessor['code_sha'],profile_hash)
        new=gate.build_plan(self.successor['code_sha'],profile_hash)
        old_raw=gate.canonical(old)
        self.assertEqual(__import__('hashlib').sha256(old_raw).hexdigest(),amendment['frozen_contract']['original_common_plan_json_sha256'])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'specs').mkdir()
            (root/'specs/plan.json').write_bytes(gate.canonical(new))
            record={'schema':'jass.cls_readiness_one_attempt_exception.v2','phase':'readiness',
                'predecessor':self.predecessor,'evidence':amendment['failed_attempt_2073']['evidence'],
                'effects':{k:0 for k in gate.EFFECTS},'successor_job_id':self.successor['job_id'],
                'successor_code_sha':self.successor['code_sha'],'successor_common_plan_sha256':gate.digest(new),
                'max_successor_attempts':1,'automatic_retries':0,
                'amendment_sha256':__import__('hashlib').sha256(raw_amend).hexdigest()}
            adm={'job_id':self.successor['job_id'],'phase':'readiness','common_plan':'specs/plan.json','common_plan_sha256':gate.digest(new)}
            if mutate: mutate(record,adm)
            path=root/'specs/exception.json';path.write_bytes(gate.canonical(record))
            adm['prior_attempt_exception']={'path':'specs/exception.json','sha256':gate.sha(path)}
            original=gate._git_object
            def objects(repo, reference):
                if reference=='HEAD:'+gate._AMENDMENT_V2:return raw_amend
                if reference.endswith(':specs/cls-panel-v1/common-plan.json'):return old_raw
                return original(gate.ROOT,reference)
            with mock.patch.dict(os.environ,{'JASS_JOB_ID':self.successor['job_id'],'JASS_ATTEMPT_ID':self.successor['attempt_id']}), \
                 mock.patch.object(gate,'_git_object',side_effect=objects), \
                 mock.patch.object(gate,'_authenticate_2073',side_effect=RuntimeError('missing proof') if proof_error else None,
                    return_value={'effects':{k:0 for k in gate.EFFECTS}}):
                return gate._readiness_exception(root,adm,self.successor['code_sha'],repo_root=root,proof_dir=root/'proof')

    def test_wrapper_authenticates_amendment_plan_blobs_and_keeps_spec_unchanged(self):
        result=self.exception_case()
        self.assertEqual(result['successor']['job_id'],self.successor['job_id'])
        self.assertEqual(result['cumulative_limits'],{'strength_games':56,'new_jass_searches':9072})
        self.assertNotIn('prior_attempt_exception',gate.materialize(gate.build_plan('b'*40,'e'*64),'readiness',{}))

    def test_wrapper_rejects_changed_evidence_amendment_effects_or_successor(self):
        changes=[lambda r,a:r.update(amendment_sha256='0'*64),
                 lambda r,a:r['evidence'].update(publisher_manifest_sha256='0'*64),
                 lambda r,a:r['effects'].update(selfplay_games=1),
                 lambda r,a:r['effects'].pop('selfplay_games'),
                 lambda r,a:r['effects'].update(fits=False),
                 lambda r,a:r.update(successor_code_sha='c'*40),
                 lambda r,a:r.update(successor_job_id=self.predecessor['job_id']),
                 lambda r,a:r.update(successor_common_plan_sha256='0'*64),
                 lambda r,a:r.update(max_successor_attempts=True),
                 lambda r,a:r.update(automatic_retries=1),
                 lambda r,a:a.update(phase='local')]
        for i, change in enumerate(changes):
            with self.subTest(case=i),self.assertRaisesRegex(gate.GateError,gate._NO_RETRY):
                self.exception_case(change)
        with self.assertRaisesRegex(gate.GateError,gate._NO_RETRY):self.exception_case(proof_error=True)

    def test_wrapper_rejects_missing_corrupt_or_escaping_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bad.json').write_bytes(b'{broken')
            for path,digest in [('missing.json','a'*64),('../escape','a'*64),('bad.json',gate.sha(root/'bad.json')),('bad.json','0'*64)]:
                adm={'phase':'readiness','prior_attempt_exception':{'path':path,'sha256':digest}}
                with self.subTest(path=path,digest=digest),self.assertRaisesRegex(gate.GateError,gate._NO_RETRY):
                    gate._readiness_exception(root,adm,'b'*40,repo_root=root)

    def publication_case(self, *, effect=0, phase='launch-regressions', corrupt=False, failed=True,
                         missing_counter=False, error_type='RegressionSuiteFailed', status_state='failed'):
        """Real failed-proof validator over synthetic authenticated transport bytes."""
        import hashlib
        from jobs.tools import fetch_result_files as transport
        from jobs.tools.cls_g0_panel_raw_audit import git_blob
        evidence={'state':'failed','phase':phase,'error_type':error_type,'completed_phases':[],
                  'actual_side_effects':{k:0 for k in gate.EFFECTS}}
        evidence['actual_side_effects']['strength_games']=effect
        if missing_counter: evidence['actual_side_effects'].pop('selfplay_games')
        data={'publisher-manifest.json':gate.canonical(dict(self.predecessor,state='failed',exit_code=2)),
              'execution-evidence.json':gate.canonical(evidence),'runner-launch.json':b'{}\n',
              'panel-regressions.json':gate.canonical(dict(passed=False,errors=1,failures=0,skipped=0,tests=42)),
              'metadata.json':b'{}\n','exit_code':b'2\n'}
        keys={'publisher-manifest.json':'publisher_manifest_sha256','execution-evidence.json':'execution_evidence_sha256',
              'runner-launch.json':'runner_launch_sha256','panel-regressions.json':'regression_report_sha256',
              'metadata.json':'metadata_sha256','exit_code':'exit_code_file_sha256'}
        e={keys[k]:hashlib.sha256(v).hexdigest() for k,v in data.items()}
        status=gate.canonical(dict(self.predecessor,state=status_state,exit_code=2))
        e.update(terminal_control_commit='d'*40,terminal_status_git_blob=git_blob(status))
        for key in ['results_document','readback_json']:
            e[key]={'source_commit':'c'*40,'git_blob':git_blob(b'{}\n'),'git_object_file_bytes_sha256':hashlib.sha256(b'{}\n').hexdigest()}
        pins={k:e[k] for k in gate._READINESS_2073_HASHES}
        def fetch(**kw):
            self.assertEqual(kw['expected_state'],'failed')
            folder=kw['out_dir'];folder.mkdir(parents=True,exist_ok=True)
            for _,name in kw['selections']:
                (folder/name).write_bytes(data[name]+(b'x' if corrupt and name=='metadata.json' else b''))
            return dict(self.predecessor,host='cpx62',result_state='failed' if failed else 'completed',exit_code=2,
                        files=[{'local_name':name} for _,name in kw['selections']])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(gate,'_READINESS_2073_HASHES',pins), \
             mock.patch.object(gate,'_git_object',side_effect=lambda repo,ref:status if ':status/' in ref else b'{}\n'), \
             mock.patch.object(transport,'fetch_files',side_effect=fetch):
            return gate._authenticate_2073(Path(tmp),Path(tmp),{'failed_attempt_2073':{'evidence':e}},Path(tmp)/'proof')

    def test_failed_publication_requires_zero_effects_before_stage_and_intact_bytes(self):
        self.assertTrue(all(v==0 for v in self.publication_case()['effects'].values()))
        for change in [{'effect':1},{'effect':False},{'phase':'execute'},{'corrupt':True},{'failed':False}]:
            with self.subTest(change=change),self.assertRaises(gate.GateError):self.publication_case(**change)


if __name__=='__main__':unittest.main()
