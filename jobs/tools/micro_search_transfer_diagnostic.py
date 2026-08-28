#!/usr/bin/env python3
"""Read-only post-M5 transfer diagnostic.

Compares frozen T0/CURRICULUM, sealed D1, exact 1000-node micro-search,
and frozen T1 on the exact accepted M5 stable-pair cohort and q200 target.
No fit, refit, self-play, strength, promotion, or decision gate is performed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from jobs.tools.deep_sibling_confirmation import load_policy
from jobs.tools.deep_sibling_pairwise import (
    PHASES,
    ParentMeta,
    accepted_pairs,
    load_feat,
    load_groups,
    metrics_by_parent,
    move_features,
)

DEFAULT_BOOTSTRAP_SAMPLES = 100_000
DEFAULT_BOOTSTRAP_SEED = 2026090221


def load_parents(path: Path) -> dict[int, ParentMeta]:
    out: dict[int, ParentMeta] = {}
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        req = {"parent_id", "parent_stm", "pieces", "legal_moves", "phase"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):
            raise ValueError(f"M5 parent metadata drift: {rd.fieldnames!r}")
        for r in rd:
            p = ParentMeta(
                parent_id=int(r["parent_id"]), stm=int(r["parent_stm"]),
                pieces=int(r["pieces"]), legal_moves=int(r["legal_moves"]),
                phase=r["phase"], partition="holdout")
            if p.parent_id in out or p.stm not in (0, 1) or p.phase not in PHASES:
                raise ValueError("invalid/duplicate M5 parent metadata")
            if not (9 <= p.pieces <= 40 and 2 <= p.legal_moves <= 16):
                raise ValueError("M5 parent outside frozen support")
            out[p.parent_id] = p
    if sorted(out) != list(range(len(out))) or len(out) != 4000:
        raise ValueError(f"M5 requires contiguous 4000 parents, got {len(out)}")
    counts = {ph: sum(p.phase == ph for p in out.values()) for ph in PHASES}
    if counts != {ph: 1000 for ph in PHASES}:
        raise ValueError(f"M5 phase quota drift: {counts}")
    return out


def load_scalar_scores(path: Path, n: int) -> tuple[np.ndarray, np.ndarray]:
    t0 = np.empty(n, dtype=np.float64)
    t1 = np.empty(n, dtype=np.float64)
    seen = 0
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        if rd.fieldnames != ["row_index", "t0_parent", "t1_parent"]:
            raise ValueError(f"M5 scalar score fields drift: {rd.fieldnames!r}")
        for r in rd:
            i = int(r["row_index"])
            if i != seen or i >= n:
                raise ValueError("M5 scalar score ordering drift")
            t0[i], t1[i] = float(r["t0_parent"]), float(r["t1_parent"])
            seen += 1
    if seen != n or not np.all(np.isfinite(t0)) or not np.all(np.isfinite(t1)):
        raise ValueError("M5 scalar score count/finite drift")
    return t0, t1


def load_q1000(path: Path, n: int) -> np.ndarray:
    q = np.empty(n, dtype=np.float64)
    seen: set[int] = set()
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        req = {"row_index", "q1000_parent"}
        if rd.fieldnames is None or not req.issubset(rd.fieldnames):
            raise ValueError(f"q1000 ladder fields drift: {rd.fieldnames!r}")
        for r in rd:
            i = int(r["row_index"])
            if i in seen or not (0 <= i < n):
                raise ValueError("duplicate/out-of-range q1000 row")
            q[i] = float(r["q1000_parent"])
            seen.add(i)
    if len(seen) != n or not np.all(np.isfinite(q)):
        raise ValueError(f"q1000 rows incomplete: {len(seen)} != {n}")
    return q


def bootstrap_delta(a: dict[str, np.ndarray], b: dict[str, np.ndarray], samples: int, seed: int) -> dict:
    pd = a["pairwise"] - b["pairwise"]
    td = a["top_hit"] - b["top_hit"]
    if len(pd) == 0 or len(pd) != len(td):
        raise ValueError("bootstrap requires aligned nonempty parent metrics")
    rng = np.random.default_rng(seed)
    n = len(pd)
    pb = np.empty(samples, dtype=np.float64)
    tb = np.empty(samples, dtype=np.float64)
    batch = 128
    for start in range(0, samples, batch):
        stop = min(samples, start + batch)
        idx = rng.integers(0, n, size=(stop - start, n))
        pb[start:stop] = pd[idx].mean(axis=1)
        tb[start:stop] = td[idx].mean(axis=1)

    def one(v: np.ndarray, boot: np.ndarray) -> dict:
        return {
            "mean": float(v.mean()),
            "ci_low": float(np.quantile(boot, 0.025)),
            "ci_high": float(np.quantile(boot, 0.975)),
            "probability_gt_zero": float(np.mean(boot > 0)),
            "samples": int(samples), "seed": int(seed), "cluster": "parent",
        }
    return {"pairwise": one(pd, pb), "top_hit": one(td, tb)}


def summary(m: dict[str, np.ndarray]) -> dict[str, float]:
    return {"pairwise": float(m["pairwise"].mean()), "top_hit": float(m["top_hit"].mean())}


def pair_outcome(score: np.ndarray, good: int, bad: int) -> int:
    if score[good] > score[bad]:
        return 1
    if score[good] < score[bad]:
        return -1
    return 0


def disagreement(pairs: dict[int, list[tuple[int, int]]], a: np.ndarray, b: np.ndarray,
                 a_name: str, b_name: str) -> dict:
    total = sum(len(v) for v in pairs.values())
    counts = {
        f"{a_name}_correct_{b_name}_wrong": 0,
        f"{b_name}_correct_{a_name}_wrong": 0,
        f"{a_name}_tie": 0,
        f"{b_name}_tie": 0,
    }
    for ps in pairs.values():
        for good, bad in ps:
            oa, ob = pair_outcome(a, good, bad), pair_outcome(b, good, bad)
            counts[f"{a_name}_tie"] += int(oa == 0)
            counts[f"{b_name}_tie"] += int(ob == 0)
            counts[f"{a_name}_correct_{b_name}_wrong"] += int(oa == 1 and ob == -1)
            counts[f"{b_name}_correct_{a_name}_wrong"] += int(ob == 1 and oa == -1)
    rates = {k: (v / total if total else math.nan) for k, v in counts.items()}
    return {"stable_pairs": total, "counts": counts, "rates": rates}


def strata(parents: dict[int, ParentMeta], parent_rows: dict[int, list[int]],
           pairs: dict[int, list[tuple[int, int]]], accepted: list[int], scores: dict[str, np.ndarray]) -> dict:
    out: dict[str, dict] = {"phase": {}, "colour": {}}
    for ph in PHASES:
        ids = [pid for pid in accepted if parents[pid].phase == ph]
        out["phase"][ph] = {
            "accepted_parents": len(ids),
            "metrics": {name: summary(metrics_by_parent(parent_rows, pairs, ids, s)) if ids else None
                        for name, s in scores.items()},
        }
    for stm, name in ((0, "white"), (1, "black")):
        ids = [pid for pid in accepted if parents[pid].stm == stm]
        out["colour"][name] = {
            "accepted_parents": len(ids),
            "metrics": {key: summary(metrics_by_parent(parent_rows, pairs, ids, s)) if ids else None
                        for key, s in scores.items()},
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parents", type=Path, required=True)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--scores", type=Path, required=True)
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--d1-policy", type=Path, required=True)
    ap.add_argument("--q1000", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--bootstrap-samples", type=int, default=DEFAULT_BOOTSTRAP_SAMPLES)
    ap.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    args = ap.parse_args()

    parents = load_parents(args.parents)
    meta = load_groups(args.groups, parents)
    feat = load_feat(args.features)
    if len(meta) != len(feat):
        raise ValueError("groups/features row mismatch")
    x = np.concatenate([feat, move_features(meta)], axis=1)
    if x.shape[1] != 126:
        raise ValueError("D1 feature width drift")
    weights = load_policy(args.d1_policy)

    t0, t1 = load_scalar_scores(args.scores, len(meta))
    teacher_t0 = np.asarray([m.t_baseline_parent for m in meta], dtype=np.float64)
    if np.count_nonzero(t0 != teacher_t0):
        raise ValueError("T0 score differs from frozen M5 teacher baseline")
    d1 = np.asarray([float(x[i] @ weights[m.parent_stm]) for i, m in enumerate(meta)], dtype=np.float64)
    q1000 = load_q1000(args.q1000, len(meta))

    parent_rows: dict[int, list[int]] = defaultdict(list)
    for i, m in enumerate(meta):
        parent_rows[m.parent_id].append(i)
    if set(parent_rows) != set(parents):
        raise ValueError("teacher did not emit siblings for every M5 parent")
    pairs = accepted_pairs(parent_rows, meta)
    accepted = sorted(pairs)
    if not accepted:
        raise ValueError("no accepted M5 stable-pair support")

    scores = {"T0": t0, "D1": d1, "micro1000": q1000, "T1": t1}
    pm = {name: metrics_by_parent(parent_rows, pairs, accepted, s) for name, s in scores.items()}
    metrics = {name: summary(m) for name, m in pm.items()}
    deltas = {
        "T1_minus_T0": bootstrap_delta(pm["T1"], pm["T0"], args.bootstrap_samples, args.bootstrap_seed),
        "T1_minus_D1": bootstrap_delta(pm["T1"], pm["D1"], args.bootstrap_samples, args.bootstrap_seed),
        "T1_minus_micro1000": bootstrap_delta(pm["T1"], pm["micro1000"], args.bootstrap_samples, args.bootstrap_seed),
    }

    denom_d = metrics["D1"]["pairwise"] - metrics["T0"]["pairwise"]
    denom_q = metrics["micro1000"]["pairwise"] - metrics["T0"]["pairwise"]
    gain_t1 = metrics["T1"]["pairwise"] - metrics["T0"]["pairwise"]
    ratios = {
        "R_D": None if denom_d <= 0 else gain_t1 / denom_d,
        "R_1000": None if denom_q <= 0 else gain_t1 / denom_q,
        "definitions": {
            "R_D": "(A_T1-A_T0)/(A_D1-A_T0)",
            "R_1000": "(A_T1-A_T0)/(A_1000-A_T0)",
            "denominator_guard": "NA when denominator <= 0",
        },
    }

    report = {
        "schema": "jass.micro_search_post_m5_transfer_diagnostic.v1",
        "diagnostic_only": True,
        "scientific_gate": False,
        "accepted_parents": len(accepted),
        "stable_pairs": int(sum(len(v) for v in pairs.values())),
        "metrics": metrics,
        "bootstrap_deltas": deltas,
        "strata": strata(parents, parent_rows, pairs, accepted, scores),
        "disagreement": {
            "T1_vs_D1": disagreement(pairs, t1, d1, "T1", "D1"),
            "T1_vs_micro1000": disagreement(pairs, t1, q1000, "T1", "micro1000"),
        },
        "transfer_ratios": ratios,
        "stable_pair_rule": {
            "same_sign_50k_200k": True,
            "min_abs_d50_cp": 10,
            "min_abs_d200_cp": 30,
            "exact_terminal_tb_wdl_precedence": True,
            "teacher_target": "q200_parent",
        },
        "bootstrap": {"cluster": "parent", "samples": args.bootstrap_samples, "seed": args.bootstrap_seed},
        "fits": 0, "pattern_eval_fits": 0, "d1_refits": 0, "t_refits": 0,
        "selfplay": 0, "strength_games": 0, "promotion_authorized": False,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "A_T0": metrics["T0"]["pairwise"], "A_D1": metrics["D1"]["pairwise"],
        "A_1000": metrics["micro1000"]["pairwise"], "A_T1": metrics["T1"]["pairwise"],
        "R_D": ratios["R_D"], "R_1000": ratios["R_1000"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
