"""The actual generic runner and original result publisher carry a fitted model."""
from __future__ import annotations
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from jobs.tools import launch_gate_v2 as g
from jobs.tools import launch_regressions_v2 as regress
from jobs.tools import run_experiment_stage as core
from jobs.tools.launch_runtime_v2 import atomic_json,EFFECTS
from jobs.tools.ed4_choice_value_fit import PHASES,OUTPUTS
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'infra'))
from runner_v3_store import prepare_run_dir,FilesystemResultStore


class FittedModelPublicationTests(unittest.TestCase):
    def test_actual_fit_stage_publisher_and_authenticated_model_readback(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'repo';repo.mkdir();run=root/'run';art=run/'artefacts';art.mkdir(parents=True)
            (repo/'fixture.py').write_text('import os,sys\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(ROOT))+')\n'
                'from jobs.tests.test_ed4_choice_value_fit import fixture_run\n'
                'fixture_run(Path(os.environ["JASS_RESULT_DIR"]),Path(os.environ["JASS_ARTEFACT_DIR"]))\n')
            for cmd in (['git','init','-q'],['git','config','user.email','fixture@example.invalid'],
                        ['git','config','user.name','Fixture'],['git','add','.'],['git','commit','-qm','fixture']):
                subprocess.run(cmd,cwd=repo,check=True)
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
            effects={k:int(k=='fits') for k in EFFECTS}
            profile=dict(schema='jass.launch_profile.v2',campaign='fixture',stage='fit',
                command=[sys.executable,'fixture.py'],regressions=['jobs.tests.test_launch_gate_v2'],
                required_phases=PHASES,evidence_outputs=OUTPUTS,rehearsal_max_effects=effects)
            spec=dict(schema='jass.stage_spec.v1',code_sha=head,campaign='fixture',stage='fit',
                command=profile['command'],working_directory='.',inputs=[],
                outputs=[dict(scope='artifact',path=p,required=True,nonempty=True,kind='file')
                         for p in OUTPUTS+['execution-evidence.json','scientific-summary.json']],
                resources=dict(hostname=None,nproc=None,clean_worktree=True),
                timeouts=dict(stage_seconds=120,terminate_grace_seconds=1),
                artifact_directory_contract='empty_or_runner_launch',
                environment=dict(inherit=[],set={'LAUNCH_MODE':'rehearsal','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}),
                scientific_side_effects=dict(fits=1,strength_games=0,promotions=0,bakes=0),
                success=dict(required_exit_code=0,next_stage=None))
            sp=root/'spec.json';atomic_json(sp,spec)
            job='cpx62-ed4-choice-fixture';attempt='20260908T000000Z-'+head[:8]
            with patch.dict(os.environ,{'JASS_JOB_ID':job,'JASS_ATTEMPT_ID':attempt}):
                rc,receipt=core.run_stage(spec_path=sp,repo_root=repo,result_dir=run,artifact_dir=art)
            self.assertEqual(rc,0,receipt)
            self.assertEqual(regress.run(profile['regressions'],art/'launch-regressions.json'),0)
            evidence=g.read(art/'execution-evidence.json');g.validate_evidence(evidence,profile,'rehearsal')
            hashes={p:g.sha(art/p) for p in ['execution-evidence.json','launch-regressions.json']+OUTPUTS}
            proof=dict(schema='jass.launch_receipt.v2',mode='rehearsal',verdict='REHEARSAL_EXECUTION_COMPLETE_V2',
                code_sha=head,common_spec_sha256=g.common_spec(spec),spec_sha256=receipt['spec_sha256'],
                profile_sha256=g.digest(profile),runtime={'fixture':True},output_sha256=hashes,job_id=job,attempt_id=attempt)
            atomic_json(art/'launch-receipt.json',proof)
            prepare_run_dir(run,dict(job_id=job,attempt_id=attempt,code_sha=head,host='fixture',state='completed',exit_code=0),100000)
            store=root/'store';FilesystemResultStore(store).publish(run,job,attempt,True)
            fake=root/'rclone'
            fake.write_text('#!'+sys.executable+'\nimport sys,os,shutil\nfrom pathlib import Path\n'
                'def local(x):return Path(os.environ["FIXTURE_STORE"])/x.split("r2:jass-data/runs/",1)[1]\n'
                'a=sys.argv[1:]\nif a[0]=="cat":sys.stdout.buffer.write(local(a[1]).read_bytes())\n'
                'elif a[0]=="copyto":shutil.copyfile(local(a[1]),a[2])\nelse:raise SystemExit(2)\n')
            fake.chmod(0o755)
            from jobs.tools.fetch_result_files import fetch_files
            with patch.dict(os.environ,{'FIXTURE_STORE':str(store)}):
                dest=root/'download'
                files=['launch-receipt.json','execution-evidence.json','launch-regressions.json']+OUTPUTS
                fetch_files(rclone=str(fake),prefix=f'r2:jass-data/runs/{job}/{attempt}',out_dir=dest,
                    selections=[('artefacts/'+p,p) for p in files]+[('stage-receipt.json','stage-receipt.json')])
                production=copy.deepcopy(spec);production['environment']['set']['LAUNCH_MODE']='production'
                downloaded={p:g.sha(dest/p) for p in hashes}
                g.validate_proof(g.read(dest/'launch-receipt.json'),g.read(dest/'stage-receipt.json'),
                    g.read(dest/'execution-evidence.json'),g.read(dest/'launch-regressions.json'),
                    profile,production,{'fixture':True},downloaded)
                self.assertEqual(g.read(dest/'candidate-seal.json')['model_sha256'],g.sha(dest/'ED4_CHOICE.pjtw'))
                with (store/job/attempt/'artefacts/ED4_CHOICE.pjtw').open('ab') as f:f.write(b'corrupt')
                with self.assertRaises(Exception):fetch_files(rclone=str(fake),prefix=f'r2:jass-data/runs/{job}/{attempt}',
                    out_dir=root/'bad',selections=[('artefacts/ED4_CHOICE.pjtw','ED4_CHOICE.pjtw')])
                (store/job/attempt/'_SUCCESS').unlink()
                with self.assertRaises(Exception):fetch_files(rclone=str(fake),prefix=f'r2:jass-data/runs/{job}/{attempt}',
                    out_dir=root/'missing',selections=[('artefacts/candidate-seal.json','seal.json')])

if __name__=='__main__':unittest.main()
