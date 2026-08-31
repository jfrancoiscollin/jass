#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Frozen PL8 fresh 8000-parent deep-transfer readout. No fitting occurs here."""
from __future__ import annotations
import argparse,csv,json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
import numpy as np

PHASES=("P0","P1","P2","P3")
EXACT_SENTINEL=2
BOOTSTRAP_SAMPLES=100000
BOOTSTRAP_SEED=2026103121

@dataclass(frozen=True)
class Parent: pid:int; stm:int; phase:str; pieces:int; legal:int
@dataclass(frozen=True)
class Sib: row:int; pid:int; stm:int; exact:int; t0:float; q1:float; q50:float; q200:float

def load_parents(path:Path)->dict[int,Parent]:
    out={}
    with path.open(newline='',encoding='utf-8') as f:
        rd=csv.DictReader(f,delimiter='\t');req={'parent_id','parent_stm','phase','pieces','legal_moves'}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):raise ValueError('PL8 parent fields drift')
        for r in rd:
            p=Parent(int(r['parent_id']),int(r['parent_stm']),r['phase'],int(r['pieces']),int(r['legal_moves']))
            if p.pid in out or p.stm not in (0,1) or p.phase not in PHASES or not 9<=p.pieces<=40 or not 2<=p.legal<=16:raise ValueError('PL8 parent support drift')
            out[p.pid]=p
    if sorted(out)!=list(range(8000)):raise ValueError(f'PL8 requires 8000 contiguous parents, got {len(out)}')
    counts={ph:sum(p.phase==ph for p in out.values()) for ph in PHASES}
    if counts!={ph:2000 for ph in PHASES}:raise ValueError(f'PL8 phase quotas drift {counts}')
    return out

def load_groups(path:Path,parents:dict[int,Parent])->list[Sib]:
    out=[]
    with path.open(newline='',encoding='utf-8') as f:
        rd=csv.DictReader(f,delimiter='\t');req={'row_index','parent_id','parent_stm','exact_parent_utility','t_baseline_parent','q1k_parent','q50_parent','q200_parent'}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):raise ValueError(f'PL8 deep fields drift {rd.fieldnames}')
        for r in rd:
            s=Sib(int(r['row_index']),int(r['parent_id']),int(r['parent_stm']),int(r['exact_parent_utility']),float(r['t_baseline_parent']),float(r['q1k_parent']),float(r['q50_parent']),float(r['q200_parent']))
            p=parents.get(s.pid)
            if p is None or p.stm!=s.stm or s.exact not in (-1,0,1,EXACT_SENTINEL):raise ValueError('PL8 deep identity drift')
            out.append(s)
    if [s.row for s in out]!=list(range(len(out))):raise ValueError('PL8 deep row ordering drift')
    return out

def stable(a:Sib,b:Sib)->int:
    if a.pid!=b.pid:raise ValueError('cross-parent pair')
    if a.exact!=EXACT_SENTINEL and b.exact!=EXACT_SENTINEL and a.exact!=b.exact:return 1 if a.exact>b.exact else -1
    d50=a.q50-b.q50;d200=a.q200-b.q200
    if d50==0 or d200==0 or ((d50>0)!=(d200>0)) or abs(d50)<10 or abs(d200)<30:return 0
    return 1 if d200>0 else -1

def accepted_pairs(parent_rows,meta):
    out={}
    for pid,rows0 in parent_rows.items():
        rows=sorted(rows0);pairs=[]
        for k,i in enumerate(rows):
            for j in rows[k+1:]:
                r=stable(meta[i],meta[j])
                if r>0:pairs.append((i,j))
                elif r<0:pairs.append((j,i))
        if pairs:out[pid]=pairs
    return out

