"""Complete confirmation with deterministic source/teacher fixtures, actual publisher.

The separate native contract runs the SAME fixture entrypoint with compiled source
and native evaluation. CPX rehearsal replaces fixture transport/teacher with R2/Scan.
"""
from __future__ import annotations
import gzip
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from jobs.tools import ed3_confirmation as c, ed3_confirmation_data as d
from jobs.tools.launch_runtime_v2 import atomic_json
ROOT=Path(__file__).resolve().parents[2]


def fixture_run(result, art, mode='rehearsal', actual_native=False):
    from jobs.tools import ed2_preflight as ep, ed2_value_math as m
    from jobs.tests.test_ed3_confirmation import sample_records
    result.mkdir(parents=True,exist_ok=True);art.mkdir(parents=True,exist_ok=True)
    state={}
    def loader(result,art):
        work=result/'work';work.mkdir()
        n=5
        probe=Path(os.environ['ED3_CONFIRM_NATIVE_PROBE']) if actual_native else work/'probe'
        if actual_native:
            n,extras=map(int,subprocess.check_output([str(probe),'--layout'],text=True).split());assert extras==120
        models={}
        for arm,shift in [('BASE',0.),('HARD',.01),('SOFT',.02)]:
            path=work/(arm+'.pjtw');weights=np.zeros(2*(n+120),dtype='<i4')
            weights[2*n]=int(shift*1000)
            path.write_bytes(struct.pack('<5I',0x57544a50,3,1000,n,120)+weights.tobytes());models[arm]=path
        identities=dict(models={a:d.sha(p) for a,p in models.items()},probe_sha256='fixture')
        atomic_json(art/'model-identities.json',identities)
        # Transport fixture contains a full-sized target array, but only sealed ids
        # are ever dereferenced by the real native_readout implementation.
        targets=work/'targets.npy';np.save(targets,np.full(2000000,.5,dtype=np.float32))
        state.update(models=models,identities=identities,probe=probe,targets=targets)
        return state
    def prepare(state,result,art,mode):
        source=art/'source'
        if actual_native:
            source_binary=Path(os.environ['ED3_CONFIRM_SOURCE'])
            ex=result/'work/exclusions.txt'
            ex.write_text(''.join(f'{i:013x}:0000000000000:0000000000000:0000000000000:0\n' for i in range(2000)))
            subprocess.run([str(source_binary),str(ex),str(source),'production' if mode=='production' else 'smoke'],check=True,timeout=240)
            ep.validate_source(source,ex,'production' if mode=='production' else 'smoke')
        else:
            source.mkdir();parents=[];groups=[];prs=[];crs=[];samples=sample_records(784*3)
            for role,quota in [('calibration',2),('train',64),('test',32)]:
                for ph in range(4):
                    for stm in range(2):
                        for _ in range(quota):
                            pid=len(parents);rec=samples[pid*3][:32]+bytes([stm])+b'\0'*5;prs.append(rec)
                            parents.append(dict(parent_id=pid,parent_phase=f'P{ph}',parent_stm=stm,split=role))
                            for a in range(2):
                                crs.append(samples[pid*3+a+1][:32]+bytes([1-stm])+b'\0'*5)
                                groups.append(dict(parent_id=pid,row_index=len(crs)-1,child_rule_terminal=0))
            import csv
            for name,rows in [('parents.tsv',parents),('groups.tsv',groups)]:
                with (source/name).open('w') as f:
                    writer=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t');writer.writeheader();writer.writerows(rows)
            d.write_records(source/'parents.jnnw',prs);d.write_records(source/'children.jnnw',crs)
            atomic_json(source/'source.json',dict(fixture=True,parents=len(prs),children=len(crs)))
        parents,groups=ep.load_tsv(source/'parents.tsv'),ep.load_tsv(source/'groups.tsv')
        chosen=d.selected_groups(parents,groups,mode);children=ep.records(source/'children.jnnw')
        ids=[r for g in chosen for r in g['rows']]
        guard_rows=sample_records(256 if mode=='rehearsal' else 8192)
        guard=dict(indices=list(range(len(guard_rows))),opening_ids=list(range(len(guard_rows))))
        plan=dict(subsets={'development':guard,'confirmation':guard},targets_read_at_selection=0)
        atomic_json(art/'guard-plan.json',plan)
        seal=dict(source_files={name:d.sha(source/name) for name in ep.FILES},guard_plan_sha256=d.sha(art/'guard-plan.json'))
        atomic_json(art/'cohort-seal.json',seal)
        d.write_records(result/'work/decisions.jnnw',[children[r] for r in ids]);d.write_records(result/'work/guard.jnnw',guard_rows)
        state.update(groups=chosen,children=children,ids=ids,guard=guard,seal=seal,source=source)
        return state
    def calibrate(state,evidence):
        evidence.value['actual_side_effects']['new_scan_searches']=17;evidence.save()
        return dict(calibration_searches=17,calibration_requested_nodes=3400000,batch_cap_seconds=60.,fixture=True)
    def score(state,art,work,mode,cost,evidence):
        terminal={r for g in state['groups'] for r in g['terminals']};calls=0;paths=[]
        for shard in range(8):
            path=art/f'reference-{shard}.jsonl';paths.append(path)
            with path.open('x') as f:
                for rid in sorted(state['ids']):
                    if rid%8!=shard:continue
                    t=rid in terminal
                    f.write(json.dumps(dict(row=rid,budget=200000,score=10000 if t else rid%31,
                        terminal=t,elapsed_seconds=0 if t else .01,last_info_nodes=0 if t else 10000))+'\n');calls+=not t
        high,n=c.load_scores(paths,state['groups']);assert n==calls
        cost.update(reference_searches=calls,reference_requested_nodes=calls*200000,reference_rows=len(high))
        evidence.value['actual_side_effects']['new_scan_searches']+=calls
        if mode=='production':evidence.value['actual_side_effects']['test_target_reads']+=len(high)
        evidence.save();return high
    def fake_probe(binary,records,model,out):
        rec=ep.records(records);x=np.zeros((len(rec),240))
        for i,r in enumerate(rec):x[i,0]=int.from_bytes(r[:8],'little').bit_count()/20
        _,_,w=m.read_model(model);z=x@w;sign=np.array([1 if r[32] else -1 for r in rec]);cp=np.trunc(sign*z*100).astype(int)
        out.write_text('fixture-native\n');return x,z,cp
    kw=dict(loader=loader,preparer=prepare,calibrator=calibrate,scorer=score)
    if actual_native:return c.run(result,art,mode,**kw)
    with patch('jobs.tools.ed3_soft_value_fit.run_probe',fake_probe):return c.run(result,art,mode,**kw)


