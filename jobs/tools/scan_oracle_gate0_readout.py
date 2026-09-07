#!/usr/bin/env python3
"""Read-only Scan-oracle Gate-0 paired runtime readout."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from pathlib import Path

import numpy as np

BOOTSTRAPS = 20_000
SEED = 2026090702
SCAN_BUDGET = 200_000


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", newline="") if path.suffix == ".gz" else path.open("r", encoding="utf-8", newline="")


def selected_ids(path: Path) -> list[int]:
    ids = [int(x) for x in path.read_text(encoding="utf-8").split()]
    if len(ids) != 512 or len(set(ids)) != 512:
        raise ValueError("selected parent cardinality drift")
    return ids


def load_groups(path: Path, ids: set[int]):
    by_parent: dict[int, list[int]] = {pid: [] for pid in ids}
    semantic: dict[tuple[int, int, int, str, int], int] = {}
    phase: dict[int, str] = {}
    with open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        req = {"row_index","parent_id","from","to","captured_hex","promotes","parent_phase"}
        if reader.fieldnames is None or not req.issubset(reader.fieldnames):
            raise ValueError("group fields drift")
        for row in reader:
            pid = int(row["parent_id"])
            if pid not in ids:
                continue
            rid = int(row["row_index"])
            key = (pid, int(row["from"]), int(row["to"]), row["captured_hex"].lower(), int(row["promotes"]))
            if key in semantic:
                raise ValueError("duplicate semantic sibling")
            semantic[key] = rid
            by_parent[pid].append(rid)
            old = phase.setdefault(pid, row["parent_phase"])
            if old != row["parent_phase"]:
                raise ValueError("parent phase drift")
    if any(len(v) < 2 for v in by_parent.values()):
        raise ValueError("missing selected parent siblings")
    return by_parent, semantic, phase


def load_scan(paths: list[Path], wanted_rows: set[int]) -> dict[int, float]:
    out: dict[int, float] = {}
    for path in paths:
        with open_text(path) as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            req = {"row_index","budget_nodes","parent_score_centi"}
            if reader.fieldnames is None or not req.issubset(reader.fieldnames):
                raise ValueError(f"{path}: Scan fields drift")
            for row in reader:
                if int(row["budget_nodes"]) != SCAN_BUDGET:
                    continue
                rid = int(row["row_index"])
                if rid not in wanted_rows:
                    continue
                if rid in out:
                    raise ValueError("duplicate Scan row")
                value = float(row["parent_score_centi"])
                if not math.isfinite(value):
                    raise ValueError("nonfinite Scan score")
                out[rid] = value
    if set(out) != wanted_rows:
        raise ValueError(f"Scan coverage drift missing={len(wanted_rows-set(out))}")
    return out


def load_arm(path: Path, ids: set[int]):
    out = {}
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        req = {"parent_id","from","to","captured_hex","promotes","nodes","completed_depth","eval_calls","wall_us","d3_feature_calls"}
        if reader.fieldnames is None or not req.issubset(reader.fieldnames):
            raise ValueError("arm fields drift")
        for row in reader:
            pid = int(row["parent_id"])
            if pid not in ids or pid in out:
                raise ValueError("arm parent coverage/duplicate drift")
            out[pid] = {
                "key": (pid,int(row["from"]),int(row["to"]),row["captured_hex"].lower(),int(row["promotes"])),
                "nodes": int(row["nodes"]), "depth": float(row["completed_depth"]),
                "eval_calls": float(row["eval_calls"]), "wall_us": float(row["wall_us"]),
                "d3_feature_calls": int(row["d3_feature_calls"]),
            }
    if set(out) != ids:
        raise ValueError(f"arm coverage drift rows={len(out)}")
    return out


def p95(x: np.ndarray) -> float:
    return float(np.percentile(x, 95))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--ids", type=Path, required=True)
    ap.add_argument("--scan-score", type=Path, action="append", required=True)
    ap.add_argument("--control", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--candidate-name", default="D3")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    ordered = selected_ids(args.ids); ids = set(ordered)
    by_parent, semantic, phase = load_groups(args.groups, ids)
    wanted_rows = {rid for pid in ids for rid in by_parent[pid]}
    scan = load_scan(args.scan_score, wanted_rows)
    control = load_arm(args.control, ids); candidate = load_arm(args.candidate, ids)

    rc=[]; rd=[]; hc=[]; hd=[]; depth_delta=[]; eval_delta=[]; wall_ratio=[]
    rows=[]
    for pid in ordered:
        best = max(scan[rid] for rid in by_parent[pid])
        ck = control[pid]["key"]; dk = candidate[pid]["key"]
        if ck not in semantic or dk not in semantic:
            raise ValueError(f"selected move not found among frozen siblings parent={pid}")
        cr = best - scan[semantic[ck]]; dr = best - scan[semantic[dk]]
        if cr < -1e-9 or dr < -1e-9:
            raise ValueError("negative Scan regret")
        rc.append(cr); rd.append(dr); hc.append(cr == 0.0); hd.append(dr == 0.0)
        depth_delta.append(candidate[pid]["depth"]-control[pid]["depth"])
        eval_delta.append(candidate[pid]["eval_calls"]-control[pid]["eval_calls"])
        if control[pid]["wall_us"] <= 0 or candidate[pid]["wall_us"] <= 0:
            raise ValueError("nonpositive wall timing")
        wall_ratio.append(candidate[pid]["wall_us"]/control[pid]["wall_us"])
        rows.append({"parent_id":pid,"phase":phase[pid],"control_regret":cr,"candidate_regret":dr})

    rc=np.asarray(rc); rd=np.asarray(rd); improvement=rc-rd
    rng=np.random.default_rng(SEED)
    boots=np.empty(BOOTSTRAPS,dtype=np.float64)
    n=len(ordered)
    for i in range(BOOTSTRAPS):
        idx=rng.integers(0,n,size=n)
        boots[i]=float(np.mean(improvement[idx]))
    lo,hi=np.percentile(boots,[2.5,97.5])
    wr=np.asarray(wall_ratio); dd=np.asarray(depth_delta); ed=np.asarray(eval_delta)
    control_top=float(np.mean(hc)); candidate_top=float(np.mean(hd))
    mean_imp=float(np.mean(improvement)); median_wall=float(np.median(wr))
    supported = mean_imp > 0 and float(lo) > 0 and candidate_top >= control_top and median_wall <= 1.05

    def metrics(regret: np.ndarray, hit: list[bool]):
        return {"mean_regret":float(np.mean(regret)),"median_regret":float(np.median(regret)),
                "p95_regret":p95(regret),"top_hit":float(np.mean(hit)),
                "catastrophic_regret_ge_50":float(np.mean(regret >= 50.0))}

    payload={
        "schema":"jass.scan_oracle_gate0_readout.v1","benchmark_only":True,
        "parents":n,"scan_reference_nodes":SCAN_BUDGET,
        "control":metrics(rc,hc),"candidate_name":args.candidate_name,"candidate":metrics(rd,hd),
        "paired":{"mean_regret_improvement":mean_imp,"regret_improvement_ci95":[float(lo),float(hi)],
                  "top_hit_delta":candidate_top-control_top,"mean_completed_depth_delta":float(np.mean(dd)),
                  "mean_eval_calls_delta":float(np.mean(ed)),"median_wall_ratio":median_wall},
        "gate":{"mean_regret_improvement_gt_0":mean_imp>0,"regret_lcb95_gt_0":float(lo)>0,
                "top_hit_not_worse":candidate_top>=control_top,"median_wall_ratio_le_1p05":median_wall<=1.05,
                "verdict":"GATE0_SUPPORTED" if supported else "GATE0_NOT_SUPPORTED"},
        "retrospective_d3_would_have_been_rejected": (not supported) if args.candidate_name=="D3" else None,
        "bootstrap":{"repetitions":BOOTSTRAPS,"seed":SEED},
        "guards":{"scan_searches":0,"fits":0,"strength_games":0,"selfplay_games":0,"promotions":0,"bakes":0},
    }
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(payload,sort_keys=True))
    return 0

if __name__ == "__main__": raise SystemExit(main())
