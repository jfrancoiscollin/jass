#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Residual feature family probe for L3_RESIDUAL_FEATURE_DISCOVERY_V1_20260828.

The learner is intentionally tiny and fixed around sealed D1:
    R_F(child) = D1(child) + w @ ((F(child)-mean_train)/std_train)
D1's coefficient is exactly one and there is no intercept.  q50/q200 are read
only through the already-preregistered stable-pair relation; they can never be
feature inputs.  Q1/T2-fresh paths are rejected by source-role guards.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from scipy.optimize import minimize

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.rich_d_teacher import read_feat
from jobs.tools.rich_d_phase_c_readout import (
    Parent,
    Sibling,
    accepted_pairs,
    load_d1,
    load_groups,
    move_features,
    parent_metrics,
)

RFF_MAGIC = b"RFF1"
RFF_WIDTH = 66
L2 = 1e-3
MAXITER = 500
GTOL = 1e-7
MAXCOR = 10
PAIR_CAP = 250_000
PAIR_ORDER_SEED = 2026090701
BOOTSTRAP_SAMPLES = 100_000
BOOTSTRAP_SEED = 2026090702
SHAM_SEED_BASE = 2026090703
SHAM_COUNT = 32
PHASES = ("P0", "P1", "P2", "P3")

FAMILY_NAMES: dict[str, tuple[str, ...]] = {
    "F1": (
        "capture_legal_move_delta", "capture_legal_capture_delta", "capture_max_length_delta",
        "capture_mean_length_delta", "capture_max_kings_delta", "capture_mean_kings_delta",
        "capture_unique_landing_delta", "capture_unique_origin_delta", "capture_promotions_delta",
        "capture_promoting_captures_delta", "capture_forced_move_delta", "capture_landing_dispersion_delta",
    ),
    "F2": (
        "response_count", "response_capture_fraction", "response_promotion_fraction",
        "response_material_delta_min", "response_material_delta_mean", "response_material_delta_max",
        "response_parent_moves_min", "response_parent_moves_mean", "response_parent_moves_max",
        "response_parent_max_capture_min", "response_parent_max_capture_mean", "response_parent_max_capture_max",
        "response_parent_capture_fraction", "response_parent_forced_fraction",
    ),
    "F3": (
        "promotion_min_distance_delta", "promotion_mean_distance_delta", "promotion_le1_delta",
        "promotion_le2_delta", "promotion_le3_delta", "promotion_no_path_delta",
        "promotion_safe_min_distance_delta", "promotion_safe_mean_distance_delta", "promotion_safe_le1_delta",
        "promotion_safe_le2_delta", "promotion_safe_le3_delta", "promotion_safe_no_path_delta",
    ),
    "F4": (
        "structure_components_delta", "structure_largest_component_delta", "structure_isolated_delta",
        "structure_edges_delta", "structure_edge_file_delta", "structure_central16_delta",
        "structure_home_row_delta", "structure_blocked_delta", "structure_mean_nearest_delta",
        "structure_max_nearest_delta", "structure_abs_wing_skew_delta", "structure_bbox_area_delta",
        "structure_frontmost_advancement_delta", "structure_rearmost_advancement_delta",
        "structure_holes3_delta", "structure_quiet_mobility_per_man_delta",
    ),
    "F5": (
        "king_count_delta", "king_slide_delta", "king_safe_slide_delta", "king_denied_slide_delta",
        "king_edge_delta", "king_central16_delta", "king_trapped_delta", "king_min_enemy_distance_delta",
        "king_mean_enemy_distance_delta", "king_enemy_diagonal_delta", "king_pair_min_distance_delta",
        "king_pair_diagonal_delta",
    ),
}
FAMILY_NAMES["F6"] = tuple(name for fam in ("F1", "F2", "F3", "F4", "F5") for name in FAMILY_NAMES[fam])
FAMILY_SLICES = {
    "F1": slice(0, 12), "F2": slice(12, 26), "F3": slice(26, 38),
    "F4": slice(38, 54), "F5": slice(54, 66), "F6": slice(0, 66),
}
assert {k: len(v) for k, v in FAMILY_NAMES.items()} == {"F1":12,"F2":14,"F3":12,"F4":16,"F5":12,"F6":66}

# These tokens must never appear as feature names or be accepted by the model API.
FORBIDDEN_FEATURE_TOKENS = (
    "q1000", "q5k", "q50", "q200", "wdl", "d1_score", "t2_score",
    "source_identity", "split_membership", "outcome",
)
for names in FAMILY_NAMES.values():
    assert not any(token in name.lower() for name in names for token in FORBIDDEN_FEATURE_TOKENS)