class FullPublicationTests(unittest.TestCase):
    def test_real_stage_publisher_and_authenticated_readout(self):
        from jobs.tools import run_experiment_stage as core
        from jobs.tools.fetch_result_files import fetch_files
        sys.path.insert(0,str(ROOT/'infra'))
        from runner_v3_store import prepare_run_dir,FilesystemResultStore
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'repo';repo.mkdir();run=root/'run';art=run/'artefacts';art.mkdir(parents=True)
            (repo/'fixture.py').write_text('import sys,os\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(ROOT))+')\nfrom jobs.tests.test_ed3_confirmation_publication import fixture_run\nfixture_run(Path(os.environ["JASS_RESULT_DIR"]),Path(os.environ["JASS_ARTEFACT_DIR"]))\n')
            for cmd in (['git','init','-q'],['git','config','user.email','fixture@example.invalid'],['git','config','user.name','Fixture'],['git','add','.'],['git','commit','-qm','fixture']):subprocess.run(cmd,cwd=repo,check=True)
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
            spec=dict(schema='jass.stage_spec.v1',code_sha=head,campaign='fixture',stage='ed3-confirmation',
                command=[sys.executable,'fixture.py'],working_directory='.',inputs=[],
                outputs=[dict(scope='artifact',path=n,required=True,nonempty=True,kind='file') for n in c.OUTPUTS+['execution-evidence.json','scientific-summary.json']],
                resources=dict(hostname=None,nproc=None,clean_worktree=True),timeouts=dict(stage_seconds=120,terminate_grace_seconds=1),
                artifact_directory_contract='empty_or_runner_launch',environment={'inherit':[],'set':{'LAUNCH_MODE':'rehearsal','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}},
                scientific_side_effects=dict(fits=0,strength_games=0,promotions=0,bakes=0),success=dict(required_exit_code=0,next_stage=None))
            sp=root/'spec.json';atomic_json(sp,spec)
            job='cpx62-confirm-fixture';attempt='20260909T000000Z-'+head[:8]
            with patch.dict(os.environ,{'JASS_JOB_ID':job,'JASS_ATTEMPT_ID':attempt}):rc,receipt=core.run_stage(spec_path=sp,repo_root=repo,result_dir=run,artifact_dir=art)
            self.assertEqual(rc,0,receipt)
            ev=d.read_json(art/'execution-evidence.json');self.assertEqual(ev['completed_phases'],c.PHASES)
            summary=d.read_json(art/'scientific-summary.json');self.assertIsNone(summary['scientific_verdict']);self.assertEqual(summary['fits'],0)
            expected={n:d.sha(art/n) for n in c.OUTPUTS}
            prepare_run_dir(run,dict(job_id=job,attempt_id=attempt,code_sha=head,host='fixture',state='completed',exit_code=0),100000)
            store=root/'store';FilesystemResultStore(store).publish(run,job,attempt,True)
            bin=root/'bin';bin.mkdir();rclone=bin/'rclone'
            rclone.write_text('#!'+sys.executable+'\nimport os,sys,shutil\nfrom pathlib import Path\ndef local(x):return Path(os.environ["FIXTURE_STORE"])/x.split("r2:jass-data/runs/",1)[1]\na=sys.argv[1:]\nif a[0]=="cat":sys.stdout.buffer.write(local(a[1]).read_bytes())\nelif a[0]=="copyto":shutil.copyfile(local(a[1]),a[2])\nelse:raise SystemExit(2)\n');rclone.chmod(0o755)
            prefix=f'r2:jass-data/runs/{job}/{attempt}'
            with patch.dict(os.environ,{'FIXTURE_STORE':str(store)}):
                out=root/'readback';fetch_files(rclone=str(rclone),prefix=prefix,selections=[('artefacts/'+n,n) for n in c.OUTPUTS],out_dir=out)
                self.assertEqual(expected,{n:d.sha(out/n) for n in c.OUTPUTS})
                (store/job/attempt/'artefacts/confirmation-readout.json').write_text('{}')
                with self.assertRaises(Exception):fetch_files(rclone=str(rclone),prefix=prefix,selections=[('artefacts/confirmation-readout.json','r.json')],out_dir=root/'bad')
                (store/job/attempt/'_SUCCESS').unlink()
                with self.assertRaises(Exception):fetch_files(rclone=str(rclone),prefix=prefix,selections=[('artefacts/cohort-seal.json','s.json')],out_dir=root/'no-marker')

    def test_failure_retains_original_phase_without_raw_secret(self):
        with tempfile.TemporaryDirectory() as td:
            result=Path(td);art=result/'artefacts';art.mkdir()
            def bad(*args):raise ValueError('SECRET_must_not_be_in_status')
            with self.assertRaises(ValueError):c.run(result,art,'rehearsal',loader=bad)
            ev=d.read_json(art/'execution-evidence.json')
            self.assertEqual(ev['phase'],'authenticate');self.assertEqual(ev['error_type'],'ValueError')
            self.assertNotIn('SECRET',json.dumps(ev));self.assertEqual(ev['completed_phases'],[])

if __name__=='__main__':unittest.main()
