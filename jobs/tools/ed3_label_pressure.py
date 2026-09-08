#!/usr/bin/env python3
"""ED3-P0: exploratory TRAIN/replay diagnostic, never reads TEST targets.

Uses only authenticated existing artifacts. No engine, optimizer, model selection,
new teacher search or held-out read is reachable from this entrypoint.
"""
from __future__ import annotations
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import sys
import traceback
import numpy as np
from scipy.special import expit
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from jobs.tools.launch_runtime_v2 import StageEvidence, atomic_json

P0 = ('cpx62-1875-l3-ed2-data-teacher-preflight-v1', '20260908T171140Z-bc30d685',
      'bc30d6858c4d590625f8831c4995f055816b95c2')
N1 = ('cpx62-1878-l3-ed2-numerical-recovery-n1', '20260908T191343Z-d71679e9',
      'd71679e96d78609b6d32052be80ca78c0deaece0')
BASE = ('cpx62-1849-l3-decision-math-d1-wdl-listwise-fit-stage-env-recovery-requeue-v1',
        '20260906T222203Z-08fd187a', '08fd187aa187f26bd7179df2c68056a74e28355d')
TARGET = ('cpx62-1340-jass-megacorpus-comparative-fit-v1', '20260814T123246Z-2ce07222',
          '2ce07222f86c1468a1081fbdc53e9e17a0c5326e')
MODEL_HASH = {'BASE': 'e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0',
              'POINT': '4fc96d5e7407a24961dc7287110641a9a98a4370a47810d9474a87c84c106f8e',
              'PARTIAL': '3db65fe6dcc3dc828a7467ac27a43c4904c33d5791b484a2b2f19efcef70570e'}
SOURCE_SEAL = '31f763049fef50544bd1cbb240eeb4f51670728ae0697a77e982186df007152c'
TRAIN_NAMES = [f'train-{i}.jsonl' for i in range(8)]
N1_NAMES = TRAIN_NAMES + ['train-labels-sealed.json', 'label-support.json', 'wdl-selection.json',
          'wdl-selection.seal.json', 'native/train-native.tsv.gz', 'native/replay-native.tsv.gz',
          'native/POINT-train-native.tsv.gz', 'native/PARTIAL-train-native.tsv.gz',
          'POINT.pjtw', 'PARTIAL.pjtw']
PHASES = ['authenticate', 'load-train-and-replay', 'measure', 'publish']


def check(ok, code):
    if not ok:
        raise ValueError(code)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def load_json(path):
    return json.loads(path.read_text())


def fetch_existing(identity, names, root, report):
    from jobs.tools.fetch_result_files import fetch_files
    job, attempt, code = identity
    # Literal positive allowlists, never inventory-driven target/TEST selection.
    result = fetch_files(rclone='rclone', prefix=f'r2:jass-data/runs/{job}/{attempt}',
                         selections=[('artefacts/'+p, p) for p in names],
                         out_dir=root, expected_state='completed')
    check((result['job_id'], result['attempt_id'], result['code_sha'], result['result_state'], result['exit_code'])
          == (job, attempt, code, 'completed', 0), 'source_identity')
    atomic_json(report, result)


def table(path, rows):
    with gzip.open(path, 'rt') as f:
        a = np.loadtxt(f, delimiter='\t', skiprows=1, ndmin=2)
    check(a.shape == (rows, 124) and np.isfinite(a).all(), 'native_table_shape')
    check(np.array_equal(a[:, 0], np.arange(rows)), 'native_table_order')
    check(((0 <= a[:, 3]) & (a[:, 3] <= 1)).all(), 'phase_range')
    return np.hstack((a[:, 4:]*a[:, 3,None], a[:, 4:]*(1-a[:, 3,None]))), a[:, 1]


def weights(path, expected):
    check(sha(path) == expected, 'model_identity')
    raw = path.read_bytes()
    magic, version, scale, npat, ne = struct.unpack_from('<5I', raw)
    check(magic == 0x57544A50 and version & 255 == 3 and not version & 256
          and scale == 1000 and ne == 120 and len(raw) == 20+8*(npat+ne), 'model_layout')
    return np.frombuffer(raw, '<i4', offset=20+8*npat).astype(float)/1000


