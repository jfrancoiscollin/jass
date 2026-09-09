"""ED4-P0 synthetic-only preflight. No real artifact/source input is accepted."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = 'docs/experiments/L3_ED4_CHOICE_SET_PREFLIGHT_V1_20260909.md'
RECORDS = 'jobs/tests/fixtures/ed4-choice-native-records-v1.json'
TERMINAL = 'ED4_CHOICE_SET_OBJECTIVE_PREFLIGHT_COMPLETE_V1'
SOURCES = [PROTOCOL, RECORDS, 'jobs/tools/ed4_choice_math.py',
           'jobs/tools/ed4_choice_fixtures.py', 'jobs/tools/ed4_choice_preflight.py',
           'jobs/tools/ed2_value_math.py', 'jobs/tools/ed2_value_probe.cpp']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def write(path, obj):
    tmp = path.with_suffix('.tmp')
    tmp.write_bytes(encoded(obj))
    tmp.replace(path)


def need(ok, code):
    if not ok:
        raise ValueError(code)


def environment():
    env = os.environ.copy()
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
                'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
        env[key] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def one_cpu():
    # The ordinary Linux CI receipt also proves process affinity, not just BLAS limits.
    if hasattr(os, 'sched_getaffinity'):
        cpu = min(os.sched_getaffinity(0))
        os.sched_setaffinity(0, {cpu})
        need(len(os.sched_getaffinity(0)) == 1, 'cpu_affinity')
        return {'single_cpu_affinity': True, 'cpu': cpu}
    raise RuntimeError('full_preflight_requires_single_cpu_affinity')


def numeric(out):
    import numpy as np
    import scipy
    from unittest.mock import patch
    from jobs.tools import ed4_choice_math as m
    from jobs.tools.ed4_choice_fixtures import fixture
    d, meta = fixture()
    beta = np.linspace(-.001, .001, 240)
    _, grad, hess = m.derivatives(beta, d)
    checks = []
    for coordinate in (0, 49, 100, 104, 120, 220, 239):
        delta = np.zeros(240); delta[coordinate] = 1e-7
        vp, gp, _ = m.derivatives(beta+delta, d)
        vm, gm, _ = m.derivatives(beta-delta, d)
        ge = abs((vp-vm)/2e-7-grad[coordinate])
        hf = (gp-gm)/2e-7
        need(ge <= 1e-6, 'finite_difference_gradient')
        need(np.allclose(hf, hess[:, coordinate], rtol=1e-5, atol=1e-5), 'finite_difference_hessian')
        checks.append({'coordinate': coordinate, 'gradient_absolute_error': float(ge),
                       'hessian_max_absolute_error': float(np.max(abs(hf-hess[:, coordinate])))})
    asym = float(np.max(abs(hess-hess.T)))
    need(asym <= 1e-10, 'hessian_asymmetry')
    x = np.zeros((3, 240)); x[:, 0] = [-10, 10, 0]
    groups = [{'id': 0, 'stm': 1, 'rows': [0, 1, 2], 'V': [0, 1, 2], 'A': [0, 1], 'edges': []}]
    groups += [{'id': i, 'stm': 0, 'rows': [], 'V': [], 'A': [], 'edges': []} for i in range(1, 512)]
    witness = m.design(x, np.zeros(3), groups, np.zeros((1, 240)), np.zeros(1), np.array([.5]))
    _, wg, wh = m.derivatives(np.zeros(240), witness)
    expected = -100/(3*512)+.001
    need(np.array_equal(wg, np.zeros(240)) and abs(wh[0, 0]-expected) <= 1e-12, 'negative_curvature_witness')
    class MockSuccess:
        success = True
        x = np.zeros(240)
        message = 'expected synthetic saddle rejection; no optimizer invocation'
    with patch.object(m, 'minimize', return_value=MockSuccess()):
        try:
            m.fit(witness)
        except m.NumericalFailure as exc:
            refusal = exc.report
        else:
            raise ValueError('saddle_wrongly_accepted')
    reports = []; vectors = []
    for invocation in (1, 2):
        write(out/'progress.json', {'synthetic_optimizer_invocations': invocation})
        try:
            fitted, report = m.fit(d)
        except m.NumericalFailure as exc:
            write(out/'numeric-failure.json', exc.report)
            raise
        reports.append(report); vectors.append(fitted)
    need(vectors[0].tobytes() == vectors[1].tobytes(), 'repeated_beta_drift')
    need(encoded(reports[0]) == encoded(reports[1]), 'repeated_solver_report_drift')
    fitted = vectors[0]
    qbeta = np.rint(fitted*1000)/1000
    qvalue = m.derivatives(qbeta, d)[0]
    initial = m.derivatives(np.zeros(240), d)[0]
    need(np.isfinite(qvalue) and qvalue <= initial+1e-12, 'quantized_objective')
    need(np.count_nonzero(qbeta) > 0, 'zero_quantized_residual')
    np.save(out/'beta.npy', fitted, allow_pickle=False)
    meta['arrays_sha256'] = {key: digest(np.asarray(d[key], dtype='<f8').tobytes())
                             for key in ('phi', 'z', 'replay_x', 'replay_z', 'y')}
    write(out/'numeric.json', {
        'fixture': meta, 'finite_differences': checks, 'hessian_asymmetry': asym,
        'negative_curvature_witness': {'expected_curvature': expected, 'refusal': refusal},
        'solver_reports': reports, 'beta_sha256': digest(fitted.astype('<f8').tobytes()),
        'quantized_beta_sha256': digest(qbeta.astype('<f8').tobytes()),
        'quantized_objective': qvalue, 'repeated_beta_and_reports_identical': True,
        'synthetic_optimizer_invocations': 2,
        'versions': {'python': sys.version.split()[0], 'numpy': np.__version__, 'scipy': scipy.__version__}})


def full_worker(out, probe):
    affinity = one_cpu()
    subprocess.run([sys.executable, '-m', 'jobs.tools.ed4_choice_preflight',
                    '--_numeric-worker', str(out)], cwd=ROOT, env=environment(),
                   timeout=60, check=True)
    import numpy as np
    from jobs.tools import ed2_value_math as old
    fixture = json.loads((ROOT/RECORDS).read_bytes())
    records = [bytes.fromhex(h) for h in fixture['records_hex']]
    need(len(records) == 16 and all(len(r) == 38 and r[33:] == bytes(5) for r in records), 'literal_record_contract')
    data = out/'development-only.jnnw'
    data.write_bytes(b'JNNW'+struct.pack('<I', 16)+b''.join(records))
    layout = subprocess.run([str(probe), '--layout'], check=True, capture_output=True, text=True, timeout=30)
    npat, nextra = map(int, layout.stdout.split())
    need(npat > 0 and nextra == 120, 'native_layout')
    base = out/'development-only-zero.pjtw'
    base.write_bytes(struct.pack('<5I', 0x57544a50, 3, 1000, npat, 120)+bytes(8*(npat+120)))
    beta = np.load(out/'beta.npy', allow_pickle=False)
    model = out/'development-only-residual.pjtw'
    serialization = old.quantize(base, beta, model)
    need(serialization['changed_extra_coefficients'] > 0, 'native_nonzero_residual')
    tie = np.zeros(240); tie[:4] = [.0005, .0015, -.0005, -.0015]
    tie_model = out/'development-only-ties.pjtw'
    old.quantize(base, tie, tie_model)
    need(np.array_equal(old.read_model(tie_model)[2][:4], [0, .002, 0, -.002]), 'ties_to_even')
    tables = []
    for index, candidate in enumerate((base, model, model)):
        table = out/f'native-{index}.tsv'
        subprocess.run([str(probe), str(data), str(candidate), str(table)], check=True, timeout=45)
        tables.append(old.native_table(table, 16))
    bx, bz, _ = tables[0]; qx, qz, qc = tables[1]; rx, rz, rc = tables[2]
    need(np.array_equal(bx, qx) and np.array_equal(qx, rx), 'native_feature_order')
    need(np.array_equal(qz, rz) and np.array_equal(qc, rc), 'native_reload_identity')
    _, _, weights = old.read_model(model)
    need(np.array_equal(weights, np.rint(beta*1000)/1000), 'native_quantization_identity')
    err = float(np.max(abs(qz-(bz+bx@weights))))
    need(err <= 1e-9 and np.any(qz != bz), 'native_logit_mapping_or_zero_effect')
    numeric_report = json.loads((out/'numeric.json').read_bytes())
    report = {
        'terminal': TERMINAL, 'classification': 'SYNTHETIC_TECHNICAL_ONLY',
        'next': 'REVIEW_AND_PREREGISTER_ED4_CANDIDATE',
        'automatic_continuation': False, 'runtime_authorized': False,
        'source_sha256': {p: digest((ROOT/p).read_bytes()) for p in SOURCES},
        'numeric': numeric_report,
        'native': {'probe_sha256': digest(probe.read_bytes()), 'records_sha256': digest(data.read_bytes()),
                   'rows': 16, 'layout': {'patterns': npat, 'extras': nextra},
                   'serialization': serialization, 'maximum_logit_error': err,
                   'exact_features_and_repeated_integer_scores': True, 'ties_to_even': True,
                   'baseline_reload_processes': 1, 'quantized_reload_processes': 2},
        'resource_contract': {**affinity, 'numeric_cap_seconds': 60, 'whole_cap_seconds': 300,
                              'numeric_library_threads': 1},
        'effect_ledger': {'synthetic_optimizer_invocations': 2, 'mocked_saddle_optimizer_invocations': 0,
                          'real_fits': 0, 'real_data_reads': 0, 'real_model_reads': 0,
                          'real_candidates': 0, 'searches': 0, 'games': 0, 'promotions': 0,
                          'bakes': 0, 'control_queue_mutations': 0},
        'STOP_ED3': True, 'champion': 'CURRICULUM'}
    write(out/'worker-report.json', report)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out-dir', type=Path)
    ap.add_argument('--native-probe', type=Path)
    ap.add_argument('--_numeric-worker', type=Path, help=argparse.SUPPRESS)
    ap.add_argument('--_full-worker', type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    os.environ.update(environment())
    if args._numeric_worker:
        numeric(args._numeric_worker); return 0
    if args._full_worker:
        full_worker(args._full_worker, args.native_probe); return 0
    need(args.out_dir is not None and args.native_probe is not None, 'out_dir_and_native_probe_required')
    out = args.out_dir.resolve(); out.mkdir(parents=True, exist_ok=False)
    write(out/'progress.json', {'synthetic_optimizer_invocations': 0})
    start = time.monotonic()
    try:
        probe = args.native_probe.resolve()
        need(probe.is_file() and os.access(probe, os.X_OK), 'compiled_native_probe_required')
        subprocess.run([sys.executable, '-m', 'jobs.tools.ed4_choice_preflight',
                        '--_full-worker', str(out), '--native-probe', str(probe)],
                       cwd=ROOT, env=environment(), timeout=300, check=True)
        report = json.loads((out/'worker-report.json').read_bytes())
        need(report.get('terminal') == TERMINAL and report['effect_ledger']['synthetic_optimizer_invocations'] == 2, 'complete_receipt')
        report['elapsed_seconds'] = time.monotonic()-start
        write(out/'report.json', report)
        seal = {'schema': 'ED4_P0_LOCAL_RECEIPT_V1', 'report_sha256': digest((out/'report.json').read_bytes())}
        write(out/'manifest.json', seal)
        need(json.loads((out/'manifest.json').read_bytes())['report_sha256'] == digest((out/'report.json').read_bytes()), 'receipt_readback')
        print(TERMINAL); return 0
    except Exception as exc:
        progress = json.loads((out/'progress.json').read_bytes())
        write(out/'failure.json', {'terminal': 'ED4_P0_TECHNICAL_FAILURE_V1',
                                   'type': type(exc).__name__, 'message': str(exc),
                                   'progress': progress, 'automatic_continuation': False})
        print('ED4_P0_TECHNICAL_FAILURE_V1', file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