@dataclass(frozen=True)
class ParentEx(Parent):
    canonical: str

@dataclass
class Source:
    tag: str
    parents: dict[int, ParentEx]
    siblings: list[Sibling]
    x: np.ndarray
    d1: np.ndarray
    parent_rows: dict[int, list[int]]
    pairs: dict[int, list[tuple[int, int]]]
    accepted_ids: list[int]

@dataclass(frozen=True)
class PairRef:
    canonical: str
    good: int
    bad: int


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_rff(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) < 12 or raw[:4] != RFF_MAGIC:
        raise ValueError("bad RFF1 header")
    n = int.from_bytes(raw[4:8], "little")
    k = int.from_bytes(raw[8:12], "little")
    if k != RFF_WIDTH:
        raise ValueError(f"RFF1 width drift {k} != {RFF_WIDTH}")
    expected = 12 + n * k * 4
    if len(raw) != expected:
        raise ValueError("RFF1 size/count drift")
    x = np.frombuffer(raw, dtype="<f4", offset=12, count=n*k).reshape(n, k).astype(np.float64)
    if not np.all(np.isfinite(x)):
        raise ValueError("nonfinite RFF1 features")
    return x


def family_matrix(x: np.ndarray, family: str) -> np.ndarray:
    if x.ndim != 2 or x.shape[1] != RFF_WIDTH or family not in FAMILY_SLICES:
        raise ValueError("family feature geometry drift")
    return np.asarray(x[:, FAMILY_SLICES[family]], dtype=np.float64)


def load_parents_with_canonical(path: Path) -> dict[int, ParentEx]:
    out: dict[int, ParentEx] = {}
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {"parent_id", "parent_stm", "phase", "pieces", "legal_moves", "canonical_fingerprint"}
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise ValueError(f"parent metadata lacks residual identity fields: {rd.fieldnames!r}")
        for row in rd:
            pid = int(row["parent_id"])
            p = ParentEx(pid, int(row["parent_stm"]), row["phase"], int(row["pieces"]), int(row["legal_moves"]), row["canonical_fingerprint"].strip())
            if pid in out or not p.canonical or p.stm not in (0,1) or p.phase not in PHASES:
                raise ValueError("invalid residual parent metadata")
            out[pid] = p
    if sorted(out) != list(range(len(out))):
        raise ValueError("parent ids not contiguous")
    return out


def d1_scores(eval_features: np.ndarray, siblings: Sequence[Sibling], d1: dict) -> np.ndarray:
    if eval_features.shape != (len(siblings), 120):
        raise ValueError("D1 eval feature geometry drift")
    xd = np.concatenate((eval_features, move_features(siblings)), axis=1)
    if xd.shape[1] != 126:
        raise ValueError("D1 width drift")
    out = np.empty(len(siblings), dtype=np.float64)
    for i, s in enumerate(siblings):
        bank = "white_parent" if s.parent_stm == 0 else "black_parent"
        out[i] = float(xd[i] @ np.asarray(d1["weights"][bank], dtype=np.float64))
    return out


def load_source(tag: str, parents_path: Path, groups_path: Path, eval_path: Path,
                residual_path: Path, d1: dict) -> Source:
    # Fail closed on consumed validation names: TRAIN/DEV screening must never
    # point at Q1 or T2-fresh artefacts. Identity-only exclusion happens later.
    role_text = " ".join(map(str, (parents_path, groups_path, eval_path, residual_path))).lower()
    if any(token in role_text for token in ("1617-l3-joint-td-q1", "1628c-l3-t2")):
        raise ValueError("consumed Q1/T2-fresh source forbidden during residual screening")
    parents = load_parents_with_canonical(parents_path)
    base_parents = {pid: Parent(p.parent_id,p.stm,p.phase,p.pieces,p.legal_moves) for pid,p in parents.items()}
    siblings = load_groups(groups_path, base_parents)
    ev = read_feat(eval_path)
    x = read_rff(residual_path)
    if not (len(siblings) == len(ev) == len(x)):
        raise ValueError("source sibling/feature row-count drift")
    parent_rows: dict[int, list[int]] = {pid: [] for pid in parents}
    for i,s in enumerate(siblings): parent_rows[s.parent_id].append(i)
    pairs = accepted_pairs(parent_rows, siblings)
    ids = sorted(pairs)
    if not ids:
        raise ValueError("source has no accepted stable parents")
    return Source(tag, parents, siblings, x, d1_scores(ev, siblings, d1), parent_rows, pairs, ids)