def groups_and_scores(p0, n1, expected_parents=512):
    with (p0/'source/groups.tsv').open() as f:
        all_rows = list(csv.DictReader(f, delimiter='\t'))
    groups = {}
    for row in all_rows:
        if row['split'] != 'train':
            continue
        pid = int(row['parent_id'])
        item = groups.setdefault(pid, dict(id=pid, cell=row['parent_phase']+'_stm'+row['parent_stm'],
                                          stm=int(row['parent_stm']), rows=[], terminals=[]))
        rid = int(row['row_index']); item['rows'].append(rid)
        if int(row['child_rule_terminal']):
            item['terminals'].append(rid)
    groups = list(groups.values())
    check(len(groups) == expected_parents, 'train_parent_support')
    allowed = {r for g in groups for r in g['rows']}
    terminals = {r for g in groups for r in g['terminals']}
    seal = load_json(n1/'train-labels-sealed.json')
    check(seal['source_seal'] == SOURCE_SEAL and seal['test_teacher_calls'] == 0, 'train_seal')
    check(set(seal['teacher_files']) == set(TRAIN_NAMES), 'teacher_file_set')
    scores = {}
    for name in TRAIN_NAMES:
        check(sha(n1/name) == seal['teacher_files'][name], 'teacher_hash')
        with (n1/name).open() as f:
            for line in f:
                x = json.loads(line); key = x['row'], x['budget']
                check(x['row'] in allowed and x['budget'] in (5000, 50000), 'forbidden_target_role')
                check(key not in scores and type(x['score']) is int and x['terminal'] == (x['row'] in terminals), 'teacher_schema')
                scores[key] = float(x['score'])
    check(set(scores) == {(r,b) for r in allowed for b in (5000,50000)}, 'teacher_coverage')
    return groups, scores


def pair_data(groups, scores):
    import itertools
    order = [r for group in groups for r in group['rows']]
    local = {r:i for i,r in enumerate(order)}
    winners=[]; losers=[]; masses=[]; signs=[]; gaps=[]
    for group in groups:
        rows = [r for r in group['rows'] if r not in group['terminals']]
        keep=[]
        for a,b in itertools.combinations(rows, 2):
            w,l = (a,b) if scores[a,50000] > scores[b,50000] else (b,a)
            if min(scores[w,5000], scores[w,50000]) > max(scores[l,5000], scores[l,50000]):
                keep.append((w,l))
        for w,l in keep:
            winners.append(local[w]);losers.append(local[l]);masses.append(1/(len(groups)*len(keep)))
            signs.append(1 if group['stm'] == 1 else -1);gaps.append(scores[w,50000]-scores[l,50000])
    check(bool(gaps), 'empty_pair_support')
    return (np.array(winners), np.array(losers), np.array(masses), np.array(signs), np.array(gaps)), len(order)


def weighted_mean(values, mass):
    return float(np.dot(values,mass)/mass.sum()) if mass.sum() > 0 else None


def summarize(x, logits, replay_x, replay_logits, y, edges):
    w,l,mass,sign,gap = edges
    dx = sign[:,None]*(x[w]-x[l])
    result = dict(schema='jass.ed3.label_pressure.v1', diagnostic_only=True,
                  reference_is_exact_truth=False, train_pairs=len(w), parent_weight_mass=float(mass.sum()),
                  temperature_rule='weighted_median_positive_train_gap_div_log3', arms={})
    # Fixed train-only scale rule, not chosen from these diagnostic results.
    sort=np.argsort(gap, kind='stable'); cumulative=np.cumsum(mass[sort])
    median=float(gap[sort[np.searchsorted(cumulative, mass.sum()/2, side='left')]])
    result['prospective_tau']=float(median/np.log(3.0))
    for arm,z in logits.items():
        d=sign*(z[w]-z[l]);force=expit(-d); grad=-(dx.T@(mass*force))
        rz=replay_logits[arm];wdl_grad=replay_x.T@(expit(rz)-y)/len(y)
        denominator=float(np.linalg.norm(grad)*np.linalg.norm(wdl_grad))
        rows=[]
        for lo,hi in ((0,10),(10,50),(50,200),(200,float('inf'))):
            mask=(gap>lo)&(gap<=hi); wt=mass[mask]
            rows.append(dict(scan_gap_lower_exclusive=lo,scan_gap_upper_inclusive=None if np.isinf(hi) else hi,
                             pairs=int(mask.sum()),parent_weight_mass=float(wt.sum()),
                             predicted_margin_mean=weighted_mean(d[mask],wt),
                             positive_margin_share=weighted_mean((d[mask]>0).astype(float),wt),
                             hard_label_force_mass_share=float(np.dot(wt,force[mask])/np.dot(mass,force))))
        result['arms'][arm]=dict(margin_mean=weighted_mean(d,mass),margin_abs_mean=weighted_mean(abs(d),mass),
            margin_change_vs_base_mean=weighted_mean(d-sign*(logits['BASE'][w]-logits['BASE'][l]),mass),
            force_on_already_ordered_share=float(np.dot(mass*force,d>0)/np.dot(mass,force)),
            pair_gradient_norm=float(np.linalg.norm(grad)), replay_gradient_norm=float(np.linalg.norm(wdl_grad)),
            pair_replay_gradient_cosine=float(grad@wdl_grad/denominator) if denominator else None,
            replay_logloss=float(np.mean(np.logaddexp(0,rz)-y*rz)),
            replay_brier=float(np.mean((expit(rz)-y)**2)), bins=rows)
    result['limits'] = ['TRAIN/replay only: no generalization or causal success claim',
                        'force mass is derivative magnitude in margin space, not a parameter-gradient share',
                        'gradient opposition at a joint optimum is not proof of harmful task conflict',
                        'Scan ranges and preference targets are not certified bounds or WDL probabilities',
                        'old ED2 TEST and historical WDL holdout remain prohibited for ED3 tuning']
    return result


