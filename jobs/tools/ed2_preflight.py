#!/usr/bin/env python3
"""ED2 fresh-data seal and CPX-only teacher sizing. No learning or held-out labels."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BUDGETS = (5000, 50000, 200000)
QUOTAS = {'production': {'calibration': 2, 'train': 64, 'test': 32},
          'smoke': {'calibration': 1, 'train': 2, 'test': 1}}
SEEDS = {'calibration': 202609081101, 'train': 202609081102, 'test': 202609081103}
FILES = ('parents.jnnw', 'children.jnnw', 'parents.tsv', 'groups.tsv', 'source.json')


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write_new(path: Path, obj) -> None:
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')


def records(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b'JNNW':
        raise ValueError('bad counted JNNW')
    n = struct.unpack_from('<I', raw, 4)[0]
    if not n or len(raw) != 8 + 38*n:
        raise ValueError('JNNW cardinality drift')
    result = [raw[8+i*38:8+(i+1)*38] for i in range(n)]
    for rec in result:
        values(rec)
    return result


def values(rec: bytes):
    if len(rec) != 38 or rec[32] not in (0, 1) or rec[33:] != b'\0'*5:
        raise ValueError('non-score-free record')
    b = struct.unpack_from('<QQQQ', rec)
    if any(x >> 50 for x in b) or any(b[i] & b[j] for i in range(4) for j in range(i)):
        raise ValueError('invalid bitboards')
    return (*b, rec[32])


def fingerprint(v) -> str:
    return ':'.join([f'{x:013x}' for x in v[:4]] + [str(v[4])])


def canonical(rec: bytes) -> str:
    wm, wk, bm, bk, stm = values(rec)
    rot = lambda b: sum(1 << (49-i) for i in range(50) if b & (1 << i))
    return min(fingerprint((wm,wk,bm,bk,stm)), fingerprint((rot(bm),rot(bk),rot(wm),rot(wk),1-stm)))


def load_tsv(path: Path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def exclude(parents: Path, children: Path, out: Path) -> None:
    pr, cr = records(parents), records(children)
    if len(pr) != 2000 or not 4000 <= len(cr) <= 32000:
        raise ValueError('BASE2000 exclusion cardinality drift')
    ids = sorted({canonical(r) for r in pr+cr})
    with out.open('x') as f:
        f.write(''.join(x+'\n' for x in ids))


def validate_source(source: Path, exclusions: Path, mode: str = 'production') -> dict:
    quota = QUOTAS[mode]
    pr, cr = records(source/'parents.jnnw'), records(source/'children.jnnw')
    parents, groups = load_tsv(source/'parents.tsv'), load_tsv(source/'groups.tsv')
    producer = json.loads((source/'source.json').read_text())
    if (producer.get('schema'),producer.get('mode'),producer.get('parents'),producer.get('children')) != ('jass.ed2.scorefree_source.v1',mode,len(pr),len(cr)):
        raise ValueError('producer schema/count mismatch')
    if any(producer.get(x) != 0 for x in ('evaluations','searches','fits','scores_generated')) or producer.get('one_endpoint_per_trajectory') is not True:
        raise ValueError('source information boundary drift')
    if len(pr) != 8*sum(quota.values()) or len(parents) != len(pr) or len(groups) != len(cr):
        raise ValueError('source cardinality mismatch')
    if [int(g['row_index']) for g in groups] != list(range(len(cr))):
        raise ValueError('child row alignment drift')
    used = set(exclusions.read_text().splitlines())
    if len(used) != producer['excluded_identities']:
        raise ValueError('exclusion count drift')
    by_parent = {i: [] for i in range(len(pr))}
    for g in groups:
        pid = int(g['parent_id'])
        if pid not in by_parent:
            raise ValueError('unknown child owner')
        by_parent[pid].append(g)
    counts = {split: {f'P{p}_stm{s}': 0 for p in range(4) for s in (0,1)} for split in quota}
    trajectories = set()
    child_counts = {s: 0 for s in quota}
    for pid, (p,rec) in enumerate(zip(parents,pr)):
        v = values(rec); n = sum(x.bit_count() for x in v[:4]); ph = 'P'+str(0 if n>=30 else 1 if n>=20 else 2 if n>=12 else 3)
        split = p['split']
        if (int(p['parent_id']),p['parent_fingerprint'],p['canonical_fingerprint'],p['parent_phase'],int(p['parent_stm'])) != (pid,fingerprint(v),canonical(rec),ph,v[4]) or not 9 <= n <= 40:
            raise ValueError('parent identity/phase mismatch')
        if split not in quota or int(p['seed']) != SEEDS[split]:
            raise ValueError('split seed mismatch')
        trajectory = (int(p['seed']), int(p['trajectory_index']))
        if trajectory in trajectories:
            raise ValueError('trajectory leakage')
        trajectories.add(trajectory)
        counts[split][f'{ph}_stm{v[4]}'] += 1
        siblings = by_parent[pid]
        if not 2 <= len(siblings) <= 16:
            raise ValueError('sibling support drift')
        footprint = {canonical(rec)}
        for a,g in enumerate(siblings):
            rid = int(g['row_index']); c = cr[rid]
            if (g['sibling_identity'],g['child_fingerprint'],g['parent_phase'],int(g['parent_stm']),g['split']) != (f'{pid}:{a}',fingerprint(values(c)),ph,v[4],split):
                raise ValueError('child identity drift')
            if values(c)[4] != 1-v[4] or int(g['child_rule_terminal']) not in (0,1) or (int(g['child_rule_terminal'])==1) != (int(g['child_legal_moves'])==0):
                raise ValueError('child STM/terminal drift')
            footprint.add(canonical(c))
        if footprint & used:
            raise ValueError('canonical parent/child leakage across groups or benchmark')
        used.update(footprint)
        child_counts[split] += len(siblings)
    if any(n != quota[s] for s,c in counts.items() for n in c.values()):
        raise ValueError('phase/STM quota mismatch')
    return dict(parents=len(pr),children=len(cr),cells=counts,children_by_split=child_counts,
                benchmark_overlap=0,between_parent_footprint_overlap=0,unique_trajectory_endpoints=len(trajectories))


def seal(source: Path, exclusions: Path, out: Path, mode='production') -> dict:
    result = validate_source(source,exclusions,mode)
    result.update(schema='jass.ed2.source_seal.v1',mode=mode,
                  files={f:sha(source/f) for f in FILES},exclusions_sha256=sha(exclusions),
                  train_teacher_score_reads=0,test_teacher_score_reads=0,
                  fit_authorized=False,code_sha=os.environ.get('ED2_CODE_SHA'))
    write_new(out,result)
    return result


def calibration_ids(source: Path) -> list[int]:
    parents = load_tsv(source/'parents.tsv'); groups = load_tsv(source/'groups.tsv')
    wanted = [int(p['parent_id']) for p in parents if p['split']=='calibration']
    selected=[]
    for pid in wanted:
        legal=[int(g['row_index']) for g in groups if int(g['parent_id'])==pid and g['split']=='calibration' and int(g['child_rule_terminal'])==0]
        if not legal:
            raise ValueError('calibration parent has no nonterminal child')
        selected.append(min(legal))
    if len(selected)!=16:
        raise ValueError('calibration requires 16 disjoint sentinel parents')
    return selected


def measure(source: Path, seal_path: Path, scan: Path, build: Path, out: Path) -> dict:
    # Import only at execution. Never read scientific train/test score fields.
    from jobs.tools.scan_ceiling_scan_score import NodeScanEngine, record_to_scan_pos, SCAN_COMMIT
    s=json.loads(seal_path.read_text()); b=json.loads(build.read_text())
    if s.get('schema')!='jass.ed2.source_seal.v1' or s.get('mode')!='production' or s['files']!={f:sha(source/f) for f in FILES}:
        raise ValueError('data seal mismatch')
    if b.get('source_commit')!=SCAN_COMMIT or b.get('scan_binary_sha256')!=sha(scan):
        raise ValueError('official Scan binary provenance mismatch')
    rows=records(source/'children.jnnw'); selected=calibration_ids(source)
    timings={str(n): [] for n in BUDGETS}
    engine=NodeScanEngine(str(scan.resolve()),label='ED2-calibration-only')
    baseline={}; searches=0
    try:
        for rid in selected:
            for n in BUDGETS:
                obs=engine.search_nodes(record_to_scan_pos(rows[rid]),n,30.0)
                elapsed=float(obs['elapsed_seconds'])
                if not math.isfinite(elapsed) or elapsed<=0:
                    raise ValueError('invalid observed teacher duration')
                timings[str(n)].append(elapsed); searches+=1
                if rid==selected[0]:
                    baseline[n]=(obs['parent_score_centi'],obs['done_move'],obs['depth'],obs['last_info_nodes'])
        for n in BUDGETS:
            obs=engine.search_nodes(record_to_scan_pos(rows[selected[0]]),n,30.0); searches+=1
            if baseline[n]!=(obs['parent_score_centi'],obs['done_move'],obs['depth'],obs['last_info_nodes']):
                raise ValueError('Scan deterministic replay mismatch')
    finally:
        engine.close()
    train=s['children_by_split']['train']; test=s['children_by_split']['test']
    planned={5000:train,50000:train,200000:test}
    # Explicit conservative engineering estimate, NOT a statistical runtime bound.
    serial=sum(max(timings[str(n)])*planned[n] for n in BUDGETS)
    projected=2*serial/8 + 600
    r=dict(schema='jass.ed2.preflight.v1',
           verdict='ED2_DATA_AND_TEACHER_PREFLIGHT_READY_V1' if projected<=2700 else 'ED2_COMPUTE_REVIEW_REQUIRED_V1',
           data=s,source_seal_sha256=sha(seal_path),scan_binary_sha256=sha(scan),scan_commit=SCAN_COMMIT,
           calibration_searches=searches,calibration_requested_nodes=17*sum(BUDGETS),
           calibration_parent_count=16,calibration_disjoint_from_train_test=True,
           observed_seconds_by_budget=timings,calibration_score_values_published=0,
           full_teacher_requested_nodes=sum(n*count for n,count in planned.items()),
           full_teacher_rows_by_budget={str(n):k for n,k in planned.items()},
           projected_teacher_plus_fit_seconds=projected,projection_workers=8,projection_safety_factor=2,
           projection_is_guarantee=False,training_labels_generated=0,test_labels_generated=0,
           fits=0,new_jass_search_nodes=0,strength_games=0,selfplay_games=0,promotions=0,bakes=0,
           fit_authorized=False,automatic_continuation=False,
           next_stage='IMPLEMENT_AND_PREREGISTER_PAIRED_VALUE_FIT' if projected<=2700 else 'STOP_COMPUTE_REVIEW')
    write_new(out,r)
    return r


def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    e=sub.add_parser('exclude'); e.add_argument('--parents',type=Path,required=True); e.add_argument('--children',type=Path,required=True); e.add_argument('--out',type=Path,required=True)
    s=sub.add_parser('seal'); s.add_argument('--source',type=Path,required=True); s.add_argument('--exclusions',type=Path,required=True); s.add_argument('--out',type=Path,required=True); s.add_argument('--mode',choices=QUOTAS,default='production')
    m=sub.add_parser('measure'); m.add_argument('--source',type=Path,required=True); m.add_argument('--seal',type=Path,required=True); m.add_argument('--scan',type=Path,required=True); m.add_argument('--build',type=Path,required=True); m.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    try:
        if a.cmd=='exclude': exclude(a.parents,a.children,a.out)
        elif a.cmd=='seal': seal(a.source,a.exclusions,a.out,a.mode)
        else: print(measure(a.source,a.seal,a.scan,a.build,a.out)['verdict'])
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(f'ED2_PREFLIGHT_TECHNICAL_FAILURE: {exc}',file=sys.stderr); return 2
if __name__=='__main__': raise SystemExit(main())
