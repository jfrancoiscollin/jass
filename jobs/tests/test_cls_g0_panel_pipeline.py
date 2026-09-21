"""Actual gate/core/publisher-reader integration using a synthetic, zero-game stage."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
from jobs.tools import cls_g0_panel_gate_v1 as gate
from jobs.tools import fetch_result_files as fetch
from jobs.tools import launch_gate_v2 as v2
from jobs.tools import run_experiment_stage as core

SYNTHETIC_STAGE = r"""
import json,os,pathlib,sys,gzip,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]))
from jobs.tools import cls_g0_panel_readiness as ready
from jobs.tools.launch_runtime_v2 import StageEvidence,atomic_json
result=pathlib.Path(os.environ['JASS_RESULT_DIR']); art=pathlib.Path(os.environ['JASS_ARTEFACT_DIR']);art.mkdir(exist_ok=True)
ctx=json.loads((result/'panel-admission-context.json').read_text());plan=ctx['common_plan']
profile=json.loads(pathlib.Path(ctx['paths']['profile']).read_text());names=profile['evidence_outputs']
pool=[f'W:W{a},{b}:B{c}' for a in range(3,51) for b in range(a+1,51) for c in (1,2)][:2048]
raw=('\n'.join(pool)+'\n').encode();seal=ready.seal_openings(raw,raw,set())
ctx['opening_selection_sha256']=seal['selection_sha256'];atomic_json(result/'panel-admission-context.json',ctx)
e=StageEvidence(art,'rehearsal')
for phase in profile['required_phases']:
 e.begin(phase)
 if phase=='execute':
  e.record_effect('strength_games',56);e.record_effect('new_jass_searches',168)
 e.complete()
e.finish()
for n in names:
 if n not in ('manifest.json','opening-freeze.json','stage-games.json.gz'):atomic_json(art/n,{'synthetic':True})
