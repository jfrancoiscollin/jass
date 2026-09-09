#!/usr/bin/env python3
"""ED3-P2: frozen BASE/HARD/SOFT, new decision endpoints, separate historical guard.

No optimizer is called. Development and confirmation use the same entrypoint,
transport, source generator, Scan workers, native evaluator and publisher.
"""
from __future__ import annotations
import argparse
import gzip
import json
import math
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import time
import traceback
import numpy as np
from scipy.special import expit
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools import ed3_confirmation_data as data
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

PHASES = ['authenticate', 'select-and-seal', 'calibrate-cost', 'score-reference', 'native-readout', 'statistics', 'publish']
MODEL_SHA = {'BASE': 'e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0',
             'HARD': '3db65fe6dcc3dc828a7467ac27a43c4904c33d5791b484a2b2f19efcef70570e',
             'SOFT': 'd8a193de2017a6c156a46d89692245bdc1af00d29d056af3a41e7d6d4f5a486a'}
SOFT_SOURCE = ('cpx62-1882-l3-ed3-soft-value-fit-production-v1', '20260908T220255Z-20a5e4eb',
               '20a5e4ebebedbf9340eafd3750506c1aed851506')
SOFT_SEAL = '57709bdfad0063cdd1b815a8a8a22c9e713c2d963b7ff4d478b008fca2c5166b'
SCAN_SOURCE = ('home-1650-l3-scan-ceiling-preflight-v1', '20260829T132800Z-28e12fba')
SCAN_SHA = '96b80c6aec1592f856a78ad7617ca6224b26be926800a6e37ede3b26f4e9cfa1'
NODE_BUDGET = 200000
OUTPUTS = ['model-identities.json', 'cohort-seal.json', 'guard-plan.json', 'teacher-cost.json',
           'confirmation-readout.json'] + ['source/'+n for n in ('parents.jnnw', 'children.jnnw', 'parents.tsv', 'groups.tsv', 'source.json')]
need = data.require


def fetch(identity, names, root, receipt):
    from jobs.tools.fetch_result_files import fetch_files
    job, attempt = identity[:2]
    r = fetch_files(rclone='rclone', prefix=f'r2:jass-data/runs/{job}/{attempt}',
                    selections=[(p, p) for p in names], out_dir=root, expected_state='completed')
    need((r['job_id'], r['attempt_id'], r['result_state'], r['exit_code']) == (job, attempt, 'completed', 0), 'input_identity')
    if len(identity) == 3:
        need(r['code_sha'] == identity[2], 'input_code')
    atomic_json(receipt, r)