def load_scores(path:Path,meta:list[Sib]):
    cols={k:np.empty(len(meta),dtype=np.float64) for k in ('t0_parent','pl8_parent','t1_parent','micro1000_parent')};seen=0
    with path.open(newline='',encoding='utf-8') as f:
        rd=csv.DictReader(f,delimiter='\t');want=['row_index','t0_parent','pl8_parent','t1_parent','micro1000_parent']
        if rd.fieldnames!=want:raise ValueError('PL8 scalar score fields drift')
        for r in rd:
            i=int(r['row_index'])
            if i!=seen or i>=len(meta):raise ValueError('PL8 score ordering drift')
            for k in cols:cols[k][i]=float(r[k])
            seen+=1
    if seen!=len(meta) or any(not np.all(np.isfinite(v)) for v in cols.values()):raise ValueError('PL8 score count/finite drift')
    teacher_t0=np.asarray([m.t0 for m in meta])
    if np.any(cols['t0_parent']!=teacher_t0):raise ValueError('T0 scalar mismatch vs deep teacher')
    return cols

def parent_metrics(rows,pairs,score):
    acc=[];incoming=set();participating=set()
    for good,bad in pairs:
        participating.update((good,bad));incoming.add(bad)
        acc.append(1.0 if score[good]>score[bad] else (0.5 if score[good]==score[bad] else 0.0))
    tops=participating-incoming
    vals=np.asarray([score[i] for i in rows]);mx=vals.max();model_top=[rows[k] for k,v in enumerate(vals) if v==mx]
    return float(np.mean(acc)),float(np.mean([i in tops for i in model_top]))
def metrics(parent_rows,pairs,ids,score):
    pp=[];tt=[]
    for pid in ids:
        a,b=parent_metrics(parent_rows[pid],pairs[pid],score);pp.append(a);tt.append(b)
    return {'pairwise':np.asarray(pp),'top_hit':np.asarray(tt)}
def boot_delta(a,b,samples=BOOTSTRAP_SAMPLES,seed=BOOTSTRAP_SEED):
    pd=a['pairwise']-b['pairwise'];td=a['top_hit']-b['top_hit'];n=len(pd)
    if n==0:raise ValueError('no accepted PL8 parents')
    rng=np.random.Generator(np.random.PCG64(seed));pb=np.empty(samples);tb=np.empty(samples)
    for st in range(0,samples,128):
        en=min(samples,st+128);idx=rng.integers(0,n,size=(en-st,n));pb[st:en]=pd[idx].mean(1);tb[st:en]=td[idx].mean(1)
    def one(d,z):return {'mean':float(d.mean()),'ci_low':float(np.quantile(z,.025)),'ci_high':float(np.quantile(z,.975)),'probability_gt_zero':float(np.mean(z>0)),'samples':samples,'seed':seed,'cluster':'parent'}
    return {'pairwise':one(pd,pb),'top_hit':one(td,tb)}
