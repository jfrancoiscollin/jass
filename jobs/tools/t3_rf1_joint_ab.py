#!/usr/bin/env python3
"""Deterministic T3 RF1 joint A/B residual students.

Contract: docs/experiments/L3_T3_RF1_JOINT_AB_V1_20260829.md
A = exact F6(66) -> residual. B = exact F6(66) + one sealed-D1 scalar.
Parent ranking score is T0_parent + residual; equivalently T3_child=T0_child-residual.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
import numpy as np
from jobs.tools import residual_feature_probe as rf

F6_WIDTH=66; A_WIDTH=66; B_WIDTH=67; HIDDEN=(256,128,64)
INIT_SEED=2026090801; ORDER_SEED=2026090802; PAIR_CAP_SEED=2026090803; D1_INIT_SEED=2026090804
BATCH_SIZE=4096; EPOCHS=80; LR0=1e-3; WEIGHT_DECAY=1e-5; GRAD_CLIP=5.0; PAIR_CAP_PER_CELL=150_000
PHASES=("P0","P1","P2","P3"); SCHEMA="jass.t3_rf1_joint_ab.v1"
F6_POSITIONAL_NAMES=tuple(f"F6_ALL_NEW_{i:02d}" for i in range(F6_WIDTH))
FORBIDDEN_INPUT_NAMES=frozenset({"t2","q1000","q5k","q50","q200","wdl","result","source","split","partition","holdout","parent_id","q1","rf1_fresh"})

@dataclass(frozen=True)
class StaticMeta:
    parent_id:int; parent_stm:int; parent_phase:str; t_baseline_parent:float; d1_parent:float
@dataclass(frozen=True)
class Pair:
    parent_id:int; parent_stm:int; parent_phase:str; good:int; bad:int

def _seed_for(name:str,base:int=INIT_SEED)->int:
    return int.from_bytes(hashlib.sha256(f"{SCHEMA}:{base}:{name}".encode()).digest()[:8],"little")
def _he(shape,fan_in,name,base=INIT_SEED):
    return np.random.default_rng(_seed_for(name,base)).standard_normal(shape)*math.sqrt(2.0/fan_in)

def init_paired_models():
    """Nested init: shared F6 block and all common downstream weights are byte-identical."""
    w0=_he((66,256),66,"W0_F6"); w1=_he((256,128),256,"W1"); w2=_he((128,64),128,"W2"); w3=_he((64,1),64,"W3")
    d1=np.random.default_rng(D1_INIT_SEED).standard_normal((1,256))*math.sqrt(2.0/67)
    a={"W0":w0.copy(),"b0":np.zeros(256),"W1":w1.copy(),"b1":np.zeros(128),"W2":w2.copy(),"b2":np.zeros(64),"W3":w3.copy(),"b3":np.zeros(1)}
    b={"W0":np.vstack([w0,d1]),"b0":np.zeros(256),"W1":w1.copy(),"b1":np.zeros(128),"W2":w2.copy(),"b2":np.zeros(64),"W3":w3.copy(),"b3":np.zeros(1)}
    rec={"schema":"jass.t3_nested_init.v1","global_seed":INIT_SEED,"d1_extra_row_seed":D1_INIT_SEED,
         "layer_seed_derivation":f"uint64_le(sha256('{SCHEMA}:<base>:<layer>')[:8])",
         "shared_f6_w0_sha256":hashlib.sha256(w0.tobytes()).hexdigest(),"shared_w1_sha256":hashlib.sha256(w1.tobytes()).hexdigest(),
         "shared_w2_sha256":hashlib.sha256(w2.tobytes()).hexdigest(),"shared_w3_sha256":hashlib.sha256(w3.tobytes()).hexdigest()}
    return a,b,rec

def load_static_meta(path:Path)->list[StaticMeta]:
    out=[]
    with path.open(newline="",encoding="utf-8") as f:
        rd=csv.DictReader(f,delimiter="\t"); req={"parent_id","parent_stm","phase","t_baseline_parent","d1_parent"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames): raise ValueError(f"static-meta fields drift: {rd.fieldnames!r}")
        for r in rd:
            stm=int(r["parent_stm"]); ph=r["phase"]
            if stm not in (0,1) or ph not in PHASES: raise ValueError("invalid parent cell metadata")
            out.append(StaticMeta(int(r["parent_id"]),stm,ph,float(r["t_baseline_parent"]),float(r["d1_parent"])))
    return out

def load_pairs(path:Path,meta:Sequence[StaticMeta])->list[Pair]:
    out=[]
    with path.open(newline="",encoding="utf-8") as f:
        rd=csv.DictReader(f,delimiter="\t"); req={"parent_id","parent_stm","good_row","bad_row"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames): raise ValueError("pair fields drift")
        for r in rd:
            pid,stm,g,b=int(r["parent_id"]),int(r["parent_stm"]),int(r["good_row"]),int(r["bad_row"])
            if not(0<=g<len(meta) and 0<=b<len(meta)): raise ValueError("pair row out of range")
            mg,mb=meta[g],meta[b]
            if (mg.parent_id,mb.parent_id,mg.parent_stm,mb.parent_stm)!=(pid,pid,stm,stm) or mg.parent_phase!=mb.parent_phase: raise ValueError("pair/static metadata mismatch")
            out.append(Pair(pid,stm,mg.parent_phase,g,b))
    return out

def pair_cell(p:Pair): return p.parent_phase,p.parent_stm

def cap_and_weight_pairs(pairs:Sequence[Pair],cap:int=PAIR_CAP_PER_CELL):
    cells={}
    for p in pairs: cells.setdefault(pair_cell(p),[]).append(p)
    if not cells: raise ValueError("no T3 training pairs")
    sel=[]; per={}; counts={}
    for cell in sorted(cells):
        def key(p): return hashlib.sha256(f"{PAIR_CAP_SEED}:{p.parent_id}:{p.good}:{p.bad}".encode()).digest(),p.parent_id,p.good,p.bad
        seq=sorted(cells[cell],key=key)[:cap]; sel.extend(seq); per[cell]=len(seq); counts[f"{cell[0]}_{'white' if cell[1]==0 else 'black'}"]=len(seq)
    ncell=len(per); w=np.asarray([1.0/(ncell*per[pair_cell(p)]) for p in sel],dtype=np.float64)
    if not np.isclose(w.sum(),1.0,rtol=0,atol=1e-12): raise AssertionError("balanced pair weights drift")
    return sel,w,counts

def fit_normalization(x:np.ndarray,row_ids:Iterable[int]):
    ids=np.asarray(sorted(set(map(int,row_ids))),dtype=np.int64)
    if not len(ids): raise ValueError("no normalization rows")
    mean=x[ids].mean(0); std=x[ids].std(0); std[std<1e-8]=1.0
    return mean,std

def forward(m,x):
    z0=x@m["W0"]+m["b0"];a0=np.maximum(z0,0);z1=a0@m["W1"]+m["b1"];a1=np.maximum(z1,0);z2=a1@m["W2"]+m["b2"];a2=np.maximum(z2,0);o=(a2@m["W3"]+m["b3"])[:,0]
    return o,(x,z0,a0,z1,a1,z2,a2)
def backward(m,c,go):
    x,z0,a0,z1,a1,z2,a2=c; go=go[:,None]; g={}
    g["W3"]=a2.T@go;g["b3"]=go.sum(0);gz2=(go@m["W3"].T)*(z2>0);g["W2"]=a1.T@gz2;g["b2"]=gz2.sum(0);gz1=(gz2@m["W2"].T)*(z1>0);g["W1"]=a0.T@gz1;g["b1"]=gz1.sum(0);gz0=(gz1@m["W1"].T)*(z0>0);g["W0"]=x.T@gz0;g["b0"]=gz0.sum(0);return g
def _clip(g):
    n=math.sqrt(sum(float(np.sum(v*v)) for v in g.values()))
    if n>GRAD_CLIP:
        s=GRAD_CLIP/n
        for k in g:g[k]*=s
    return n
def lr_for_epoch(e):
    lr=LR0
    if e>=40:lr*=.3
    if e>=60:lr*=.3
    return lr

def train_model(model,x,base_parent,pairs,mean,std):
    ps,w,counts=cap_and_weight_pairs(pairs);xn=(x-mean)/std;am={k:np.zeros_like(v) for k,v in model.items()};av={k:np.zeros_like(v) for k,v in model.items()};rng=np.random.default_rng(ORDER_SEED);base=np.arange(len(ps));step=0;hist=[];b1,b2,eps=.9,.999,1e-8
    for epoch in range(EPOCHS):
        order=base.copy();rng.shuffle(order);loss=0.;maxnorm=0.
        for start in range(0,len(order),BATCH_SIZE):
            ii=order[start:start+BATCH_SIZE];good=np.asarray([ps[int(j)].good for j in ii]);bad=np.asarray([ps[int(j)].bad for j in ii]);bw=w[ii];rows=np.concatenate([good,bad]);rr,cache=forward(model,xn[rows]);n=len(good);d=(base_parent[good]+rr[:n])-(base_parent[bad]+rr[n:]);loss+=float(np.dot(bw,np.logaddexp(0,-d)));dd=-1/(1+np.exp(np.clip(d,-60,60)));fac=bw*len(ps)/BATCH_SIZE;grad=np.concatenate([dd*fac,-dd*fac]);gr=backward(model,cache,grad)
            for k in gr:
                if k.startswith("W"):gr[k]+=WEIGHT_DECAY*model[k]
            maxnorm=max(maxnorm,_clip(gr));step+=1;lr=lr_for_epoch(epoch)
            for k in model:
                am[k]=b1*am[k]+(1-b1)*gr[k];av[k]=b2*av[k]+(1-b2)*(gr[k]*gr[k]);mh=am[k]/(1-b1**step);vh=av[k]/(1-b2**step);model[k]-=lr*mh/(np.sqrt(vh)+eps)
        if not all(np.all(np.isfinite(v)) for v in model.values()):raise FloatingPointError("nonfinite T3 parameters")
        hist.append({"epoch":epoch+1,"lr":lr_for_epoch(epoch),"weighted_pairwise_logloss":loss,"pairs":len(ps),"max_preclip_grad_norm":maxnorm})
    return model,{"pairs":len(ps),"cell_counts":counts,"history":hist}

def build_inputs(rffd:Path,meta:Sequence[StaticMeta]):
    f6=rf.family_matrix(rf.read_rffd(rffd),"F6_ALL_NEW")
    if f6.shape!=(len(meta),66):raise ValueError(f"F6 geometry drift {f6.shape}")
    d1=np.asarray([m.d1_parent for m in meta],dtype=np.float64); xb=np.concatenate([f6,d1[:,None]],1);base=np.asarray([m.t_baseline_parent for m in meta],dtype=np.float64)
    if not(np.all(np.isfinite(f6)) and np.all(np.isfinite(xb)) and np.all(np.isfinite(base))):raise ValueError("nonfinite T3 inputs")
    return f6,xb,base

def parent_scores(model,x,base,mean,std): return base+forward(model,(x-mean)/std)[0]
def _params(m):return {k:v.tolist() for k,v in sorted(m.items())}
def _save(path,p):
    raw=(json.dumps(p,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode();path.write_bytes(raw);return hashlib.sha256(raw).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--rffd",type=Path,required=True);ap.add_argument("--static-meta",type=Path,required=True);ap.add_argument("--pairs",type=Path,required=True);ap.add_argument("--output-a",type=Path,required=True);ap.add_argument("--output-b",type=Path,required=True);ap.add_argument("--receipt",type=Path,required=True);ap.add_argument("--t0-sha",required=True);ap.add_argument("--d1-sha",required=True);ap.add_argument("--rf1-sha",required=True);args=ap.parse_args()
    meta=load_static_meta(args.static_meta);pairs=load_pairs(args.pairs,meta);xa,xb,base=build_inputs(args.rffd,meta);sel,_,cells=cap_and_weight_pairs(pairs);rows=[p.good for p in sel]+[p.bad for p in sel];mf,sf=fit_normalization(xa,rows);md,sd=fit_normalization(xb[:,66:67],rows);mb=np.concatenate([mf,md]);sb=np.concatenate([sf,sd]);ma,mbm,init=init_paired_models();ma,ra=train_model(ma,xa,base,pairs,mf,sf);mbm,rb=train_model(mbm,xb,base,pairs,mb,sb)
    common={"schema":SCHEMA,"score_convention":"higher_is_better_for_parent","base":"byte-identical T0 parent score, coefficient 1","architecture":{"hidden":list(HIDDEN),"relu_hidden":True,"linear_output":True},"optimization":{"optimizer":"adam","init_seed":INIT_SEED,"order_seed":ORDER_SEED,"pair_cap_seed":PAIR_CAP_SEED,"d1_init_seed":D1_INIT_SEED,"batch_size":BATCH_SIZE,"epochs":EPOCHS,"lr0":LR0,"lr_multiplier_after_epochs":{"40":.3,"60":.3},"weight_decay":WEIGHT_DECAY,"grad_clip":GRAD_CLIP,"pair_cap_per_phase_colour_cell":PAIR_CAP_PER_CELL,"equal_cell_total_weight":True},"provenance":{"t0_sha256":args.t0_sha,"d1_sha256":args.d1_sha,"rf1_sha256":args.rf1_sha},"nested_initialization":init,"forbidden_inputs":sorted(FORBIDDEN_INPUT_NAMES)}
    pa=dict(common);pa.update({"arm":"T3_F6_ONLY","input_width":66,"input_names":list(F6_POSITIONAL_NAMES),"input_semantics":"exact frozen F6_ALL_NEW packed order","normalization":{"mean":mf.tolist(),"std":sf.tolist()},"params":_params(ma),"training":ra})
    pb=dict(common);pb.update({"arm":"T3_JOINT_D1_F6","input_width":67,"input_names":list(F6_POSITIONAL_NAMES)+["sealed_d1_parent_score"],"input_semantics":"exact frozen F6_ALL_NEW packed order plus sealed D1 scalar last","normalization":{"mean":mb.tolist(),"std":sb.tolist()},"params":_params(mbm),"training":rb})
    sha_a=_save(args.output_a,pa);sha_b=_save(args.output_b,pb);receipt={"schema":"jass.t3_rf1_joint_ab_train_receipt.v1","artifact_a_sha256":sha_a,"artifact_b_sha256":sha_b,"pairs":len(sel),"cell_counts":cells,"shared_f6_normalization":True,"shared_pair_list_and_order":True,"q1_label_reads":0,"q1_score_reads":0,"t2_fresh_label_reads":0,"t2_fresh_score_reads":0,"rf1_fresh_label_reads":0,"rf1_fresh_score_reads":0};args.receipt.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n");print(json.dumps(receipt,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
