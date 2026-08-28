#!/usr/bin/env python3
"""Historical OOS screen for L3_RESIDUAL_FEATURE_DISCOVERY_V1_20260828.

Fits every preregistered residual family on DSSD-A only, evaluates frozen probes
on DSSD-B and Rich-D-C, runs parent-cluster bootstrap and 32 deterministic
parent-sign shams/family, and selects at most one winner by the frozen rules.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import numpy as np

from jobs.tools import residual_feature_probe as rf
from jobs.tools.deep_sibling_pairwise import load_feat

PHASES=("P0","P1","P2","P3")
EXACT_SENTINEL=2
BOOTSTRAP_SAMPLES=100_000
BOOTSTRAP_SEED=2026090702
D1_SHA="e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49"
MOVE_NAMES=["num_captures","captured_kings","promotes","moving_king","from_norm","to_norm"]

@dataclass(frozen=True)
class Parent:
    parent_id:int; stm:int; phase:str; canonical:str
@dataclass(frozen=True)
class Sibling:
    row_index:int; parent_id:int; parent_stm:int; from_sq:int; to_sq:int
    num_captures:int; captured_kings:int; promotes:int; moving_king:int
    exact_parent_utility:int; q50_parent:float; q200_parent:float
@dataclass
class Cohort:
    name:str; parents:dict[int,Parent]; meta:list[Sibling]; features:np.ndarray; eval120:np.ndarray
    parent_rows:dict[int,list[int]]; pairs:dict[int,list[tuple[int,int]]]; d1:np.ndarray

def load_parents(path:Path)->dict[int,Parent]:
    out={}
    with path.open(newline="",encoding="utf-8") as f:
        rd=csv.DictReader(f,delimiter="\t")
        req={"parent_id","parent_stm","phase","canonical_fingerprint"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames): raise ValueError(f"parent fields drift: {rd.fieldnames}")
        for r in rd:
            p=Parent(int(r["parent_id"]),int(r["parent_stm"]),r["phase"],r["canonical_fingerprint"])
            if p.parent_id in out or p.stm not in (0,1) or p.phase not in PHASES or not p.canonical: raise ValueError("invalid parent")
            out[p.parent_id]=p
    if sorted(out)!=list(range(len(out))): raise ValueError("parent ids drift")
    return out

def load_groups(path:Path,parents:dict[int,Parent])->list[Sibling]:
    out=[]
    with path.open(newline="",encoding="utf-8") as f:
        rd=csv.DictReader(f,delimiter="\t")
        req={"row_index","parent_id","parent_stm","from","to","num_captures","captured_kings","promotes","moving_king","exact_parent_utility","q50_parent","q200_parent"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames): raise ValueError(f"group fields drift: {rd.fieldnames}")
        for r in rd:
            s=Sibling(int(r["row_index"]),int(r["parent_id"]),int(r["parent_stm"]),int(r["from"]),int(r["to"]),int(r["num_captures"]),int(r["captured_kings"]),int(r["promotes"]),int(r["moving_king"]),int(r["exact_parent_utility"]),float(r["q50_parent"]),float(r["q200_parent"]))
            p=parents.get(s.parent_id)
            if p is None or p.stm!=s.parent_stm or s.exact_parent_utility not in (-1,0,1,EXACT_SENTINEL): raise ValueError("group identity drift")
            out.append(s)
    if [x.row_index for x in out]!=list(range(len(out))): raise ValueError("row index drift")
    return out

def stable_relation(a:Sibling,b:Sibling)->int:
    if a.parent_id!=b.parent_id: raise ValueError("cross-parent pair")
    if a.exact_parent_utility!=EXACT_SENTINEL and b.exact_parent_utility!=EXACT_SENTINEL and a.exact_parent_utility!=b.exact_parent_utility:
        return 1 if a.exact_parent_utility>b.exact_parent_utility else -1
    d50=a.q50_parent-b.q50_parent; d200=a.q200_parent-b.q200_parent
    if d50==0 or d200==0 or ((d50>0)!=(d200>0)) or abs(d50)<10 or abs(d200)<30: return 0
    return 1 if d200>0 else -1

def accepted(parent_rows,meta):
    out={}
    for pid,rows0 in sorted(parent_rows.items()):
        rows=sorted(rows0); pp=[]
        for k,i in enumerate(rows):
            for j in rows[k+1:]:
                rel=stable_relation(meta[i],meta[j])
                if rel>0: pp.append((i,j))
                elif rel<0: pp.append((j,i))
        if pp: out[pid]=pp
    return out

def move_features(meta:Sequence[Sibling])->np.ndarray:
    return np.asarray([[m.num_captures,m.captured_kings,m.promotes,m.moving_king,m.from_sq/50.0,m.to_sq/50.0] for m in meta],dtype=np.float64)

def load_d1(path:Path)->dict:
    raw=path.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
    if sha!=D1_SHA: raise ValueError(f"D1 sha drift {sha}")
    p=json.loads(raw)
    if p.get("schema")!="jass.deep_sibling_policy.v1" or p.get("usable") is not True or p.get("eval_feature_width")!=120: raise ValueError("D1 schema drift")
    if p.get("move_feature_names")!=MOVE_NAMES or p.get("score_convention")!="higher_is_better_for_parent": raise ValueError("D1 contract drift")
    return p

def d1_scores(policy:dict,eval120:np.ndarray,meta:Sequence[Sibling])->np.ndarray:
    x=np.concatenate((eval120,move_features(meta)),axis=1); out=np.empty(len(meta),dtype=np.float64)
    for i,m in enumerate(meta):
        bank="white_parent" if m.parent_stm==0 else "black_parent"
        w=np.asarray(policy["weights"][bank],dtype=np.float64)
        if len(w)!=126: raise ValueError("D1 width drift")
        out[i]=float(x[i]@w)
    return out

def make_cohort(name,parents_path,groups_path,rffd_path,feat_path,policy):
    parents=load_parents(parents_path); meta=load_groups(groups_path,parents)
    f=rf.read_rffd(rffd_path); e=load_feat(feat_path)
    if len(meta)!=len(f) or len(meta)!=len(e): raise ValueError(f"{name} row geometry drift")
    rows=defaultdict(list)
    for i,m in enumerate(meta): rows[m.parent_id].append(i)
    if set(rows)!=set(parents): raise ValueError(f"{name} missing parent")
    pairs=accepted(rows,meta)
    return Cohort(name,parents,meta,f,e,dict(rows),pairs,d1_scores(policy,e,meta))

def parent_metric(rows,pairs,score):
    acc=[]; incoming=set(); participating=set()
    for g,b in pairs:
        participating.update((g,b)); incoming.add(b)
        acc.append(1.0 if score[g]>score[b] else 0.5 if score[g]==score[b] else 0.0)
    tops=participating-incoming
    vals=np.asarray([score[i] for i in rows]); mx=vals.max(); model=[rows[k] for k,v in enumerate(vals) if v==mx]
    return float(np.mean(acc)),float(np.mean([i in tops for i in model]))

def parent_arrays(c:Cohort,score:np.ndarray):
    ids=sorted(c.pairs); pair=[]; top=[]
    for pid in ids:
        a,b=parent_metric(c.parent_rows[pid],c.pairs[pid],score); pair.append(a); top.append(b)
    return ids,np.asarray(pair),np.asarray(top)

def point_delta(c:Cohort,score:np.ndarray,base:np.ndarray,ids_filter=None):
    ids,a,t=parent_arrays(c,score); _,ba,bt=parent_arrays(c,base)
    if ids_filter is not None:
        mask=np.asarray([ids_filter(c.parents[p]) for p in ids],dtype=bool); a=a[mask];t=t[mask];ba=ba[mask];bt=bt[mask]
    return {"parents":int(len(a)),"pairwise":float(np.mean(a-ba)) if len(a) else math.nan,"top_hit":float(np.mean(t-bt)) if len(t) else math.nan}

def pooled_parent_deltas(cohorts,score_map):
    pd=[]; td=[]
    for c in cohorts:
        ids,a,t=parent_arrays(c,score_map[c.name]); _,ba,bt=parent_arrays(c,c.d1)
        pd.extend(a-ba); td.extend(t-bt)
    return np.asarray(pd),np.asarray(td)

def bootstrap(pd,td,samples=BOOTSTRAP_SAMPLES,seed=BOOTSTRAP_SEED):
    if len(pd)==0 or len(pd)!=len(td): raise ValueError("bootstrap geometry")
    rng=np.random.default_rng(seed); n=len(pd); pb=np.empty(samples);tb=np.empty(samples)
    for start in range(0,samples,128):
        stop=min(samples,start+128); idx=rng.integers(0,n,size=(stop-start,n))
        pb[start:stop]=pd[idx].mean(1); tb[start:stop]=td[idx].mean(1)
    def one(v,b): return {"mean":float(v.mean()),"ci_low":float(np.quantile(b,.025)),"ci_high":float(np.quantile(b,.975)),"probability_gt_zero":float(np.mean(b>0)),"samples":samples,"seed":seed}
    return {"pairwise":one(pd,pb),"top_hit":one(td,tb)}

def train_pairs(c:Cohort):
    g=[];b=[];fps=[]
    for pid in sorted(c.pairs):
        fp=c.parents[pid].canonical
        for good,bad in c.pairs[pid]: g.append(good);b.append(bad);fps.append(fp)
    g=np.asarray(g,dtype=np.int64);b=np.asarray(b,dtype=np.int64)
    keep=rf.deterministic_pair_cap(g,b,fps)
    return g[keep],b[keep],[fps[i] for i in keep]

def row_fps(c:Cohort): return [c.parents[m.parent_id].canonical for m in c.meta]

def run_family(family,A,B,C,artifact_dir,shams=32):
    xa=rf.family_matrix(A.features,family); xb=rf.family_matrix(B.features,family); xc=rf.family_matrix(C.features,family)
    g,b,_=train_pairs(A)
    art=rf.fit_probe(family,xa,A.d1,g,b,d1_sha256=D1_SHA)
    artifact_dir.mkdir(parents=True,exist_ok=True); p=artifact_dir/f"{family}.json"; rf.save_artifact(p,art); replay=rf.load_artifact(p)
    sa=art.predict(xa,A.d1); sb=art.predict(xb,B.d1); sc=art.predict(xc,C.d1)
    replay_ok=np.array_equal(sb,replay.predict(xb,B.d1)) and np.array_equal(sc,replay.predict(xc,C.d1))
    score_map={B.name:sb,C.name:sc}; pd,td=pooled_parent_deltas((B,C),score_map); boot=bootstrap(pd,td)
    phase={ph:{"pairwise":float(np.mean(np.concatenate([
        (parent_arrays(c,score_map[c.name])[1]-parent_arrays(c,c.d1)[1])[[c.parents[p].phase==ph for p in parent_arrays(c,score_map[c.name])[0]]]
        for c in (B,C)]))} for ph in PHASES}
    color={nm:{"pairwise":float(np.mean(np.concatenate([
        (parent_arrays(c,score_map[c.name])[1]-parent_arrays(c,c.d1)[1])[[c.parents[p].stm==st for p in parent_arrays(c,score_map[c.name])[0]]]
        for c in (B,C)]))} for nm,st in (("white",0),("black",1))}
    sham_deltas=[]; sham_opt=[]
    afp=row_fps(A); bfp=row_fps(B); cfp=row_fps(C)
    for s in range(shams):
        xas=rf.apply_parent_sign_sham(xa,afp,cohort="TRAIN_A",sham_index=s)
        xbs=rf.apply_parent_sign_sham(xb,bfp,cohort="DEV_B",sham_index=s)
        xcs=rf.apply_parent_sign_sham(xc,cfp,cohort="DEV_C",sham_index=s)
        aa=rf.fit_probe(family,xas,A.d1,g,b,d1_sha256=D1_SHA)
        sm={B.name:aa.predict(xbs,B.d1),C.name:aa.predict(xcs,C.d1)}
        sp,_=pooled_parent_deltas((B,C),sm); sham_deltas.append(float(sp.mean())); sham_opt.append(bool(aa.optimizer.get("success")))
    Bp=point_delta(B,sb,B.d1); Cp=point_delta(C,sc,C.d1)
    max_sham=max(sham_deltas)
    gates={
        "pooled_pairwise_ci_low_gt_0":boot["pairwise"]["ci_low"]>0,
        "dev_b_pairwise_point_gt_0":Bp["pairwise"]>0,
        "dev_c_pairwise_point_gt_0":Cp["pairwise"]>0,
        "positive_each_phase":all(phase[x]["pairwise"]>0 for x in PHASES),
        "positive_both_colours":all(color[x]["pairwise"]>0 for x in color),
        "observed_gt_all_32_shams":float(pd.mean())>max_sham,
        "optimizer_success":bool(art.optimizer.get("success")),
        "artifact_replay":bool(replay_ok),
    }
    return {"family":family,"screen_pass":all(gates.values()),"optimizer":art.optimizer,"artifact":str(p),"artifact_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"pairs_train":int(len(g)),"dev_b":Bp,"dev_c":Cp,"pooled":{"pairwise_delta":float(pd.mean()),"top_hit_delta":float(td.mean()),"bootstrap":boot},"phase":phase,"colour":color,"negative_controls":{"count":shams,"pooled_pairwise_deltas":sham_deltas,"max_pooled_pairwise_delta":max_sham,"all_optimizer_success":all(sham_opt)},"gates":gates}

def main():
    ap=argparse.ArgumentParser()
    for c in ("a","b","c"):
        ap.add_argument(f"--{c}-parents",type=Path,required=True);ap.add_argument(f"--{c}-groups",type=Path,required=True);ap.add_argument(f"--{c}-rffd",type=Path,required=True);ap.add_argument(f"--{c}-feat",type=Path,required=True)
    ap.add_argument("--d1",type=Path,required=True);ap.add_argument("--report",type=Path,required=True);ap.add_argument("--artifact-dir",type=Path,required=True)
    args=ap.parse_args(); policy=load_d1(args.d1)
    A=make_cohort("TRAIN_A",args.a_parents,args.a_groups,args.a_rffd,args.a_feat,policy);B=make_cohort("DEV_B",args.b_parents,args.b_groups,args.b_rffd,args.b_feat,policy);C=make_cohort("DEV_C",args.c_parents,args.c_groups,args.c_rffd,args.c_feat,policy)
    families=["CTX2_REF",*rf.ELIGIBLE_FAMILIES]; results=[run_family(f,A,B,C,args.artifact_dir) for f in families]
    eligible=[x for x in results if x["family"]!="CTX2_REF" and x["screen_pass"]]
    lexical={f:i for i,f in enumerate(rf.ELIGIBLE_FAMILIES)}
    winner=None
    if eligible:
        eligible.sort(key=lambda x:(-x["pooled"]["pairwise_delta"],-x["pooled"]["top_hit_delta"],lexical[x["family"]]))
        winner=eligible[0]["family"]
    verdict="RESIDUAL_FEATURE_FAMILY_ESTABLISHED" if winner else "RESIDUAL_FEATURE_FAMILY_NOT_ESTABLISHED"
    report={"schema":"jass.residual_feature_historical_screen.v1","verdict":verdict,"passed":bool(winner),"winner":winner,"bootstrap":{"cluster":"parent","samples":BOOTSTRAP_SAMPLES,"seed":BOOTSTRAP_SEED},"pair_cap_seed":rf.PAIR_ORDER_SEED,"sham_seed_base":rf.SHAM_SEED_BASE,"d1_sha256":D1_SHA,"cohorts":{"TRAIN_A":{"parents":len(A.parents),"accepted":len(A.pairs),"stable_pairs":sum(map(len,A.pairs.values()))},"DEV_B":{"parents":len(B.parents),"accepted":len(B.pairs),"stable_pairs":sum(map(len,B.pairs.values()))},"DEV_C":{"parents":len(C.parents),"accepted":len(C.pairs),"stable_pairs":sum(map(len,C.pairs.values()))}},"families":results,"q1_label_reads":0,"q1_score_reads":0,"t2_fresh_label_reads":0,"t2_fresh_score_reads":0,"fresh_labels":0,"selfplay":0,"strength_games":0,"runtime_elo":0,"bake":False,"promotion_authorized":False,"next_stage":"residual_feature_freeze" if winner else None}
    args.report.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"verdict":verdict,"winner":winner,"screen_pass":[x["family"] for x in eligible]},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
