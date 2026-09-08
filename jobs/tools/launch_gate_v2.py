#!/usr/bin/env python3
"""Fail-closed admission around the unchanged v1 stage runner.

A production stage re-reads an authenticated, successfully published rehearsal
from R2. Its code, normalized spec, profile, runtime, regressions and outputs must
match. This guards engineering mistakes, not a malicious repository administrator.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools.launch_runtime_v2 import EFFECTS, atomic_json, now

HEX40 = re.compile(r'^[0-9a-f]{40}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{1,180}$')
MODE_KEY = 'LAUNCH_MODE'


class GateError(RuntimeError):
    pass


def need(ok, code):
    if not ok:
        raise GateError(code)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def read(path):
    need(path.is_file() and not path.is_symlink(), 'FILE_MISSING_OR_SYMLINK')
    need(path.stat().st_size < 2_000_000, 'JSON_TOO_LARGE')
    return json.loads(path.read_text())


def common_spec(spec):
    result = copy.deepcopy(spec)
    mode = result['environment']['set'].pop(MODE_KEY, None)
    need(mode in ('rehearsal', 'production'), 'MODE_REQUIRED')
    # This is the only permitted spec difference. Changes to command, data,
    # budget, code, resources or outputs invalidate every previous rehearsal.
    return digest(result)


def profile_path(repo, rel):
    need(isinstance(rel, str), 'PROFILE_PATH')
    p = Path(rel)
    need(p.parts[:2] == ('jobs', 'launch_profiles') and '..' not in p.parts
         and not p.is_absolute() and p.suffix == '.json', 'PROFILE_PATH')
    resolved = (repo / p).resolve(strict=True)
    need(resolved.is_relative_to(repo.resolve()) and not (repo / p).is_symlink(), 'PROFILE_PATH')
    return resolved


def validate_contract(spec, admission, profile, actual_spec_sha, actual_profile_sha, job):
    need(set(admission) == {'schema', 'job_id', 'profile', 'profile_sha256', 'spec_sha256', 'rehearsal'},
         'ADMISSION_FIELDS')
    need(admission['schema'] == 'jass.launch_admission.v2', 'ADMISSION_SCHEMA')
    need(admission['job_id'] == job and bool(ID.fullmatch(job)), 'JOB_IDENTITY')
    need(admission['spec_sha256'] == actual_spec_sha, 'SPEC_IDENTITY')
    need(admission['profile_sha256'] == actual_profile_sha, 'PROFILE_IDENTITY')
    need(profile['schema'] == 'jass.launch_profile.v2', 'PROFILE_SCHEMA')
    need(spec['campaign'] == profile['campaign'] and spec['stage'] == profile['stage'], 'STAGE_IDENTITY')
    need(spec['command'] == profile['command'], 'ENTRYPOINT_IDENTITY')
    need(bool(HEX40.fullmatch(spec['code_sha'])), 'CODE_IDENTITY')
    need(spec['resources']['hostname'] is not None and spec['resources']['nproc'] is not None,
         'TARGET_HOST_REQUIRED')
    need(spec['resources']['clean_worktree'] is True, 'CLEAN_WORKTREE_REQUIRED')
    need(profile['regressions'] and all(n in profile['regressions'] for n in
         ('jobs.tests.test_launch_gate_v2', 'jobs.tests.test_launch_gate_pipeline_v2')),
         'BASE_REGRESSIONS_REQUIRED')
    need(profile['required_phases'] and len(set(profile['required_phases'])) == len(profile['required_phases']),
         'PHASE_CONTRACT_REQUIRED')
    expected_outputs = set(profile['evidence_outputs']) | {'execution-evidence.json', 'scientific-summary.json'}
    declared = {x['path'] for x in spec['outputs'] if x['required'] and x['nonempty'] and x['scope'] == 'artifact'}
    need(expected_outputs <= declared, 'OUTPUT_CONTRACT_REQUIRED')
    for p in profile['evidence_outputs']:
        need(not Path(p).is_absolute() and '..' not in Path(p).parts, 'OUTPUT_PATH')
    for k in ('rehearsal_max_effects', 'production_max_effects'):
        need(set(profile[k]) == set(EFFECTS), 'EFFECTS_REQUIRED')
        need(all(type(v) is int and v >= 0 for v in profile[k].values()), 'EFFECTS_INVALID')
    mode = spec['environment']['set'].get(MODE_KEY)
    common_spec(spec)
    if mode == 'production':
        r = admission['rehearsal']
        need(isinstance(r, dict) and set(r) == {'job_id', 'attempt_id', 'receipt_sha256'}, 'REHEARSAL_REQUIRED')
        need(bool(ID.fullmatch(r['job_id'])) and bool(ID.fullmatch(r['attempt_id']))
             and bool(HEX64.fullmatch(r['receipt_sha256'])), 'REHEARSAL_IDENTITY')
        need(r['job_id'] != job, 'REHEARSAL_SELF_REFERENCE')
    else:
        need(admission['rehearsal'] is None, 'REHEARSAL_MODE_CONFLICT')
    return mode


def validate_evidence(evidence, profile, mode):
    need(evidence.get('schema') == 'jass.execution_evidence.v2'
         and evidence.get('state') == 'completed' and evidence.get('mode') == mode, 'EXECUTION_EVIDENCE')
    need(evidence.get('completed_phases') == profile['required_phases'], 'INCOMPLETE_PIPELINE')
    effects = evidence.get('actual_side_effects', {})
    need(set(effects) == set(EFFECTS) and all(type(x) is int and x >= 0 for x in effects.values()), 'EFFECT_COUNTERS')
    limits = profile[mode+'_max_effects']
    need(all(effects[k] <= limits[k] for k in EFFECTS), 'REHEARSAL_SPENT_SCIENCE' if mode == 'rehearsal' else 'PRODUCTION_BUDGET_EXCEEDED')


def validate_proof(proof, receipt, evidence, regressions, profile, spec, runtime, output_hashes):
    need(proof.get('schema') == 'jass.launch_receipt.v2' and proof.get('mode') == 'rehearsal'
         and proof.get('verdict') == 'REHEARSAL_EXECUTION_COMPLETE_V2', 'REHEARSAL_NOT_COMPLETE')
    need(proof.get('code_sha') == spec['code_sha'], 'STALE_REHEARSAL_CODE')
    need(proof.get('common_spec_sha256') == common_spec(spec), 'STALE_REHEARSAL_SPEC')
    need(proof.get('profile_sha256') == digest(profile), 'STALE_REHEARSAL_PROFILE')
    need(proof.get('runtime') == runtime, 'STALE_REHEARSAL_RUNTIME')
    need(receipt.get('state') == 'completed' and receipt.get('exit_code') == 0
         and receipt.get('outputs_authenticated') is True and receipt.get('code_sha') == spec['code_sha'],
         'STAGE_RECEIPT_FAILED')
    need(receipt.get('spec_sha256') == proof.get('spec_sha256'), 'STAGE_RECEIPT_IDENTITY')
    need(regressions.get('passed') is True and regressions.get('tests', 0) > 0
         and regressions.get('skipped') == 0 and regressions.get('failures') == 0
         and regressions.get('errors') == 0 and regressions.get('suites') == profile['regressions'], 'REGRESSIONS_NOT_PROVEN')
    need(proof.get('output_sha256') == output_hashes, 'PUBLISHED_OUTPUT_ROUNDTRIP')
    validate_evidence(evidence, profile, 'rehearsal')


def runtime_identity(python):
    from jobs.tools.launch_runtime_v2 import available_cpus
    import platform
    import socket
    # Same numerical interpreter and package versions on both admissions.
    code = ('import json,platform,importlib.metadata as m;'
            'print(json.dumps({"python":platform.python_version(),'
            '"packages":sorted((x.metadata["Name"],x.version) for x in m.distributions())},sort_keys=True))')
    caps = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    raw = subprocess.check_output([python, '-c', code], env=caps, timeout=20)
    return dict(host=socket.gethostname(), nproc=available_cpus(), machine=platform.machine(),
                libc=list(platform.libc_ver()), interpreter_sha256=sha(Path(python).resolve()),
                numeric_environment_sha256=hashlib.sha256(raw).hexdigest())


def authenticate_published(admission, spec, profile, runtime, result):
    from jobs.tools.fetch_result_files import fetch_files
    r = admission['rehearsal']
    root = result / 'launch-prerequisite'
    prefix = 'r2:jass-data/runs/' + r['job_id'] + '/' + r['attempt_id']
    names = ['launch-receipt.json', 'execution-evidence.json', 'launch-regressions.json'] + profile['evidence_outputs']
    selections = [('artefacts/' + x, x) for x in names] + [('stage-receipt.json', 'stage-receipt.json')]
    verified = fetch_files(rclone='rclone', prefix=prefix, selections=selections,
                           out_dir=root, expected_state='completed')
    need((verified['job_id'], verified['attempt_id'], verified['code_sha'], verified['result_state'], verified['exit_code'])
         == (r['job_id'], r['attempt_id'], spec['code_sha'], 'completed', 0), 'PUBLISHED_IDENTITY')
    need(verified.get('host') == spec['resources']['hostname'], 'PUBLISHED_HOST')
    need(sha(root/'launch-receipt.json') == r['receipt_sha256'], 'REHEARSAL_RECEIPT_HASH')
    proof = read(root/'launch-receipt.json')
    need(proof.get('job_id') == r['job_id'] and proof.get('attempt_id') == r['attempt_id'], 'RECEIPT_JOB_IDENTITY')
    hashes = {p: sha(root/p) for p in ['execution-evidence.json', 'launch-regressions.json'] + profile['evidence_outputs']}
    validate_proof(proof, read(root/'stage-receipt.json'), read(root/'execution-evidence.json'),
                   read(root/'launch-regressions.json'), profile, spec, runtime, hashes)
    atomic_json(result/'launch-prerequisite.json', dict(verdict='FULL_PIPELINE_REHEARSAL_PASS',
                published_roundtrip=True, source_job=r['job_id'], source_attempt=r['attempt_id'],
                receipt_sha256=r['receipt_sha256'], common_spec_sha256=common_spec(spec)))


def execute(args):
    spec = read(args.spec)
    admission = read(args.admission)
    repo = args.repo_root.resolve(strict=True)
    pp = profile_path(repo, admission['profile'])
    profile = read(pp)
    need(sha(args.admission) == args.admission_sha256, 'ADMISSION_HASH')
    need(subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() == spec['code_sha'], 'CHECKOUT_IDENTITY')
    need(not subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True).strip(), 'DIRTY_CHECKOUT')
    mode = validate_contract(spec, admission, profile, sha(args.spec), sha(pp), os.environ.get('JASS_JOB_ID', ''))
    runtime = runtime_identity(profile['command'][0])
    need(runtime['host'] == spec['resources']['hostname'] and runtime['nproc'] == spec['resources']['nproc'], 'HOST_MISMATCH')
    args.result_dir.mkdir(parents=True, exist_ok=True)
    # Transport / gate is bounded by the outer generic dispatcher timeout.
    if mode == 'production':
        authenticate_published(admission, spec, profile, runtime, args.result_dir)
    log = args.result_dir/'launch-regressions.log'
    report = args.result_dir/'launch-regressions.json'
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    with log.open('xb') as stream:
        cp = subprocess.run([profile['command'][0], str(repo/'jobs/tools/launch_regressions_v2.py'),
                             '--profile', str(pp), '--out', str(report)], cwd=repo, env=env,
                            stdout=stream, stderr=subprocess.STDOUT, timeout=180)
    need(cp.returncode == 0 and read(report).get('passed') is True, 'REGRESSION_SUITE_FAILED')
    # Do not prepopulate the artefact directory before the original runner's
    # ownership check. Admission evidence is kept in result/ until after run_stage.
    from jobs.tools import run_experiment_stage as core
    rc, receipt = core.run_stage(spec_path=args.spec, repo_root=repo,
                                result_dir=args.result_dir, artifact_dir=args.artifact_dir)
    import shutil
    shutil.copyfile(report, args.artifact_dir/'launch-regressions.json')
    if rc != 0:
        raise GateError('STAGE_FAILED:' + str(receipt.get('failure_stage', 'UNKNOWN')))
    evidence = read(args.artifact_dir/'execution-evidence.json')
    validate_evidence(evidence, profile, mode)
    output_hashes = {p: sha(args.artifact_dir/p) for p in ['execution-evidence.json', 'launch-regressions.json'] + profile['evidence_outputs']}
    proof = dict(schema='jass.launch_receipt.v2', mode=mode,
                 verdict='REHEARSAL_EXECUTION_COMPLETE_V2' if mode == 'rehearsal' else 'ADMITTED_STAGE_COMPLETE_V2',
                 code_sha=spec['code_sha'], common_spec_sha256=common_spec(spec), spec_sha256=sha(args.spec),
                 profile_sha256=digest(profile), runtime=runtime, output_sha256=output_hashes,
                 job_id=os.environ['JASS_JOB_ID'], attempt_id=os.environ['JASS_ATTEMPT_ID'])
    atomic_json(args.artifact_dir/'launch-receipt.json', proof)
    summary = read(args.artifact_dir/'scientific-summary.json')
    summary['launch'] = dict(mode=mode, receipt_sha256=sha(args.artifact_dir/'launch-receipt.json'),
                             common_spec_sha256=common_spec(spec), production_admitted=mode == 'production',
                             publisher_roundtrip_verified=mode == 'production')
    atomic_json(args.artifact_dir/'scientific-summary.json', summary)
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('spec', 'admission', 'repo-root', 'result-dir', 'artifact-dir'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--admission-sha256', required=True)
    a = p.parse_args()
    try:
        return execute(a)
    except Exception as exc:
        code = str(exc) if isinstance(exc, GateError) else type(exc).__name__
        value = dict(schema='jass.launch_failure.v2', classification='TECHNICAL',
                     state='failed', failure_code=code, scientific_verdict=None,
                     job_id=os.environ.get('JASS_JOB_ID'), attempt_id=os.environ.get('JASS_ATTEMPT_ID'),
                     snapshot_at=now(), next_stage=None)
        e = a.artifact_dir/'execution-evidence.json'
        if e.is_file() and not e.is_symlink():
            ev = read(e)
            value['last_phase'] = ev.get('phase')
            value['error_type'] = ev.get('error_type')
            value['frames'] = ev.get('frames', [])
        atomic_json(a.artifact_dir/'attempt-diagnostic.json', value)
        atomic_json(a.artifact_dir/'scientific-summary.json', value)
        print('LAUNCH_BLOCKED_OR_FAILED: '+code, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
