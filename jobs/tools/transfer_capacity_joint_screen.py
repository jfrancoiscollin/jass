#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Preregistered L3 transfer/capacity/joint T+D screen.

Consumes ONLY frozen M3 artifacts, CURRICULUM, the sealed D1 policy and the
production scalar/anchor binaries. M5/1612 are deliberately not accepted as
inputs. No fresh q200 labels, self-play, strength or promotion are possible.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from collections import defaultdict

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize
from scipy.special import expit

import micro_search_m4_distill as m4

SPLIT_SEED = 2026090401
B1_SEED = 2026090402
BOOTSTRAP_SEED = 2026090403
ANCHOR_SEED = 2026090212
ANCHOR_N = 500_000
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
M3_EXPECTED_PARENTS = 100_000
M3_EXPECTED_ROWS = 928_639
M3_EXPECTED_CONSTRAINTS = 828_639
EXTRAS = 120
MOVE_FEATURES = 6
MAXITER = 200
MAXCOR = 5
BOOTSTRAP_SAMPLES = 20_000

ARMS = {
    "A0_M4_REPLICATION": (1e-5, "top", False),
    "A1_L2_0": (0.0, "top", False),
    "A2_L2_1E7": (1e-7, "top", False),
    "A3_L2_1E6": (1e-6, "top", False),
    "A4_L2_1E4": (1e-4, "top", False),
    "A5_MARGIN_L2_1E6": (1e-6, "top", True),
    "A6_MARGIN_L2_1E5": (1e-5, "top", True),
    "A7_DENSE_L2_1E6": (1e-6, "dense", False),
    "A8_DENSE_MARGIN_L2_1E6": (1e-6, "dense", True),
}
GUARDS = {
    "G0": (12.0, 35.0),
    "G1": (20.0, 60.0),
    "G2": (35.0, 100.0),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def phase_of(pieces: int) -> str:
    if 30 <= pieces <= 40: return "P0"
    if 20 <= pieces <= 29: return "P1"
    if 12 <= pieces <= 19: return "P2"
    if 9 <= pieces <= 11: return "P3"
    raise ValueError(f"pieces outside frozen support: {pieces}")


def split_bucket(fingerprint: str) -> int:
    d = hashlib.sha256(f"{SPLIT_SEED}:{fingerprint}".encode()).digest()
    return int.from_bytes(d[:8], "big") % 100


def margin_weight(cp: np.ndarray | float) -> np.ndarray | float:
    return np.clip(np.abs(cp) / 100.0, 0.25, 4.0)


def read_groups(path: Path) -> dict:
    opener = gzip.open if path.suffix == ".gz" else open
    cols = defaultdict(list)
    with opener(path, "rt", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f, delimiter="\t")
        req = {"row_index","parent_id","parent_fingerprint","parent_stm","parent_pieces",
               "from","to","num_captures","promotes","moving_king","captured_kings",
               "t0_parent","micro1000_parent"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):
            raise SystemExit(f"M3 groups missing columns: {sorted(req-set(rd.fieldnames or []))}")
        for r in rd:
            for k in req:
                cols[k].append(r[k])
    n = len(cols["row_index"])
    if [int(x) for x in cols["row_index"]] != list(range(n)):
        raise SystemExit("M3 groups row alignment drift")
    out = {
        "parent_id": np.asarray(cols["parent_id"], dtype=np.int32),
        "fingerprint": np.asarray(cols["parent_fingerprint"], dtype=object),
        "stm": np.asarray(cols["parent_stm"], dtype=np.int8),
        "pieces": np.asarray(cols["parent_pieces"], dtype=np.int16),
        "from": np.asarray(cols["from"], dtype=np.int16),
        "to": np.asarray(cols["to"], dtype=np.int16),
        "num_captures": np.asarray(cols["num_captures"], dtype=np.float64),
        "promotes": np.asarray(cols["promotes"], dtype=np.float64),
        "moving_king": np.asarray(cols["moving_king"], dtype=np.float64),
        "captured_kings": np.asarray(cols["captured_kings"], dtype=np.float64),
        "t0": np.asarray(cols["t0_parent"], dtype=np.float64),
        "teacher": np.asarray(cols["micro1000_parent"], dtype=np.float64),
    }
    return out


def parent_rows(parent: np.ndarray) -> dict[int, np.ndarray]:
    out: dict[int, list[int]] = defaultdict(list)
    for i, p in enumerate(parent): out[int(p)].append(i)
    return {p: np.asarray(v, dtype=np.int32) for p, v in out.items()}


def parent_meta(groups: dict) -> dict[int, dict]:
    rows = parent_rows(groups["parent_id"])
    out = {}
    fps = set()
    for p, rr in rows.items():
        fp = str(groups["fingerprint"][rr[0]])
        if any(str(groups["fingerprint"][i]) != fp for i in rr): raise SystemExit("fingerprint drift within parent")
        stm = int(groups["stm"][rr[0]]); pieces = int(groups["pieces"][rr[0]])
        if any(int(groups["stm"][i]) != stm or int(groups["pieces"][i]) != pieces for i in rr):
            raise SystemExit("parent metadata drift within siblings")
        if fp in fps: raise SystemExit("canonical parent fingerprint duplicated")
        fps.add(fp)
        out[p] = {"fingerprint": fp, "stm": stm, "pieces": pieces,
                  "phase": phase_of(pieces), "split": "train" if split_bucket(fp) < 80 else "dev"}
    if len(out) != M3_EXPECTED_PARENTS: raise SystemExit(f"parent support {len(out)} != {M3_EXPECTED_PARENTS}")
    tr = {v["fingerprint"] for v in out.values() if v["split"] == "train"}
    dv = {v["fingerprint"] for v in out.values() if v["split"] == "dev"}
    if tr & dv: raise SystemExit("canonical TRAIN/DEV overlap")
    return out


def semantic_key(groups: dict, i: int) -> tuple:
    return (int(groups["from"][i]), int(groups["to"][i]), int(groups["num_captures"][i]),
            int(groups["captured_kings"][i]), int(groups["promotes"][i]), int(groups["moving_king"][i]))


def make_dense_constraints(groups: dict, pmeta: dict[int, dict], split: str) -> dict[str, np.ndarray]:
    rows = parent_rows(groups["parent_id"])
    good=[]; bad=[]; pid=[]; margin=[]
    for p in sorted(rows):
        if pmeta[p]["split"] != split: continue
        rr = list(map(int, rows[p])); rr.sort(key=lambda i: (-groups["teacher"][i], semantic_key(groups,i)))
        if len(rr) < 2: continue
        top = rr[0]
        pairs = {(top, j) for j in rr[1:]}
        pairs.update((rr[k], rr[k+1]) for k in range(len(rr)-1) if groups["teacher"][rr[k]] != groups["teacher"][rr[k+1]])
        for g,b in sorted(pairs):
            if groups["teacher"][g] <= groups["teacher"][b]: continue
            good.append(g); bad.append(b); pid.append(p); margin.append(groups["teacher"][g]-groups["teacher"][b])
    return {"good":np.asarray(good,np.int32),"bad":np.asarray(bad,np.int32),
            "parent_id":np.asarray(pid,np.int32),"teacher_margin":np.asarray(margin,np.float64)}


def filter_constraints(c: dict, train_ids: set[int]) -> dict:
    mask = np.asarray([int(p) in train_ids for p in c["parent_id"]], dtype=bool)
    return {k: np.asarray(v)[mask] for k,v in c.items()}


def build_pair_design(design: dict, constraints: dict, header, w0):
    # Disable the old M4 row cap: every preregistered pair is consumed.
    old = m4.ROW_CAP; m4.ROW_CAP = 10_000_000
    try:
        P,E,z0,active,meta = m4.build_pair_design(design,constraints,header,w0)
    finally:
        m4.ROW_CAP = old
    # m4 deterministically permutes constraints using its frozen pair seed.
    rng = np.random.Generator(np.random.PCG64(m4.PAIR_SEED))
    order = rng.permutation(len(constraints["good"]))
    margins = np.asarray(constraints["teacher_margin"],dtype=np.float64)[order]
    return P,E,z0,active,meta,margins


def fit_residual(P,E,z0,l2,weights=None, extra=None, extra_l2=None):
    npat=P.shape[1]; ne=E.shape[1]; nx=0 if extra is None else extra.shape[1]
    theta0=np.zeros(npat+ne+nx,dtype=np.float64)
    n=float(len(z0)); ww=np.ones(len(z0)) if weights is None else np.asarray(weights,dtype=np.float64)
    ww=ww/ww.mean()
    def fg(t):
        z=z0+np.asarray(P.dot(t[:npat]))+np.asarray(E.dot(t[npat:npat+ne]))
        if extra is not None: z=z+extra.dot(t[npat+ne:])
        q=-ww*expit(-z)/n
        loss=float(np.sum(ww*np.logaddexp(0.0,-z))/n)
        gp=np.asarray(P.T.dot(q)); ge=np.asarray(E.T.dot(q)); parts=[gp,ge]
        reg=0.5*l2*float(np.dot(t[:npat+ne],t[:npat+ne])); loss+=reg
        parts[0]=parts[0]+l2*t[:npat]; parts[1]=parts[1]+l2*t[npat:npat+ne]
        if extra is not None:
            el2=l2 if extra_l2 is None else extra_l2
            gx=np.asarray(extra.T.dot(q))+el2*t[npat+ne:]
            loss+=0.5*el2*float(np.dot(t[npat+ne:],t[npat+ne:])); parts.append(gx)
        return loss,np.concatenate(parts)
    r=minimize(fg,theta0,jac=True,method="L-BFGS-B",options={"maxiter":MAXITER,"maxcor":MAXCOR})
    return np.asarray(r.x), {"success":bool(r.success),"status":int(r.status),"message":str(r.message),
        "iterations":int(r.nit),"objective":float(r.fun),"gradient_inf_norm":float(np.max(np.abs(r.jac))),
        "l2":l2,"maxiter":MAXITER,"maxcor":MAXCOR}


def theta_to_delta(theta,active,header,w0):
    _,_,_,npat,next_=header; a=len(active); d=np.zeros_like(w0,dtype=np.float64)
    d[active]=theta[:a]; d[npat+active]=theta[a:2*a]
    d[2*npat:2*npat+next_]=theta[2*a:2*a+next_]
    d[2*npat+next_:]=theta[2*a+next_:2*a+2*next_]
    return d


def select_anchor(children: Path, out: Path):
    raw=children.read_bytes();
    if raw[:4]!=b"JNNW": raise SystemExit("bad M3 children")
    n=struct.unpack_from("<I",raw,4)[0]
    if n<M3_EXPECTED_ROWS or len(raw)!=8+38*n: raise SystemExit("M3 children size drift")
    rng=np.random.Generator(np.random.PCG64(ANCHOR_SEED)); chosen=np.sort(rng.choice(n,size=ANCHOR_N,replace=False))
    with out.open("wb") as f:
        f.write(b"JNNW"); f.write(struct.pack("<I",ANCHOR_N))
        for i in chosen:
            off=8+38*int(i); f.write(raw[off:off+38])
    return hashlib.sha256(chosen.astype("<i8").tobytes()).hexdigest()


def run_anchor(binary,states,t0,cand,report):
    subprocess.run([str(binary),str(states),str(t0),str(cand),str(report)],check=True)
    return json.loads(report.read_text())


def guard_scale(delta, header,w0,curriculum,anchor_binary,anchor_states,outdir,guard):
    rms_lim,p99_lim=guard
    def ev(s,label):
        p=outdir/f"cand-{label}.pjtw"; w=np.rint(w0.astype(np.float64)+s*delta).astype(np.int64)
        m4.write_candidate(p,header,w); r=run_anchor(anchor_binary,anchor_states,curriculum,p,outdir/f"anchor-{label}.json")
        return float(r["rms_abs_cp"])<=rms_lim and float(r["p99_abs_cp"])<=p99_lim,r,p,w
    ok,r,p,w=ev(1.0,"1")
    if ok: return 1.0,r,p,w
    lo,hi=0.0,1.0
    ok0,_,_,_=ev(0.0,"0")
    if not ok0: raise SystemExit("s=0 failed anchor")
    for k in range(16):
        mid=(lo+hi)/2; ok,_,_,_=ev(mid,f"b{k}")
        if ok: lo=mid
        else: hi=mid
    ok,r,p,w=ev(lo,"final")
    if not ok: raise SystemExit("final shrink violates guard")
    return lo,r,p,w


def score_binary(binary,children,t0,cand,outdir,label):
    tsv=outdir/f"score-{label}.tsv"; rep=outdir/f"score-{label}.json"
    subprocess.run([str(binary),str(children),str(t0),str(cand),str(tsv),str(rep)],check=True)
    vals=[]
    with tsv.open() as f:
        rd=csv.DictReader(f,delimiter="\t")
        for r in rd: vals.append(float(r["t1_parent"]))
    a=np.asarray(vals,dtype=np.float64)
    if len(a)!=M3_EXPECTED_ROWS: raise SystemExit("production score row count drift")
    return a


def float_scores(design,header,w):
    _,_,scale,npat,next_=header
    cols=design["canonical_cols"].astype(np.int64); signs=design["signs"].astype(np.float64)
    wm=design["tempo_wmg"].astype(np.float64); ex=design["extras"].astype(np.float64); pov=design["parent_pov_sign"].astype(np.float64)
    mg=(signs*w[cols]).sum(axis=1)+ex.dot(w[2*npat:2*npat+next_])
    eg=(signs*w[npat+cols]).sum(axis=1)+ex.dot(w[2*npat+next_:])
    return pov*100.0*(wm*mg+(1.0-wm)*eg)/float(scale)


def parent_metric_arrays(groups,pmeta,score,split="dev"):
    rows=parent_rows(groups["parent_id"]); pair_num=[]; pair_den=[]; top=[]; pids=[]
    for p in sorted(rows):
        if pmeta[p]["split"]!=split: continue
        rr=list(map(int,rows[p])); t=groups["teacher"][rr]; s=score[rr]
        num=0.0; den=0
        for a in range(len(rr)):
            for b in range(a+1,len(rr)):
                if t[a]==t[b]: continue
                den+=1; good=a if t[a]>t[b] else b; bad=b if good==a else a
                num+=1.0 if s[good]>s[bad] else (0.5 if s[good]==s[bad] else 0.0)
        if den==0: continue
        teacher_top={rr[i] for i,v in enumerate(t) if v==np.max(t)}
        model_top=[rr[i] for i,v in enumerate(s) if v==np.max(s)]
        pair_num.append(num); pair_den.append(den); top.append(np.mean([i in teacher_top for i in model_top])); pids.append(p)
    return {"pid":np.asarray(pids,np.int32),"num":np.asarray(pair_num),"den":np.asarray(pair_den),"top":np.asarray(top)}


def metric_summary(a):
    return {"pairwise":float(a["num"].sum()/a["den"].sum()),"top_hit":float(a["top"].mean()),"parents":int(len(a["pid"])),"pairs":int(a["den"].sum())}


def bootstrap_delta(a,b):
    if not np.array_equal(a["pid"],b["pid"]): raise SystemExit("bootstrap parent alignment drift")
    rng=np.random.default_rng(BOOTSTRAP_SEED); n=len(a["pid"]); outp=[]; outt=[]
    batch=128
    for st in range(0,BOOTSTRAP_SAMPLES,batch):
        m=min(batch,BOOTSTRAP_SAMPLES-st); ix=rng.integers(0,n,size=(m,n))
        ap=a["num"][ix].sum(1)/a["den"][ix].sum(1); bp=b["num"][ix].sum(1)/b["den"][ix].sum(1)
        outp.extend((ap-bp).tolist()); outt.extend((a["top"][ix].mean(1)-b["top"][ix].mean(1)).tolist())
    def sm(x):
        x=np.asarray(x); return {"mean":float(x.mean()),"ci_low":float(np.quantile(x,.025)),"ci_high":float(np.quantile(x,.975)),"p_gt_0":float(np.mean(x>0)),"samples":BOOTSTRAP_SAMPLES,"seed":BOOTSTRAP_SEED}
    return {"pairwise":sm(outp),"top_hit":sm(outt)}


def strata(groups,pmeta,score):
    allm=parent_metric_arrays(groups,pmeta,score,"dev"); out={"global":metric_summary(allm),"phase":{},"colour":{}}
    for ph in ("P0","P1","P2","P3"):
        ids={p for p,v in pmeta.items() if v["split"]=="dev" and v["phase"]==ph}; mask=np.asarray([int(p) in ids for p in allm["pid"]])
        out["phase"][ph]=metric_summary({k:(v[mask] if isinstance(v,np.ndarray) else v) for k,v in allm.items()}) if mask.any() else None
    for c,name in ((0,"white"),(1,"black")):
        ids={p for p,v in pmeta.items() if v["split"]=="dev" and v["stm"]==c}; mask=np.asarray([int(p) in ids for p in allm["pid"])
        out["colour"][name]=metric_summary({k:(v[mask] if isinstance(v,np.ndarray) else v) for k,v in allm.items()}) if mask.any() else None
    return out,allm


def load_d1(path: Path):
    j=json.loads(path.read_text());
    if j.get("schema")!="jass.deep_sibling_policy.v1" or not j.get("usable"): raise SystemExit("sealed D1 policy unusable")
    w0=np.asarray(j["weights"]["white_parent"],dtype=np.float64); w1=np.asarray(j["weights"]["black_parent"],dtype=np.float64)
    if w0.shape!=(126,) or w1.shape!=(126,): raise SystemExit("D1 width drift")
    return w0,w1


def d_features(design,groups):
    mv=np.column_stack([groups["num_captures"],groups["captured_kings"],groups["promotes"],groups["moving_king"],groups["from"]/50.0,groups["to"]/50.0])
    x=np.concatenate([design["extras"].astype(np.float64),mv],axis=1)
    if x.shape[1]!=126: raise SystemExit("DSSD static feature width drift")
    return x


def fit_dense_pair(x,good,bad,z0=None,l2=1e-3):
    d=x[good]-x[bad]; scale=d.std(0); scale[scale<1e-8]=1; dn=d/scale; base=np.zeros(len(d)) if z0 is None else z0
    def fg(w):
        z=base+dn.dot(w); q=-expit(-z)/len(z); return float(np.logaddexp(0,-z).mean()+.5*l2*np.dot(w,w)),dn.T.dot(q)+l2*w
    r=minimize(fg,np.zeros(dn.shape[1]),jac=True,method="L-BFGS-B",options={"maxiter":500,"gtol":1e-6,"maxcor":20})
    return np.asarray(r.x)/scale,{"success":bool(r.success),"status":int(r.status),"iterations":int(r.nit),"objective":float(r.fun),"l2":l2}


def b1_probe(design,groups,pmeta,train_pairs):
    # Fixed architecture written before any DEV metric: exact active categorical
    # identities -> trainable 8-d embedding sum, 120 normalized extras + phase4+side,
    # 64-ReLU head, Adam lr1e-3, batch4096, 6 epochs.
    cols=design["canonical_cols"].astype(np.int64); signs=design["signs"].astype(np.float64)
    active=np.unique(cols[np.isin(groups["parent_id"],np.asarray([p for p,v in pmeta.items() if v["split"]=="train"]))])
    mp=np.full(int(cols.max())+1,-1,dtype=np.int32); mp[active]=np.arange(len(active),dtype=np.int32); ci=mp[cols]
    ex=design["extras"].astype(np.float64); train_rows=np.isin(groups["parent_id"],np.asarray([p for p,v in pmeta.items() if v["split"]=="train"]))
    mu=ex[train_rows].mean(0); sd=ex[train_rows].std(0); sd[sd<1e-8]=1; ex=(ex-mu)/sd
    phase=np.zeros((len(ex),4)); side=groups["stm"].astype(np.float64)[:,None]
    for i,p in enumerate(groups["pieces"]): phase[i,(0 if p>=30 else 1 if p>=20 else 2 if p>=12 else 3)]=1
    rng=np.random.default_rng(B1_SEED); emb=rng.normal(0,.02,size=(len(active),8)); W1=rng.normal(0,.02,size=(133,64)); b1=np.zeros(64); W2=rng.normal(0,.02,size=64); b2=0.0
    params=[emb,W1,b1,W2]; ms=[np.zeros_like(x) for x in params]; vs=[np.zeros_like(x) for x in params]; mb=0.; vb=0.; step=0
    good,bad=train_pairs
    for ep in range(6):
        order=rng.permutation(len(good))
        for st in range(0,len(order),4096):
            ix=order[st:st+4096]; rg=good[ix]; rb=bad[ix]
            def fwd(rr):
                e=(emb[ci[rr]]*signs[rr,:,None]).sum(1); inp=np.concatenate([e,ex[rr],phase[rr],side[rr]],axis=1); pre=inp.dot(W1)+b1; h=np.maximum(pre,0); sc=h.dot(W2)+b2; return inp,pre,h,sc
            ig,pg,hg,sg=fwd(rg); ib,pb,hb,sb=fwd(rb); z=sg-sb; q=-expit(-z)/len(z)
            gW2=hg.T.dot(q)+hb.T.dot(-q); gb2=float(q.sum()+(-q).sum()); ghg=q[:,None]*W2; ghb=-q[:,None]*W2
            gpg=ghg*(pg>0); gpb=ghb*(pb>0); gW1=ig.T.dot(gpg)+ib.T.dot(gpb); gb1=gpg.sum(0)+gpb.sum(0)
            gig=gpg.dot(W1.T)[:,:8]; gib=gpb.dot(W1.T)[:,:8]; gemb=np.zeros_like(emb)
            for k in range(8):
                np.add.at(gemb,ci[rg,k],gig*signs[rg,k,None]); np.add.at(gemb,ci[rb,k],gib*signs[rb,k,None])
            grads=[gemb,gW1,gb1,gW2]; step+=1
            for n,(p,g) in enumerate(zip(params,grads)):
                ms[n]=.9*ms[n]+.1*g; vs[n]=.999*vs[n]+.001*g*g; mh=ms[n]/(1-.9**step); vh=vs[n]/(1-.999**step); p-=1e-3*mh/(np.sqrt(vh)+1e-8)
            mb=.9*mb+.1*gb2; vb=.999*vb+.001*gb2*gb2; b2-=1e-3*(mb/(1-.9**step))/(math.sqrt(vb/(1-.999**step))+1e-8)
    e=(emb[ci]*signs[:,:,None]).sum(1); inp=np.concatenate([e,ex,phase,side],axis=1); score=np.maximum(inp.dot(W1)+b1,0).dot(W2)+b2
    receipt={"seed":B1_SEED,"active_patterns":int(len(active)),"embedding_dim":8,"dense_extras":120,"phase_one_hot":4,"side":1,"hidden":64,"activation":"relu","optimizer":"adam","lr":1e-3,"batch":4096,"epochs":6,"pair_family":"top_plus_adjacent","parameter_count":int(emb.size+W1.size+b1.size+W2.size+1),"train_only_normalization":True,"forbidden_inputs":["D1","q1000_as_input","q50","q200","WDL","search_scores"]}
    return score,receipt


def main():
    ap=argparse.ArgumentParser();
    for a in ("design","constraints","groups","children","curriculum","d1-policy","anchor-binary","score-binary","outdir"): ap.add_argument("--"+a,required=True)
    args=ap.parse_args(); out=Path(args.outdir); out.mkdir(parents=True,exist_ok=True)
    design_path=Path(args.design); constraints_path=Path(args.constraints); groups_path=Path(args.groups); children=Path(args.children); curriculum=Path(args.curriculum); d1p=Path(args.d1_policy)
    if sha256(curriculum)!=CURRICULUM_SHA: raise SystemExit("CURRICULUM SHA drift")
    # Anti-leakage is structural: this program exposes no M5/1612 input option.
    forbidden=[x for x in map(str,[design_path,constraints_path,groups_path,children]) if "1610" in x or "1612" in x or "m5" in x.lower()]
    if forbidden: raise SystemExit(f"forbidden M5/1612 input path: {forbidden}")
    dnp=np.load(design_path,allow_pickle=False); design={k:dnp[k] for k in dnp.files}; cnp=np.load(constraints_path,allow_pickle=False); cons={k:cnp[k] for k in cnp.files}; groups=read_groups(groups_path)
    if len(groups["parent_id"])!=M3_EXPECTED_ROWS or len(cons["good"])!=M3_EXPECTED_CONSTRAINTS: raise SystemExit("M3 support drift")
    pmeta=parent_meta(groups); tr={p for p,v in pmeta.items() if v["split"]=="train"}; dv={p for p,v in pmeta.items() if v["split"]=="dev"}
    split_report={"seed":SPLIT_SEED,"method":"sha256(seed:canonical_parent_fingerprint)%100","train_parents":len(tr),"dev_parents":len(dv),"parent_overlap":0,"canonical_overlap":0,
      "train_by_phase":{ph:sum(v["split"]=="train" and v["phase"]==ph for v in pmeta.values()) for ph in ("P0","P1","P2","P3")},"dev_by_phase":{ph:sum(v["split"]=="dev" and v["phase"]==ph for v in pmeta.values()) for ph in ("P0","P1","P2","P3")},"train_by_colour":{"white":sum(v["split"]=="train" and v["stm"]==0 for v in pmeta.values()),"black":sum(v["split"]=="train" and v["stm"]==1 for v in pmeta.values())},"dev_by_colour":{"white":sum(v["split"]=="dev" and v["stm"]==0 for v in pmeta.values()),"black":sum(v["split"]=="dev" and v["stm"]==1 for v in pmeta.values())}}
    header,w0=m4.load_pjtw(curriculum); top=filter_constraints(cons,tr); dense=make_dense_constraints(groups,pmeta,"train")
    Ptop,Etop,z0top,atop,mtop,mar_top=build_pair_design(design,top,header,w0); Pd,Ed,z0d,ad,md,mar_d=build_pair_design(design,dense,header,w0)
    anchor_states=out/"anchor.jnnw"; anchor_sel_sha=select_anchor(children,anchor_states); arm_results={}; arm_models={}
    for name,(l2,fam,weighted) in ARMS.items():
        P,E,z0,active,meta,margins=(Ptop,Etop,z0top,atop,mtop,mar_top) if fam=="top" else (Pd,Ed,z0d,ad,md,mar_d)
        weights=margin_weight(margins) if weighted else None; theta,opt=fit_residual(P,E,z0,l2,weights); delta=theta_to_delta(theta,active,header,w0); arm_models[name]=(delta,opt,fam)
        arm_results[name]={"fit":opt,"pair_family":fam,"margin_weighted":weighted,"l2":l2,"regimes":{}}
        for g,lim in GUARDS.items():
            gd=out/f"{name}-{g}"; gd.mkdir(exist_ok=True); s,ar,cand,wi=guard_scale(delta,header,w0,curriculum,Path(args.anchor_binary),anchor_states,gd,lim); sc=score_binary(Path(args.score_binary),children,curriculum,cand,gd,"dev"); st,ma=strata(groups,pmeta,sc)
            arm_results[name]["regimes"][g]={"scale":s,"anchor":{"rms_abs_cp":float(ar["rms_abs_cp"]),"p99_abs_cp":float(ar["p99_abs_cp"]),"max_abs_cp":int(ar["max_abs_cp"]),"serialize_reload":bool(ar["serialize_reload"])},"changed_int32_coefficients":int(np.count_nonzero(wi!=w0)),"metrics":st,"candidate_sha256":sha256(cand)}
    def best(g): return max(ARMS,key=lambda n:(arm_results[n]["regimes"][g]["metrics"]["global"]["pairwise"],arm_results[n]["regimes"][g]["metrics"]["global"]["top_hit"]))
    bests={g:best(g) for g in GUARDS}; best0=bests["G0"]; delta,opt,fam=arm_models[best0]; wf=w0.astype(np.float64)+delta; b0_float=float_scores(design,header,wf); b0_dir=out/"B0"; b0_dir.mkdir(exist_ok=True); wi=np.rint(wf).astype(np.int64); b0_int=b0_dir/"b0-int32.pjtw"; m4.write_candidate(b0_int,header,wi); b0_prod=score_binary(Path(args.score_binary),children,curriculum,b0_int,b0_dir,"int32"); b0_fst,b0_fma=strata(groups,pmeta,b0_float); b0_ist,b0_ima=strata(groups,pmeta,b0_prod)
    # Dense train pair row indices for B1/C models, preserve deterministic m4 permutation not needed for dense learners.
    b1_good=dense["good"].astype(np.int64); b1_bad=dense["bad"].astype(np.int64); b1_score,b1_receipt=b1_probe(design,groups,pmeta,(b1_good,b1_bad)); b1_st,b1_ma=strata(groups,pmeta,b1_score)
    dx=d_features(design,groups); dw,dbl=load_d1(d1p); d1=np.asarray([dx[i].dot(dw if groups["stm"][i]==0 else dbl) for i in range(len(dx))]); t0=groups["t0"].copy(); teacher=groups["teacher"].copy(); t0_st,t0_ma=strata(groups,pmeta,t0); d1_st,d1_ma=strata(groups,pmeta,d1); q_st,q_ma=strata(groups,pmeta,teacher)
    good=top["good"].astype(np.int64); bad=top["bad"].astype(np.int64)
    phase=np.zeros((len(dx),4));
    for i,p in enumerate(groups["pieces"]): phase[i,(0 if p>=30 else 1 if p>=20 else 2 if p>=12 else 3)]=1
    c0x=np.column_stack([t0,d1,phase,groups["stm"]]); c0w,c0rec=fit_dense_pair(c0x,good,bad,l2=1e-6); c0=c0x.dot(c0w); c0_st,c0_ma=strata(groups,pmeta,c0)
    c1w,c1rec=fit_dense_pair(dx,good,bad,z0=t0[good]-t0[bad],l2=1e-3); c1=t0+dx.dot(c1w); c1_st,c1_ma=strata(groups,pmeta,c1)
    dord=np.random.Generator(np.random.PCG64(m4.PAIR_SEED)).permutation(len(top["good"])); dd=(dx[top["good"]]-dx[top["bad"]])[dord]; c2theta,c2rec=fit_residual(Ptop,Etop,z0top,1e-5,None,extra=dd,extra_l2=1e-3); c2delta=theta_to_delta(c2theta[:Ptop.shape[1]+Etop.shape[1]],atop,header,w0); c2=float_scores(design,header,w0.astype(np.float64)+c2delta)+dx.dot(c2theta[Ptop.shape[1]+Etop.shape[1]:]); c2_st,c2_ma=strata(groups,pmeta,c2)
    models={"T0":(t0_st,t0_ma),"D1":(d1_st,d1_ma),"micro1000":(q_st,q_ma),"B0_FLOAT":(b0_fst,b0_fma),"B0_INT32":(b0_ist,b0_ima),"B1":(b1_st,b1_ma),"C0":(c0_st,c0_ma),"C1":(c1_st,c1_ma),"C2":(c2_st,c2_ma)}
    # principal CIs versus T0 and D1/best pure where aligned.
    cis={}
    for n in ("B0_FLOAT","B0_INT32","B1","C0","C1","C2"):
        cis[n+"_minus_T0"]=bootstrap_delta(models[n][1],t0_ma)
    for n in ("C0","C1","C2"):
        cis[n+"_minus_D1"]=bootstrap_delta(models[n][1],d1_ma)
    best_joint=max(("C0","C1","C2"),key=lambda n:models[n][0]["global"]["pairwise"])
    report={"schema":"jass.transfer_capacity_joint_screen.v1","passed":True,"verdict":"TRANSFER_CAPACITY_JOINT_SCREEN_READY","prereg_sha":"78b2da436f990b6db870c7c1f7b3ee7a7d12b130","anti_leakage":{"m5_1612_fit_reads":0,"m5_1612_model_selection_reads":0,"m5_1612_input_options_exposed":False,"new_q200_labels":0},"split":split_report,"stage_a":{"arms":arm_results,"best_by_guard":bests},"stage_b":{"B0":{"source_arm":best0,"float":b0_fst,"int32":b0_ist,"quantization_pairwise_loss":b0_fst["global"]["pairwise"]-b0_ist["global"]["pairwise"],"unanchored_rms_p99":"reported_by_anchor_artifacts"},"B1":{"receipt":b1_receipt,"metrics":b1_st}},"stage_c":{"C0":{"receipt":c0rec,"metrics":c0_st},"C1":{"receipt":c1rec,"metrics":c1_st},"C2":{"receipt":c2rec,"metrics":c2_st},"best_joint":best_joint},"baselines":{"T0":t0_st,"D1":d1_st,"micro1000":q_st},"principal_bootstrap_cis":cis,"anchor_selection":{"seed":ANCHOR_SEED,"rows":ANCHOR_N,"index_sha256":anchor_sel_sha},"implementation_freeze":{"C0_l2":1e-6,"C1_l2":1e-3,"C2_pattern_l2":1e-5,"C2_d_l2":1e-3,"bootstrap_samples":BOOTSTRAP_SAMPLES,"bootstrap_seed":BOOTSTRAP_SEED},"artifacts":{"design_sha256":sha256(design_path),"constraints_sha256":sha256(constraints_path),"groups_sha256":sha256(groups_path),"children_sha256":sha256(children),"curriculum_sha256":sha256(curriculum),"d1_policy_sha256":sha256(d1p)},"fits":9+1+3,"pattern_eval_fits":9+1,"d1_refits":0,"selfplay":0,"strength_games":0,"promotion_authorized":False,"automatic_promotion":False,"fresh_q200_generated":0}
    (out/"screen-report.json").write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=True)+"\n"); print(json.dumps({"verdict":report["verdict"],"best_G0":best0,"best_joint":best_joint,"B1":b1_st["global"],"C2":c2_st["global"]},sort_keys=True))

if __name__=="__main__": main()
