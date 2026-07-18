#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fit an offline sibling ranker on Gen2-MMTO P3 hard negatives.

This is a signal test, not a runtime integration. It learns whether immediate
child geometry can separate a converting sibling from the move selected by the
frozen champion. Splits are inherited from parent IDs emitted by
``gen2_p3_decision_lab.py``; train-only standardisation prevents leakage.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs" / "tools"))

import conversion_teacher as ct  # type: ignore  # noqa: E402
import conversion_head as ch  # type: ignore  # noqa: E402


def load_events(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not row.get("hard_pair_eligible"):
            continue
        parent_id = str(row.get("parent_id", ""))
        if not parent_id or parent_id in seen:
            raise ValueError("missing or duplicate parent_id")
        if row.get("split") not in {"train", "holdout"}:
            raise ValueError(f"bad split for {parent_id}")
        for key in ("good_child_fen", "bad_child_fen"):
            if not isinstance(row.get(key), str):
                raise ValueError(f"{parent_id}: missing {key}")
        seen.add(parent_id)
        out.append(row)
    if not out:
        raise ValueError("no hard-negative events")
    return out


def features_for_fens(fens: list[str]) -> np.ndarray:
    records = [ct.fen_to_record(fen) for fen in fens]
    planes = [struct.unpack_from("<4Q", record, 0) for record in records]
    wm, wk, bm, bk = (np.asarray([row[i] for row in planes], dtype=np.uint64) for i in range(4))
    x, _, _, _ = ch.extract_features(wm, wk, bm, bk)
    return x


def expanded_names(mode: str) -> list[str]:
    names = list(ch.FEATURE_NAMES)
    if mode == "quadratic":
        names += [f"{ch.FEATURE_NAMES[i]}*{ch.FEATURE_NAMES[j]}"
                  for i in range(ch.NUM_FEATURES) for j in range(i, ch.NUM_FEATURES)]
    return names


def expand(x: np.ndarray, mode: str) -> np.ndarray:
    if mode == "linear":
        return x
    cols = [x]
    cols.extend((x[:, i] * x[:, j])[:, None]
                for i in range(x.shape[1]) for j in range(i, x.shape[1]))
    return np.hstack(cols)


def pair_matrix(events: list[dict], mean: np.ndarray, scale: np.ndarray,
                mode: str) -> np.ndarray:
    good = features_for_fens([str(row["good_child_fen"]) for row in events])
    bad = features_for_fens([str(row["bad_child_fen"]) for row in events])
    good_z = (good - mean) / scale
    bad_z = (bad - mean) / scale
    return expand(good_z, mode) - expand(bad_z, mode)


def metrics(d: np.ndarray, weights: np.ndarray) -> dict[str, float | int]:
    margin = d @ weights
    return {
        "n": int(len(margin)),
        "accuracy": float(np.mean(margin > 0)) if len(margin) else 0.0,
        "log_loss": float(np.mean(np.logaddexp(0.0, -margin))) if len(margin) else math.inf,
        "mean_margin": float(np.mean(margin)) if len(margin) else 0.0,
    }


def verify_accuracy(events: list[dict]) -> float | None:
    correct = total = 0
    for event in events:
        scores = {str(row.get("fen")): float(row.get("verify_parent_score", 0.0))
                  for row in event.get("ranked_children", []) if isinstance(row, dict)}
        good = str(event["good_child_fen"])
        bad = str(event["bad_child_fen"])
        if good in scores and bad in scores:
            total += 1
            correct += int(scores[good] > scores[bad])
    return correct / total if total else None


def fit(args: argparse.Namespace) -> dict[str, object]:
    events = load_events(args.events)
    train = [row for row in events if row["split"] == "train"]
    holdout = [row for row in events if row["split"] == "holdout"]
    if len(train) < args.min_train or len(holdout) < args.min_holdout:
        raise ValueError(f"insufficient split train={len(train)} holdout={len(holdout)}")

    train_children = ([str(row["good_child_fen"]) for row in train]
                      + [str(row["bad_child_fen"]) for row in train])
    raw = features_for_fens(train_children)
    mean = raw.mean(axis=0)
    scale = raw.std(axis=0)
    scale = np.where(scale > 1e-9, scale, 1.0)
    d_train = pair_matrix(train, mean, scale, args.mode)
    d_hold = pair_matrix(holdout, mean, scale, args.mode)
    ncol = d_train.shape[1]

    def objective(w: np.ndarray) -> tuple[float, np.ndarray]:
        margin = d_train @ w
        loss = float(np.mean(np.logaddexp(0.0, -margin)) + 0.5 * args.l2 * np.dot(w, w))
        coeff = -1.0 / (1.0 + np.exp(np.clip(margin, -60.0, 60.0)))
        grad = (d_train.T @ coeff) / len(d_train) + args.l2 * w
        return loss, grad

    result = minimize(lambda w: objective(w), np.zeros(ncol), jac=True,
                      method="L-BFGS-B", options={"maxiter": args.max_iter, "ftol": 1e-12})
    if not result.success:
        raise RuntimeError(f"optimizer failed: {result.message}")
    weights = np.asarray(result.x, dtype=np.float64)
    train_metrics = metrics(d_train, weights)
    hold_metrics = metrics(d_hold, weights)
    signal = (hold_metrics["n"] >= args.min_holdout
              and hold_metrics["accuracy"] >= args.min_accuracy
              and hold_metrics["log_loss"] < math.log(2.0))
    report: dict[str, object] = {
        "schema": 1,
        "mode": args.mode,
        "events": str(args.events),
        "train": train_metrics,
        "holdout": hold_metrics,
        "verify_train_accuracy": verify_accuracy(train),
        "verify_holdout_accuracy": verify_accuracy(holdout),
        "signal": signal,
        "gates": {
            "min_train": args.min_train,
            "min_holdout": args.min_holdout,
            "min_accuracy": args.min_accuracy,
            "log_loss_below_intercept": math.log(2.0),
        },
        "optimizer": {
            "iterations": int(result.nit),
            "objective": float(result.fun),
            "l2": args.l2,
            "converged": bool(result.success),
        },
        "model": {
            "feature_names": expanded_names(args.mode),
            "base_mean": mean.tolist(),
            "base_scale": scale.tolist(),
            "weights": weights.tolist(),
        },
    }
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("linear", "quadratic"), default="quadratic")
    parser.add_argument("--l2", type=float, default=1e-3)
    parser.add_argument("--max-iter", type=int, default=200)
    parser.add_argument("--min-train", type=int, default=40)
    parser.add_argument("--min-holdout", type=int, default=20)
    parser.add_argument("--min-accuracy", type=float, default=0.55)
    args = parser.parse_args(argv)
    if args.l2 < 0 or not 0.5 < args.min_accuracy <= 1.0:
        parser.error("invalid l2/min-accuracy")
    try:
        report = fit(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({k: report[k] for k in ("train", "holdout", "signal")}, sort_keys=True))
    return 0 if report["signal"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