def summarize(m):return {k:float(v.mean()) for k,v in m.items()}

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--parents',type=Path,required=True);ap.add_argument('--groups',type=Path,required=True);ap.add_argument('--scores',type=Path,required=True);ap.add_argument('--anchor-report',type=Path,required=True);ap.add_argument('--model-sha',required=True);ap.add_argument('--report',type=Path,required=True);a=ap.parse_args()
    parents=load_parents(a.parents);meta=load_groups(a.groups,parents);scores=load_scores(a.scores,meta)
    anchor=json.loads(a.anchor_report.read_text());anchor_ok=(anchor.get('schema')=='jass.pl8_anchor.v1' and anchor.get('states')==500000 and anchor.get('seed')==2026103102 and anchor.get('serialize_reload') is True and float(anchor.get('rms_abs_cp',1e99))<=12 and float(anchor.get('p99_abs_cp',1e99))<=35)
    if not anchor_ok:raise ValueError('PL8 anchor guard failed')
    parent_rows=defaultdict(list)
    for i,s in enumerate(meta):parent_rows[s.pid].append(i)
    if set(parent_rows)!=set(parents):raise ValueError('PL8 deep teacher missing parents')
    pairs=accepted_pairs(parent_rows,meta);accepted=sorted(pairs)
    if not accepted:raise ValueError('PL8 has no stable-pair support')
    m0=metrics(parent_rows,pairs,accepted,scores['t0_parent']);mp=metrics(parent_rows,pairs,accepted,scores['pl8_parent']);mt1=metrics(parent_rows,pairs,accepted,scores['t1_parent']);mm=metrics(parent_rows,pairs,accepted,scores['micro1000_parent'])
    boot=boot_delta(mp,m0)
    phase={};represented=[]
    for ph in PHASES:
        ids=[p for p in accepted if parents[p].phase==ph]
        if ids:
            represented.append(ph);x=metrics(parent_rows,pairs,ids,scores['pl8_parent'])['pairwise'];y=metrics(parent_rows,pairs,ids,scores['t0_parent'])['pairwise'];phase[ph]={'accepted_parents':len(ids),'pairwise_delta':float((x-y).mean())}
        else:phase[ph]={'accepted_parents':0,'pairwise_delta':None}
    colour={};colour_ok=True
    for stm,name in ((0,'white'),(1,'black')):
        ids=[p for p in accepted if parents[p].stm==stm]
        if ids:
            x=metrics(parent_rows,pairs,ids,scores['pl8_parent'])['pairwise'];y=metrics(parent_rows,pairs,ids,scores['t0_parent'])['pairwise'];d=float((x-y).mean());colour[name]={'accepted_parents':len(ids),'pairwise_delta':d};colour_ok &= d>0
        else:colour[name]={'accepted_parents':0,'pairwise_delta':None};colour_ok=False
    gates={'pl8_minus_t0_pairwise_ci95_low_gt_zero':bool(boot['pairwise']['ci_low']>0),'pl8_minus_t0_top_hit_ci95_low_gt_zero':bool(boot['top_hit']['ci_low']>0),'positive_pairwise_delta_every_represented_phase':bool(represented and all(phase[p]['pairwise_delta']>0 for p in represented)),'positive_pairwise_delta_both_colours':bool(colour_ok),'anchor_guards_survive_serialize_reload':True}
    passed=all(gates.values());verdict='PL8_DEEP_TRANSFER_ESTABLISHED' if passed else 'PL8_DEEP_TRANSFER_NOT_ESTABLISHED'
    report={'schema':'jass.pl8_deep_transfer.v1','verdict':verdict,'passed':passed,'experiment_terminal':not passed,'next_stage':'PL8_RUNTIME_CHARACTERIZATION' if passed else None,'model_sha256':a.model_sha,'selected_parents':8000,'phase_selected':{ph:2000 for ph in PHASES},'accepted_parents':len(accepted),'stable_pairs':sum(len(v) for v in pairs.values()),'represented_phases':represented,'metrics':{'t0':summarize(m0),'pl8':summarize(mp),'old_t1_diagnostic':summarize(mt1),'micro1000_diagnostic':summarize(mm)},'delta_pl8_minus_t0':boot,'phase_deltas':phase,'colour_deltas':colour,'bootstrap':{'samples':BOOTSTRAP_SAMPLES,'seed':BOOTSTRAP_SEED,'cluster':'parent'},'stable_pair_rule':{'same_sign_50k_200k':True,'min_abs_d50_cp':10,'min_abs_d200_cp':30,'exact_terminal_tb_wdl_precedence':True,'teacher_target':'q200_parent'},'gates':gates,'anchor':anchor,'fit_runs_this_stage':0,'fresh_deep_labels':True,'strength_games':0,'runtime_micro_search':False,'f6_present_at_inference':False,'d_present_at_inference':False,'d1_present_at_inference':False,'rich_d_present_at_inference':False,'promotion_authorized':False}
    a.report.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'verdict':verdict,'accepted_parents':len(accepted),'pairwise':boot['pairwise'],'top_hit':boot['top_hit']},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
