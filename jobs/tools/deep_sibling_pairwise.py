#!/usr/bin/env python3
"""Frozen Phase-A learner for Deep Search Sibling Distillation v1.

Consumes only the already-frozen target-blind parent selection plus the completed
5k/50k/200k sibling teacher extract. Stable-pair acceptance, features, learner,
bootstrap, shams, and gates are exactly those preregistered in
L3_DEEP_SEARCH_SIBLING_DISTILLATION_V1_20260826.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

MOVE_FEATURE_NAMES = [
    "num_captures",
    "captured_kings",
    "promotes",
    "moving_king",
    "from_norm",
    "to_norm",
]
PHASES = ("P0", "P1", "P2", "P3")
EXACT_SENTINEL = 2


@dataclass(frozen=True)
class ParentMeta:
    parent_id: int
    stm: int
    pieces: int
    legal_moves: int
    phase: str
    partition: str


@dataclass(frozen=True)
class SiblingMeta:
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


def load_feat(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) < 12 or raw[:4] != b"FEAT":
        raise ValueError(f"{path}: bad FEAT header")
    n, k = struct.unpack_from("<II", raw, 4)
    expected = 12 + n * k * 4
    if len(raw) != expected:
        raise ValueError(f"{path}: size drift n={n} k={k} size={len(raw)} expected={expected}")
    if k != 120:
        raise ValueError(f"production eval feature width drift: {k} != 120")
    return np.frombuffer(raw, dtype="<f4", offset=12, count=n * k).reshape(n, k).astype(np.float64)


def load_parents(path: Path) -> dict[int, ParentMeta]:
    out: dict[int, ParentMeta] = {}
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {"parent_id", "parent_stm", "pieces", "legal_moves", "phase", "partition"}
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise ValueError(f"selected parents missing fields: {rd.fieldnames!r}")
        for row in rd:
            p = ParentMeta(
                parent_id=int(row["parent_id"]),
                stm=int(row["parent_stm"]),
                pieces=int(row["pieces"]),
                legal_moves=int(row["legal_moves"]),
                phase=row["phase"],
                partition=row["partition"],
            )
            if p.parent_id in out:
                raise ValueError("duplicate selected parent_id")
            if p.stm not in (0, 1) or p.phase not in PHASES or p.partition not in ("train", "holdout"):
                raise ValueError("invalid selected parent metadata")
            if not (9 <= p.pieces <= 40 and 2 <= p.legal_moves <= 16):
                raise ValueError("selected parent outside frozen eligibility")
            out[p.parent_id] = p
    if sorted(out) != list(range(len(out))):
        raise ValueError("selected parent IDs are not contiguous 0..N-1")
    return out


def load_groups(path: Path, parents: dict[int, ParentMeta]) -> list[SiblingMeta]:
    out: list[SiblingMeta] = []
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {
            "row_index", "parent_id", "parent_stm", "from", "to", "num_captures",
            "promotes", "moving_king", "captured_kings", "exact_parent_utility",
            "t_baseline_parent", "q5k_parent", "q50_parent", "q200_parent",
        }
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise ValueError(f"teacher groups missing fields: {rd.fieldnames!r}")
        for row in rd:
            s = SiblingMeta(
                row_index=int(row["row_index"]),
                parent_id=int(row["parent_id"]),
                parent_stm=int(row["parent_stm"]),
                from_sq=int(row["from"]),
                to_sq=int(row["to"]),
                num_captures=int(row["num_captures"]),
                captured_kings=int(row["captured_kings"]),
                promotes=int(row["promotes"]),
                moving_king=int(row["moving_king"]),
                exact_parent_utility=int(row["exact_parent_utility"]),
                t_baseline_parent=float(row["t_baseline_parent"]),
                q5k_parent=float(row["q5k_parent"]),
                q50_parent=float(row["q50_parent"]),
                q200_parent=float(row["q200_parent"]),
            )
            p = parents.get(s.parent_id)
            if p is None or p.stm != s.parent_stm:
                raise ValueError("teacher row parent identity drift")
            if s.exact_parent_utility not in (-1, 0, 1, EXACT_SENTINEL):
                raise ValueError("invalid exact_parent_utility")
            out.append(s)
    if [s.row_index for s in out] != list(range(len(out))):
        raise ValueError("teacher row_index is not contiguous and ordered")
    return out


def move_features(meta: list[SiblingMeta]) -> np.ndarray:
    return np.asarray([
        [
            m.num_captures,
            m.captured_kings,
            m.promotes,
            m.moving_king,
            m.from_sq / 50.0,
            m.to_sq / 50.0,
        ]
        for m in meta
    ], dtype=np.float64)


def stable_relation(a: SiblingMeta, b: SiblingMeta) -> int:
    """Return +1 if a>b, -1 if b>a, 0 if pair is not accepted."""
    if a.parent_id != b.parent_id:
        raise ValueError("stable relation requires siblings of one parent")
    if (a.exact_parent_utility != EXACT_SENTINEL
            and b.exact_parent_utility != EXACT_SENTINEL
            and a.exact_parent_utility != b.exact_parent_utility):
        return 1 if a.exact_parent_utility > b.exact_parent_utility else -1

    d50 = a.q50_parent - b.q50_parent
    d200 = a.q200_parent - b.q200_parent
    if d50 == 0 or d200 == 0:
        return 0
    if (d50 > 0) != (d200 > 0):
        return 0
    if abs(d50) < 10 or abs(d200) < 30:
        return 0
    return 1 if d200 > 0 else -1


def accepted_pairs(parent_rows: dict[int, list[int]], meta: list[SiblingMeta]) -> dict[int, list[tuple[int, int]]]:
    out: dict[int, list[tuple[int, int]]] = {}
    for pid in sorted(parent_rows):
        rows = sorted(parent_rows[pid])
        pairs: list[tuple[int, int]] = []
        for pos, i in enumerate(rows):
            for j in rows[pos + 1:]:
                rel = stable_relation(meta[i], meta[j])
                if rel > 0:
                    pairs.append((i, j))
                elif rel < 0:
                    pairs.append((j, i))
        if pairs:
            out[pid] = pairs
    return out


def pair_matrix(pairs_by_parent: dict[int, list[tuple[int, int]]], parent_ids: Iterable[int], x: np.ndarray,
                cap: int) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    keyed: list[tuple[int, int, int]] = []
    for pid in sorted(parent_ids):
        for good, bad in pairs_by_parent.get(pid, []):
            keyed.append((pid, good, bad))
    if cap > 0 and len(keyed) > cap:
        keyed = keyed[:cap]
    if not keyed:
        return np.empty((0, x.shape[1]), dtype=np.float64), keyed
    good = np.asarray([p[1] for p in keyed], dtype=np.int64)
    bad = np.asarray([p[2] for p in keyed], dtype=np.int64)
    return x[good] - x[bad], keyed


def fit_pairwise(d: np.ndarray, l2: float, maxiter: int, gtol: float) -> tuple[np.ndarray | None, dict]:
    if len(d) == 0:
        return None, {"success": False, "status": -1, "message": "no training pairs", "iterations": 0, "pairs": 0}
    scale = d.std(axis=0)
    scale[scale < 1e-8] = 1.0
    dn = d / scale
    n = float(len(dn))

    def fun_grad(w: np.ndarray) -> tuple[float, np.ndarray]:
        z = dn @ w
        loss = float(np.logaddexp(0.0, -z).sum() / n + 0.5 * l2 * np.dot(w, w))
        grad = -(dn.T @ expit(-z)) / n + l2 * w
        return loss, grad

    r = minimize(
        lambda w: fun_grad(w),
        np.zeros(dn.shape[1], dtype=np.float64),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": maxiter, "gtol": gtol, "maxcor": 20},
    )
    raw_w = np.asarray(r.x, dtype=np.float64) / scale
    receipt = {
        "success": bool(r.success), "status": int(r.status), "message": str(r.message),
        "iterations": int(r.nit), "objective": float(r.fun),
        "gradient_inf_norm": float(np.max(np.abs(r.jac))), "gtol": gtol, "pairs": int(len(d)),
    }
    return raw_w, receipt


def parent_metrics(rows: list[int], pairs: list[tuple[int, int]], score: np.ndarray) -> tuple[float, float]:
    if not pairs:
        raise ValueError("parent metric requires accepted stable pairs")
    acc = []
    incoming: set[int] = set()
    participating: set[int] = set()
    for good, bad in pairs:
        participating.update((good, bad))
        incoming.add(bad)
        if score[good] > score[bad]:
            acc.append(1.0)
        elif score[good] == score[bad]:
            acc.append(0.5)
        else:
            acc.append(0.0)
    teacher_top = participating - incoming
    if not teacher_top:
        raise ValueError("stable-pair relation has no maximal sibling")
    vals = np.asarray([score[i] for i in rows], dtype=np.float64)
    top = np.max(vals)
    model_top = [rows[k] for k, v in enumerate(vals) if v == top]
    top_hit = float(np.mean([i in teacher_top for i in model_top]))
    return float(np.mean(acc)), top_hit


def metrics_by_parent(parent_rows: dict[int, list[int]], pairs_by_parent: dict[int, list[tuple[int, int]]],
                      ids: list[int], score: np.ndarray) -> dict[str, np.ndarray]:
    pair, top = [], []
    for pid in ids:
        a, b = parent_metrics(parent_rows[pid], pairs_by_parent[pid], score)
        pair.append(a)
        top.append(b)
    return {"pairwise": np.asarray(pair, dtype=np.float64), "top_hit": np.asarray(top, dtype=np.float64)}


def bootstrap_deltas(pair_delta: np.ndarray, top_delta: np.ndarray, samples: int, seed: int) -> dict:
    if len(pair_delta) == 0 or len(pair_delta) != len(top_delta):
        raise ValueError("bootstrap requires aligned nonempty parent deltas")
    rng = np.random.default_rng(seed)
    n = len(pair_delta)
    pair_out = np.empty(samples, dtype=np.float64)
    top_out = np.empty(samples, dtype=np.float64)
    batch = 512
    for start in range(0, samples, batch):
        stop = min(samples, start + batch)
        idx = rng.integers(0, n, size=(stop - start, n))
        pair_out[start:stop] = pair_delta[idx].mean(axis=1)
        top_out[start:stop] = top_delta[idx].mean(axis=1)

    def summarise(values: np.ndarray, boot: np.ndarray) -> dict:
        return {
            "mean": float(values.mean()), "ci_low": float(np.quantile(boot, 0.025)),
            "ci_high": float(np.quantile(boot, 0.975)), "probability_gt_zero": float(np.mean(boot > 0)),
            "samples": samples, "seed": seed,
        }

    return {"pairwise": summarise(pair_delta, pair_out), "top_hit": summarise(top_delta, top_out)}


def summary(m: dict[str, np.ndarray]) -> dict[str, float]:
    return {k: float(v.mean()) if len(v) else math.nan for k, v in m.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selected-parents", type=Path, required=True)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--policy-out", type=Path, required=True)
    ap.add_argument("--l2", type=float, default=1e-3)
    ap.add_argument("--maxiter", type=int, default=500)
    ap.add_argument("--gtol", type=float, default=1e-6)
    ap.add_argument("--max-train-pairs-per-color", type=int, default=250000)
    ap.add_argument("--bootstrap-samples", type=int, default=100000)
    ap.add_argument("--bootstrap-seed", type=int, default=2026083103)
    ap.add_argument("--shams", type=int, default=16)
    ap.add_argument("--sham-seed", type=int, default=2026083104)
    args = ap.parse_args()

    parents = load_parents(args.selected_parents)
    meta = load_groups(args.groups, parents)
    feat = load_feat(args.features)
    if len(meta) != len(feat):
        raise SystemExit("row count mismatch groups/features")
    x = np.concatenate([feat, move_features(meta)], axis=1)
    if x.shape[1] != 126:
        raise SystemExit(f"DSSD feature width drift: {x.shape[1]} != 126")

    parent_rows: dict[int, list[int]] = defaultdict(list)
    for i, m in enumerate(meta):
        parent_rows[m.parent_id].append(i)
    if set(parent_rows) != set(parents):
        raise SystemExit("teacher did not emit siblings for every frozen selected parent")
    pairs = accepted_pairs(parent_rows, meta)
    accepted = sorted(pairs)
    train_accepted = [p for p in accepted if parents[p].partition == "train"]
    holdout_accepted = [p for p in accepted if parents[p].partition == "holdout"]

    selected_holdout = [p for p in parents if parents[p].partition == "holdout"]
    support_gates = {
        "selected_total_ge_6000": len(parents) >= 6000,
        "selected_holdout_ge_1000": len(selected_holdout) >= 1000,
        "selected_holdout_each_phase_ge_200": all(sum(parents[p].phase == ph for p in selected_holdout) >= 200 for ph in PHASES),
        "selected_holdout_each_color_ge_300": all(sum(parents[p].stm == c for p in selected_holdout) >= 300 for c in (0, 1)),
        "accepted_parent_has_stable_pair": all(len(pairs[p]) >= 1 for p in accepted),
    }
    support_ok = all(support_gates.values())
    accepted_counts = {
        "total": len(accepted), "train": len(train_accepted), "holdout": len(holdout_accepted),
        "holdout_by_phase": {ph: sum(parents[p].phase == ph for p in holdout_accepted) for ph in PHASES},
        "holdout_by_color": {"white": sum(parents[p].stm == 0 for p in holdout_accepted),
                             "black": sum(parents[p].stm == 1 for p in holdout_accepted)},
        "stable_pairs_total": int(sum(len(v) for v in pairs.values())),
        "stable_pairs_train": int(sum(len(pairs[p]) for p in train_accepted)),
        "stable_pairs_holdout": int(sum(len(pairs[p]) for p in holdout_accepted)),
    }

    base_report = {
        "schema": "jass.deep_sibling_pairwise.v1",
        "feature_width_eval": 120, "feature_width_move": 6, "feature_width_total": 126,
        "move_features": MOVE_FEATURE_NAMES,
        "selection": {
            "parents_total": len(parents), "parents_train": sum(p.partition == "train" for p in parents.values()),
            "parents_holdout": len(selected_holdout),
            "holdout_by_phase": {ph: sum(parents[p].phase == ph for p in selected_holdout) for ph in PHASES},
            "holdout_by_color": {"white": sum(parents[p].stm == 0 for p in selected_holdout),
                                 "black": sum(parents[p].stm == 1 for p in selected_holdout)},
        },
        "accepted": accepted_counts,
        "stable_pair_rule": {"same_sign_50k_200k": True, "min_abs_d50_cp": 10, "min_abs_d200_cp": 30,
                             "exact_terminal_tb_wdl_precedence": True, "teacher_target": "q200_parent"},
        "fit": {"objective": "pairwise_logistic_deep_search_sibling", "l2": args.l2, "maxiter": args.maxiter,
                "gtol": args.gtol, "max_train_pairs_per_color": args.max_train_pairs_per_color,
                "separate_color_banks": True, "zero_initialization": True},
        "bootstrap": {"samples": args.bootstrap_samples, "seed": args.bootstrap_seed, "cluster": "parent"},
        "negative_controls": {"shams": args.shams, "seed": args.sham_seed},
        "support": {"established": support_ok, "gates": support_gates},
        "pattern_eval_fits": 0, "curriculum_modified": False, "policy_value_blending": False,
        "strength_games": 0, "promotion_authorized": False, "automatic_promotion": False,
    }

    unusable = {"schema": "jass.deep_sibling_policy.v1", "usable": False}
    if not support_ok:
        base_report.update({"passed": False, "verdict": "DEEP_SIBLING_SUPPORT_NOT_ESTABLISHED", "next_stage": None})
        args.report.write_text(json.dumps(base_report, indent=2, sort_keys=True) + "\n")
        args.policy_out.write_text(json.dumps(unusable, indent=2, sort_keys=True) + "\n")
        return 0

    train_by_color = {c: [p for p in train_accepted if parents[p].stm == c] for c in (0, 1)}
    matrices: dict[int, np.ndarray] = {}
    pair_keys: dict[int, list[tuple[int, int, int]]] = {}
    weights: dict[int, np.ndarray | None] = {}
    receipts: dict[str, dict] = {}
    for c in (0, 1):
        d, keys = pair_matrix(pairs, train_by_color[c], x, args.max_train_pairs_per_color)
        matrices[c], pair_keys[c] = d, keys
        w, rec = fit_pairwise(d, args.l2, args.maxiter, args.gtol)
        weights[c] = w
        receipts["white" if c == 0 else "black"] = rec

    optimizer_ok = all(receipts[k]["success"] for k in ("white", "black"))
    if optimizer_ok:
        model_score = np.asarray([float(x[i] @ weights[m.parent_stm]) for i, m in enumerate(meta)])
    else:
        model_score = np.zeros(len(meta), dtype=np.float64)
    baseline_score = np.asarray([m.t_baseline_parent for m in meta], dtype=np.float64)
    cheap_score = np.asarray([m.q5k_parent for m in meta], dtype=np.float64)

    if holdout_accepted:
        mm = metrics_by_parent(parent_rows, pairs, holdout_accepted, model_score)
        bm = metrics_by_parent(parent_rows, pairs, holdout_accepted, baseline_score)
        cm = metrics_by_parent(parent_rows, pairs, holdout_accepted, cheap_score)
        pair_delta = mm["pairwise"] - bm["pairwise"]
        top_delta = mm["top_hit"] - bm["top_hit"]
        boot = bootstrap_deltas(pair_delta, top_delta, args.bootstrap_samples, args.bootstrap_seed)
    else:
        mm = bm = cm = {"pairwise": np.asarray([]), "top_hit": np.asarray([])}
        pair_delta = top_delta = np.asarray([])
        boot = {"pairwise": {"mean": math.nan, "ci_low": math.nan, "ci_high": math.nan},
                "top_hit": {"mean": math.nan, "ci_low": math.nan, "ci_high": math.nan}}

    phase_deltas = {}
    for ph in PHASES:
        ids = [p for p in holdout_accepted if parents[p].phase == ph]
        if ids:
            a = metrics_by_parent(parent_rows, pairs, ids, model_score)["pairwise"]
            b = metrics_by_parent(parent_rows, pairs, ids, baseline_score)["pairwise"]
            phase_deltas[ph] = {"parents": len(ids), "pairwise_delta": float((a - b).mean())}
        else:
            phase_deltas[ph] = {"parents": 0, "pairwise_delta": math.nan}
    color_deltas = {}
    for c, name in ((0, "white"), (1, "black")):
        ids = [p for p in holdout_accepted if parents[p].stm == c]
        if ids:
            a = metrics_by_parent(parent_rows, pairs, ids, model_score)["pairwise"]
            b = metrics_by_parent(parent_rows, pairs, ids, baseline_score)["pairwise"]
            color_deltas[name] = {"parents": len(ids), "pairwise_delta": float((a - b).mean())}
        else:
            color_deltas[name] = {"parents": 0, "pairwise_delta": math.nan}

    sham_deltas: list[float] = []
    sham_receipts: list[dict] = []
    if holdout_accepted and all(len(matrices[c]) for c in (0, 1)):
        rng = np.random.default_rng(args.sham_seed)
        for _ in range(args.shams):
            sw: dict[int, np.ndarray | None] = {}
            sr = {}
            for c, name in ((0, "white"), (1, "black")):
                d = matrices[c]
                signs = rng.choice(np.asarray([-1.0, 1.0]), size=len(d))
                w, rec = fit_pairwise(d * signs[:, None], args.l2, args.maxiter, args.gtol)
                sw[c] = w
                sr[name] = rec
            ss = np.asarray([float(x[i] @ sw[m.parent_stm]) for i, m in enumerate(meta)])
            sm = metrics_by_parent(parent_rows, pairs, holdout_accepted, ss)["pairwise"]
            sham_deltas.append(float((sm - bm["pairwise"]).mean()))
            sham_receipts.append(sr)
    max_sham = max(sham_deltas) if sham_deltas else math.inf
    true_delta = float(pair_delta.mean()) if len(pair_delta) else math.nan

    phase_positive = all(v["parents"] > 0 and v["pairwise_delta"] > 0 for v in phase_deltas.values())
    colors_positive = all(v["parents"] > 0 and v["pairwise_delta"] > 0 for v in color_deltas.values())
    gates = {
        "support": support_ok,
        "optimizer_success_both_colors": optimizer_ok,
        "holdout_pairwise_ge_0_58": bool(len(mm["pairwise"]) and float(mm["pairwise"].mean()) >= 0.58),
        "pairwise_delta_ci95_low_gt_0": bool(len(pair_delta) and boot["pairwise"]["ci_low"] > 0),
        "top_hit_delta_ci95_low_gt_0": bool(len(top_delta) and boot["top_hit"]["ci_low"] > 0),
        "positive_pairwise_delta_each_phase": phase_positive,
        "positive_pairwise_delta_both_colors": colors_positive,
        "true_pairwise_improvement_exceeds_all_16_shams": bool(len(sham_deltas) == args.shams and true_delta > max_sham),
    }
    passed = all(gates.values())
    verdict = "DEEP_SIBLING_RANK_SIGNAL_ESTABLISHED" if passed else "DEEP_SIBLING_RANK_SIGNAL_NOT_ESTABLISHED"

    policy = {
        "schema": "jass.deep_sibling_policy.v1", "usable": bool(passed), "eval_feature_width": 120,
        "move_feature_names": MOVE_FEATURE_NAMES, "score_convention": "higher_is_better_for_parent",
        "weights": {"white_parent": [float(v) for v in weights[0]] if weights[0] is not None else [],
                    "black_parent": [float(v) for v in weights[1]] if weights[1] is not None else []},
        "training": {"l2": args.l2, "target": "stable_50k_200k_sibling_order",
                     "max_train_pairs_per_color": args.max_train_pairs_per_color},
    }
    args.policy_out.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n")

    base_report.update({
        "passed": bool(passed), "verdict": verdict, "next_stage": "phase_b_confirmation" if passed else None,
        "model": summary(mm), "baseline_t": summary(bm), "cheap_search_5k_diagnostic": summary(cm),
        "delta_model_minus_t": boot, "phase_strata": phase_deltas, "color_strata": color_deltas,
        "convergence": receipts,
        "train_pairs_used_by_color": {"white": len(pair_keys[0]), "black": len(pair_keys[1])},
        "negative_controls": {"shams": args.shams, "seed": args.sham_seed,
                              "pairwise_delta_vs_t": sham_deltas, "max_sham_delta": max_sham,
                              "true_delta_exceeds_all_shams": len(sham_deltas) == args.shams and true_delta > max_sham,
                              "convergence": sham_receipts},
        "gates": gates,
    })
    args.report.write_text(json.dumps(base_report, indent=2, sort_keys=True, allow_nan=True) + "\n")
    print(json.dumps({"verdict": verdict, "accepted_holdout": len(holdout_accepted),
                      "model_pairwise": summary(mm)["pairwise"], "t_pairwise": summary(bm)["pairwise"],
                      "pairwise_ci_low": boot["pairwise"]["ci_low"], "top_hit_ci_low": boot["top_hit"]["ci_low"],
                      "max_sham_delta": max_sham}, sort_keys=True, allow_nan=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