def unzip(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(src, 'rb') as i, dest.open('xb') as o:
        shutil.copyfileobj(i, o)


def authenticate(result, art):
    from jobs.tools import ed3_label_pressure as audit, ed3_soft_value_fit as build, ed2_preflight as ep
    roots = {k: result/'inputs'/k for k in ('p0', 'n1', 'base', 'soft', 'scan')}
    p0_names = ['artefacts/ed2-source-seal.json', 'artefacts/benchmark-exclusions.txt', 'work/build/jass_ed2_source']
    p0_names += ['artefacts/source/'+f for f in ep.FILES]
    n1_names = ['artefacts/'+f for f in ('PARTIAL.pjtw', 'wdl-selection.json', 'wdl-selection.seal.json',
                  'build-outputs/jass_ed2_value_probe.gz', 'scratch-cleanup.json')]
    n1_names += ['work/'+f for f in ('current.jnnw', 'current.jsm', 'current-context30.npy')]
    soft_names = ['artefacts/'+f for f in ('SOFT.pjtw', 'candidate-seal.json', 'fit-report.json', 'native-roundtrip.json', 'train-contract.json')]
    scan_names = ['artefacts/'+f for f in ('scan-build-manifest.json', 'scan-home-compiled.gz', 'scan-data-eval', 'scan.ini')]
    for key, identity, names in [('p0', audit.P0, p0_names), ('n1', audit.N1, n1_names),
                ('base', audit.BASE, ['artefacts/WDL_CONTROL.pjtw.gz']), ('soft', SOFT_SOURCE, soft_names),
                ('scan', SCAN_SOURCE, scan_names)]:
        fetch(identity, names, roots[key], art/('verified-'+key+'.json'))
    w = result/'work'; w.mkdir(parents=True, exist_ok=True)
    p0, n1, soft = (roots[k]/'artefacts' for k in ('p0', 'n1', 'soft'))
    need(data.sha(p0/'ed2-source-seal.json') == audit.SOURCE_SEAL, 'old_source_seal')
    old_seal = data.read_json(p0/'ed2-source-seal.json')
    need(old_seal['files'] == {f:data.sha(p0/'source'/f) for f in ep.FILES}, 'old_source_bytes')
    need(old_seal['exclusions_sha256'] == data.sha(p0/'benchmark-exclusions.txt'), 'benchmark_exclusions')
    build.verify_candidate(soft, 'production')
    need(data.sha(soft/'candidate-seal.json') == SOFT_SEAL, 'candidate_seal_identity')
    unzip(roots['base']/'artefacts/WDL_CONTROL.pjtw.gz', w/'BASE.pjtw')
    models = {'BASE': w/'BASE.pjtw', 'HARD': n1/'PARTIAL.pjtw', 'SOFT': soft/'SOFT.pjtw'}
    need({k:data.sha(p) for k,p in models.items()} == MODEL_SHA, 'frozen_models')
    from jobs.tools.ed2_value_math import read_model
    base, offset, _ = read_model(models['BASE'])
    for model in models.values():
        raw, off, _ = read_model(model)
        need(off == offset and raw[:off] == base[:offset], 'frozen_pattern_prefix')
    cleanup = data.read_json(n1/'scratch-cleanup.json')['retained_binaries']['jass_ed2_value_probe']
    archive = n1/'build-outputs/jass_ed2_value_probe.gz'
    need(data.sha(archive) == cleanup['archive_sha256'], 'probe_archive')
    unzip(archive, w/'probe'); need(data.sha(w/'probe') == cleanup['sha256'], 'probe_binary'); (w/'probe').chmod(0o500)
    source_binary = roots['p0']/'work/build/jass_ed2_source'; source_binary.chmod(0o500)
    scan = w/'scan'; (scan/'data').mkdir(parents=True)
    sr = roots['scan']/'artefacts'
    unzip(sr/'scan-home-compiled.gz', scan/'scan'); (scan/'scan').chmod(0o500)
    shutil.copyfile(sr/'scan-data-eval', scan/'data/eval'); shutil.copyfile(sr/'scan.ini', scan/'scan.ini')
    sb = data.read_json(sr/'scan-build-manifest.json')
    need(sb['source_commit'] == '7aae17e7b7bfc47744601afb1ee7655e18983ce5' and sb['scan_binary_sha256'] == SCAN_SHA
         and data.sha(scan/'scan') == SCAN_SHA, 'scan_identity')
    selection = data.read_json(n1/'wdl-selection.json')
    need(data.read_json(n1/'wdl-selection.seal.json')['sha256'] == data.sha(n1/'wdl-selection.json'), 'old_guard_seal')
    current = roots['n1']/'work/current.jnnw'; meta = roots['n1']/'work/current.jsm'
    need(data.sha(current) == selection['source_data_sha256'] and data.sha(meta) == selection['source_meta_sha256'], 'historical_source')
    identities = dict(schema='jass.ed3.confirmation_models.v1', models=MODEL_SHA, soft_seal_sha256=SOFT_SEAL,
                      probe_sha256=data.sha(w/'probe'), source_binary_sha256=data.sha(source_binary),
                      scan_sha256=SCAN_SHA, fits=0, retuning=False)
    atomic_json(art/'model-identities.json', identities)
    return dict(p0=p0, n1=n1, selection=selection, current=current, meta=meta,
                targets=roots['n1']/'work/current-context30.npy', source_binary=source_binary,
                models=models, probe=w/'probe', scan=scan/'scan', identities=identities)


def prepare(d, result, art, mode):
    from jobs.tools import ed2_preflight as ep
    from tools import selfplay_frontier as sf
    source = art/'source'
    used = set((d['p0']/'benchmark-exclusions.txt').read_text().splitlines())
    used |= data.source_fingerprints([d['p0']/'source/parents.jnnw', d['p0']/'source/children.jnnw'])
    if mode == 'production':
        used |= data.source_fingerprints([result/'launch-prerequisite/source/parents.jnnw',
                                         result/'launch-prerequisite/source/children.jnnw'])
        d['selection'] = dict(d['selection'], subsets=dict(d['selection']['subsets']))
        dev_plan = data.read_json(result/'launch-prerequisite/guard-plan.json')
        d['selection']['subsets']['ed3_rehearsal'] = dev_plan['subsets']['development']
    raw = d['current'].read_bytes()
    for subset in d['selection']['subsets'].values():
        for i in subset['indices']:
            used.add(data.canonical(data.zero_record(raw[8+38*i:8+38*(i+1)])))
    exclusion = result/'work/exclusions.txt'
    exclusion.write_text(''.join(k+'\n' for k in sorted(used)))
    with (result/'work/source.log').open('xb') as log:
        subprocess.run([str(d['source_binary']), str(exclusion), str(source), 'production' if mode == 'production' else 'smoke'],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=240)
    counts = ep.validate_source(source, exclusion, 'production' if mode == 'production' else 'smoke')
    parents, groups = ep.load_tsv(source/'parents.tsv'), ep.load_tsv(source/'groups.tsv')
    selected = data.selected_groups(parents, groups, mode)
    # Miniature identities are developmental only. Production generates fresh
    # endpoints AFTER admission and excludes every published miniature footprint.
    fp = used | data.source_fingerprints([source/'parents.jnnw', source/'children.jnnw'])
    schema, n = sf._meta_file_info(d['meta'])
    need(n == 2000000, 'historical_meta_count')
    with d['meta'].open('rb') as f:
        def opening(i):
            f.seek(8+i*schema.record.size)
            return sf._decode_meta(f.read(schema.record.size), schema).opening_id
        plan = data.select_guard(raw, opening, d['selection'], fp,
                    roles=('confirmation',) if mode == 'production' else ('development',),
                    sizes=(8192,) if mode == 'production' else (256,))
    atomic_json(art/'guard-plan.json', plan)
    seal = dict(schema='jass.ed3.confirmation_cohort.v1', source_files={f:data.sha(source/f) for f in ep.FILES},
                guard_plan_sha256=data.sha(art/'guard-plan.json'), exclusions_sha256=data.sha(exclusion),
                source_binary_sha256=data.sha(d['source_binary']), models=d['identities']['models'],
                counts=counts, mode=mode, decision_parents=len(selected),
                old_ed2_and_benchmark_overlap=0, selection_before_target_reads=True,
                mapping={'train':'confirmation512' if mode == 'production' else 'development16',
                         'test':'unused_reserved', 'calibration':'timing_only'},
                development_footprints_excluded=(mode == 'production'),
                historical_guard_not_new_outcomes=True)
    atomic_json(art/'cohort-seal.json', seal)
    if mode == 'production':
        for name in ('model-identities.json',):
            need(data.sha(art/name) == data.sha(result/'launch-prerequisite'/name), 'model_or_binary_differs_from_rehearsal')
    role = 'confirmation' if mode == 'production' else 'development'
    g = plan['subsets'][role]
    data.write_records(result/'work/guard.jnnw', [data.zero_record(raw[8+38*i:8+38*(i+1)]) for i in g['indices']])
    children = ep.records(source/'children.jnnw')
    ids = [r for group in selected for r in group['rows']]
    data.write_records(result/'work/decisions.jnnw', [children[i] for i in ids])
    d.update(source=source, groups=selected, children=children, guard=g, ids=ids, seal=seal)
    return d


def verify_sealed_inputs(art):
    s = data.read_json(art/'cohort-seal.json')
    need(s['source_files'] == {f:data.sha(art/'source'/f) for f in s['source_files']}, 'source_mutation')
    need(s['guard_plan_sha256'] == data.sha(art/'guard-plan.json'), 'guard_plan_mutation')


def calibration(d, evidence):
    from jobs.tools import ed2_preflight as ep
    from jobs.tools.scan_ceiling_scan_score import NodeScanEngine, record_to_scan_pos
    parents = ep.load_tsv(d['source']/'parents.tsv'); groups = ep.load_tsv(d['source']/'groups.tsv')
    ids = []
    for p in parents:
        if p['split'] != 'calibration': continue
        rows = [int(r['row_index']) for r in groups if r['parent_id'] == p['parent_id'] and not int(r['child_rule_terminal'])]
        need(bool(rows), 'calibration_nonterminal_support'); ids.append(min(rows))
    need(len(ids) in (8,16), 'calibration_count'); timings = []
    engine = NodeScanEngine(str(d['scan'].resolve()), label='ED3-P2-calibration')
    first = None
    try:
        for rid in ids + ids[:1]:
            evidence.value['actual_side_effects']['new_scan_searches'] += 1; evidence.save()
            obs = engine.search_nodes(record_to_scan_pos(d['children'][rid]), NODE_BUDGET, 30)
            elapsed = float(obs['elapsed_seconds'])
            need(math.isfinite(elapsed) and elapsed > 0, 'calibration_clock')
            timings.append(elapsed)
            signature = [obs[k] for k in ('parent_score_centi', 'done_move', 'depth', 'last_info_nodes')]
            if first is None: first = signature
        need(signature == first, 'calibration_replay_mismatch')
    finally:
        engine.close()
    maximum_shard = max(sum(r % 8 == i for r in d['ids']) for i in range(8))
    deadline = max(60., 2*max(timings)*maximum_shard + 60.)
    need(deadline <= 1200, 'COMPUTE_REVIEW_REQUIRED')
    return dict(calibration_searches=len(ids)+1, calibration_requested_nodes=(len(ids)+1)*NODE_BUDGET,
                maximum_seconds_per_row=max(timings), batch_cap_seconds=deadline,
                planned_maximum_reference_calls=len(d['ids']), workers=8, calibration_scores_published=False,
                durations_are_not_guarantees=True)


def score_worker(art, scan, mode, shard, output):
    from jobs.tools import ed2_preflight as ep
    from jobs.tools.scan_ceiling_scan_score import NodeScanEngine, record_to_scan_pos, terminal_observation
    verify_sealed_inputs(art)
    need(mode in ('production','rehearsal') and 0 <= shard < 8, 'worker_role')
    source = art/'source'
    gs = data.selected_groups(ep.load_tsv(source/'parents.tsv'), ep.load_tsv(source/'groups.tsv'), mode)
    children = ep.records(source/'children.jnnw')
    ids = sorted(r for g in gs for r in g['rows'] if r % 8 == shard)
    terminal = {r for g in gs for r in g['terminals']}
    engine = NodeScanEngine(str(scan.resolve()), label=f'ED3-P2-{shard}')
    try:
        with output.open('x') as f:
            for rid in ids:
                obs = terminal_observation() if rid in terminal else engine.search_nodes(record_to_scan_pos(children[rid]), NODE_BUDGET, 30)
                f.write(json.dumps(dict(row=rid, budget=NODE_BUDGET, score=int(obs['parent_score_centi']),
                         terminal=rid in terminal, elapsed_seconds=float(obs['elapsed_seconds']),
                         last_info_nodes=int(obs['last_info_nodes'])), sort_keys=True)+'\n'); f.flush()
    finally:
        engine.close()


def load_scores(paths, groups):
    want = {r for g in groups for r in g['rows']}; terminal = {r for g in groups for r in g['terminals']}
    scores = {}; calls = 0
    for path in paths:
        for line in path.read_text().splitlines():
            r = json.loads(line); rid = r['row']
            need(rid in want and rid not in scores and r['budget'] == NODE_BUDGET and type(r['score']) is int
                 and type(r['terminal']) is bool and r['terminal'] == (rid in terminal), 'reference_coverage_or_role')
            need(np.isfinite(r['elapsed_seconds']) and r['elapsed_seconds'] >= 0, 'reference_clock')
            need((r['last_info_nodes'] == 0 and r['score'] == 10000) if r['terminal'] else 0 < r['last_info_nodes'] <= NODE_BUDGET,
                 'reference_snapshot')
            scores[rid] = r['score']; calls += int(not r['terminal'])
    need(set(scores) == want, 'incomplete_reference_no_partial_harvest')
    return {(r, NODE_BUDGET):v for r,v in scores.items()}, calls


def reference(d, art, work, mode, cost, evidence):
    paths = [art/f'reference-{i}.jsonl' for i in range(8)]
    logs, procs = [], []; start = time.monotonic()
    # Predeclare the maximum started work; exact successful counts replace it below.
    nonterminal = sum(r not in g['terminals'] for g in d['groups'] for r in g['rows'])
    evidence.value['actual_side_effects']['new_scan_searches'] += nonterminal
    evidence.value['side_effect_counters_upper_bounds_until_workers_complete'] = True; evidence.save()
    try:
        for i, path in enumerate(paths):
            log = (work/f'reference-{i}.log').open('xb'); logs.append(log)
            cmd = [sys.executable, str(Path(__file__).resolve()), 'score', '--art', str(art), '--scan', str(d['scan']),
                   '--mode', mode, '--shard', str(i), '--out', str(path)]
            procs.append(subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        while any(p.poll() is None for p in procs):
            need(not any(p.poll() not in (None,0) for p in procs), 'worker_failed_no_partial_harvest')
            if time.monotonic()-start > cost['batch_cap_seconds']: raise TimeoutError('ED3_REFERENCE_BATCH_CAP')
            time.sleep(.1)
        need(all(p.returncode == 0 for p in procs), 'worker_failed')
    finally:
        for p in procs:
            try: os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError: pass
        for p in procs:
            try: p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try: os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                p.wait()
        for f in logs: f.close()
    scores, calls = load_scores(paths, d['groups'])
    need(calls == nonterminal, 'reference_call_accounting')
    evidence.value['side_effect_counters_upper_bounds_until_workers_complete'] = False
    cost.update(reference_searches=calls, reference_requested_nodes=calls*NODE_BUDGET,
                reference_rows=len(scores), reference_wall_seconds=time.monotonic()-start)
    if mode == 'production': evidence.value['actual_side_effects']['test_target_reads'] += len(scores)
    evidence.save()
    return scores


def native_readout(d, result, art, mode, evidence):
    from jobs.tools.ed3_soft_value_fit import run_probe
    from jobs.tools.ed2_value_math import read_model
    q = {}; hold = {}; feature_paths = {}; logits = {}
    for arm, model in d['models'].items():
        need(data.sha(model) == d['identities']['models'][arm], 'model_mutation')
        for name in ('decisions', 'guard'):
            table = run_probe(d['probe'], result/'work'/(name+'.jnnw'), model, result/'work'/f'{arm}-{name}.tsv')
            x, z, cp = table
            if arm == 'BASE': feature_paths[name] = x; logits[name] = z
            else:
                need(np.array_equal(x, feature_paths[name]), 'native_features_differ')
                _, _, bw = read_model(d['models']['BASE']); _, _, aw = read_model(model)
                need(np.allclose(z, logits[name]+x@(aw-bw), atol=1e-9, rtol=0), 'native_value_mapping')
            if name == 'decisions':
                q[arm] = np.zeros(len(d['children']), dtype=int); q[arm][d['ids']] = cp
            else: hold[arm] = cp
    repeated = run_probe(d['probe'], result/'work/decisions.jnnw', d['models']['BASE'], result/'work/BASE-repeat.tsv')[2]
    need(np.array_equal(repeated, q['BASE'][d['ids']]), 'native_identity_control')
    # All selection and all model identities were sealed before this FIRST guard read.
    verify_sealed_inputs(art)
    targets = np.load(d['targets'], mmap_mode='r', allow_pickle=False)
    need(targets.shape == (2000000,) and targets.dtype == np.float32, 'context30_shape')
    y = np.asarray(targets[d['guard']['indices']], dtype=float)
    need(np.isfinite(y).all() and ((y >= 0) & (y <= 1)).all(), 'context30_values')
    from jobs.tools.ed2_preflight import records
    signs = np.array([1 if r[32] else -1 for r in records(result/'work/guard.jnnw')])
    losses, metrics = {}, {}
    for arm, cp in hold.items():
        z = signs*cp/100.0; losses[arm] = np.logaddexp(0,z)-y*z
        metrics[arm] = dict(logloss=float(losses[arm].mean()), brier=float(np.mean((expit(z)-y)**2)))
    if mode == 'production': evidence.value['actual_side_effects']['test_target_reads'] += len(y)
    evidence.save()
    return q, losses, metrics


def statistics(d, high, scores, losses, metrics, mode):
    from jobs.tools import ed2_value_math as m
    rows = {arm:m.decision_rows(d['groups'], high, cp) for arm, cp in scores.items()}
    vsbase = m.compare_decisions(rows['BASE'], rows['SOFT'], 202609090801)
    vshard = m.compare_decisions(rows['HARD'], rows['SOFT'], 202609090802)
    sanity = m.compare_decisions(rows['BASE'], rows['BASE'], 202609090803)
    need(sanity['mean'] == 0 and sanity['ci95'] == [0.,0.] and sanity['decision_changes'] == 0, 'nonempty_identity_sanity')
    wdl = m.bootstrap_opening(losses['SOFT']-losses['BASE'], d['guard']['opening_ids'], 202609090804)
    gates = dict(regret_beats_base=vsbase['ci95'][0]>0, regret_beats_hard=vshard['ci95'][0]>0,
                 top_hit_not_lower=vsbase['top_hit_delta']>=0 and vshard['top_hit_delta']>=0,
                 harms_not_more_than_improvements=vsbase['harmed']<=vsbase['improved'],
                 wdl_noninferior=wdl['ci95'][1]<=.002,
                 brier_noninferior=metrics['SOFT']['brier']<=metrics['BASE']['brier']+.002)
    return dict(schema='jass.ed3.confirmation_readout.v1', mode=mode, gates=gates,
                versus_base=vsbase, versus_hard=vshard, wdl_delta_bootstrap=wdl, wdl=metrics,
                aggregate={arm:dict(regret_mean=float(np.mean([r['regret'] for r in rs])),
                                   top_hit=float(np.mean([r['hit'] for r in rs]))) for arm,rs in rows.items()},
                parents=len(d['groups']), guard_rows=len(d['guard']['indices']), identity_sanity=sanity,
                historical_guard=True, fresh_wdl_outcomes=False, scan_is_exact_truth=False), rows


def run(result, art, mode, loader=authenticate, preparer=prepare, calibrator=calibration,
        scorer=reference, native=native_readout):
    evidence = StageEvidence(art, mode)
    try:
        need(shutil.disk_usage(result).free > 3_000_000_000, 'disk_space')
        evidence.begin('authenticate'); d = loader(result, art); evidence.complete()
        evidence.begin('select-and-seal'); d = preparer(d, result, art, mode); evidence.complete()
        evidence.begin('calibrate-cost'); cost = calibrator(d, evidence); atomic_json(art/'teacher-cost.json', cost); evidence.complete()
        evidence.begin('score-reference'); verify_sealed_inputs(art)
        high = scorer(d, art, result/'work', mode, cost, evidence); atomic_json(art/'teacher-cost.json', cost); evidence.complete()
        evidence.begin('native-readout'); scores, losses, metrics = native(d, result, art, mode, evidence); evidence.complete()
        evidence.begin('statistics'); report, rows = statistics(d, high, scores, losses, metrics, mode); evidence.complete()
        evidence.begin('publish')
        verify_sealed_inputs(art)
        need({a:data.sha(p) for a,p in d['models'].items()} == d['identities']['models'], 'final_model_identity')
        atomic_json(art/'confirmation-readout.json', report); atomic_json(art/'parent-readout.json', rows)
        success = all(report['gates'].values())
        verdict = ('ED3_SOFT_CONFIRMATION_SUPPORTED_V1' if success else 'ED3_SOFT_CONFIRMATION_NOT_SUPPORTED_V1') if mode == 'production' else 'ED3_CONFIRMATION_REHEARSAL_COMPLETE_V1'
        summary = dict(schema='jass.ed3.confirmation_terminal.v1', verdict=verdict, mode=mode,
            scientific_verdict=verdict if mode=='production' else None, fits=0, models=d['identities']['models'],
            parents=report['parents'], wdl_rows=report['guard_rows'], result=report, cost=cost,
            cohort_seal_sha256=data.sha(art/'cohort-seal.json'), test_target_reads=evidence.value['actual_side_effects']['test_target_reads'],
            new_scan_searches=evidence.value['actual_side_effects']['new_scan_searches'],
            new_jass_searches=0, strength_games=0, selfplay_games=0, promotions=0, bakes=0,
            runtime_authorized=False, automatic_continuation=False,
            next_stage=('PREREGISTER_NATIVE_GATE0' if success else 'STOP_ED3') if mode=='production' else 'AUTHENTICATE_REHEARSAL')
        atomic_json(art/'scientific-summary.json', summary); evidence.complete(); evidence.finish()
        return summary
    except BaseException as exc:
        evidence.fail(exc)
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command')
    s = sub.add_parser('score')
    for name in ('art','scan','out'): s.add_argument('--'+name, type=Path, required=True)
    s.add_argument('--mode', choices=('rehearsal','production'), required=True); s.add_argument('--shard', type=int, required=True)
    a = p.parse_args()
    if a.command == 'score':
        score_worker(a.art, a.scan, a.mode, a.shard, a.out); return 0
    from jobs.tools.ed2_value_entrypoint import install_shutdown_handlers
    install_shutdown_handlers()
    run(Path(os.environ['JASS_RESULT_DIR']), Path(os.environ['JASS_ARTEFACT_DIR']), os.environ['LAUNCH_MODE'])
    return 0

if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception:
        traceback.print_exc(); raise SystemExit(2)
