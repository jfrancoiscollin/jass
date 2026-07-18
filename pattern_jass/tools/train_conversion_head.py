#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fit the CVH1 P3 conversion expert on terminal self-play outcomes.

The base PJTW champion is never modified. This tool learns only a small
leader-relative logistic head. Splits are group-based (game/opening provenance),
never random by row.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conversion_head import FEATURE_NAMES, SCHEMA, extract_features  # noqa: E402

REC_DTYPE = np.dtype([
    ("wm", "<u8"), ("wk", "<u8"), ("bm", "<u8"), ("bk", "<u8"),
    ("stm", "u1"), ("score", "<i4"), ("wdl", "i1"),
])
REC_SIZE = 38
EPS = 1e-12


def open_jnnw(path: str) -> np.memmap:
    with open(path, "rb") as fh:
        header = fh.read(8)
    if len(header) != 8 or header[:4] != b"JNNW":
        raise SystemExit(f"{path}: invalid JNNW header")
    count = struct.unpack_from("<I", header, 4)[0]
    size = Path(path).stat().st_size
    expected = 8 + count * REC_SIZE
    if size != expected:
        raise SystemExit(f"{path}: size {size} != expected {expected}")
    return np.memmap(path, dtype=REC_DTYPE, mode="r", offset=8, shape=(count,))


def load_groups(path: str, n_expected: int) -> np.ndarray:
    p = Path(path)
    if p.suffix == ".npy":
        groups = np.load(p, allow_pickle=False)
    else:
        groups = np.asarray([line.strip() for line in p.read_text(encoding="utf-8").splitlines()])
    groups = np.asarray(groups)
    if groups.ndim != 1 or len(groups) != n_expected:
        raise SystemExit(f"groups length/shape {groups.shape} != ({n_expected},)")
    return groups


def grouped_split(groups: np.ndarray, holdout_frac: float,
                  seed: int) -> tuple[np.ndarray, np.ndarray]:
    unique = np.unique(groups)
    if len(unique) < 2:
        raise SystemExit("need at least two provenance groups")
    rng = np.random.default_rng(seed)
    shuffled = unique.copy()
    rng.shuffle(shuffled)
    n_hold = max(1, int(round(len(shuffled) * holdout_frac)))
    n_hold = min(n_hold, len(shuffled) - 1)
    hold_groups = set(shuffled[:n_hold].tolist())
    hold = np.fromiter((g in hold_groups for g in groups), dtype=bool, count=len(groups))
    train = ~hold
    if set(groups[train].tolist()) & set(groups[hold].tolist()):
        raise AssertionError("group leakage")
    return train, hold


def equal_group_weights(groups: np.ndarray) -> np.ndarray:
    _, inverse, counts = np.unique(groups, return_inverse=True, return_counts=True)
    w = 1.0 / counts[inverse].astype(np.float64)
    return w * (len(w) / w.sum())


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 0.5 * (np.tanh(0.5 * z) + 1.0)


def weighted_logloss(y: np.ndarray, p: np.ndarray, w: np.ndarray) -> float:
    ce = -(y * np.log(p + EPS) + (1.0 - y) * np.log(1.0 - p + EPS))
    return float(np.dot(w, ce) / w.sum())


def weighted_brier(y: np.ndarray, p: np.ndarray, w: np.ndarray) -> float:
    return float(np.dot(w, (p - y) ** 2) / w.sum())


