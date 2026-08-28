#!/usr/bin/env python3
"""Deterministic T2 phase-specialist state-only student.

Contract frozen by L3_T2_PHASE_SPECIALIST_DEEP_FRESH_V1_20260828:
- exactly 326 state-only child inputs: 120 production extras, 200 board bits,
  T0 child scalar, child STM, and four hard child-phase indicators;
- no move-local, parent-context, D1, search score, WDL, source, or Q1 metric input;
- shared 326->256->128 ReLU trunk and four hard phase residual heads
  128->64->1 ReLU; T2(child)=T0(child)+residual;
- one shared network across colours; parent score is -T2(child);
- deterministic Adam with phase x parent-colour balanced pairwise objective.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

INPUT_WIDTH = 326
EVAL_WIDTH = 120
BOARD_WIDTH = 200
PHASE_WIDTH = 4
TRUNK = (256, 128)
HEAD_HIDDEN = 64
PHASES = ("P0", "P1", "P2", "P3")
INIT_SEED = 2026090601
PAIR_ORDER_SEED = 2026090602
BATCH_SIZE = 4096
EPOCHS = 80
LR0 = 1e-3
WEIGHT_DECAY = 1e-5
GRAD_CLIP = 5.0
PAIR_CAP_PER_CELL = 150_000

JNNW_DTYPE = np.dtype([
    ("wm", "<u8"), ("wk", "<u8"), ("bm", "<u8"), ("bk", "<u8"),
    ("stm", "u1"), ("score", "<i4"), ("wdl", "i1"),
])
assert JNNW_DTYPE.itemsize == 38

FORBIDDEN_INPUT_NAMES = frozenset({
    "from", "to", "num_captures", "captured_kings", "promotes", "moving_king",
    "parent_phase", "parent_stm", "parent_colour", "parent_legal_moves", "parent_id",
    "d1", "d1_score", "q1000", "q5k", "q50", "q200", "wdl", "source",
    "partition", "holdout", "q1", "q1_metric", "q1_score", "q1_label",
})

@dataclass(frozen=True)
class StaticMeta:
    parent_id: int
    parent_stm: int
    parent_phase: str
    t_baseline_parent: float

@dataclass(frozen=True)
class Pair:
    parent_id: int
    parent_stm: int
    parent_phase: str
    good: int
    bad: int


def phase_from_pieces(pieces: int) -> int:
    if 30 <= pieces <= 40: return 0
    if 20 <= pieces <= 29: return 1
    if 12 <= pieces <= 19: return 2
    if 0 <= pieces <= 11: return 3
    raise ValueError(f"piece count outside child phase contract: {pieces}")


def read_jnnw(path: Path) -> np.ndarray:
    size = path.stat().st_size
    if size < 8: raise ValueError("JNNW truncated")
    with path.open("rb") as f: hdr = f.read(8)
    if hdr[:4] != b"JNNW": raise ValueError("bad JNNW magic")
    n = struct.unpack_from("<I", hdr, 4)[0]
    if size != 8 + 38*n: raise ValueError("JNNW size/count drift")
    if n == 0: return np.empty(0, dtype=JNNW_DTYPE)
    return np.memmap(path, dtype=JNNW_DTYPE, mode="r", offset=8, shape=(n,))


def read_feat(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) < 12 or raw[:4] != b"FEAT": raise ValueError("bad FEAT header")
    n,k = struct.unpack_from("<II", raw, 4)
    if k != EVAL_WIDTH or len(raw) != 12+n*k*4: raise ValueError("FEAT geometry drift")
    return np.frombuffer(raw, dtype="<f4", offset=12, count=n*k).reshape(n,k).astype(np.float64)


def board_planes(records: np.ndarray) -> np.ndarray:
    out = np.empty((len(records), BOARD_WIDTH), dtype=np.float64)
    for pidx, field in enumerate(("wm","wk","bm","bk")):
        vals = np.asarray(records[field], dtype=np.uint64)
        for sq in range(50):
            out[:, pidx*50+sq] = ((vals >> np.uint64(sq)) & np.uint64(1)).astype(np.float64)
    return out


def child_piece_counts(records: np.ndarray) -> np.ndarray:
    out = np.zeros(len(records), dtype=np.int16)
    for field in ("wm","wk","bm","bk"):
        out += np.fromiter((int(v).bit_count() for v in records[field]), dtype=np.int16, count=len(records))
    return out


def load_static_meta(path: Path) -> list[StaticMeta]:
    out: list[StaticMeta] = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {"parent_id", "parent_stm", "phase", "t_baseline_parent"}
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise ValueError(f"static-meta fields drift: {rd.fieldnames!r}")
        for r in rd:
            stm=int(r["parent_stm"]); ph=r["phase"]
            if stm not in (0,1) or ph not in PHASES: raise ValueError("invalid parent cell metadata")
            out.append(StaticMeta(int(r["parent_id"]), stm, ph, float(r["t_baseline_parent"])))
    return out


def build_state_features(eval_features: np.ndarray, records: np.ndarray, meta: Sequence[StaticMeta]) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    """Build exactly 326 allowed state-only child inputs.

    The function intentionally cannot accept move-local, D1, search or Q1 data.
    `t_baseline_parent` is the already-produced parent-POV T0 child score, so
    exact child-STM T0 is its negation.
    """
    n=len(meta)
    if eval_features.shape != (n,EVAL_WIDTH) or len(records) != n: raise ValueError("row alignment drift")
    x=np.empty((n,INPUT_WIDTH),dtype=np.float64)
    x[:,:120]=eval_features
    x[:,120:320]=board_planes(records)
    t0_child=-np.asarray([m.t_baseline_parent for m in meta],dtype=np.float64)
    x[:,320]=t0_child
    stm=np.asarray(records["stm"],dtype=np.int8)
    if not np.all((stm==0)|(stm==1)): raise ValueError("invalid child STM")
    x[:,321]=stm.astype(np.float64)
    pieces=child_piece_counts(records)
    phases=np.asarray([phase_from_pieces(int(pc)) for pc in pieces],dtype=np.int8)
    x[:,322:326]=0.0
    x[np.arange(n),322+phases]=1.0
    if x.shape != (n,326) or not np.all(np.isfinite(x)): raise ValueError("T2 input contract drift")
    return x,t0_child,phases


def load_pairs(path: Path, meta: Sequence[StaticMeta]) -> list[Pair]:
    out=[]
    with path.open(newline="",encoding="utf-8") as f:
        rd=csv.DictReader(f,delimiter="\t")
        required={"parent_id","parent_stm","good_row","bad_row"}
        if rd.fieldnames is None or not required.issubset(rd.fieldnames): raise ValueError("pair fields drift")
        for r in rd:
            g,b=int(r["good_row"]),int(r["bad_row"]); stm=int(r["parent_stm"]); pid=int(r["parent_id"])
            if not (0<=g<len(meta) and 0<=b<len(meta)): raise ValueError("pair row out of range")
            mg,mb=meta[g],meta[b]
            if mg.parent_id!=pid or mb.parent_id!=pid or mg.parent_stm!=stm or mb.parent_stm!=stm or mg.parent_phase!=mb.parent_phase:
                raise ValueError("pair/static metadata mismatch")
            out.append(Pair(pid,stm,mg.parent_phase,g,b))
    return out


def pair_cell(p: Pair) -> tuple[str,int]: return (p.parent_phase,p.parent_stm)


def cap_and_weight_pairs(pairs: Sequence[Pair], cap: int=PAIR_CAP_PER_CELL) -> tuple[list[Pair],np.ndarray,dict[str,int]]:
    cells: dict[tuple[str,int],list[Pair]]={}
    for p in pairs: cells.setdefault(pair_cell(p),[]).append(p)
    if not cells: raise ValueError("no T2 training pairs")
    selected=[]; counts={}
    for cell in sorted(cells):
        seq=cells[cell]
        def key(p: Pair):
            h=hashlib.sha256(f"{PAIR_ORDER_SEED}:{p.parent_id}:{p.good}:{p.bad}".encode()).digest()
            return h,p.parent_id,p.good,p.bad
        seq=sorted(seq,key=key)[:cap]
        selected.extend(seq); counts[f"{cell[0]}_{'white' if cell[1]==0 else 'black'}"]=len(seq)
    ncell=len(cells)
    cell_counts={cell:min(len(seq),cap) for cell,seq in cells.items()}
    weights=np.asarray([1.0/(ncell*cell_counts[pair_cell(p)]) for p in selected],dtype=np.float64)
    # Sum of pair weights is one; each nonempty phase x colour cell sums equally.
    if not np.isclose(weights.sum(),1.0,rtol=0,atol=1e-12): raise AssertionError("balanced weights do not sum to one")
    return selected,weights,counts


def fit_normalization(x: np.ndarray, row_ids: Iterable[int]) -> tuple[np.ndarray,np.ndarray]:
    ids=np.asarray(sorted(set(int(i) for i in row_ids)),dtype=np.int64)
    if not len(ids): raise ValueError("no train rows")
    mean=x[ids].mean(axis=0); std=x[ids].std(axis=0); std[std<1e-8]=1.0
    return mean,std


def init_model(seed: int=INIT_SEED) -> dict[str,np.ndarray]:
    rng=np.random.default_rng(seed); m={}
    dims=(INPUT_WIDTH,)+TRUNK
    for i in range(len(dims)-1):
        m[f"TW{i}"]=rng.standard_normal((dims[i],dims[i+1]))*math.sqrt(2.0/dims[i]); m[f"Tb{i}"]=np.zeros(dims[i+1])
    for p in range(4):
        m[f"H{p}W0"]=rng.standard_normal((TRUNK[-1],HEAD_HIDDEN))*math.sqrt(2.0/TRUNK[-1]); m[f"H{p}b0"]=np.zeros(HEAD_HIDDEN)
        m[f"H{p}W1"]=rng.standard_normal((HEAD_HIDDEN,1))*math.sqrt(2.0/HEAD_HIDDEN); m[f"H{p}b1"]=np.zeros(1)
    return m


def forward_residual(model: dict[str,np.ndarray], x: np.ndarray, phases: np.ndarray):
    z0=x@model["TW0"]+model["Tb0"]; a0=np.maximum(z0,0.0)
    z1=a0@model["TW1"]+model["Tb1"]; h=np.maximum(z1,0.0)
    r=np.empty(len(x),dtype=np.float64); head_cache={}
    for p in range(4):
        idx=np.flatnonzero(phases==p)
        if not len(idx): continue
        zh=h[idx]@model[f"H{p}W0"]+model[f"H{p}b0"]; ah=np.maximum(zh,0.0)
        r[idx]=(ah@model[f"H{p}W1"]+model[f"H{p}b1"])[:,0]
        head_cache[p]=(idx,zh,ah)
    return r,(x,z0,a0,z1,h,head_cache)


def backward_residual(model: dict[str,np.ndarray], cache, grad_r: np.ndarray) -> dict[str,np.ndarray]:
    x,z0,a0,z1,h,heads=cache; grads={k:np.zeros_like(v) for k,v in model.items()}; gh=np.zeros_like(h)
    for p,(idx,zh,ah) in heads.items():
        g=grad_r[idx,None]
        grads[f"H{p}W1"]=ah.T@g; grads[f"H{p}b1"]=g.sum(axis=0)
        gah=g@model[f"H{p}W1"].T; gzh=gah*(zh>0)
        grads[f"H{p}W0"]=h[idx].T@gzh; grads[f"H{p}b0"]=gzh.sum(axis=0); gh[idx]+=gzh@model[f"H{p}W0"].T
    gz1=gh*(z1>0); grads["TW1"]=a0.T@gz1; grads["Tb1"]=gz1.sum(axis=0)
    ga0=gz1@model["TW1"].T; gz0=ga0*(z0>0); grads["TW0"]=x.T@gz0; grads["Tb0"]=gz0.sum(axis=0)
    return grads


def clip_grads(grads: dict[str,np.ndarray]) -> float:
    norm=math.sqrt(sum(float(np.sum(g*g)) for g in grads.values()))
    if norm>GRAD_CLIP:
        scale=GRAD_CLIP/norm
        for k in grads: grads[k]*=scale
    return norm


def lr_for_epoch(epoch:int)->float:
    lr=LR0
    if epoch>=40: lr*=0.3
    if epoch>=60: lr*=0.3
    return lr


def parent_scores(model:dict[str,np.ndarray], xn:np.ndarray, t0_child:np.ndarray, phases:np.ndarray)->np.ndarray:
    r,_=forward_residual(model,xn,phases)
    return -(t0_child+r)


def train_model(x:np.ndarray,t0_child:np.ndarray,phases:np.ndarray,pairs:Sequence[Pair],mean:np.ndarray,std:np.ndarray):
    ps,w,counts=cap_and_weight_pairs(pairs); xn=(x-mean)/std; model=init_model();
    adam_m={k:np.zeros_like(v) for k,v in model.items()}; adam_v={k:np.zeros_like(v) for k,v in model.items()}
    rng=np.random.default_rng(INIT_SEED); beta1,beta2,eps=.9,.999,1e-8; step=0; history=[]
    base=np.arange(len(ps),dtype=np.int64)
    for epoch in range(EPOCHS):
        order=base.copy(); rng.shuffle(order); total_loss=0.0; total_weight=0.0; maxnorm=0.0
        for start in range(0,len(order),BATCH_SIZE):
            idx=order[start:start+BATCH_SIZE]; good=np.asarray([ps[int(j)].good for j in idx]); bad=np.asarray([ps[int(j)].bad for j in idx]); bw=w[idx]
            rows=np.concatenate([good,bad]); rr,cache=forward_residual(model,xn[rows],phases[rows]); ng=len(good)
            t2g=t0_child[good]+rr[:ng]; t2b=t0_child[bad]+rr[ng:]; d=t2b-t2g
            loss=np.logaddexp(0.0,-d); total_loss+=float(np.dot(bw,loss)); total_weight+=float(bw.sum())
            g_d=-1.0/(1.0+np.exp(np.clip(d,-60,60))); scale=bw/max(float(bw.sum()),1e-30); g_d*=scale
            grad=np.concatenate([-g_d,g_d]); grads=backward_residual(model,cache,grad)
            for k in grads:
                if k.endswith("W0") or k.endswith("W1") or k.startswith("TW"): grads[k]+=WEIGHT_DECAY*model[k]
            maxnorm=max(maxnorm,clip_grads(grads)); step+=1; lr=lr_for_epoch(epoch)
            for k in model:
                adam_m[k]=beta1*adam_m[k]+(1-beta1)*grads[k]; adam_v[k]=beta2*adam_v[k]+(1-beta2)*(grads[k]*grads[k])
                mh=adam_m[k]/(1-beta1**step); vh=adam_v[k]/(1-beta2**step); model[k]-=lr*mh/(np.sqrt(vh)+eps)
        if not all(np.all(np.isfinite(v)) for v in model.values()): raise FloatingPointError("nonfinite T2 parameters")
        history.append({"epoch":epoch+1,"lr":lr_for_epoch(epoch),"weighted_pairwise_logloss":total_loss/max(total_weight,1e-30),"pairs":len(ps),"max_preclip_grad_norm":maxnorm})
    return model,{"pairs":len(ps),"cell_counts":counts,"history":history}


def artifact_payload(model,mean,std,receipt):
    arr=lambda a:a.tolist()
    return {
        "schema":"jass.t2_phase_specialist.v1","input_width":326,
        "input_contract":{"eval_extras":120,"board_planes":200,"t0_child_scalar":1,"child_stm":1,"child_phase_one_hot":4,"forbidden_inputs":sorted(FORBIDDEN_INPUT_NAMES)},
        "architecture":{"trunk":[326,256,128],"phase_heads":[128,64,1],"hard_child_phase_routing":True,"shared_across_colours":True,"residual_on_t0":True},
        "optimization":{"optimizer":"adam","init_seed":INIT_SEED,"pair_order_seed":PAIR_ORDER_SEED,"batch_size":BATCH_SIZE,"epochs":EPOCHS,"lr0":LR0,"lr_multiplier_after_epochs":{"40":.3,"60":.3},"weight_decay":WEIGHT_DECAY,"grad_clip":GRAD_CLIP,"pair_cap_per_phase_colour_cell":PAIR_CAP_PER_CELL,"equal_cell_total_weight":True},
        "normalization":{"mean":arr(mean),"std":arr(std)},"params":{k:arr(v) for k,v in sorted(model.items())},"receipt":receipt,
    }


def save_artifact(path:Path,payload:dict)->str:
    raw=(json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode(); path.write_bytes(raw); return hashlib.sha256(raw).hexdigest()


def load_artifact(path:Path):
    j=json.loads(path.read_text())
    if j.get("schema")!="jass.t2_phase_specialist.v1" or j.get("input_width")!=326: raise ValueError("T2 artifact schema drift")
    model={k:np.asarray(v,dtype=np.float64) for k,v in j["params"].items()}; mean=np.asarray(j["normalization"]["mean"],dtype=np.float64); std=np.asarray(j["normalization"]["std"],dtype=np.float64)
    if mean.shape!=(326,) or std.shape!=(326,) or np.any(std<=0): raise ValueError("T2 normalization drift")
    return j,model,mean,std


def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument("--feat",type=Path,required=True); ap.add_argument("--children",type=Path,required=True); ap.add_argument("--static-meta",type=Path,required=True); ap.add_argument("--pairs",type=Path,required=True); ap.add_argument("--output",type=Path,required=True); ap.add_argument("--receipt",type=Path,required=True); args=ap.parse_args()
    feat=read_feat(args.feat); rec=read_jnnw(args.children); meta=load_static_meta(args.static_meta)
    if not(len(feat)==len(rec)==len(meta)): raise ValueError("T2 source row drift")
    x,t0,ph=build_state_features(feat,rec,meta); pairs=load_pairs(args.pairs,meta); selected,_,_=cap_and_weight_pairs(pairs); rows=[p.good for p in selected]+[p.bad for p in selected]; mean,std=fit_normalization(x,rows); model,train_receipt=train_model(x,t0,ph,pairs,mean,std)
    payload=artifact_payload(model,mean,std,train_receipt); sha=save_artifact(args.output,payload); args.receipt.write_text(json.dumps({"schema":"jass.t2_phase_specialist_train_receipt.v1","artifact_sha256":sha,"rows":len(x),"pairs":train_receipt["pairs"],"cell_counts":train_receipt["cell_counts"],"input_width":326,"q1_label_reads":0,"q1_score_reads":0},sort_keys=True,indent=2)+"\n")
    return 0

if __name__=="__main__": raise SystemExit(main())
