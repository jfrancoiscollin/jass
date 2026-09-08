"""Actual generic runner -> full synthetic audit -> publisher -> authenticated fetch.

Only the network transport is a local fake rclone. The real target-host rehearsal
must separately exercise the actual R2 backend before production is admissible.
"""
from __future__ import annotations
import copy
import json
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
from jobs.tools.launch_runtime_v2 import atomic_json, EFFECTS
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'infra'))
from runner_v3_store import prepare_run_dir, FilesystemResultStore


class ActualStageRoundtripTests(unittest.TestCase):
    def test_actual_stage_publication_fetch_and_fail_closed_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);repo=root/'repo';repo.mkdir();run=root/'run';art=run/'artefacts';art.mkdir(parents=True)
            program=("import sys,os\nfrom pathlib import Path\nsys.path.insert(0,"+repr(str(ROOT))+ ")\n"
                     "from jobs.tests.test_ed3_label_pressure import fixture_run\n"
                     "fixture_run(Path(os.environ['JASS_RESULT_DIR']),Path(os.environ['JASS_ARTEFACT_DIR']))\n")
            (repo/'fixture.py').write_text(program)
            for cmd in (['git','init','-q'],['git','config','user.email','fixture@example.invalid'],
                        ['git','config','user.name','Fixture'],['git','add','.'],['git','commit','-qm','fixture']):
                subprocess.run(cmd,cwd=repo,check=True)
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
            profile=dict(schema='jass.launch_profile.v2',campaign='fixture',stage='audit',
                         command=[sys.executable,'fixture.py'],regressions=['jobs.tests.test_launch_gate_v2'],
                         required_phases=['authenticate','load-train-and-replay','measure','publish'],
                         evidence_outputs=['ed3-label-pressure.json'],rehearsal_max_effects={k:0 for k in EFFECTS})
            spec=dict(schema='jass.stage_spec.v1',code_sha=head,campaign='fixture',stage='audit',
                      command=profile['command'],working_directory='.',inputs=[],
                      outputs=[dict(scope='artifact',path=p,required=True,nonempty=True,kind='file')
                               for p in ('ed3-label-pressure.json','scientific-summary.json','execution-evidence.json')],
                      resources=dict(hostname=None,nproc=None,clean_worktree=True),
                      timeouts=dict(stage_seconds=60,terminate_grace_seconds=1),
                      artifact_directory_contract='empty_or_runner_launch',
                      environment={'inherit':[],'set':{'LAUNCH_MODE':'rehearsal','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}},
                      scientific_side_effects=dict(fits=0,strength_games=0,promotions=0,bakes=0),
                      success=dict(required_exit_code=0,next_stage=None))
            sp=root/'stage.json';atomic_json(sp,spec)
            job='cpx62-fixture-rehearsal';attempt='20260908T000000Z-'+head[:8]
            with patch.dict(os.environ,{'JASS_JOB_ID':job,'JASS_ATTEMPT_ID':attempt}):
                rc,receipt=core.run_stage(spec_path=sp,repo_root=repo,result_dir=run,artifact_dir=art)
            self.assertEqual(rc,0,receipt)
            self.assertEqual(regress.run(profile['regressions'],art/'launch-regressions.json'),0)
            evidence=g.read(art/'execution-evidence.json');g.validate_evidence(evidence,profile,'rehearsal')
            hashes={p:g.sha(art/p) for p in ['execution-evidence.json','launch-regressions.json']+profile['evidence_outputs']}
            runtime={'host':'fixture-host','nproc':1}
            proof=dict(schema='jass.launch_receipt.v2',mode='rehearsal',verdict='REHEARSAL_EXECUTION_COMPLETE_V2',
                       code_sha=head,common_spec_sha256=g.common_spec(spec),spec_sha256=g.sha(sp),
                       profile_sha256=g.digest(profile),runtime=runtime,output_sha256=hashes,job_id=job,attempt_id=attempt)
            atomic_json(art/'launch-receipt.json',proof)
            manifest=dict(job_id=job,attempt_id=attempt,code_sha=head,host='fixture-host',state='completed',exit_code=0)
            prepare_run_dir(run,manifest,100000)
            store=root/'store';FilesystemResultStore(store).publish(run,job,attempt,True)
            # These are the actual publisher bytes, not a fabricated receipt.
            fake=root/'bin';fake.mkdir();rcpath=fake/'rclone'
            rcpath.write_text('#!'+sys.executable+'\n'+
                'import sys,os,shutil\nfrom pathlib import Path\n'+
                'def local(x):\n return Path(os.environ["FIXTURE_STORE"])/x.split("r2:jass-data/runs/",1)[1]\n'+
                'a=sys.argv[1:]\n'+
                'if a[0]=="cat":sys.stdout.buffer.write(local(a[1]).read_bytes())\n'+
                'elif a[0]=="copyto":shutil.copyfile(local(a[1]),a[2])\n'+
                'else:raise SystemExit(2)\n')
            rcpath.chmod(0o755)
            admission={'rehearsal':dict(job_id=job,attempt_id=attempt,receipt_sha256=g.sha(art/'launch-receipt.json'))}
            production=copy.deepcopy(spec);production['environment']['set']['LAUNCH_MODE']='production'
            # Runtime host matching also appears in the published outer manifest.
            production['resources']['hostname']='fixture-host'
            # Preserve normalized identity while setting a concrete host for this
            # fixture: reissue proof with the same stage's normalized host contract.
            # The production gate must not accept such a mutation.
            with patch.dict(os.environ,{'PATH':str(fake)+os.pathsep+os.environ['PATH'],'FIXTURE_STORE':str(store)}):
                with self.assertRaisesRegex(g.GateError,'STALE_REHEARSAL_SPEC'):
                    g.authenticate_published(admission,production,profile,runtime,root/'reject-change')
                production['resources']['hostname']=None
                # For the synthetic-only fixture host is None in the stage spec;
                # test direct proof matching after authenticated transport below.
                from jobs.tools.fetch_result_files import fetch_files
                dest=root/'download';verified=fetch_files(rclone='rclone',
                    prefix=f'r2:jass-data/runs/{job}/{attempt}',out_dir=dest,expected_state='completed',
                    selections=[('artefacts/'+p,p) for p in ['launch-receipt.json','execution-evidence.json','launch-regressions.json','ed3-label-pressure.json']]
                               +[('stage-receipt.json','stage-receipt.json')])
                self.assertEqual(verified['code_sha'],head)
                downloaded_hashes={p:g.sha(dest/p) for p in hashes}
                g.validate_proof(g.read(dest/'launch-receipt.json'),g.read(dest/'stage-receipt.json'),
                                 g.read(dest/'execution-evidence.json'),g.read(dest/'launch-regressions.json'),
                                 profile,production,runtime,downloaded_hashes)
                (store/job/attempt/'_SUCCESS').unlink()
                with self.assertRaises(Exception):
                    fetch_files(rclone='rclone',prefix=f'r2:jass-data/runs/{job}/{attempt}',out_dir=root/'bad',
                                selections=[('artefacts/launch-receipt.json','receipt.json')],expected_state='completed')

if __name__=='__main__':unittest.main()
