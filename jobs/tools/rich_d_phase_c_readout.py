#!/usr/bin/env python3
"""Frozen Rich-D Phase-C readout for L3_RICH_D_TEACHER_TO_T_V1_20260827.

No fitting occurs here. The script evaluates the already-frozen Rich-D artifact,
the sealed linear D1 policy, byte-identical CURRICULUM/T, and q5k diagnostic on
one fresh deep-labelled Phase-C cohort. Stable-pair acceptance and parent-cluster
metrics match the original DSSD contract.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from jobs.tools.rich_d_teacher import (
    build_static_features,
    forward,
    read_feat,
    read_jnnw,
    StaticMeta,
)

PHASES = ("P0", "P1", "P2", "P3")
EXACT_SENTINEL = 2
BOOTSTRAP_SAMPLES = 100_000
BOOTSTRAP_SEED = 2026090104
MOVE_FEATURE_NAMES = (
    "num_captures", "captured_kings", "promotes", "moving_king", "from_norm", "to_norm"
)


@dataclass(frozen=True)
class Parent:
    parent_id: int
    stm: int
    phase: str
    pieces: int
    legal_moves: int


@dataclass(frozen=True)
class Sibling:
    row_index: int
    parent_id: int
    parent_stm: int
    from_sq: int
    to_sq: int
    num_captures: int
    captured_kings: int
    promotes: int
    moving_king: int
    exact_parent_utility: int
    t_baseline_parent: float
    q5k_parent: float
    q50_parent: float
    q200_parent: float


def load_parents(path: Path) -> dict[int, Parent]:
    out: dict[int, Parent] = {}
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {"parent_id", "parent_stm", "phase", "pieces", "legal_moves"}
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise ValueError(f"parent metadata drift: {rd.fieldnames!r}")
        for r in rd:
            p = Parent(int(r["parent_id"]), int(r["parent_stm"]), r["phase"], int(r["pieces"]), int(r["legal_moves"]))
            if p.parent_id in out or p.stm not in (0, 1) or p.phase not in PHASES:
                raise ValueError("invalid/duplicate parent metadata")
            if not (9 <= p.pieces <= 40 and 2 <= p.legal_moves <= 16):
                raise ValueError("parent outside frozen Phase-C support")
            out[p.parent_id] = p
    if sorted(out) != list(range(len(out))):
        raise ValueError("parent ids are not contiguous")
    return out


def load_groups(path: Path, parents: dict[int, Parent]) -> list[Sibling]:
    out: list[Sibling] = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {
            "row_index", "parent_id", "parent_stm", "from", "to", "num_captures",
            "captured_kings", "promotes", "moving_king", "exact_parent_utility",
            "t_baseline_parent", "q5k_parent", "q50_parent", "q200_parent",
        }
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise ValueError(f"teacher group fields drift: {rd.fieldnames!r}")
        for r in rd:
            s = Sibling(
                int(r["row_index"]), int(r["parent_id"]), int(r["parent_stm"]),
                int(r["from"]), int(r["to"]), int(r["num_captures"]), int(r["captured_kings"]),
                int(r["promotes"]), int(r["moving_king"]), int(r["exact_parent_utility"]),
                float(r["t_baseline_parent"]), float(r["q5k_parent"]), float(r["q50_parent"]), float(r["q200_parent"]),
            )
            p = parents.get(s.parent_id)
            if p is None or p.stm != s.parent_stm:
                raise ValueError("teacher/parent identity drift")
            if s.exact_parent_utility not in (-1, 0, 1, EXACT_SENTINEL):
                raise ValueError("invalid exact utility")
            out.append(s)
    if [s.row_index for s in out] != list(range(len(out))):
        raise ValueError("row_index drift")
    return out


def stable_relation(a: Sibling, b: Sibling) -> int:
    if a.parent_id != b.parent_id:
        raise ValueError("relation across parents")
    if a.exact_parent_utility != EXACT_SENTINEL and b.exact_parent_utility != EXACT_SENTINEL and a.exact_parent_utility != b.exact_parent_utility:
        return 1 if a.exact_parent_utility > b.exact_parent_utility else -1
    d50 = a.q50_parent - b.q50_parent
    d200 = a.q200_parent - b.q200_parent
    if d50 == 0 or d200 == 0 or ((d50 > 0) != (d200 > 0)):
        return 0
    if abs(d50) < 10 or abs(d200) < 30:
        return 0
    return 1 if d200 > 0 else -1


def accepted_pairs(parent_rows: dict[int, list[int]], meta: Sequence[Sibling]) -> dict[int, list[tuple[int, int]]]:
    out: dict[int, list[tuple[int, int]]] = {}
    for pid in sorted(parent_rows):
        rows = sorted(parent_rows[pid]); pairs: list[tuple[int, int]] = []
        for pos, i in enumerate(rows):
            for j in rows[pos + 1:]:
                rel = stable_relation(meta[i], meta[j])
                if rel > 0: pairs.append((i, j))
                elif rel < 0: pairs.append((j, i))
        if pairs: out[pid] = pairs
    return out


def move_features(meta: Sequence[Sibling]) -> np.ndarray:
    return np.asarray([[m.num_captures, m.captured_kings, m.promotes, m.moving_king, m.from_sq / 50.0, m.to_sq / 50.0] for m in meta], dtype=np.float64)


def parent_metrics(rows: list[int], pairs: list[tuple[int, int]], score: np.ndarray) -> tuple[float, float]:
    acc: list[float] = []; incoming: set[int] = set(); participating: set[int] = set()
    for good, bad in pairs:
        participating.update((good, bad)); incoming.add(bad)
        if score[good] > score[bad]: acc.append(1.0)
        elif score[good] == score[bad]: acc.append(0.5)
        else: acc.append(0.0)
    teacher_top = participating - incoming
    if not acc or not teacher_top:
        raise ValueError("invalid stable-pair graph")
    vals = np.asarray([score[i] for i in rows], dtype=np.float64)
    mx = np.max(vals)
    model_top = [rows[k] for k, v in enumerate(vals) if v == mx]
    return float(np.mean(acc)), float(np.mean([i in teacher_top for i in model_top]))


def metrics(parent_rows: dict[int, list[int]], pairs: dict[int, list[tuple[int, int]]], ids: list[int], score: np.ndarray) -> dict[str, np.ndarray]:
    pp, tt = [], []
    for pid in ids:
        a, b = parent_metrics(parent_rows[pid], pairs[pid], score); pp.append(a); tt.append(b)
    return {"pairwise": np.asarray(pp, dtype=np.float64), "top_hit": np.asarray(tt, dtype=np.float64)}


def bootstrap_delta(a: dict[str, np.ndarray], b: dict[str, np.ndarray], samples: int, seed: int) -> dict:
    pd = a["pairwise"] - b["pairwise"]; td = a["top_hit"] - b["top_hit"]
    if len(pd) == 0 or len(pd) != len(td): raise ValueError("empty bootstrap")
    rng = np.random.default_rng(seed); n = len(pd)
    pb = np.empty(samples); tb = np.empty(samples)
    batch = 128
    for start in range(0, samples, batch):
        stop = min(samples, start + batch)
        idx = rng.integers(0, n, size=(stop-start, n))
        pb[start:stop] = pd[idx].mean(axis=1); tb[start:stop] = td[idx].mean(axis=1)
    def s(v, boot):
        return {"mean": float(v.mean()), "ci_low": float(np.quantile(boot, .025)), "ci_high": float(np.quantile(boot, .975)), "probability_gt_zero": float(np.mean(boot > 0)), "samples": samples, "seed": seed}
    return {"pairwise": s(pd, pb), "top_hit": s(td, tb)}


def summary(m: dict[str, np.ndarray]) -> dict[str, float]:
    return {k: float(v.mean()) for k, v in m.items()}


def load_rich(path: Path, expected_sha: str) -> dict:
    raw = path.read_bytes(); sha = hashlib.sha256(raw).hexdigest()
    if sha != expected_sha: raise ValueError(f"Rich-D SHA drift {sha} != {expected_sha}")
    p = json.loads(raw)
    if p.get("schema") != "jass.rich_d_teacher.v1" or p.get("input_width") != 333 or p.get("architecture") != [333,384,192,96,1]:
        raise ValueError("Rich-D artifact contract drift")
    return p


def rich_scores(payload: dict, x: np.ndarray, meta: Sequence[Sibling]) -> np.ndarray:
    out = np.empty(len(meta), dtype=np.float64)
    for colour, name in ((0, "white_parent"), (1, "black_parent")):
        ids = np.asarray([i for i,m in enumerate(meta) if m.parent_stm == colour], dtype=np.int64)
        bank_p = payload["banks"][name]
        bank = {k: np.asarray(v, dtype=np.float64) for k,v in bank_p["params"].items()}
        mean = np.asarray(bank_p["mean"], dtype=np.float64); std = np.asarray(bank_p["std"], dtype=np.float64)
        vals, _ = forward(bank, (x[ids] - mean) / std)
        out[ids] = vals
    if not np.all(np.isfinite(out)): raise ValueError("nonfinite Rich-D score")
    return out


def load_d1(path: Path) -> dict:
    p = json.loads(path.read_text())
    if p.get("schema") != "jass.deep_sibling_policy.v1" or p.get("usable") is not True or p.get("eval_feature_width") != 120:
        raise ValueError("D1 policy drift")
    if p.get("move_feature_names") != list(MOVE_FEATURE_NAMES) or p.get("score_convention") != "higher_is_better_for_parent":
        raise ValueError("D1 feature/score drift")
    for name in ("white_parent", "black_parent"):
        if len(p["weights"][name]) != 126: raise ValueError("D1 width drift")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parents", type=Path, required=True)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--children", type=Path, required=True)
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--rich", type=Path, required=True)
    ap.add_argument("--rich-sha", required=True)
    ap.add_argument("--d1", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--bootstrap-samples", type=int, default=BOOTSTRAP_SAMPLES)
    ap.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    args = ap.parse_args()

    parents = load_parents(args.parents); meta = load_groups(args.groups, parents)
    rec = read_jnnw(args.children); feat = read_feat(args.features)
    if not (len(meta) == len(rec) == len(feat)): raise ValueError("row-count drift")
    smeta = [StaticMeta(m.parent_id,m.parent_stm,parents[m.parent_id].phase,parents[m.parent_id].pieces,parents[m.parent_id].legal_moves,m.from_sq,m.to_sq,m.num_captures,m.captured_kings,m.promotes,m.moving_king,m.t_baseline_parent) for m in meta]
    xrich = build_static_features(feat, rec, smeta)
    parent_rows: dict[int,list[int]] = defaultdict(list)
    for i,m in enumerate(meta): parent_rows[m.parent_id].append(i)
    if set(parent_rows) != set(parents): raise ValueError("missing emitted parent")
    pairs = accepted_pairs(parent_rows, meta); ids = sorted(pairs)

    accepted_by_phase = {ph: sum(parents[p].phase == ph for p in ids) for ph in PHASES}
    accepted_by_colour = {"white": sum(parents[p].stm == 0 for p in ids), "black": sum(parents[p].stm == 1 for p in ids)}
    support = {
        "selected_total_eq_8000": len(parents) == 8000,
        "accepted_parents_ge_6000": len(ids) >= 6000,
        "accepted_each_phase_ge_1000": all(accepted_by_phase[p] >= 1000 for p in PHASES),
        "accepted_each_colour_ge_2500": accepted_by_colour["white"] >= 2500 and accepted_by_colour["black"] >= 2500,
    }
    base = {
        "schema":"jass.rich_d_phase_c_readout.v1", "selected_parents":len(parents), "emitted_siblings":len(meta),
        "accepted_parents":len(ids), "accepted_by_phase":accepted_by_phase, "accepted_by_colour":accepted_by_colour,
        "stable_pairs":int(sum(len(v) for v in pairs.values())), "support_gates":support,
        "bootstrap":{"cluster":"parent","samples":args.bootstrap_samples,"seed":args.bootstrap_seed},
        "rich_d_artifact_sha256":args.rich_sha, "rich_d_refits":0, "t_refits":0, "pattern_eval_fits":0,
        "strength_games":0, "runtime_rich_d":False, "promotion_authorized":False,
    }
    if not all(support.values()):
        base.update({"passed":False,"verdict":"RICH_D_FRESH_SUPPORT_NOT_ESTABLISHED","next_stage":None})
        args.report.write_text(json.dumps(base,indent=2,sort_keys=True)+"\n"); return 0

    rich = load_rich(args.rich, args.rich_sha)
    rs1 = rich_scores(rich, xrich, meta)
    # Replay from bytes, not the same in-memory dict.
    rs2 = rich_scores(load_rich(args.rich, args.rich_sha), xrich, meta)
    replay = bool(np.array_equal(rs1, rs2))
    d1 = load_d1(args.d1); xd1 = np.concatenate([feat, move_features(meta)], axis=1)
    ds = np.empty(len(meta), dtype=np.float64)
    for i,m in enumerate(meta):
        name = "white_parent" if m.parent_stm == 0 else "black_parent"
        ds[i] = float(xd1[i] @ np.asarray(d1["weights"][name], dtype=np.float64))
    ts = np.asarray([m.t_baseline_parent for m in meta], dtype=np.float64)
    qs = np.asarray([m.q5k_parent for m in meta], dtype=np.float64)

    rm, dm, tm, qm = (metrics(parent_rows,pairs,ids,s) for s in (rs1,ds,ts,qs))
    rd = bootstrap_delta(rm,dm,args.bootstrap_samples,args.bootstrap_seed)
    rt = bootstrap_delta(rm,tm,args.bootstrap_samples,args.bootstrap_seed)

    phase_delta = {}
    for ph in PHASES:
        z = [p for p in ids if parents[p].phase == ph]
        a=metrics(parent_rows,pairs,z,rs1)["pairwise"]; b=metrics(parent_rows,pairs,z,ds)["pairwise"]
        phase_delta[ph] = {"parents":len(z),"rich_minus_d1_pairwise":float((a-b).mean())}
    colour_delta = {}
    for c,n in ((0,"white"),(1,"black")):
        z=[p for p in ids if parents[p].stm == c]
        a=metrics(parent_rows,pairs,z,rs1)["pairwise"]; b=metrics(parent_rows,pairs,z,ds)["pairwise"]
        colour_delta[n] = {"parents":len(z),"rich_minus_d1_pairwise":float((a-b).mean())}

    rsum, dsum, tsum, qsum = map(summary,(rm,dm,tm,qm))
    gates = {
        "rich_pairwise_ge_0_80": rsum["pairwise"] >= .80,
        "rich_minus_d1_pairwise_ci95_low_gt_0": rd["pairwise"]["ci_low"] > 0,
        "rich_minus_d1_top_hit_ci95_low_gt_0": rd["top_hit"]["ci_low"] > 0,
        "rich_minus_t_pairwise_ci95_low_gt_0": rt["pairwise"]["ci_low"] > 0,
        "rich_minus_d1_positive_each_phase": all(phase_delta[p]["rich_minus_d1_pairwise"] > 0 for p in PHASES),
        "rich_minus_d1_positive_both_colours": all(colour_delta[c]["rich_minus_d1_pairwise"] > 0 for c in ("white","black")),
        "deterministic_artifact_replay": replay,
    }
    passed = all(gates.values())
    base.update({
        "metrics":{"rich_d":rsum,"d1":dsum,"t_curriculum":tsum,"q5k_diagnostic":qsum},
        "delta_rich_minus_d1":rd,"delta_rich_minus_t":rt,"phase_deltas":phase_delta,"colour_deltas":colour_delta,
        "milestones":{"pairwise_ge_0_85":rsum["pairwise"]>=.85,"pairwise_ge_0_90":rsum["pairwise"]>=.90},
        "gates":gates,"passed":passed,
        "verdict":"RICH_D_TEACHER_SIGNAL_ESTABLISHED" if passed else "RICH_D_TEACHER_SIGNAL_NOT_ESTABLISHED",
        "next_stage":"rich_d_to_t_r2" if passed else None,
    })
    args.report.write_text(json.dumps(base,indent=2,sort_keys=True)+"\n")
    return 0

if __name__ == "__main__": raise SystemExit(main())
