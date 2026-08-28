#!/usr/bin/env python3
"""Deterministic T2 phase-specialist state-only student.

Frozen scientific contract:
- 326 child-state inputs only: 120 production extras + 200 board bits +
  T0 child scalar + child STM + 4 hard child-phase indicators.
- No move-local, parent-context, D1, q1000/q5k/q50/q200/WDL/source/Q1 inputs.
- Shared 326->256->128 ReLU trunk, four hard phase heads 128->64->1 ReLU.
- T2(child)=T0(child)+residual; parent score = -T2(child).
- One shared network across colours.
- Deterministic Adam and equal total pairwise objective weight per nonempty
  parent phase x parent-colour cell.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, math, struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
import numpy as np

INPUT_WIDTH=326; EVAL_WIDTH=120; BOARD_WIDTH=200; PHASE_WIDTH=4
TRUNK=(256,128); HEAD_HIDDEN=64; PHASES=("P0","P1","P2","P3")
INIT_SEED=2026090601; PAIR_ORDER_SEED=2026090602; BATCH_SIZE=4096; EPOCHS=80
LR0=1e-3; WEIGHT_DECAY=1e-5; GRAD_CLIP=5.0; PAIR_CAP_PER_CELL=150_000
JNNW_DTYPE=np.dtype([("wm","<u8"),("wk","<u8"),("bm","<u8"),("bk","<u8"),("stm","u1"),("score","<i4"),("wdl","i1")]); assert JNNW_DTYPE.itemsize==38
FORBIDDEN_INPUT_NAMES=frozenset({"from","to","num_captures","captured_kings","promotes","moving_king","parent_phase","parent_stm","parent_colour","parent_legal_moves","parent_id","d1","d1_score","q1000","q5k","q50","q200","wdl","source","partition","holdout","q1","q1_metric","q1_score","q1_label"})

@dataclass(frozen=True)
class StaticMeta:
    parent_id:int; parent_stm:int; parent_phase:str; t_baseline_parent:float
@dataclass(frozen=True)
class Pair:
    parent_id:int; parent_stm:int; parent_phase:str; good:int; bad:int

def phase_from_pieces(pieces:int)->int:
    if 30<=pieces<=40:return 0
    if 20<=pieces<=29:return 1
    if 12<=pieces<=19:return 2
    if 0<=pieces<=11:return 3
    raise ValueError(f"piece count outside child phase contract: {pieces}")

def read_jnnw(path:Path)->np.ndarray:
    size=path.stat().st_size
    if size<8:raise ValueError("JNNW truncated")
    with path.open("rb") as f:hdr=f.read(8)
    if hdr[:4]!=b"JNNW":raise ValueError("bad JNNW magic")
    n=struct.unpack_from("<I",hdr,4)[0]
    if size!=8+38*n:raise ValueError("JNNW size/count drift")
    return np.empty(0,dtype=JNNW_DTYPE) if n==0 else np.memmap(path,dtype=JNNW_DTYPE,mode="r",offset=8,shape=(n,))

def read_feat(path:Path)->np.ndarray:
    raw=path.read_bytes()
    if len(raw)<12 or raw[:4]!=b"FEAT":raise ValueError("bad FEAT header")
    n,k=struct.unpack_from("<II",raw,4)
    if k!=120 or len(raw)!=12+n*k*4:raise ValueError("FEAT geometry drift")
    return np.frombuffer(raw,dtype="<f4",offset=12,count=n*k).reshape(n,k).astype(np.float64)

def board_planes(records:np.ndarray)->np.ndarray:
    out=np.empty((len(records),200),dtype=np.float64)
    for pi,field in enumerate(("wm","wk","bm","bk")):
        vals=np.asarray(records[field],dtype=np.uint64)
        for sq in range(50):out[:,pi*50+sq]=((vals>>np.uint64(sq))&np.uint64(1)).astype(np.float64)
    return out

def child_piece_counts(records:np.ndarray)->np.ndarray:
    out=np.zeros(len(records),dtype=np.int16)
    for field in ("wm","wk","bm","bk"):
        out+=np.fromiter((int(v).bit_count() for v in records[field]),dtype=np.int16,count=len(records))
    return out

def load_static_meta(path:Path)->list[StaticMeta]:
    out=[]
    with path.open(newline="",encoding="utf-8") as f:
        rd=csv.DictReader(f,delimiter="\t"); req={"parent_id","parent_stm","phase","t_baseline_parent"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):raise ValueError(f"static-meta fields drift: {rd.fieldnames!r}")
        for r in rd:
            stm=int(r["parent_stm"]); ph=r["phase"]
            if stm not in (0,1) or ph not in PHASES:raise ValueError("invalid parent cell metadata")
            out.append(StaticMeta(int(r["parent_id"]),stm,ph,float(r["t_baseline_parent"])))
    return out

def build_state_features(eval_features:np.ndarray,records:np.ndarray,meta:Sequence[StaticMeta])->tuple[np.ndarray,np.ndarray,np.ndarray]:
    """Build exact 326 allowed inputs; deliberately accepts no forbidden data."""
    n=len(meta)
    if eval_features.shape!=(n,120) or len(records)!=n:raise ValueError("row alignment drift")
    x=np.empty((n,326),dtype=np.float64); x[:,:120]=eval_features; x[:,120:320]=board_planes(records)
    # Teacher metadata stores parent-POV T0 child score; child-STM scalar is exact negation.
    t0_child=-np.asarray([m.t_baseline_parent for m in meta],dtype=np.float64); x[:,320]=t0_child
    stm=np.asarray(records["stm"],dtype=np.int8)
    if not np.all((stm==0)|(stm==1)):raise ValueError("invalid child STM")
    x[:,321]=stm.astype(np.float64)
    phases=np.asarray([phase_from_pieces(int(pc)) for pc in child_piece_counts(records)],dtype=np.int8)
    x[:,322:326]=0.0; x[np.arange(n),322+phases.astype(np.int64)]=1.0
    if not np.all(np.isfinite(x)):raise ValueError("T2 input contract drift")
    return x,t0_child,phases

def load_pairs(path:Path,meta:Sequence[StaticMeta])->list[Pair]:
    out=[]
    with path.open(newline="",encoding="utf-8") as f:
        rd=csv.DictReader(f,delimiter="\t"); req={"parent_id","parent_stm","good_row","bad_row"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):raise ValueError("pair fields drift")
        for r in rd:
            g,b=int(r["good_row"]),int(r["bad_row"]); pid,stm=int(r["parent_id"]),int(r["parent_stm"])
            if not(0<=g<len(meta) and 0<=b<len(meta)):raise ValueError("pair row out of range")
            mg,mb=meta[g],meta[b]
            if (mg.parent_id,mb.parent_id,mg.parent_stm,mb.parent_stm)!=(pid,pid,stm,stm) or mg.parent_phase!=mb.parent_phase:raise ValueError("pair/static metadata mismatch")
            out.append(Pair(pid,stm,mg.parent_phase,g,b))
    return out

def pair_cell(p:Pair)->tuple[str,int]:return p.parent_phase,p.parent_stm

def cap_and_weight_pairs(pairs:Sequence[Pair],cap:int=PAIR_CAP_PER_CELL)->tuple[list[Pair],np.ndarray,dict[str,int]]:
    cells={}
    for p in pairs:cells.setdefault(pair_cell(p),[]).append(p)
    if not cells:raise ValueError("no T2 training pairs")
    selected=[]; counts={}; per_cell={}
    for cell in sorted(cells):
        def key(p):return hashlib.sha256(f"{PAIR_ORDER_SEED}:{p.parent_id}:{p.good}:{p.bad}".encode()).digest(),p.parent_id,p.good,p.bad
        seq=sorted(cells[cell],key=key)[:cap]; selected.extend(seq); per_cell[cell]=len(seq); counts[f"{cell[0]}_{'white' if cell[1]==0 else 'black'}"]=len(seq)
    ncell=len(per_cell); weights=np.asarray([1.0/(ncell*per_cell[pair_cell(p)]) for p in selected],dtype=np.float64)
    if not np.isclose(weights.sum(),1.0,rtol=0,atol=1e-12):raise AssertionError("balanced pair weights drift")
    return selected,weights,counts

def fit_normalization(x:np.ndarray,row_ids:Iterable[int])->tuple[np.ndarray,np.ndarray]:
    ids=np.asarray(sorted(set(map(int,row_ids))),dtype=np.int64)
    if not len(ids):raise ValueError("no train rows")
    mean=x[ids].mean(axis=0); std=x[ids].std(axis=0); std[std<1e-8]=1.0; return mean,std

def init_model(seed:int=INIT_SEED)->dict[str,np.ndarray]:
    rng=np.random.default_rng(seed); m={}; dims=(326,256,128)
    for i in range(2):m[f"TW{i}"]=rng.standard_normal((dims[i],dims[i+1]))*math.sqrt(2/dims[i]);m[f"Tb{i}"]=np.zeros(dims[i+1])
    for p in range(4):
        m[f"H{p}W0"]=rng.standard_normal((128,64))*math.sqrt(2/128);m[f"H{p}b0"]=np.zeros(64)
        m[f"H{p}W1"]=rng.standard_normal((64,1))*math.sqrt(2/64);m[f"H{p}b1"]=np.zeros(1)
    return m

def forward_residual(model,x,phases):
    z0=x@model["TW0"]+model["Tb0"];a0=np.maximum(z0,0);z1=a0@model["TW1"]+model["Tb1"];h=np.maximum(z1,0);r=np.empty(len(x));heads={}
    for p in range(4):
        idx=np.flatnonzero(phases==p)
        if not len(idx):continue
        zh=h[idx]@model[f"H{p}W0"]+model[f"H{p}b0"];ah=np.maximum(zh,0);r[idx]=(ah@model[f"H{p}W1"]+model[f"H{p}b1"])[:,0];heads[p]=(idx,zh,ah)
    return r,(x,z0,a0,z1,h,heads)

def backward_residual(model,cache,grad_r):
    x,z0,a0,z1,h,heads=cache;g={k:np.zeros_like(v) for k,v in model.items()};gh=np.zeros_like(h)
    for p,(idx,zh,ah) in heads.items():
        go=grad_r[idx,None];g[f"H{p}W1"]=ah.T@go;g[f"H{p}b1"]=go.sum(0);gz=(go@model[f"H{p}W1"].T)*(zh>0);g[f"H{p}W0"]=h[idx].T@gz;g[f"H{p}b0"]=gz.sum(0);gh[idx]+=gz@model[f"H{p}W0"].T
    gz1=gh*(z1>0);g["TW1"]=a0.T@gz1;g["Tb1"]=gz1.sum(0);gz0=(gz1@model["TW1"].T)*(z0>0);g["TW0"]=x.T@gz0;g["Tb0"]=gz0.sum(0);return g

def clip_grads(grads):
    norm=math.sqrt(sum(float(np.sum(v*v)) for v in grads.values()))
    if norm>5:
        s=5/norm
        for k in grads:grads[k]*=s
    return norm

def lr_for_epoch(epoch):
    lr=1e-3
    if epoch>=40:lr*=.3
    if epoch>=60:lr*=.3
    return lr

def parent_scores(model,xn,t0_child,phases):return -(t0_child+forward_residual(model,xn,phases)[0])
def _is_weight(k):return "W" in k and not k.startswith("Tb")

def train_model(x,t0_child,phases,pairs,mean,std):
    ps,w,counts=cap_and_weight_pairs(pairs);xn=(x-mean)/std;model=init_model();am={k:np.zeros_like(v) for k,v in model.items()};av={k:np.zeros_like(v) for k,v in model.items()};rng=np.random.default_rng(INIT_SEED);step=0;history=[];base=np.arange(len(ps));b1,b2,eps=.9,.999,1e-8
    for epoch in range(80):
        order=base.copy();rng.shuffle(order);weighted_loss=0.0;maxnorm=0.0
        for start in range(0,len(order),4096):
            ii=order[start:start+4096];good=np.asarray([ps[int(j)].good for j in ii]);bad=np.asarray([ps[int(j)].bad for j in ii]);bw=w[ii];rows=np.concatenate([good,bad]);rr,cache=forward_residual(model,xn[rows],phases[rows]);n=len(good);d=(t0_child[bad]+rr[n:])-(t0_child[good]+rr[:n]);weighted_loss+=float(np.dot(bw,np.logaddexp(0,-d)))
            gd=-1/(1+np.exp(np.clip(d,-60,60))); # d = parent_good - parent_bad
            # Global objective is sum_i w_i loss_i. Constant len(ps)/BATCH_SIZE only sets step scale.
            fac=bw*len(ps)/4096;grad=np.concatenate([-gd*fac,gd*fac]);grads=backward_residual(model,cache,grad)
            for k in grads:
                if _is_weight(k):grads[k]+=1e-5*model[k]
            maxnorm=max(maxnorm,clip_grads(grads));step+=1;lr=lr_for_epoch(epoch)
            for k in model:
                am[k]=b1*am[k]+(1-b1)*grads[k];av[k]=b2*av[k]+(1-b2)*(grads[k]*grads[k]);mh=am[k]/(1-b1**step);vh=av[k]/(1-b2**step);model[k]-=lr*mh/(np.sqrt(vh)+eps)
        if not all(np.all(np.isfinite(v)) for v in model.values()):raise FloatingPointError("nonfinite T2 parameters")
        history.append({"epoch":epoch+1,"lr":lr_for_epoch(epoch),"weighted_pairwise_logloss":weighted_loss,"pairs":len(ps),"max_preclip_grad_norm":maxnorm})
    return model,{"pairs":len(ps),"cell_counts":counts,"history":history}

def artifact_payload(model,mean,std,receipt):
    return {"schema":"jass.t2_phase_specialist.v1","input_width":326,"input_contract":{"eval_extras":120,"board_planes":200,"t0_child_scalar":1,"child_stm":1,"child_phase_one_hot":4,"forbidden_inputs":sorted(FORBIDDEN_INPUT_NAMES)},"architecture":{"trunk":[326,256,128],"phase_heads":[128,64,1],"hard_child_phase_routing":True,"shared_across_colours":True,"residual_on_t0":True},"optimization":{"optimizer":"adam","init_seed":2026090601,"pair_order_seed":2026090602,"batch_size":4096,"epochs":80,"lr0":1e-3,"lr_multiplier_after_epochs":{"40":.3,"60":.3},"weight_decay":1e-5,"grad_clip":5.0,"pair_cap_per_phase_colour_cell":150000,"equal_cell_total_weight":True},"normalization":{"mean":mean.tolist(),"std":std.tolist()},"params":{k:v.tolist() for k,v in sorted(model.items())},"receipt":receipt}
def save_artifact(path,payload):
    raw=(json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode();path.write_bytes(raw);return hashlib.sha256(raw).hexdigest()
def load_artifact(path):
    j=json.loads(path.read_text());
    if j.get("schema")!="jass.t2_phase_specialist.v1" or j.get("input_width")!=326:raise ValueError("T2 artifact schema drift")
    model={k:np.asarray(v,dtype=np.float64) for k,v in j["params"].items()};mean=np.asarray(j["normalization"]["mean"],dtype=np.float64);std=np.asarray(j["normalization"]["std"],dtype=np.float64)
    if mean.shape!=(326,) or std.shape!=(326,) or np.any(std<=0):raise ValueError("T2 normalization drift")
    return j,model,mean,std

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--feat",type=Path,required=True);ap.add_argument("--children",type=Path,required=True);ap.add_argument("--static-meta",type=Path,required=True);ap.add_argument("--pairs",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);ap.add_argument("--receipt",type=Path,required=True);a=ap.parse_args()
    feat=read_feat(a.feat);rec=read_jnnw(a.children);meta=load_static_meta(a.static_meta)
    if not(len(feat)==len(rec)==len(meta)):raise ValueError("T2 source row drift")
    x,t0,ph=build_state_features(feat,rec,meta);pairs=load_pairs(a.pairs,meta);ps,_,_=cap_and_weight_pairs(pairs);mean,std=fit_normalization(x,[q for p in ps for q in (p.good,p.bad)]);model,receipt=train_model(x,t0,ph,pairs,mean,std);payload=artifact_payload(model,mean,std,receipt);sha=save_artifact(a.output,payload);a.receipt.write_text(json.dumps({"schema":"jass.t2_phase_specialist_train_receipt.v1","artifact_sha256":sha,"rows":len(x),"pairs":receipt["pairs"],"cell_counts":receipt["cell_counts"],"input_width":326,"q1_label_reads":0,"q1_score_reads":0},sort_keys=True,indent=2)+"\n");return 0
if __name__=="__main__":raise SystemExit(main())