def analyze_inputs(p0, n1, base, target, work, expected_parents=512, replay_n=8192, total_targets=2000000,
                   model_hashes=None):
    groups,scores=groups_and_scores(p0,n1,expected_parents)
    edges,rows=pair_data(groups,scores)
    if expected_parents == 512:
        check(rows == 4976 and len(edges[0]) == 17622, 'frozen_train_shape')
        counts={f'P{p}_stm{s}':0 for p in range(4) for s in (0,1)}
        for g in groups: counts[g['cell']]+=1
        check(set(counts.values()) == {64}, 'train_cells')
    x,z=table(n1/'native/train-native.tsv.gz',rows)
    rx,rz=table(n1/'native/replay-native.tsv.gz',replay_n)
    models=model_hashes or MODEL_HASH
    with gzip.open(base/'WDL_CONTROL.pjtw.gz','rb') as f:
        (work/'BASE.pjtw').write_bytes(f.read())
    bw=weights(work/'BASE.pjtw',models['BASE'])
    logits={'BASE':z};replay={'BASE':rz}
    for arm in ('POINT','PARTIAL'):
        ax,az=table(n1/f'native/{arm}-train-native.tsv.gz',rows)
        check(np.array_equal(ax,x), 'native_feature_replay')
        dw=weights(n1/(arm+'.pjtw'),models[arm])-bw
        check(np.allclose(az,z+x@dw,rtol=0,atol=1e-9), 'native_value_reconstruction')
        logits[arm]=az;replay[arm]=rz+rx@dw
    selection=load_json(n1/'wdl-selection.json')
    check(load_json(n1/'wdl-selection.seal.json')['sha256']==sha(n1/'wdl-selection.json'), 'wdl_selection_seal')
    ids=selection['subsets']['replay']['indices']
    check(len(ids)==replay_n and len(set(ids))==replay_n and min(ids)>=0 and max(ids)<1800796, 'replay_indices')
    import shutil
    with gzip.open(target/'current_2m-context30.npy.gz','rb') as f, (work/'targets.npy').open('xb') as out:
        shutil.copyfileobj(f,out)
    yy=np.load(work/'targets.npy',allow_pickle=False,mmap_mode='r')
    check(yy.shape==(total_targets,) and yy.dtype==np.float32,'target_layout')
    y=np.asarray(yy[ids],dtype=float) # The only selected target payload access.
    check(np.isfinite(y).all() and ((y>=0)&(y<=1)).all(),'replay_targets')
    return summarize(x,logits,rx,replay,y,edges)


def run(artifact, result, mode, downloader=fetch_existing, analyzer=analyze_inputs):
    evidence=StageEvidence(artifact,mode)
    work=result/'work';work.mkdir(parents=True,exist_ok=True)
    inputs=result/'inputs'
    roots={k:inputs/k for k in ('p0','n1','base','target')}
    try:
        evidence.begin('authenticate')
        for key,identity,names in [('p0',P0,['source/groups.tsv']),('n1',N1,N1_NAMES),
                                   ('base',BASE,['WDL_CONTROL.pjtw.gz']),('target',TARGET,['current_2m-context30.npy.gz'])]:
            downloader(identity,names,roots[key],artifact/('verified-'+key+'.json'))
        evidence.complete();evidence.begin('load-train-and-replay')
        # Strict role/shape/hash validation happens inside the shared analyzer.
        report=analyzer(roots['p0'],roots['n1'],roots['base'],roots['target'],work)
        evidence.complete();evidence.begin('measure')
        check(report['train_pairs']>0 and report['diagnostic_only'] is True,'nonempty_diagnostic')
        evidence.complete();evidence.begin('publish')
        atomic_json(artifact/'ed3-label-pressure.json',report)
        check(load_json(artifact/'ed3-label-pressure.json')==report,'report_roundtrip')
        summary=dict(schema='jass.ed3.p0_terminal.v1', verdict='ED3_TRAIN_PRESSURE_DIAGNOSTIC_COMPLETE_V1',
                     classification='EXPLORATORY_TRAIN_ONLY', mode=mode, fits=0,new_scan_searches=0,
                     test_target_reads=0,promotions=0,bakes=0,strength_games=0,
                     diagnostic=report, next_stage='REVIEW_ED3_TRAIN_DIAGNOSTIC',
                     paired_fit_implemented=False, automatic_continuation=False)
        atomic_json(artifact/'scientific-summary.json',summary)
        evidence.complete();evidence.finish()
        return summary
    except Exception as exc:
        evidence.fail(exc)
        raise


def main():
    result=Path(os.environ['JASS_RESULT_DIR']);artifact=Path(os.environ['JASS_ARTEFACT_DIR'])
    try:
        run(artifact,result,os.environ['LAUNCH_MODE'])
        return 0
    except Exception:
        traceback.print_exc() # private stage stderr, not mirrored into GitOps
        return 2


if __name__=='__main__':raise SystemExit(main())