def fit_normalization(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(x) == 0 or x.ndim != 2 or not np.all(np.isfinite(x)):
        raise ValueError("invalid normalization rows")
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std < 1e-12] = 1.0
    return mean, std


def pair_refs(source: Source, row_offset: int = 0) -> list[PairRef]:
    out: list[PairRef] = []
    for pid in source.accepted_ids:
        canonical = source.parents[pid].canonical
        for good,bad in source.pairs[pid]:
            out.append(PairRef(canonical, row_offset+good, row_offset+bad))
    return out


def cap_pairs(pairs: Sequence[PairRef], cap: int = PAIR_CAP) -> list[PairRef]:
    def key(p: PairRef) -> tuple[bytes,str,int,int]:
        h = hashlib.sha256(f"{PAIR_ORDER_SEED}:{p.canonical}:{p.good}:{p.bad}".encode()).digest()
        return h,p.canonical,p.good,p.bad
    ordered = sorted(pairs, key=key)
    return ordered[:cap] if len(ordered) > cap else ordered


def _loss_grad(w: np.ndarray, diffs: np.ndarray) -> tuple[float, np.ndarray]:
    margin = diffs @ w
    loss = float(np.mean(np.logaddexp(0.0, -margin)) + 0.5 * L2 * np.dot(w,w))
    # d log(1+exp(-m))/dm = -1/(1+exp(m)), stably evaluated.
    negsig = np.empty_like(margin)
    pos = margin >= 0
    negsig[pos] = np.exp(-margin[pos]) / (1.0 + np.exp(-margin[pos]))
    negsig[~pos] = 1.0 / (1.0 + np.exp(margin[~pos]))
    grad = -(diffs.T @ negsig) / len(diffs) + L2 * w
    return loss, grad


