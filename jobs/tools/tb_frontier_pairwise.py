#!/usr/bin/env python3
"""Learn a tiny move-ordering head from exact EGDB sibling preferences.

The input children are emitted by ``src/tb_frontier.cpp``.  Every parent group
contains >=2 legal sibling moves, every child is inside EGDB, and at least two
siblings have different exact WLD classes from the PARENT point of view.

This tool deliberately learns only a cheap dense head: the existing production
``--dump-eval-features`` vector plus six move-local scalars.  It never changes
CURRICULUM and it never trains a leaf evaluator.  Its only scientific question
is whether this low-cost feature family can rank exact sibling preferences on
parent-disjoint holdout positions better than CURRICULUM itself.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
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

JNNW_REC = struct.Struct("<QQQQBib")
MOVE_FEATURE_NAMES = [
    "num_captures",
    "captured_kings",
    "promotes",
    "moving_king",
    "from_norm",
    "to_norm",
]


@dataclass(frozen=True)
class RowMeta:
    row_index: int
    parent_id: int
    fingerprint: str
    parent_stm: int
    from_sq: int
    to_sq: int
    num_captures: int
    promotes: int
    moving_king: int
    captured_kings: int
    utility: int
    child_tb_wdl_stm: int


def load_feat(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) < 12 or raw[:4] != b"FEAT":
        raise ValueError(f"{path}: bad FEAT header")
    n, k = struct.unpack_from("<II", raw, 4)
    expected = 12 + n * k * 4
    if len(raw) != expected:
        raise ValueError(f"{path}: size drift n={n} k={k} size={len(raw)} expected={expected}")
    return np.frombuffer(raw, dtype="<f4", offset=12, count=n * k).reshape(n, k).astype(np.float64)


def load_jnnw_scores(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError(f"{path}: bad JNNW header")
    n = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + n * JNNW_REC.size:
        raise ValueError(f"{path}: count/size drift")
    scores = np.empty(n, dtype=np.float64)
    for i in range(n):
        scores[i] = JNNW_REC.unpack_from(raw, 8 + i * JNNW_REC.size)[5]
    return scores


def load_groups(path: Path) -> list[RowMeta]:
    out: list[RowMeta] = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        required = {
            "row_index", "parent_id", "parent_fingerprint", "parent_stm",
            "from", "to", "num_captures", "promotes", "moving_king",
            "captured_kings", "parent_utility", "child_tb_wdl_stm",
        }
        if reader.fieldnames is None or set(reader.fieldnames) != required:
            raise ValueError(f"{path}: unexpected TSV fields {reader.fieldnames!r}")
        for row in reader:
            out.append(RowMeta(
                row_index=int(row["row_index"]),
                parent_id=int(row["parent_id"]),
                fingerprint=row["parent_fingerprint"],
                parent_stm=int(row["parent_stm"]),
                from_sq=int(row["from"]),
                to_sq=int(row["to"]),
                num_captures=int(row["num_captures"]),
                promotes=int(row["promotes"]),
                moving_king=int(row["moving_king"]),
                captured_kings=int(row["captured_kings"]),
                utility=int(row["parent_utility"]),
                child_tb_wdl_stm=int(row["child_tb_wdl_stm"]),
            ))
    if [m.row_index for m in out] != list(range(len(out))):
        raise ValueError("groups row_index is not contiguous and ordered")
    for m in out:
        if m.parent_stm not in (0, 1) or m.utility not in (-1, 0, 1):
            raise ValueError("invalid color/WLD metadata")
        if m.child_tb_wdl_stm != -m.utility:
            raise ValueError("child STM WDL is not the negation of parent utility")
    return out


def split_is_holdout(fingerprint: str, seed: int, mod: int) -> bool:
    digest = hashlib.sha256(f"{seed}:{fingerprint}".encode()).digest()
    return int.from_bytes(digest[:8], "little") % mod == 0


def move_features(meta: list[RowMeta]) -> np.ndarray:
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


def informative_pairs(rows: list[int], meta: list[RowMeta]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for i in rows:
        for j in rows:
            if meta[i].utility > meta[j].utility:
                pairs.append((i, j))
    return pairs


def collect_pair_matrix(
    parent_rows: dict[int, list[int]],
    parent_ids: Iterable[int],
    meta: list[RowMeta],
    x: np.ndarray,
) -> np.ndarray:
    chunks: list[np.ndarray] = []
    for pid in parent_ids:
        pairs = informative_pairs(parent_rows[pid], meta)
        if pairs:
            good = np.fromiter((a for a, _ in pairs), dtype=np.int64)
            bad = np.fromiter((b for _, b in pairs), dtype=np.int64)
            chunks.append(x[good] - x[bad])
    if not chunks:
        return np.empty((0, x.shape[1]), dtype=np.float64)
    return np.concatenate(chunks, axis=0)


def deterministic_cap(d: np.ndarray, cap: int, seed: int) -> np.ndarray:
    if len(d) <= cap:
        return d
    rng = np.random.default_rng(seed)
    idx = np.sort(rng.choice(len(d), size=cap, replace=False))
    return d[idx]


def fit_pairwise(d: np.ndarray, l2: float, maxiter: int, gtol: float) -> tuple[np.ndarray, dict]:
    if len(d) == 0:
        raise ValueError("no training pairs")
    scale = d.std(axis=0)
    scale[scale < 1e-8] = 1.0
    dn = d / scale
    n = float(len(dn))

    def fun_grad(w: np.ndarray) -> tuple[float, np.ndarray]:
        z = dn @ w
        loss = float(np.logaddexp(0.0, -z).sum() / n + 0.5 * l2 * np.dot(w, w))
        grad = -(dn.T @ expit(-z)) / n + l2 * w
        return loss, grad

    result = minimize(
        lambda w: fun_grad(w),
        np.zeros(dn.shape[1], dtype=np.float64),
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": maxiter, "gtol": gtol, "maxcor": 20},
    )
    # Raw-feature score.  Pairwise ranking is invariant to the absent constant
    # centering term, so only the per-column scale needs folding into weights.
    raw_w = np.asarray(result.x, dtype=np.float64) / scale
    receipt = {
        "success": bool(result.success),
        "status": int(result.status),
        "message": str(result.message),
        "iterations": int(result.nit),
        "objective": float(result.fun),
        "gradient_inf_norm": float(np.max(np.abs(result.jac))),
        "gtol": gtol,
        "pairs": int(len(d)),
    }
    return raw_w, receipt


def parent_metric(rows: list[int], meta: list[RowMeta], score: np.ndarray) -> tuple[float, float, float]:
    pairs = informative_pairs(rows, meta)
    if not pairs:
        raise ValueError("non-informative parent reached metric")
    pair_values = []
    for good, bad in pairs:
        if score[good] > score[bad]:
            pair_values.append(1.0)
        elif score[good] == score[bad]:
            pair_values.append(0.5)
        else:
            pair_values.append(0.0)
    pair_acc = float(np.mean(pair_values))

    vals = np.asarray([score[i] for i in rows], dtype=np.float64)
    util = np.asarray([meta[i].utility for i in rows], dtype=np.float64)
    top = np.max(vals)
    mask = vals == top
    best_u = np.max(util)
    top_hit = float(np.mean(util[mask] == best_u))
    selected_u = float(np.mean(util[mask]))
    regret = float(best_u - selected_u)
    return pair_acc, top_hit, regret


def metrics_by_parent(
    parent_rows: dict[int, list[int]],
    parent_ids: list[int],
    meta: list[RowMeta],
    score: np.ndarray,
) -> dict[str, np.ndarray]:
    pair, top, regret = [], [], []
    for pid in parent_ids:
        a, b, c = parent_metric(parent_rows[pid], meta, score)
        pair.append(a); top.append(b); regret.append(c)
    return {
        "pairwise": np.asarray(pair),
        "top_hit": np.asarray(top),
        "regret": np.asarray(regret),
    }


def bootstrap_delta(values: np.ndarray, samples: int, seed: int) -> dict:
    if len(values) == 0:
        raise ValueError("empty bootstrap")
    rng = np.random.default_rng(seed)
    out = np.empty(samples, dtype=np.float64)
    batch = 512
    n = len(values)
    for start in range(0, samples, batch):
        stop = min(samples, start + batch)
        idx = rng.integers(0, n, size=(stop - start, n))
        out[start:stop] = values[idx].mean(axis=1)
    return {
        "mean": float(values.mean()),
        "ci_low": float(np.quantile(out, 0.025)),
        "ci_high": float(np.quantile(out, 0.975)),
        "probability_gt_zero": float(np.mean(out > 0.0)),
        "samples": samples,
        "seed": seed,
    }


def summarize(m: dict[str, np.ndarray]) -> dict:
    return {k: float(v.mean()) for k, v in m.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--baseline-jnnw", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--policy-out", type=Path, required=True)
    ap.add_argument("--split-seed", type=int, default=2026082801)
    ap.add_argument("--holdout-mod", type=int, default=5)
    ap.add_argument("--l2", type=float, default=1e-3)
    ap.add_argument("--maxiter", type=int, default=500)
    ap.add_argument("--gtol", type=float, default=1e-6)
    ap.add_argument("--max-train-pairs-per-color", type=int, default=250000)
    ap.add_argument("--bootstrap-samples", type=int, default=100000)
    ap.add_argument("--bootstrap-seed", type=int, default=2026082802)
    ap.add_argument("--shams", type=int, default=16)
    ap.add_argument("--sham-seed", type=int, default=2026082803)
    ap.add_argument("--min-holdout-parents", type=int, default=800)
    ap.add_argument("--min-holdout-per-color", type=int, default=250)
    ap.add_argument("--min-pairwise-accuracy", type=float, default=0.58)
    args = ap.parse_args()

    meta = load_groups(args.groups)
    feat = load_feat(args.features)
    baseline_child_stm = load_jnnw_scores(args.baseline_jnnw)
    if len(meta) != len(feat) or len(meta) != len(baseline_child_stm):
        raise SystemExit("row count mismatch among groups/features/baseline")
    if feat.shape[1] <= 0:
        raise SystemExit("empty eval feature vector")

    x = np.concatenate([feat, move_features(meta)], axis=1)
    # The child is always the opponent to move, so parent preference is the
    # negative of CURRICULUM's normal child-STM score.
    baseline_score = -baseline_child_stm

    parent_rows: dict[int, list[int]] = defaultdict(list)
    parent_fingerprint: dict[int, str] = {}
    parent_color: dict[int, int] = {}
    for i, m in enumerate(meta):
        parent_rows[m.parent_id].append(i)
        if m.parent_id in parent_fingerprint and parent_fingerprint[m.parent_id] != m.fingerprint:
            raise SystemExit("parent id maps to multiple fingerprints")
        parent_fingerprint[m.parent_id] = m.fingerprint
        parent_color[m.parent_id] = m.parent_stm

    parents = sorted(parent_rows)
    for pid in parents:
        if not informative_pairs(parent_rows[pid], meta):
            raise SystemExit("groups file contains non-informative parent")

    holdout = [pid for pid in parents if split_is_holdout(parent_fingerprint[pid], args.split_seed, args.holdout_mod)]
    train = [pid for pid in parents if pid not in set(holdout)]
    holdout_by_color = {c: [p for p in holdout if parent_color[p] == c] for c in (0, 1)}
    train_by_color = {c: [p for p in train if parent_color[p] == c] for c in (0, 1)}

    support_ok = (
        len(holdout) >= args.min_holdout_parents
        and all(len(holdout_by_color[c]) >= args.min_holdout_per_color for c in (0, 1))
        and all(len(train_by_color[c]) > 0 for c in (0, 1))
    )

    base_metrics = metrics_by_parent(parent_rows, holdout, meta, baseline_score) if holdout else None
    report: dict = {
        "schema": "jass.tb_frontier_pairwise.v1",
        "feature_width_eval": int(feat.shape[1]),
        "feature_width_move": len(MOVE_FEATURE_NAMES),
        "feature_width_total": int(x.shape[1]),
        "move_features": MOVE_FEATURE_NAMES,
        "parents_total": len(parents),
        "parents_train": len(train),
        "parents_holdout": len(holdout),
        "parents_train_by_color": {"white": len(train_by_color[0]), "black": len(train_by_color[1])},
        "parents_holdout_by_color": {"white": len(holdout_by_color[0]), "black": len(holdout_by_color[1])},
        "split": {"seed": args.split_seed, "holdout_mod": args.holdout_mod},
        "fit": {
            "objective": "pairwise_logistic_exact_WLD",
            "l2": args.l2,
            "maxiter": args.maxiter,
            "gtol": args.gtol,
            "max_train_pairs_per_color": args.max_train_pairs_per_color,
            "separate_color_banks": True,
        },
        "support": {
            "min_holdout_parents": args.min_holdout_parents,
            "min_holdout_per_color": args.min_holdout_per_color,
            "established": support_ok,
        },
        "baseline": summarize(base_metrics) if base_metrics else None,
        "automatic_promotion": False,
        "strength_games": 0,
        "frozen_reads": 0,
    }

    if not support_ok:
        report.update({
            "passed": False,
            "verdict": "TB_FRONTIER_SUPPORT_NOT_ESTABLISHED",
            "next_stage": None,
        })
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        args.policy_out.write_text(json.dumps({"schema": "jass.tb_move_order_policy.v1", "usable": False}, indent=2) + "\n")
        return 0

    weights_raw: dict[int, np.ndarray] = {}
    receipts: dict[str, dict] = {}
    train_pair_matrices: dict[int, np.ndarray] = {}
    for color in (0, 1):
        d = collect_pair_matrix(parent_rows, train_by_color[color], meta, x)
        d = deterministic_cap(d, args.max_train_pairs_per_color, args.split_seed + 100 + color)
        train_pair_matrices[color] = d
        w, receipt = fit_pairwise(d, args.l2, args.maxiter, args.gtol)
        weights_raw[color] = w
        receipts["white" if color == 0 else "black"] = receipt

    model_score = np.empty(len(meta), dtype=np.float64)
    for i, m in enumerate(meta):
        model_score[i] = float(x[i] @ weights_raw[m.parent_stm])

    model_metrics = metrics_by_parent(parent_rows, holdout, meta, model_score)
    base_metrics = metrics_by_parent(parent_rows, holdout, meta, baseline_score)
    delta_pair = model_metrics["pairwise"] - base_metrics["pairwise"]
    delta_top = model_metrics["top_hit"] - base_metrics["top_hit"]
    delta_regret = model_metrics["regret"] - base_metrics["regret"]
    pair_boot = bootstrap_delta(delta_pair, args.bootstrap_samples, args.bootstrap_seed)
    top_boot = bootstrap_delta(delta_top, args.bootstrap_samples, args.bootstrap_seed + 1)
    regret_boot = bootstrap_delta(delta_regret, args.bootstrap_samples, args.bootstrap_seed + 2)

    color_deltas: dict[str, dict] = {}
    for color in (0, 1):
        ids = holdout_by_color[color]
        mm = metrics_by_parent(parent_rows, ids, meta, model_score)
        bb = metrics_by_parent(parent_rows, ids, meta, baseline_score)
        color_deltas["white" if color == 0 else "black"] = {
            "parents": len(ids),
            "pairwise_delta": float((mm["pairwise"] - bb["pairwise"]).mean()),
            "top_hit_delta": float((mm["top_hit"] - bb["top_hit"]).mean()),
            "model_pairwise": float(mm["pairwise"].mean()),
            "baseline_pairwise": float(bb["pairwise"].mean()),
        }

    # Negative-control family: randomise the sign of each TRAIN pair, refit the
    # exact same model, and evaluate against the untouched exact holdout labels.
    # Separate color banks remain fixed.  16 preregistered shams make the max
    # observed sham delta a conservative ~94th-percentile family control.
    rng = np.random.default_rng(args.sham_seed)
    sham_deltas: list[float] = []
    for sham in range(args.shams):
        sham_weights: dict[int, np.ndarray] = {}
        for color in (0, 1):
            d = train_pair_matrices[color]
            signs = rng.choice(np.asarray([-1.0, 1.0]), size=len(d))
            sw, _ = fit_pairwise(d * signs[:, None], args.l2, args.maxiter, args.gtol)
            sham_weights[color] = sw
        sham_score = np.asarray([float(x[i] @ sham_weights[m.parent_stm]) for i, m in enumerate(meta)])
        sm = metrics_by_parent(parent_rows, holdout, meta, sham_score)
        sham_deltas.append(float((sm["pairwise"] - base_metrics["pairwise"]).mean()))

    max_sham = max(sham_deltas) if sham_deltas else -math.inf
    convergence_ok = all(r["success"] and r["gradient_inf_norm"] <= max(args.gtol * 10.0, 1e-5)
                         for r in receipts.values())
    both_colors_positive = all(v["pairwise_delta"] > 0.0 and v["top_hit_delta"] >= 0.0
                               for v in color_deltas.values())
    passed = (
        convergence_ok
        and float(model_metrics["pairwise"].mean()) >= args.min_pairwise_accuracy
        and pair_boot["ci_low"] > 0.0
        and top_boot["ci_low"] > 0.0
        and both_colors_positive
        and float(delta_pair.mean()) > max_sham
    )

    policy = {
        "schema": "jass.tb_move_order_policy.v1",
        "usable": bool(passed),
        "eval_feature_width": int(feat.shape[1]),
        "move_feature_names": MOVE_FEATURE_NAMES,
        "score_convention": "higher_is_better_for_parent",
        "weights": {
            "white_parent": [float(v) for v in weights_raw[0]],
            "black_parent": [float(v) for v in weights_raw[1]],
        },
        "training": {
            "split_seed": args.split_seed,
            "holdout_mod": args.holdout_mod,
            "l2": args.l2,
            "exact_target": "EGDB_WLD_sibling_order",
        },
    }
    args.policy_out.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n")

    report.update({
        "passed": bool(passed),
        "verdict": "TB_FRONTIER_RANK_SIGNAL_ESTABLISHED" if passed else "TB_FRONTIER_RANK_SIGNAL_NOT_ESTABLISHED",
        "model": summarize(model_metrics),
        "delta_model_minus_curriculum": {
            "pairwise": pair_boot,
            "top_hit": top_boot,
            "regret_model_minus_curriculum": regret_boot,
        },
        "color_strata": color_deltas,
        "convergence": receipts,
        "negative_controls": {
            "shams": args.shams,
            "seed": args.sham_seed,
            "pairwise_delta_vs_curriculum": sham_deltas,
            "max_sham_delta": max_sham,
            "true_delta_exceeds_all_shams": float(delta_pair.mean()) > max_sham,
        },
        "gates": {
            "convergence": convergence_ok,
            "min_model_pairwise_accuracy": args.min_pairwise_accuracy,
            "model_pairwise_accuracy_pass": float(model_metrics["pairwise"].mean()) >= args.min_pairwise_accuracy,
            "pairwise_delta_ci95_strictly_positive": pair_boot["ci_low"] > 0.0,
            "top_hit_delta_ci95_strictly_positive": top_boot["ci_low"] > 0.0,
            "both_color_banks_positive": both_colors_positive,
            "true_pairwise_delta_exceeds_all_shams": float(delta_pair.mean()) > max_sham,
        },
        "next_stage": "policy_move_ordering_ablation_with_curriculum_frozen" if passed else None,
    })
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "verdict": report["verdict"],
        "parents_holdout": len(holdout),
        "baseline_pairwise": report["baseline"]["pairwise"],
        "model_pairwise": report["model"]["pairwise"],
        "pairwise_delta_ci_low": pair_boot["ci_low"],
        "top_hit_delta_ci_low": top_boot["ci_low"],
        "max_sham_delta": max_sham,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
