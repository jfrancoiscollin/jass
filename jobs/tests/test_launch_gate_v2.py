from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from jobs.tools import launch_gate_v2 as g
from jobs.tools.launch_runtime_v2 import EFFECTS, StageEvidence, available_cpus


class LaunchGateTests(unittest.TestCase):
    def fixture(self):
        profile = dict(schema='jass.launch_profile.v2', campaign='audit', stage='readout',
                       command=['/python', 'jobs/tools/audit.py'],
                       regressions=['jobs.tests.test_launch_gate_v2', 'jobs.tests.test_launch_gate_pipeline_v2'],
                       required_phases=['fetch', 'compute', 'publish'],
                       evidence_outputs=['readout.json'],
                       rehearsal_max_effects={k: 0 for k in EFFECTS}, production_max_effects={k: 0 for k in EFFECTS})
        spec = dict(code_sha='a'*40, campaign='audit', stage='readout', command=profile['command'],
                    environment={'inherit': [], 'set': {'LAUNCH_MODE': 'production'}},
                    resources={'hostname': 'cpx62', 'nproc': 16, 'clean_worktree': True},
                    outputs=[dict(path=p, required=True, nonempty=True, scope='artifact')
                             for p in ('readout.json', 'execution-evidence.json', 'scientific-summary.json')],
                    inputs=[], timeouts={'stage_seconds': 600}, scientific_side_effects={'fits': 0})
        admission = dict(schema='jass.launch_admission.v2', job_id='cpx62-production',
                         profile='jobs/launch_profiles/test.json', profile_sha256='b'*64,
                         spec_sha256='c'*64,
                         rehearsal={'job_id': 'cpx62-rehearsal', 'attempt_id': 'attempt-1', 'receipt_sha256': 'd'*64})
        ev = dict(schema='jass.execution_evidence.v2', state='completed', mode='rehearsal',
                  completed_phases=profile['required_phases'], actual_side_effects={k:0 for k in EFFECTS})
        reg = dict(passed=True, tests=12, skipped=0, failures=0, errors=0, suites=profile['regressions'])
        receipt = dict(state='completed', exit_code=0, outputs_authenticated=True, code_sha='a'*40, spec_sha256='e'*64)
        runtime = dict(host='cpx62', nproc=16, version='fixed')
        hashes = {'readout.json': 'f'*64}
        proof = dict(schema='jass.launch_receipt.v2', mode='rehearsal', verdict='REHEARSAL_EXECUTION_COMPLETE_V2',
                     code_sha='a'*40, common_spec_sha256=g.common_spec(spec), profile_sha256=g.digest(profile),
                     runtime=runtime, output_sha256=hashes, spec_sha256='e'*64)
        return profile, spec, admission, ev, reg, receipt, runtime, hashes, proof

    def test_valid_admission_and_proof(self):
        p,s,a,e,r,c,v,h,f = self.fixture()
        self.assertEqual(g.validate_contract(s,a,p,'c'*64,'b'*64,'cpx62-production'),'production')
        g.validate_proof(f,c,e,r,p,s,v,h)

    def test_no_proof_blocks_before_execution(self):
        p,s,a,*_ = self.fixture(); a['rehearsal']=None
        with self.assertRaisesRegex(g.GateError,'REHEARSAL_REQUIRED'):
            g.validate_contract(s,a,p,'c'*64,'b'*64,'cpx62-production')

    def test_only_launch_mode_can_differ(self):
        _,s,*_ = self.fixture(); t=copy.deepcopy(s);t['environment']['set']['LAUNCH_MODE']='rehearsal'
        self.assertEqual(g.common_spec(s),g.common_spec(t))
        for key,value in [('inputs',[{'sha256':'changed'}]),('timeouts',{'stage_seconds':1}),('code_sha','b'*40)]:
            t=copy.deepcopy(s);t[key]=value
            self.assertNotEqual(g.common_spec(s),g.common_spec(t))

    def test_changed_code_profile_runtime_or_spec_rejected(self):
        for field in ('code_sha','common_spec_sha256','profile_sha256','runtime'):
            with self.subTest(field=field):
                p,s,a,e,r,c,v,h,f=self.fixture();f[field]='changed'
                with self.assertRaises(g.GateError): g.validate_proof(f,c,e,r,p,s,v,h)

    def test_unpublished_failed_or_incomplete_stage_not_proof(self):
        for field,value in [('state','failed'),('exit_code',2),('outputs_authenticated',False)]:
            p,s,a,e,r,c,v,h,f=self.fixture();c[field]=value
            with self.assertRaisesRegex(g.GateError,'STAGE_RECEIPT_FAILED'):g.validate_proof(f,c,e,r,p,s,v,h)

    def test_skipped_empty_missing_or_failed_regressions_rejected(self):
        for field,value in [('skipped',1),('tests',0),('suites',[]),('passed',False),('errors',1)]:
            p,s,a,e,r,c,v,h,f=self.fixture();r[field]=value
            with self.assertRaisesRegex(g.GateError,'REGRESSIONS_NOT_PROVEN'):g.validate_proof(f,c,e,r,p,s,v,h)

    def test_phase_missing_and_nonzero_rehearsal_science_rejected(self):
        p,s,a,e,r,c,v,h,f=self.fixture(); e['completed_phases']=['fetch']
        with self.assertRaisesRegex(g.GateError,'INCOMPLETE_PIPELINE'):g.validate_proof(f,c,e,r,p,s,v,h)
        p,s,a,e,r,c,v,h,f=self.fixture();e['actual_side_effects']['fits']=1
        with self.assertRaisesRegex(g.GateError,'REHEARSAL_SPENT_SCIENCE'):g.validate_proof(f,c,e,r,p,s,v,h)

    def test_replayed_artifact_hash_mismatch_rejected(self):
        p,s,a,e,r,c,v,h,f=self.fixture()
        with self.assertRaisesRegex(g.GateError,'PUBLISHED_OUTPUT_ROUNDTRIP'):g.validate_proof(f,c,e,r,p,s,v,{})

    def test_cpu_guard_ignores_openmp_only_in_probe(self):
        with patch.dict(os.environ,{'OMP_NUM_THREADS':'1','OMP_THREAD_LIMIT':'1','KEEP':'yes'}):
            with patch('subprocess.check_output',return_value='16\n') as run:
                self.assertEqual(available_cpus(),16)
            env=run.call_args.kwargs['env'];self.assertNotIn('OMP_NUM_THREADS',env);self.assertNotIn('OMP_THREAD_LIMIT',env)
            self.assertEqual(env['KEEP'],'yes');self.assertEqual(os.environ['OMP_NUM_THREADS'],'1')

    def test_failure_has_phase_and_source_without_secret_text(self):
        with tempfile.TemporaryDirectory() as d:
            e=StageEvidence(Path(d),'production');e.begin('optimizer')
            try:raise ValueError('secret_password=never_publish')
            except ValueError as ex:e.fail(ex)
            raw=(Path(d)/'execution-evidence.json').read_text();v=json.loads(raw)
            self.assertNotIn('secret_password',raw);self.assertEqual(v['phase'],'optimizer')
            self.assertEqual(v['state'],'failed');self.assertEqual(v['error_type'],'ValueError');self.assertTrue(v['frames'])

    def test_profile_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for path in ('/tmp/profile.json','jobs/launch_profiles/../../x.json','elsewhere/profile.json'):
                with self.assertRaises(g.GateError):g.profile_path(Path(d),path)

    def test_nonmatching_entrypoint_and_job_rejected(self):
        p,s,a,*_=self.fixture();s['command']=['/bin/sh','-c','bypass']
        with self.assertRaisesRegex(g.GateError,'ENTRYPOINT_IDENTITY'):g.validate_contract(s,a,p,'c'*64,'b'*64,'cpx62-production')
        p,s,a,*_=self.fixture()
        with self.assertRaisesRegex(g.GateError,'JOB_IDENTITY'):g.validate_contract(s,a,p,'c'*64,'b'*64,'cpx62-other')

if __name__=='__main__':unittest.main()