def fit_probe(x_raw: np.ndarray, d1: np.ndarray, pairs: Sequence[PairRef], family: str) -> dict:
    # d1 is accepted only to lock row alignment; it is never fit/rescaled.
    if x_raw.ndim != 2 or d1.shape != (len(x_raw),) or not np.all(np.isfinite(d1)):
        raise ValueError("probe input geometry drift")
    if x_raw.shape[1] != len(FAMILY_NAMES[family]):
        raise ValueError("probe family width drift")
    mean,std = fit_normalization(x_raw)
    z = (x_raw - mean) / std
    kept = cap_pairs(pairs)
    if not kept:
        raise ValueError("no stable pairs to fit")
    good = np.asarray([p.good for p in kept], dtype=np.int64)
    bad = np.asarray([p.bad for p in kept], dtype=np.int64)
    diffs = z[good] - z[bad]
    x0 = np.zeros(x_raw.shape[1], dtype=np.float64)
    result = minimize(lambda w: _loss_grad(w,diffs), x0, method="L-BFGS-B", jac=True,
                      options={"maxiter":MAXITER,"gtol":GTOL,"maxcor":MAXCOR})
    coef = np.asarray(result.x, dtype=np.float64)
    if not result.success or not np.all(np.isfinite(coef)):
        raise RuntimeError(f"residual optimizer failed: {result.message}")
    payload = {
        "schema":"jass.residual_feature_probe.v1", "family":family,
        "feature_names":list(FAMILY_NAMES[family]), "d1_coefficient":1.0, "intercept":0.0,
        "normalization":{"mean":mean.tolist(),"std":std.tolist()}, "coefficients":coef.tolist(),
        "training":{"l2":L2,"pair_cap":PAIR_CAP,"pair_order_seed":PAIR_ORDER_SEED,
                    "pairs_available":len(pairs),"pairs_used":len(kept),
                    "optimizer":"scipy_L-BFGS-B","zero_init":True,"maxiter":MAXITER,
                    "gtol":GTOL,"maxcor":MAXCOR,"success":bool(result.success),
                    "status":int(result.status),"nit":int(result.nit),"fun":float(result.fun)},
    }
    canonical = json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()+b"\n"
    payload["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def score_probe(payload: dict, x_raw: np.ndarray, d1: np.ndarray) -> np.ndarray:
    if payload.get("d1_coefficient") != 1.0 or payload.get("intercept") != 0.0:
        raise ValueError("D1-fixed residual contract drift")
    mean=np.asarray(payload["normalization"]["mean"],dtype=np.float64)
    std=np.asarray(payload["normalization"]["std"],dtype=np.float64)
    coef=np.asarray(payload["coefficients"],dtype=np.float64)
    if x_raw.shape != (len(d1),len(coef)) or mean.shape != coef.shape or std.shape != coef.shape:
        raise ValueError("probe replay geometry drift")
    out = d1 + ((x_raw-mean)/std) @ coef
    if not np.all(np.isfinite(out)): raise ValueError("nonfinite probe score")
    return out


def artifact_bytes(payload: dict) -> bytes:
    return (json.dumps(payload,indent=2,sort_keys=True,allow_nan=False)+"\n").encode()


def replay_contract(payload: dict, x: np.ndarray, d1: np.ndarray) -> bool:
    raw = artifact_bytes(payload)
    again = json.loads(raw)
    return bool(np.array_equal(score_probe(payload,x,d1), score_probe(again,x,d1)))


def sham_sign(canonical: str, cohort_tag: str, sham_index: int) -> float:
    if not (0 <= sham_index < SHAM_COUNT): raise ValueError("sham index outside prereg")
    digest = hashlib.sha256(f"{SHAM_SEED_BASE+sham_index}:{cohort_tag}:{canonical}".encode()).digest()
    return 1.0 if (digest[0] & 1) else -1.0


def signed_rows(source: Source, x: np.ndarray, sham_index: int) -> np.ndarray:
    out=np.array(x,copy=True)
    for pid,rows in source.parent_rows.items():
        out[rows] *= sham_sign(source.parents[pid].canonical, source.tag, sham_index)
    return out


def parent_metric_arrays(source: Source, score: np.ndarray, ids: Sequence[int] | None=None) -> dict[str,np.ndarray]:
    ids = source.accepted_ids if ids is None else list(ids)
    pp=[]; tt=[]
    for pid in ids:
        p,t=parent_metrics(source.parent_rows[pid],source.pairs[pid],score)
        pp.append(p); tt.append(t)
    return {"pairwise":np.asarray(pp,dtype=np.float64),"top_hit":np.asarray(tt,dtype=np.float64)}


def delta_arrays(source: Source, candidate: np.ndarray, ids: Sequence[int] | None=None) -> dict[str,np.ndarray]:
    a=parent_metric_arrays(source,candidate,ids); b=parent_metric_arrays(source,source.d1,ids)
    return {k:a[k]-b[k] for k in a}


def pooled_delta(sources: Sequence[Source], scores: Sequence[np.ndarray], *, phase: str|None=None,
                 colour: int|None=None) -> dict[str,np.ndarray]:
    result={"pairwise":[],"top_hit":[]}
    for source,score in zip(sources,scores,strict=True):
        ids=[pid for pid in source.accepted_ids
             if (phase is None or source.parents[pid].phase==phase)
             and (colour is None or source.parents[pid].stm==colour)]
        if not ids: continue
        d=delta_arrays(source,score,ids)
        for k in result: result[k].append(d[k])
    return {k:np.concatenate(v) if v else np.empty(0,dtype=np.float64) for k,v in result.items()}


def bootstrap(values: np.ndarray, samples: int=BOOTSTRAP_SAMPLES, seed: int=BOOTSTRAP_SEED) -> dict:
    if len(values)==0: raise ValueError("empty bootstrap")
    rng=np.random.default_rng(seed); draws=np.empty(samples,dtype=np.float64); n=len(values)
    batch=128
    for start in range(0,samples,batch):
        stop=min(samples,start+batch)
        idx=rng.integers(0,n,size=(stop-start,n))
        draws[start:stop]=values[idx].mean(axis=1)
    return {"mean":float(values.mean()),"ci_low":float(np.quantile(draws,.025)),
            "ci_high":float(np.quantile(draws,.975)),"probability_gt_zero":float(np.mean(draws>0)),
            "parents":n,"samples":samples,"seed":seed}


def family_screen(train: Source, devs: Sequence[Source], family: str) -> tuple[dict,dict]:
    tx=family_matrix(train.x,family); tpairs=pair_refs(train)
    model=fit_probe(tx,train.d1,tpairs,family)
    replay=replay_contract(model,tx,train.d1)
    dev_scores=[score_probe(model,family_matrix(s.x,family),s.d1) for s in devs]
    observed=pooled_delta(devs,dev_scores)
    pair_boot=bootstrap(observed["pairwise"]); top_boot=bootstrap(observed["top_hit"])
    by_dev={}
    for source,score in zip(devs,dev_scores,strict=True):
        d=delta_arrays(source,score)
        by_dev[source.tag]={k:float(v.mean()) for k,v in d.items()}
    phases={ph:float(pooled_delta(devs,dev_scores,phase=ph)["pairwise"].mean()) for ph in PHASES}
    colours={name:float(pooled_delta(devs,dev_scores,colour=c)["pairwise"].mean()) for c,name in ((0,"white"),(1,"black"))}

    sham_deltas=[]
    for sham in range(SHAM_COUNT):
        sx=signed_rows(train,tx,sham)
        sm=fit_probe(sx,train.d1,tpairs,family)
        ss=[]
        for source in devs:
            dx=family_matrix(source.x,family)
            ss.append(score_probe(sm,signed_rows(source,dx,sham),source.d1))
        sham_deltas.append(float(pooled_delta(devs,ss)["pairwise"].mean()))
    max_sham=max(sham_deltas)
    gates={
        "pooled_pairwise_ci95_low_gt_0":pair_boot["ci_low"]>0,
        "dev_b_pairwise_point_gt_0":by_dev["DEV-B"]["pairwise"]>0,
        "dev_c_pairwise_point_gt_0":by_dev["DEV-C"]["pairwise"]>0,
        "positive_p0_p1_p2_p3":all(phases[p]>0 for p in PHASES),
        "positive_both_colours":all(colours[c]>0 for c in ("white","black")),
        "observed_gt_all_32_shams":pair_boot["mean"]>max_sham,
        "optimizer_and_replay":bool(model["training"]["success"] and replay),
    }
    report={
        "family":family,"feature_names":list(FAMILY_NAMES[family]),
        "pooled":{"pairwise_delta":pair_boot,"top_hit_delta":top_boot},
        "by_dev":by_dev,"phase_pairwise_delta":phases,"colour_pairwise_delta":colours,
        "shams":{"count":SHAM_COUNT,"seed_base":SHAM_SEED_BASE,"pooled_pairwise_deltas":sham_deltas,
                 "max_pooled_pairwise_delta":max_sham},
        "optimizer":model["training"],"replay":replay,"gates":gates,"screen_pass":all(gates.values()),
    }
    return report,model


def union_refit(sources: Sequence[Source], family: str, historical_screen: dict, d1_sha: str) -> dict:
    xs=[]; ds=[]; pairs=[]; offset=0; receipts=[]
    for source in sources:
        fx=family_matrix(source.x,family)
        xs.append(fx); ds.append(source.d1)
        pairs.extend(pair_refs(source,offset))
        receipts.append({"tag":source.tag,"rows":len(fx),"accepted_parents":len(source.accepted_ids),
                         "stable_pairs":sum(len(source.pairs[p]) for p in source.accepted_ids)})
        offset += len(fx)
    x=np.concatenate(xs,axis=0); d=np.concatenate(ds)
    model=fit_probe(x,d,pairs,family)
    model.update({"role":"RF1_FROZEN","d1_sha256":d1_sha,"sources":receipts,
                  "historical_screen":historical_screen,"post_fresh_fit_authorized":False})
    if not replay_contract(model,x,d): raise RuntimeError("RF1 union replay failed")
    return model


def choose_winner(reports: dict[str,dict]) -> str|None:
    passed=[f for f in ("F1","F2","F3","F4","F5","F6") if reports[f]["screen_pass"]]
    if not passed: return None
    best=passed[0]
    for f in passed[1:]:
        a=reports[f]["pooled"]; b=reports[best]["pooled"]
        dp=a["pairwise_delta"]["mean"]-b["pairwise_delta"]["mean"]
        if dp>1e-12 or (abs(dp)<=1e-12 and a["top_hit_delta"]["mean"]>b["top_hit_delta"]["mean"]+1e-12):
            best=f
        # lexical order is already preserved when both ties are <=1e-12.
    return best


def parse_source_args(prefix: str, args: argparse.Namespace, d1: dict) -> Source:
    key=prefix.lower().replace("-","_")
    return load_source(prefix,
        getattr(args,f"{key}_parents"),getattr(args,f"{key}_groups"),
        getattr(args,f"{key}_eval"),getattr(args,f"{key}_residual"),d1)


def add_source_args(ap: argparse.ArgumentParser, prefix: str) -> None:
    key=prefix.lower().replace("-","_")
    for suffix in ("parents","groups","eval","residual"):
        ap.add_argument(f"--{key}-{suffix}",dest=f"{key}_{suffix}",type=Path,required=True)


def run_screen(args: argparse.Namespace) -> int:
    if _sha256(args.d1) != args.d1_sha:
        raise ValueError("sealed D1 SHA mismatch")
    d1=load_d1(args.d1)
    train=parse_source_args("TRAIN-A",args,d1)
    devb=parse_source_args("DEV-B",args,d1); devc=parse_source_args("DEV-C",args,d1)
    reports={}; models={}
    for family in ("F1","F2","F3","F4","F5","F6"):
        reports[family],models[family]=family_screen(train,(devb,devc),family)
    winner=choose_winner(reports)
    report={
        "schema":"jass.residual_feature_historical_screen.v1",
        "prereg_merge_sha":args.prereg_sha,"d1_sha256":args.d1_sha,
        "seeds":{"pair_order":PAIR_ORDER_SEED,"bootstrap":BOOTSTRAP_SEED,"sham_base":SHAM_SEED_BASE},
        "bootstrap_samples":BOOTSTRAP_SAMPLES,"sham_count":SHAM_COUNT,
        "families":reports,"winner":winner,
        "q1_label_reads":0,"q1_score_reads":0,"t2_fresh_label_reads":0,"t2_fresh_score_reads":0,
        "selfplay":0,"strength_games":0,"runtime":0,"elo":0,"bake":0,"promotion_authorized":False,
    }
    if winner is None:
        report.update({"passed":False,"verdict":"RESIDUAL_FEATURE_FAMILY_NOT_ESTABLISHED","fresh_authorized":False})
    else:
        rf1=union_refit((train,devb,devc),winner,reports[winner],args.d1_sha)
        args.rf1_out.write_bytes(artifact_bytes(rf1))
        report.update({"passed":True,"verdict":"RESIDUAL_FEATURE_HISTORICAL_SCREEN_ESTABLISHED",
                       "fresh_authorized":True,"rf1_path":str(args.rf1_out),"rf1_sha256":_sha256(args.rf1_out)})
    args.report.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({"winner":winner,"verdict":report["verdict"],"fresh_authorized":report["fresh_authorized"]},sort_keys=True))
    return 0


