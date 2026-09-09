"""Full-sized hermetic ED3-T1 calculation/publication contract.

The fixture has the frozen cardinalities and retained-pair arithmetic but never
opens an archived artifact or invokes an engine.
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
import numpy as np
from jobs.tools import ed3_transfer_diagnostic as t

def groups(rows_per,terminals=False):
    out=[]; row=0
    for pid,n in enumerate(rows_per):
        out.append({'id':pid,'cell':f'P{pid//128}_stm{(pid//64)%2}','stm':(pid//64)%2,'rows':list(range(row,row+n)),'terminals':([row] if terminals and pid%97==0 else [])})
        row+=n
    return out

def fixture_loader(result,art,evidence=None):
    tg=groups([10]*368+[9]*144); cg=groups([10]*94+[9]*418,terminals=True)
    tn=len([r for g in tg for r in g['rows']]); cn=len([r for g in cg for r in g['rows']])
    ts={}
    for gi,g in enumerate(tg):
        for j,r in enumerate(g['rows']):
            q=float(j); ts[r,50000]=q; ts[r,5000]=q if gi<38 else q+1
    def native(n):
        cp=np.arange(n,dtype=int)%31; return {'BASE':cp,'HARD':cp+((np.arange(n)%5)==0),'SOFT':cp-((np.arange(n)%7)==0),'BASE_logit':-cp.astype(float),'HARD_logit':-(cp+((np.arange(n)%5)==0)).astype(float),'SOFT_logit':-(cp-((np.arange(n)%7)==0)).astype(float)}
    cref={r:float(r%10) for g in cg for r in g['rows']}
    for g in cg:
        if g['terminals']: cref[g['terminals'][0]]=10000.
    guard={'y':(np.arange(8192)%101)/100.,'opening_ids':np.arange(8192)%2394,
           'indices':np.arange(1800796,1800796+8192),
           'signs':np.where(np.arange(8192)%2,1,-1),
           'native_cp':{a:(np.arange(8192)%41)-20+j for j,a in enumerate(t.ARMS)}}
    ci=dict(train_groups=tg,train_scores=ts,train_native=native(tn),confirmation_groups=cg,confirmation_ref=cref,confirmation_native=native(cn),guard=guard)
    from jobs.tools.ed2_value_math import decision_rows
    from scipy.special import expit
    ps={a:decision_rows(cg,{(r,200000):q for r,q in cref.items()},ci['confirmation_native'][a]) for a in t.ARMS}
    def old(base):
        b,s=ps[base],ps['SOFT'];d=np.array([a['regret']-z['regret'] for a,z in zip(b,s)])
        return {'mean':float(d.mean()),'harmed':int((d<0).sum()),'improved':int((d>0).sum()),
                'top_hit_delta':float(np.mean([z['hit']-a['hit'] for a,z in zip(b,s)])),
                'decision_changes':sum(a['choice']!=z['choice'] for a,z in zip(b,s)),'ci95':[0.,0.]}
    wdl={};loss={}
    for arm in t.ARMS:
        z=guard['signs']*guard['native_cp'][arm]/100.;loss[arm]=np.logaddexp(0,z)-guard['y']*z
        wdl[arm]=dict(logloss=float(np.mean(loss[arm])),brier=float(np.mean((expit(z)-guard['y'])**2)))
    delta=float(np.mean(loss['SOFT']-loss['BASE']))
    old_report={'versus_base':old('BASE'),'versus_hard':old('HARD'),'wdl':wdl,
                'aggregate':{a:dict(regret_mean=float(np.mean([r['regret'] for r in rs])),
                                    top_hit=float(np.mean([r['hit'] for r in rs]))) for a,rs in ps.items()},
                'wdl_delta_bootstrap':{'mean':delta,'ci95':[0.,0.]}}
    if evidence is not None:
        evidence.value['actual_side_effects']['test_target_reads']=12894
        evidence.value['existing_train_label_reads']=9952;evidence.save()
    return dict(**ci,auth={'fixture':True},
                counts={'train_parents':512,'train_children':4976,'train_pairs':17622,
                        'confirmation_parents':512,'confirmation_children':4702,'guard_rows':8192,
                        'opening_groups':2394,'native_prediction_rows':68264},
                old_result={'versus_base':old_report['versus_base'],'versus_hard':old_report['versus_hard'],
                            'wdl_soft_minus_base_ci95':[0.,0.],'wdl_soft_minus_base_mean':delta},
                old_report=old_report,old_parent_rows=ps)

class PublicationContract(unittest.TestCase):
    def test_old_wdl_mismatch_fails_without_publication(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);art=root/'artefacts';art.mkdir()
            def bad(*args,**kwargs):
                value=fixture_loader(*args,**kwargs)
                value['old_report']['wdl']['SOFT']['logloss']+=.01
                return value
            with self.assertRaisesRegex(ValueError,'old_wdl_reproduction'):
                t.run(root,art,'rehearsal',loader=bad)
            self.assertFalse((art/'publication-manifest.json').exists())

    def test_zero_retained_pairs_keeps_valid_parent_choice_and_margin(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);data=fixture_loader(root,root)
            first=data['train_groups'][0]
            for row in first['rows']:data['train_scores'][row,5000]=10000.
            values=t.calculate(**{k:data[k] for k in ('train_groups','train_scores','train_native',
                'confirmation_groups','confirmation_ref','confirmation_native','guard')})
            parent=values[3][0]
            self.assertFalse(parent['pair_support'])
            self.assertTrue(parent['choice_support'] and parent['margin_support'])
            self.assertEqual(values[0]['train']['pair_transition']['supported_parents'],511)
            self.assertAlmostEqual(values[0]['train']['pair_transition']['total_mass'],511/512,places=15)

    def test_full_sized_deterministic_payload_and_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); art=root/'artefacts'; art.mkdir()
            summary=t.run(root,art,'rehearsal',loader=fixture_loader)
            self.assertEqual(summary['verdict'],'ED3_TRANSFER_DIAGNOSTIC_REHEARSAL_COMPLETE_V1')
            self.assertEqual(len((art/'train-pair-transitions.jsonl').read_text().splitlines()),17622)
            self.assertEqual(len((art/'confirmation-pair-transitions.jsonl').read_text().splitlines())>0,True)
            manifest=json.loads((art/'publication-manifest.json').read_text())
            self.assertNotIn('publication-manifest.json',manifest['immutable_sha256'])
            self.assertNotIn('scientific-summary.json',manifest['immutable_sha256'])
            report=json.loads((art/'ed3-transfer-diagnostic.json').read_text())
            self.assertEqual(report['confirmation']['pair_transition']['support_definition'],'all_strict_Q200')
            self.assertEqual(report['train']['pair_transition']['support_definition'],'PARTIAL_retained_Q5_Q50')

    def test_actual_stage_publisher_and_checked_readback(self):
        from jobs.tools import run_experiment_stage as core
        from jobs.tools.fetch_result_files import fetch_files
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'infra'))
        from runner_v3_store import prepare_run_dir, FilesystemResultStore
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); repo=root/'repo'; repo.mkdir(); run=root/'run'; art=run/'artefacts'; art.mkdir(parents=True)
            fixture=repo/'fixture.py'
            fixture.write_text("import os,sys\nfrom pathlib import Path\nsys.path.insert(0,"+repr(str(Path(__file__).resolve().parents[2]))+")\nfrom jobs.tests.test_ed3_transfer_diagnostic_publication import fixture_loader\nfrom jobs.tools.ed3_transfer_diagnostic import run\nrun(Path(os.environ['JASS_RESULT_DIR']),Path(os.environ['JASS_ARTEFACT_DIR']),'rehearsal',loader=fixture_loader)\n")
            for cmd in (['git','init','-q'],['git','config','user.email','fixture@example.invalid'],['git','config','user.name','Fixture'],['git','add','.'],['git','commit','-qm','fixture']): subprocess.run(cmd,cwd=repo,check=True)
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
            outs=t.OUTPUTS+['execution-evidence.json','scientific-summary.json']
            spec={'schema':'jass.stage_spec.v1','code_sha':head,'campaign':'fixture','stage':'ed3-transfer-diagnostic-v1','command':[sys.executable,'fixture.py'],'working_directory':'.','inputs':[],'outputs':[{'scope':'artifact','path':x,'required':True,'nonempty':True,'kind':'file'} for x in outs],'resources':{'hostname':None,'nproc':None,'clean_worktree':True},'timeouts':{'stage_seconds':120,'terminate_grace_seconds':1},'artifact_directory_contract':'empty_or_runner_launch','environment':{'inherit':[],'set':{'LAUNCH_MODE':'rehearsal','PYTHONDONTWRITEBYTECODE':'1'}},'scientific_side_effects':{k:0 for k in ('fits','strength_games','promotions','bakes')},'success':{'required_exit_code':0,'next_stage':None}}
            sp=root/'spec.json'; sp.write_text(json.dumps(spec)); job='fixture-ed3-t1'; attempt='20260909T000000Z-'+head[:8]
            from unittest.mock import patch
            with patch.dict(os.environ,{'JASS_JOB_ID':job,'JASS_ATTEMPT_ID':attempt}): rc,receipt=core.run_stage(spec_path=sp,repo_root=repo,result_dir=run,artifact_dir=art)
            self.assertEqual(rc,0,receipt); expected={x:t.file_sha(art/x) for x in t.OUTPUTS}
            prepare_run_dir(run,{'job_id':job,'attempt_id':attempt,'code_sha':head,'host':'fixture','state':'completed','exit_code':0},100000); store=root/'store'; FilesystemResultStore(store).publish(run,job,attempt,True)
            fake=root/'rclone'; fake.write_text('#!'+sys.executable+'\nimport os,sys,shutil\nfrom pathlib import Path\ndef p(x): return Path(os.environ["FIXTURE_STORE"])/x.split("r2:jass-data/runs/",1)[1]\na=sys.argv[1:]\nif a[0]=="cat":sys.stdout.buffer.write(p(a[1]).read_bytes())\nelif a[0]=="copyto":shutil.copyfile(p(a[1]),a[2])\nelse:raise SystemExit(2)\n'); fake.chmod(0o755)
            with patch.dict(os.environ,{'FIXTURE_STORE':str(store)}):
                out=root/'out'; fetch_files(rclone=str(fake),prefix=f'r2:jass-data/runs/{job}/{attempt}',selections=[('artefacts/'+x,x) for x in t.OUTPUTS],out_dir=out); self.assertEqual(expected,{x:t.file_sha(out/x) for x in t.OUTPUTS})
                (store/job/attempt/'artefacts/ed3-transfer-diagnostic.json').write_text('{}')
                with self.assertRaises(Exception): fetch_files(rclone=str(fake),prefix=f'r2:jass-data/runs/{job}/{attempt}',selections=[('artefacts/ed3-transfer-diagnostic.json','bad.json')],out_dir=root/'bad')
                (store/job/attempt/'_SUCCESS').unlink()
                with self.assertRaises(Exception): fetch_files(rclone=str(fake),prefix=f'r2:jass-data/runs/{job}/{attempt}',selections=[('artefacts/source-authentication.json','no.json')],out_dir=root/'no')

    def test_failure_keeps_phase(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); art=root/'artefacts'; art.mkdir()
            def bad(*args,**kwargs): raise ValueError('secret-never-published')
            with self.assertRaises(ValueError): t.run(root,art,'rehearsal',loader=bad)
            ev=json.loads((art/'execution-evidence.json').read_text())
            self.assertEqual(ev['phase'],'authenticate'); self.assertEqual(ev['completed_phases'],[])
            self.assertNotIn('secret',json.dumps(ev).lower())

if __name__=='__main__': unittest.main()