def auc(y: np.ndarray, score: np.ndarray) -> float | None:
    pos = y > 0.5
    n_pos = int(pos.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    order = np.argsort(score, kind="mergesort")
    ranks = np.empty(len(score), dtype=np.float64)
    ranks[order] = np.arange(1, len(score) + 1, dtype=np.float64)
    # Average tied ranks.
    sorted_score = score[order]
    start = 0
    while start < len(score):
        end = start + 1
        while end < len(score) and sorted_score[end] == sorted_score[start]:
            end += 1
        if end - start > 1:
            ranks[order[start:end]] = 0.5 * ((start + 1) + end)
        start = end
    rank_sum = float(ranks[pos].sum())
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def calibration(y: np.ndarray, p: np.ndarray, w: np.ndarray) -> list[dict]:
    order = np.argsort(p)
    bins = np.array_split(order, 10)
    out = []
    for i, idx in enumerate(bins):
        if len(idx) == 0:
            continue
        sw = w[idx].sum()
        out.append({
            "decile": i,
            "n": int(len(idx)),
            "pred": round(float(np.dot(w[idx], p[idx]) / sw), 6),
            "observed": round(float(np.dot(w[idx], y[idx]) / sw), 6),
        })
    return out


def metrics(y: np.ndarray, z: np.ndarray, w: np.ndarray,
            intercept_p: float) -> dict:
    p = sigmoid(z)
    base = np.full(len(y), intercept_p, dtype=np.float64)
    return {
        "n": int(len(y)),
        "positive_rate": round(float(np.dot(w, y) / w.sum()), 6),
        "intercept_logloss": round(weighted_logloss(y, base, w), 6),
        "head_logloss": round(weighted_logloss(y, p, w), 6),
        "brier": round(weighted_brier(y, p, w), 6),
        "auc": None if auc(y, z) is None else round(float(auc(y, z)), 6),
        "calibration": calibration(y, p, w),
    }


def collect(mm: np.memmap, groups_all: np.ndarray, chunk: int,
            piece_min: int, piece_zero_max: int,
            margin_min: int, margin_max: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    gs: list[np.ndarray] = []
    pieces_hist: Counter[int] = Counter()
    selected = 0
    for lo in range(0, len(mm), chunk):
        hi = min(lo + chunk, len(mm))
        rec = mm[lo:hi]
        X, sign, margin, pieces = extract_features(rec["wm"], rec["wk"], rec["bm"], rec["bk"])
        mask = ((sign != 0) & (margin >= margin_min) & (margin <= margin_max)
                & (pieces >= piece_min) & (pieces < piece_zero_max))
        if not np.any(mask):
            continue
        wdl = rec["wdl"].astype(np.int8)
        stm = rec["stm"].astype(np.int8)
        wdl_black = np.where(stm == 1, wdl, -wdl)
        leader_won = ((sign > 0) & (wdl_black > 0)) | ((sign < 0) & (wdl_black < 0))
        xs.append(X[mask])
        ys.append(leader_won[mask].astype(np.float64))
        gs.append(groups_all[lo:hi][mask])
        pieces_hist.update(int(v) for v in pieces[mask])
        selected += int(mask.sum())
    if selected == 0:
        raise SystemExit("no eligible conversion positions")
    X = np.vstack(xs)
    y = np.concatenate(ys)
    groups = np.concatenate(gs)
    if len(np.unique(y)) < 2:
        raise SystemExit("eligible data contains only one target class")
    return X, y, groups, {"selected": selected, "pieces": dict(sorted(pieces_hist.items()))}


def fit(X: np.ndarray, y: np.ndarray, groups: np.ndarray,
        holdout_frac: float, seed: int, l2: float,
        max_iter: int) -> tuple[dict, dict]:
    train_mask, hold_mask = grouped_split(groups, holdout_frac, seed)
    Xtr, Xho = X[train_mask], X[hold_mask]
    ytr, yho = y[train_mask], y[hold_mask]
    gtr, gho = groups[train_mask], groups[hold_mask]
    wtr = equal_group_weights(gtr)
    who = equal_group_weights(gho)

    mean = np.average(Xtr, axis=0, weights=wtr)
    var = np.average((Xtr - mean) ** 2, axis=0, weights=wtr)
    std = np.sqrt(var)
    inv_std = np.zeros_like(std)
    inv_std[std > 1e-12] = 1.0 / std[std > 1e-12]
    Ztr = (Xtr - mean) * inv_std
    Zho = (Xho - mean) * inv_std

    prevalence = float(np.dot(wtr, ytr) / wtr.sum())
    prevalence = min(max(prevalence, 1e-6), 1.0 - 1e-6)
    center = math.log(prevalence / (1.0 - prevalence))
    theta0 = np.zeros(Ztr.shape[1] + 1, dtype=np.float64)
    theta0[0] = center

    def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
        bias = theta[0]
        coef = theta[1:]
        z = bias + Ztr @ coef
        p = sigmoid(z)
        ce = -(ytr * np.log(p + EPS) + (1.0 - ytr) * np.log(1.0 - p + EPS))
        loss = float(np.dot(wtr, ce) / wtr.sum()) + 0.5 * l2 * float(coef @ coef)
        resid = wtr * (p - ytr) / wtr.sum()
        grad = np.concatenate(([resid.sum()], Ztr.T @ resid + l2 * coef))
        return loss, grad

    result = minimize(lambda t: objective(t), theta0, jac=True,
                      method="L-BFGS-B", options={"maxiter": max_iter, "maxcor": 10})
    if not result.success and result.nit == 0:
        raise SystemExit(f"fit failed: {result.message}")
    theta = np.asarray(result.x, dtype=np.float64)
    ztr = theta[0] + Ztr @ theta[1:]
    zho = theta[0] + Zho @ theta[1:]
    diagnostics = {
        "optimizer": {"success": bool(result.success), "message": str(result.message),
                      "iterations": int(result.nit), "objective": float(result.fun)},
        "train_groups": int(len(np.unique(gtr))),
        "holdout_groups": int(len(np.unique(gho))),
        "train": metrics(ytr, ztr, wtr, prevalence),
        "holdout": metrics(yho, zho, who, prevalence),
        "logit_quantiles_holdout": np.quantile(zho - center, [0, .01, .1, .5, .9, .99, 1]).tolist(),
    }
    fitted = {
        "bias": float(theta[0]),
        "center_logit": center,
        "mean": mean.tolist(),
        "inv_std": inv_std.tolist(),
        "weight": theta[1:].tolist(),
    }
    return fitted, diagnostics


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", required=True, help="JNNW terminal-WDL corpus")
    ap.add_argument("--groups", required=True,
                    help="one game/opening provenance id per JNNW row (.npy or text)")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--chunk", type=int, default=100000)
    ap.add_argument("--holdout-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=271828)
    ap.add_argument("--l2", type=float, default=1e-3)
    ap.add_argument("--max-iter", type=int, default=100)
    ap.add_argument("--lambda-cp", type=float, default=10.0)
    ap.add_argument("--tanh-scale", type=float, default=1.0)
    ap.add_argument("--piece-min", type=int, default=8)
    ap.add_argument("--piece-full-max", type=int, default=12)
    ap.add_argument("--piece-zero-max", type=int, default=20)
    ap.add_argument("--margin-min", type=int, default=1)
    ap.add_argument("--margin-max", type=int, default=1)
    args = ap.parse_args()

    if not (0.0 < args.holdout_frac < 1.0):
        raise SystemExit("--holdout-frac must be in (0,1)")
    if args.chunk <= 0 or args.l2 < 0 or args.lambda_cp < 0 or args.tanh_scale <= 0:
        raise SystemExit("invalid numeric option")
    if not (args.piece_min <= args.piece_full_max < args.piece_zero_max):
        raise SystemExit("invalid piece gate")

    mm = open_jnnw(args.data)
    groups_all = load_groups(args.groups, len(mm))
    X, y, groups, census = collect(
        mm, groups_all, args.chunk, args.piece_min, args.piece_zero_max,
        args.margin_min, args.margin_max)
    fitted, diagnostics = fit(
        X, y, groups, args.holdout_frac, args.seed, args.l2, args.max_iter)

    model = {
        "format": "CVH1",
        "schema": SCHEMA,
        "feature_names": FEATURE_NAMES,
        "flags": 0,
        "lambda_cp": args.lambda_cp,
        "tanh_scale": args.tanh_scale,
        "piece_min": float(args.piece_min),
        "piece_full_max": float(args.piece_full_max),
        "piece_zero_max": float(args.piece_zero_max),
        "margin_min": float(args.margin_min),
        "margin_max": float(args.margin_max),
        **fitted,
        "provenance": {
            "data": str(Path(args.data)),
            "groups": str(Path(args.groups)),
            "seed": args.seed,
            "holdout_frac": args.holdout_frac,
            "l2": args.l2,
            "census": census,
        },
        "diagnostics": diagnostics,
    }
    Path(args.out_json).write_text(json.dumps(model, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "out": args.out_json,
        "eligible": census["selected"],
        "holdout_logloss": diagnostics["holdout"]["head_logloss"],
        "holdout_intercept": diagnostics["holdout"]["intercept_logloss"],
        "optimizer_success": diagnostics["optimizer"]["success"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