def self_test() -> int:
    assert [len(FAMILY_NAMES[f]) for f in ("F1","F2","F3","F4","F5","F6")] == [12,14,12,16,12,66]
    assert FAMILY_NAMES["F6"] == FAMILY_NAMES["F1"]+FAMILY_NAMES["F2"]+FAMILY_NAMES["F3"]+FAMILY_NAMES["F4"]+FAMILY_NAMES["F5"]
    assert sham_sign("abc","TRAIN-A",0)==sham_sign("abc","TRAIN-A",0)
    # Synthetic residual ranking: D1 is exactly fixed and one feature separates every pair.
    x=np.asarray([[1.0],[0.0],[2.0],[0.0],[3.0],[0.0]],dtype=np.float64)
    d=np.asarray([0.1,0.1,-0.2,-0.2,0.0,0.0])
    pairs=[PairRef(str(i//2),i,i+1) for i in (0,2,4)]
    # Use F1-shaped synthetic matrix to exercise serialization/replay.
    xx=np.zeros((6,12)); xx[:,0]=x[:,0]
    model=fit_probe(xx,d,pairs,"F1")
    score=score_probe(model,xx,d)
    assert all(score[g]>score[b] for g,b in ((0,1),(2,3),(4,5)))
    assert model["d1_coefficient"]==1.0 and model["intercept"]==0.0
    assert replay_contract(model,xx,d)
    raw=artifact_bytes(model); assert raw==artifact_bytes(json.loads(raw))
    print("RESIDUAL_FEATURE_PROBE_SELFTEST_OK widths=12,14,12,16,12,66 d1_coefficient=1")
    return 0


def main() -> int:
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="command",required=True)
    sub.add_parser("self-test")
    sc=sub.add_parser("screen")
    sc.add_argument("--d1",type=Path,required=True); sc.add_argument("--d1-sha",required=True)
    sc.add_argument("--prereg-sha",required=True); sc.add_argument("--report",type=Path,required=True)
    sc.add_argument("--rf1-out",type=Path,required=True)
    add_source_args(sc,"TRAIN-A"); add_source_args(sc,"DEV-B"); add_source_args(sc,"DEV-C")
    args=ap.parse_args()
    if args.command=="self-test": return self_test()
    if args.command=="screen": return run_screen(args)
    raise AssertionError("unreachable")

if __name__=="__main__":
    raise SystemExit(main())
