"""Real stage runner/publisher/fetcher on synthetic C0A metadata, no network."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from jobs.tools import launch_gate_v2 as gate
from jobs.tools import launch_regressions_v2 as regressions
from jobs.tools import run_experiment_stage as core
from jobs.tools import ed4_source_inventory_stage as stage
from jobs.tools.launch_runtime_v2 import atomic_json, available_cpus, EFFECTS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'infra'))
from runner_v3_store import prepare_run_dir, FilesystemResultStore


class InventoryPipelineTests(unittest.TestCase):
    def test_actual_runner_publisher_readback_and_invalid_rehearsal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); repo = root / 'repo'; repo.mkdir()
            run = root / 'run'; art = run / 'artefacts'; art.mkdir(parents=True)
            program = ('import sys,os\nfrom pathlib import Path\n'
                       'sys.path.insert(0,' + repr(str(ROOT)) + ')\n'
                       'from jobs.tests.test_ed4_source_inventory_stage import fixture_run\n'
                       'fixture_run(Path(os.environ["JASS_RESULT_DIR"]),'
                       'Path(os.environ["JASS_ARTEFACT_DIR"]),os.environ["LAUNCH_MODE"],unknown=True)\n')
            (repo / 'fixture.py').write_text(program)
            for command in (['git', 'init', '-q'], ['git', 'config', 'user.email', 'fixture@example.invalid'],
                            ['git', 'config', 'user.name', 'Fixture'], ['git', 'add', '.'],
                            ['git', 'commit', '-qm', 'synthetic C0A fixture']):
                subprocess.run(command, cwd=repo, check=True, timeout=30)
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
            # Non-recursive fixture profile. The real registered profile runs
            # both generic admission suites and every C0A suite, including this one.
            profile = dict(schema='jass.launch_profile.v2', campaign='fixture', stage='inventory',
                           command=[sys.executable, 'fixture.py'],
                           regressions=['jobs.tests.test_ed4_source_descriptor_inventory'],
                           required_phases=stage.PHASES, evidence_outputs=[stage.OUTPUT],
                           rehearsal_max_effects={k: 0 for k in EFFECTS},
                           production_max_effects={k: 0 for k in EFFECTS})
            spec = dict(schema='jass.stage_spec.v1', code_sha=head, campaign='fixture', stage='inventory',
                        command=profile['command'], working_directory='.', inputs=[],
                        outputs=[dict(scope='artifact', path=p, required=True, nonempty=True, kind='file')
                                 for p in (stage.OUTPUT, 'scientific-summary.json', 'execution-evidence.json')],
                        resources=dict(hostname=socket.gethostname(), nproc=available_cpus(), clean_worktree=True),
                        timeouts=dict(stage_seconds=60, terminate_grace_seconds=1),
                        artifact_directory_contract='empty_or_runner_launch',
                        environment={'inherit': [], 'set': {'LAUNCH_MODE': 'rehearsal',
                                     'OPENBLAS_NUM_THREADS': '1', 'PYTHONDONTWRITEBYTECODE': '1'}},
                        scientific_side_effects=dict(fits=0, strength_games=0, promotions=0, bakes=0),
                        success=dict(required_exit_code=0, next_stage=None))
            spec_path = root / 'stage.json'; atomic_json(spec_path, spec)
            job = 'cpx62-fixture-ed4-inventory-rehearsal'
            attempt = '20260909T000000Z-' + head[:8]
            with patch.dict(os.environ, {'JASS_JOB_ID': job, 'JASS_ATTEMPT_ID': attempt}):
                rc, receipt = core.run_stage(spec_path=spec_path, repo_root=repo,
                                             result_dir=run, artifact_dir=art)
            self.assertEqual(rc, 0, receipt)
            self.assertEqual(gate.read(art / stage.OUTPUT)['verdict'],
                             'ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1')
            self.assertEqual(regressions.run(profile['regressions'], art / 'launch-regressions.json'), 0)
            gate.validate_evidence(gate.read(art / 'execution-evidence.json'), profile, 'rehearsal')
            runtime = gate.runtime_identity(sys.executable)
            hashes = {p: gate.sha(art / p) for p in
                      ['execution-evidence.json', 'launch-regressions.json'] + profile['evidence_outputs']}
            proof = dict(schema='jass.launch_receipt.v2', mode='rehearsal',
                         verdict='REHEARSAL_EXECUTION_COMPLETE_V2', code_sha=head,
                         common_spec_sha256=gate.common_spec(spec), spec_sha256=receipt['spec_sha256'],
                         spec_file_sha256=gate.sha(spec_path), profile_sha256=gate.digest(profile),
                         runtime=runtime, output_sha256=hashes, job_id=job, attempt_id=attempt)
            atomic_json(art / 'launch-receipt.json', proof)
            manifest = dict(job_id=job, attempt_id=attempt, code_sha=head,
                            host=socket.gethostname(), state='completed', exit_code=0)
            prepare_run_dir(run, manifest, 100000)
            store = root / 'store'; FilesystemResultStore(store).publish(run, job, attempt, True)
            fake = root / 'bin'; fake.mkdir(); rclone = fake / 'rclone'
            rclone.write_text('#!' + sys.executable + '\nimport sys,os,shutil\nfrom pathlib import Path\n'
                              'def local(x):\n return Path(os.environ["FIXTURE_STORE"])/x.split("r2:jass-data/runs/",1)[1]\n'
                              'a=sys.argv[1:]\n'
                              'if a[0]=="cat":sys.stdout.buffer.write(local(a[1]).read_bytes())\n'
                              'elif a[0]=="copyto":shutil.copyfile(local(a[1]),a[2])\n'
                              'else:raise SystemExit(2)\n')
            rclone.chmod(0o755)
            admission = {'rehearsal': dict(job_id=job, attempt_id=attempt,
                                          receipt_sha256=gate.sha(art / 'launch-receipt.json'))}
            production = copy.deepcopy(spec); production['environment']['set']['LAUNCH_MODE'] = 'production'
            with patch.dict(os.environ, {'PATH': str(fake) + os.pathsep + os.environ['PATH'],
                                         'FIXTURE_STORE': str(store)}):
                gate.authenticate_published(admission, production, profile, runtime, root / 'accepted')
                readback = gate.read(root / 'accepted' / 'launch-prerequisite.json')
                self.assertEqual(readback['verdict'], 'FULL_PIPELINE_REHEARSAL_PASS')
                self.assertIs(readback['published_roundtrip'], True)
                downloaded = root / 'accepted' / 'launch-prerequisite' / stage.OUTPUT
                self.assertEqual(downloaded.read_bytes(), (art / stage.OUTPUT).read_bytes())
                # This proves publication mechanics only: the source universe is
                # still INSUFFICIENT and confirmation remains unauthorized.
                self.assertEqual(gate.read(downloaded)['verdict'],
                                 'ED4_C0A_INVENTORY_ADMISSION_INSUFFICIENT_V1')
                changed = copy.deepcopy(production); changed['timeouts']['stage_seconds'] += 1
                with self.assertRaisesRegex(gate.GateError, 'STALE_REHEARSAL_SPEC'):
                    gate.authenticate_published(admission, changed, profile, runtime, root / 'stale')
                (store / job / attempt / '_SUCCESS').unlink()
                with self.assertRaises(Exception):
                    gate.authenticate_published(admission, production, profile, runtime, root / 'missing-marker')


if __name__ == '__main__':
    unittest.main()