atomic_json(art/'opening-freeze.json',seal)
atomic_json(art/'runtime-identity.json',{'context_runtime_identity':plan['runtime_identity'],'models':ready.MODELS,'native_source_anchor':ready.NATIVE_SOURCE_ANCHOR})
atomic_json(art/'study-report.json',{'games':56,'pairs':28,'timed_pairs':24,'deterministic_pairs':4,'projected_main_work_seconds':{'LOCAL':100,'WDL':100},'trajectory_canonicals':[r['canonical'] for r in seal['representative']]})
with gzip.open(art/'stage-games.json.gz','wb') as f:f.write(b'{"synthetic":true}')
atomic_json(art/'manifest.json',{'output_sha256':{n:hashlib.sha256((art/n).read_bytes()).hexdigest() for n in names if n!='manifest.json'}})
"""
REGRESSIONS = r"""
import argparse,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--profile');p.add_argument('--out');a=p.parse_args()
profile=json.loads(pathlib.Path(a.profile).read_text())
pathlib.Path(a.out).write_text(json.dumps(dict(schema='jass.launch_regressions.v2',suites=profile['regressions'],tests=1,errors=0,failures=0,skipped=0,passed=True)))
"""


def git_init(path):
    for args in (['init','-q'],['config','user.email','synthetic@example.invalid'],['config','user.name','Synthetic'],['add','.'],['commit','-qm','synthetic fixture']):
        subprocess.run(['git','-C',str(path),*args],check=True,capture_output=True)
    return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()


def publisher_objects(art, result, pointer, code):
    objects={'artefacts/'+p.name:p.read_bytes() for p in art.iterdir() if p.is_file()}
    objects['stage-receipt.json']=(result/'stage-receipt.json').read_bytes()
    objects['manifest.json']=gate.canonical(dict(pointer,code_sha=code,host='cpx62',state='completed',exit_code=0))
    objects['inventory.json']=gate.canonical({'files':[{'path':n,'sha256':__import__('hashlib').sha256(raw).hexdigest(),'size_bytes':len(raw)} for n,raw in objects.items()]})
    objects['checksums.sha256']=''.join(__import__('hashlib').sha256(raw).hexdigest()+'  '+n+'\n' for n,raw in objects.items()).encode()
    objects['_SUCCESS']=b'ok'
    return objects


class PanelPipelineTests(unittest.TestCase):
    def test_gate_core_transport_and_corrupt_payload_refusal(self):
        real_run=subprocess.run; real_popen=subprocess.Popen
        def run(argv,*args,**kwargs):
            if isinstance(argv,list) and argv[0]=='/usr/bin/python3':argv=[sys.executable,*argv[1:]]
            return real_run(argv,*args,**kwargs)
        def popen(argv,*args,**kwargs):
            if isinstance(argv,list) and argv[0]=='/usr/bin/python3':argv=[sys.executable,*argv[1:]]
            return real_popen(argv,*args,**kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';control=root/'control';result=root/'result';art=root/'art'
            (repo/'jobs/tools').mkdir(parents=True);(repo/'jobs/launch_profiles').mkdir();(control/'specs').mkdir(parents=True)
            (repo/'.gitignore').write_text('__pycache__/\n')
            (control/'README').write_text('synthetic control fixture')
            for name in ('cls_g0_panel_readiness.py','launch_runtime_v2.py'):
                shutil.copyfile(gate.ROOT/'jobs/tools'/name,repo/'jobs/tools'/name)
            (repo/'jobs/tools/cls_g0_panel_stage.py').write_text(SYNTHETIC_STAGE)
            (repo/'jobs/tools/launch_regressions_v2.py').write_text(REGRESSIONS)
            profile_path=repo/'jobs/launch_profiles/cls-g0-panel-v1.json'
            shutil.copyfile(gate.ROOT/'jobs/launch_profiles/cls-g0-panel-v1.json',profile_path)
            code=git_init(repo);git_init(control)
            profile=json.loads(profile_path.read_text());plan=gate.build_plan(code,gate.sha(profile_path))
            plan_path=control/'specs/plan.json';plan_path.write_bytes(gate.canonical(plan))
            spec=gate.build_stage_spec(plan,'readiness');sp=control/'specs/spec.json';sp.write_bytes(gate.canonical(spec))
            pointer={'job_id':'cpx62-synthetic-readiness','attempt_id':'synthetic-attempt-1'}
            adm={'schema':gate.SCHEMA,'job_id':pointer['job_id'],'phase':'readiness','common_plan':'specs/plan.json','profile':'jobs/launch_profiles/cls-g0-panel-v1.json',
                'common_plan_sha256':gate.digest(plan),'profile_sha256':gate.sha(profile_path),'spec_sha256':gate.sha(sp),
                'materialized_spec_sha256':gate.digest(gate.materialize(plan,'readiness',{})),'authenticated_audit_2072':plan['audit_2072']}
            ap=control/'specs/test.admission.json';ap.write_bytes(gate.canonical(adm))
            args=SimpleNamespace(admission=ap,admission_sha256=gate.sha(ap),repo_root=repo,spec=sp,result_dir=result,artifact_dir=art)
            env={'JASS_CONTROL_REPO_DIR':str(control),'EXPECTED_LAUNCH_TIMEOUT_SECONDS':'2400','JASS_JOB_ID':pointer['job_id'],'JASS_ATTEMPT_ID':pointer['attempt_id'],'PYTHONDONTWRITEBYTECODE':'1'}
            with mock.patch.dict(os.environ,env),mock.patch.object(subprocess,'run',side_effect=run),mock.patch.object(subprocess,'Popen',side_effect=popen),mock.patch.object(core,'validate_resources',return_value={'hostname':'cpx62','nproc':16}),mock.patch.object(v2,'runtime_identity',return_value={'synthetic-runtime':True}):
                self.assertEqual(gate.execute(args),0)
                self.assertEqual(json.loads((result/'stage-receipt.json').read_text())['state'],'completed')
                objects=publisher_objects(art,result,pointer,code);prefix=f"r2:jass-data/runs/{pointer['job_id']}/{pointer['attempt_id']}"
                def rclone(argv,*a,**kw):
                    if argv[:2]==['rclone','cat']:
                        return SimpleNamespace(returncode=0,stdout=objects[argv[2][len(prefix)+1:]],stderr=b'')
                    if argv[:2]==['rclone','copyto']:
                        Path(argv[3]).write_bytes(objects[argv[2][len(prefix)+1:]])
                        return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
                    return run(argv,*a,**kw)
                with mock.patch.object(subprocess,'run',side_effect=rclone):
                    typed=gate.readiness_from_r2(pointer,plan,profile,root/'roundtrip')
                    self.assertEqual(typed['publisher_manifest_sha256'],__import__('hashlib').sha256(objects['manifest.json']).hexdigest())
                    objects['artefacts/study-report.json']=b'{"tampered":true}'
                    with self.assertRaisesRegex(RuntimeError,'download verification failed'):
                        gate.readiness_from_r2(pointer,plan,profile,root/'tampered')

if __name__=='__main__':unittest.main()
