#!/usr/bin/env python3
"""Frozen D4c pairwise rank-breaker fit and exploratory offline readout."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import d4_search_utility_offline as d4
from jobs.tools import d4b_search_utility_micro as d4b

WIDTH = 96
FEATURE_WIDTH = 24
L2 = 1e-3
MAX_ITER = 500
MAXCOR = 10
GTOL = 1e-6
BOOTSTRAPS = 20_000
BOOTSTRAP_SEED = 2026090803

FIT_VERDICT = "D4C_RANK_BREAKER_FIT_COMPLETE_V1"
PASS = "D4C_RANK_BREAKER_OFFLINE_SUPPORTED_V1"
FAIL = "D4C_RANK_BREAKER_OFFLINE_NOT_SUPPORTED_V1"


def configure() -> None:
    d4b.configure_base()


def load_rows(path: Path, split: str) -> list[dict[str, Any]]:
    configure()
    return d4.load_selected(path, split)


def arrays(rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    return d4.arrays(rows)


def score_matrix(beta: np.ndarray, rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x, mask, phase, labels = arrays(rows)
    blocks = np.asarray(beta, dtype=np.float64).reshape(4, FEATURE_WIDTH)
    score = np.einsum("nij,nj->ni", x, blocks[phase], optimize=True)
    score = score.copy(); score[~mask] = -np.inf
    return score, phase, labels


def pair_matrix(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    x, mask, phase, labels = arrays(rows)
    count = int(np.sum(mask)) - len(rows)
    out = np.zeros((count, WIDTH), dtype=np.float64)
    k = 0
    for i in range(len(rows)):
        y = int(labels[i]); p = int(phase[i]); base = p * FEATURE_WIDTH
        for j in range(4):
            if j == y or not bool(mask[i, j]):
                continue
            out[k, base:base + FEATURE_WIDTH] = x[i, y] - x[i, j]
            k += 1
    if k != count or count <= 0:
        raise ValueError(f"D4c pair cardinality drift k={k} expected={count}")
    return out


def loss_grad(beta: np.ndarray, pairs: np.ndarray) -> tuple[float, np.ndarray]:
    z = pairs @ beta
    loss = float(np.mean(np.logaddexp(0.0, -z))) + 0.5 * L2 * float(np.dot(beta, beta))
    # d softplus(-z)/dz = -1/(1+exp(z)); stable form via exp(-logaddexp(0,z)).
    coeff = -np.exp(-np.logaddexp(0.0, z))
    grad = (pairs.T @ coeff) / pairs.shape[0] + L2 * beta
    return loss, np.asarray(grad, dtype=np.float64)


def metric_view(beta: np.ndarray, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    score, _, labels = score_matrix(beta, rows)
    pred = np.argmax(score, axis=1)
    baseline = np.zeros(len(rows), dtype=np.int64)
    correct = pred == labels
    base_correct = baseline == labels
    nonfirst = labels > 0
    false_override = (pred > 0) & (labels == 0)
    correct_override = (pred == labels) & nonfirst

    pair_num = 0.0; pair_den = 0
    base_pair_num = 0.0
    for i, row in enumerate(rows):
        y = int(labels[i]); candidates = row["candidates"]
        for j in range(len(candidates)):
            if j == y: continue
            pair_den += 1
            delta = float(score[i, y] - score[i, j])
            pair_num += 1.0 if delta > 0 else (0.5 if delta == 0 else 0.0)
            # Legacy order ranks lower index first.
            base_pair_num += 1.0 if y < j else 0.0
    if pair_den <= 0:
        raise ValueError("D4c empty pair metric")

    pred_counts = {f"rank{i+1}": int(np.sum(pred == i)) for i in range(4)}
    return {
        "examples": len(rows),
        "baseline_top1": float(np.mean(base_correct)),
        "d4c_top1": float(np.mean(correct)),
        "top1_gain": float(np.mean(correct.astype(np.float64) - base_correct.astype(np.float64))),
        "baseline_pairwise_accuracy": float(base_pair_num / pair_den),
        "d4c_pairwise_accuracy": float(pair_num / pair_den),
        "pairs": pair_den,
        "change_rate": float(np.mean(pred > 0)),
        "predicted_rank_counts": pred_counts,
        "nonfirst_labels": int(np.sum(nonfirst)),
        "nonfirst_label_fraction": float(np.mean(nonfirst)),
        "correct_nonfirst_overrides": int(np.sum(correct_override)),
        "correct_nonfirst_override_rate": float(np.mean(correct_override[nonfirst])) if np.any(nonfirst) else 0.0,
        "false_overrides_on_rank1_labels": int(np.sum(false_override)),
        "false_override_rate_on_rank1_labels": float(np.mean(false_override[~nonfirst])) if np.any(~nonfirst) else 0.0,
        "correct": correct,
        "baseline_correct": base_correct,
    }


def bootstrap_top1(delta: np.ndarray) -> dict[str, float | int]:
    if delta.ndim != 1 or len(delta) == 0:
        raise ValueError("D4c bootstrap input drift")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    boot = np.empty(BOOTSTRAPS, dtype=np.float64)
    batch = 512
    for start in range(0, BOOTSTRAPS, batch):
        stop = min(BOOTSTRAPS, start + batch)
        idx = rng.integers(0, len(delta), size=(stop - start, len(delta)))
        boot[start:stop] = delta[idx].mean(axis=1)
    return {
        "mean": float(np.mean(delta)),
        "ci_low": float(np.quantile(boot, 0.025)),
        "ci_high": float(np.quantile(boot, 0.975)),
        "repetitions": BOOTSTRAPS,
        "seed": BOOTSTRAP_SEED,
    }


def strip_internal(m: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in m.items() if k not in ("correct", "baseline_correct")}


def cmd_fit(a: argparse.Namespace) -> int:
    rows = load_rows(a.train, "train")
    pairs = pair_matrix(rows)
    initial = np.zeros(WIDTH, dtype=np.float64)
    result = minimize(
        lambda beta: loss_grad(np.asarray(beta, dtype=np.float64), pairs),
        initial,
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": MAX_ITER, "maxcor": MAXCOR, "gtol": GTOL},
    )
    beta = np.asarray(result.x, dtype=np.float64)
    if beta.shape != (WIDTH,) or not np.all(np.isfinite(beta)):
        raise ValueError("D4c optimizer returned invalid model")
    model = d4.seal_model(a.model, beta)
    train = strip_internal(metric_view(beta, rows))
    report = {
        "schema": "jass.d4c.rank_breaker_fit.v1",
        "verdict": FIT_VERDICT,
        "objective": "pairwise_label_vs_other_logistic",
        "fixed_legacy_logit": False,
        "legacy_rank_feature_retained": True,
        "features": list(d4.FEATURES),
        "feature_width": FEATURE_WIDTH,
        "phase_blocks": 4,
        "model_width": WIDTH,
        "l2": L2,
        "optimizer": "L-BFGS-B",
        "max_iter": MAX_ITER,
        "maxcor": MAXCOR,
        "gtol": GTOL,
        "initialization": "zeros",
        "train_examples": len(rows),
        "train_pairs": int(pairs.shape[0]),
        "optimizer_success": bool(result.success),
        "optimizer_status": int(result.status),
        "optimizer_message": str(result.message),
        "optimizer_iterations": int(getattr(result, "nit", -1)),
        "optimizer_function_evaluations": int(getattr(result, "nfev", -1)),
        "train": train,
        "model": model,
        "fits": 1,
        "model_searches": 0,
        "hyperparameter_searches": 0,
        "temperature_searches": 0,
        "runtime_scale_searches": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
    }
    a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True)); return 0


def cmd_readout(a: argparse.Namespace) -> int:
    fit = json.loads(a.fit_report.read_text(encoding="utf-8"))
    prep = json.loads(a.prepare_report.read_text(encoding="utf-8"))
    teacher = json.loads(a.teacher_report.read_text(encoding="utf-8"))
    if fit.get("verdict") != FIT_VERDICT or fit.get("fits") != 1:
        raise ValueError("D4c fit provenance drift")
    if prep.get("verdict") != "D4B_EXAMPLES_READY_V1":
        raise ValueError("D4c reused prepare is not ready")
    if teacher.get("verdict") != "D4B_TEACHER_COMPLETE_V1" or teacher.get("teacher_searches") != 512:
        raise ValueError("D4c teacher provenance drift")
    beta = np.load(a.model, allow_pickle=False)
    if beta.dtype != np.dtype(np.float64) or beta.shape != (WIDTH,) or not np.all(np.isfinite(beta)):
        raise ValueError("D4c sealed model drift")
    if fit.get("model", {}).get("sha256") != d4.sha_file(a.model):
        raise ValueError("D4c model SHA drift")

    valid_rows = load_rows(a.valid, "valid"); test_rows = load_rows(a.test, "test")
    valid = metric_view(beta, valid_rows); test = metric_view(beta, test_rows)
    delta = test["correct"].astype(np.float64) - test["baseline_correct"].astype(np.float64)
    boot = bootstrap_top1(delta)
    gates = {
        "valid_top1_gt_baseline": valid["d4c_top1"] > valid["baseline_top1"],
        "test_top1_gt_baseline": test["d4c_top1"] > test["baseline_top1"],
        "test_paired_top1_gain_mean_gt_0": boot["mean"] > 0.0,
        "test_change_rate_ge_0p01": test["change_rate"] >= 0.01,
        "test_change_rate_le_0p35": test["change_rate"] <= 0.35,
        "test_correct_nonfirst_override_rate_ge_0p05": test["correct_nonfirst_override_rate"] >= 0.05,
    }
    supported = all(gates.values())
    out = {
        "schema": "jass.d4c.rank_breaker_offline_terminal.v1",
        "verdict": PASS if supported else FAIL,
        "model_sha256": d4.sha_file(a.model),
        "objective": "pairwise_label_vs_other_logistic",
        "fixed_legacy_logit": False,
        "legacy_rank_feature_retained": True,
        "teacher_searches": 512,
        "teacher_nodes_per_root": 20_000,
        "valid": strip_internal(valid),
        "test": {**strip_internal(test), "paired_top1_gain_bootstrap": boot},
        "gates": gates,
        "scan_gate0_authorized": supported,
        "fits": 1,
        "strength_games": 0,
        "selfplay_games": 0,
        "promotions": 0,
        "bakes": 0,
        "strength_authorized": False,
    }
    a.report.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, sort_keys=True)); return 0


def main() -> int:
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fit")
    p.add_argument("--train", type=Path, required=True); p.add_argument("--model", type=Path, required=True); p.add_argument("--report", type=Path, required=True); p.set_defaults(fn=cmd_fit)
    p = sub.add_parser("readout")
    p.add_argument("--model", type=Path, required=True); p.add_argument("--valid", type=Path, required=True); p.add_argument("--test", type=Path, required=True)
    p.add_argument("--prepare-report", type=Path, required=True); p.add_argument("--fit-report", type=Path, required=True); p.add_argument("--teacher-report", type=Path, required=True); p.add_argument("--report", type=Path, required=True); p.set_defaults(fn=cmd_readout)
    a = ap.parse_args()
    try:
        return int(a.fn(a))
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"d4c_rank_breaker: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
