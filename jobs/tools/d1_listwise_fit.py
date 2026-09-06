#!/usr/bin/env python3
"""Frozen D1 two-arm PatternEval fitter: WDL control vs WDL + selected-action listwise.

This is intentionally a D1-specific fitter rather than a change to the generic
trainer.  Both arms share the exact CURRENT_2M WDL objective, fold, prune map,
CURRICULUM prior, optimizer and feature files.  The sole treatment difference is
lambda_decision = 0 (WDL_CONTROL) versus 1 (WDL_LISTWISE).
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "pattern_jass" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import patterns  # noqa: E402
import train  # noqa: E402
import train_stream as ts  # noqa: E402

ARM_CONTROL = "WDL_CONTROL"
ARM_LISTWISE = "WDL_LISTWISE"
GROUP_SCHEMA = "jass.d1.selected_action_groups.v1"
REPORT_SCHEMA = "jass.d1.fit_contract.v1"
RECORDS = 2_000_000
HOLDOUT = 200_000
TRAIN = RECORDS - HOLDOUT
ACTIONS = 38_053
PARENTS = 4_000
TRAIN_PARENTS = 3_200
L2 = 1e-5
CHUNK = 20_000
MAX_ITER = 2_000
MAXCOR = 20
GTOL = 1e-4
LAMBDA = {ARM_CONTROL: 0.0, ARM_LISTWISE: 1.0}
SCALE = 1000


class D1FitError(RuntimeError):
    pass


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise D1FitError(f"cannot read JSON {path}: {exc}") from exc
    if type(value) is not dict:
        raise D1FitError(f"JSON object required: {path}")
    return value


def load_groups(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = _json(path)
    if payload.get("schema") != GROUP_SCHEMA or payload.get("parents") != PARENTS \
            or payload.get("actions") != ACTIONS:
        raise D1FitError("decision group identity/count drift")
    if payload.get("split_parents") != {"train": 3200, "valid": 400, "test": 400}:
        raise D1FitError("decision split parent counts drift")
    groups = payload.get("groups")
    if not isinstance(groups, list) or len(groups) != PARENTS:
        raise D1FitError("decision group list drift")
    cursor = 0
    train_groups: list[dict[str, Any]] = []
    for parent_id, group in enumerate(groups):
        if type(group) is not dict or group.get("parent_id") != parent_id:
            raise D1FitError("decision parent ordering drift")
        start = group.get("start"); count = group.get("count"); selected = group.get("selected_local_action_index")
        stm = group.get("parent_stm"); split = group.get("split")
        if type(start) is not int or start != cursor or type(count) is not int or not 2 <= count <= 16:
            raise D1FitError("decision action span drift")
        if type(selected) is not int or not 0 <= selected < count:
            raise D1FitError("decision selected action drift")
        if type(stm) is not int or stm not in (0, 1) or split not in {"train", "valid", "test"}:
            raise D1FitError("decision group metadata drift")
        cursor += count
        if split == "train":
            train_groups.append(group)
    if cursor != ACTIONS or len(train_groups) != TRAIN_PARENTS:
        raise D1FitError("decision action/train-parent cardinality drift")
    return groups, train_groups


def _validate_external_targets(path: Path, n: int) -> np.ndarray:
    try:
        arr = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise D1FitError(f"cannot load target sidecar: {exc}") from exc
    if not isinstance(arr, np.ndarray) or arr.dtype != np.dtype(np.float32) or arr.shape != (n,):
        raise D1FitError("target sidecar must be float32 vector aligned to CURRENT_2M")
    if not bool(np.all(np.isfinite(arr))) or float(np.min(arr)) < 0.0 or float(np.max(arr)) > 1.0:
        raise D1FitError("target sidecar values outside [0,1]")
    return arr


def _decision_design(data: Path, feat_path: Path, folder: Any, remap: np.ndarray,
                     pat_n: int, extras_n: int) -> sp.csr_matrix:
    mm, n = ts.open_jnnw(str(data))
    feat, k = ts.open_feat(str(feat_path), n)
    if n != ACTIONS or k != extras_n:
        raise D1FitError("decision data/feature cardinality drift")
    wm = np.ascontiguousarray(mm["wm"]); wk = np.ascontiguousarray(mm["wk"])
    bm = np.ascontiguousarray(mm["bm"]); bk = np.ascontiguousarray(mm["bk"])
    cols, signs = folder.cols_signs(bm, wm)
    mapped = remap[cols]
    # CURRENT_2M prune is common to both arms. Pattern buckets unseen in that WDL
    # corpus deploy as zero, so auxiliary-only unseen buckets must contribute zero
    # rather than leaking through the pruned fallback slot 0.
    if signs is None:
        signs_eff = (mapped != 0).astype(np.float64)
    else:
        signs_eff = np.asarray(signs, dtype=np.float64) * (mapped != 0)
    wmg = ts._tempo_wmg_bb(wm, bm).astype(np.float64)
    weg = 1.0 - wmg
    xpat = train.build_sparse_X_phased(mapped, wmg, weg, pat_n, signs_eff)
    extras = np.asarray(feat, dtype=np.float64)
    xext = train.build_extras_phased(extras, wmg, weg)
    design = sp.hstack([xpat, xext], format="csr").astype(np.float64)
    if design.shape[0] != ACTIONS:
        raise D1FitError("decision design row drift")
    return design


def listwise_loss_grad(weights: np.ndarray, design: sp.csr_matrix,
                       groups: Sequence[Mapping[str, Any]]) -> tuple[float, np.ndarray, dict[str, float]]:
    """Parent-equal selected-action softmax CE and exact gradient."""
    if not groups:
        raise D1FitError("empty listwise parent set")
    z_black = np.asarray(design @ weights).ravel()
    residual = np.zeros(design.shape[0], dtype=np.float64)
    total = 0.0
    top1 = 0
    selected_prob_sum = 0.0
    for group in groups:
        start = int(group["start"]); count = int(group["count"])
        selected = int(group["selected_local_action_index"])
        pov = 1.0 if int(group["parent_stm"]) == 1 else -1.0
        q = pov * z_black[start:start + count]
        qmax = float(np.max(q))
        ex = np.exp(q - qmax)
        denom = float(np.sum(ex))
        probs = ex / denom
        total += (qmax + math.log(denom)) - float(q[selected])
        selected_prob_sum += float(probs[selected])
        if int(np.argmax(q)) == selected:
            top1 += 1
        r = probs.copy(); r[selected] -= 1.0
        residual[start:start + count] = pov * r
    n = len(groups)
    grad = np.asarray(design.T @ residual).ravel() / n
    return total / n, grad, {
        "parents": float(n),
        "selected_probability_mean": selected_prob_sum / n,
        "top1": top1 / n,
    }


def _write_json(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise D1FitError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def fit(args: argparse.Namespace) -> dict[str, Any]:
    if args.arm not in LAMBDA:
        raise D1FitError("unknown arm")
    if args.holdout_count != HOLDOUT:
        raise D1FitError(f"D1 holdout must be exactly {HOLDOUT}")
    lam = LAMBDA[args.arm]
    mm, n = ts.open_jnnw(str(args.data))
    feat, extras_n = ts.open_feat(str(args.feat), n)
    if n != RECORDS:
        raise D1FitError(f"D1 requires CURRENT_2M, got {n}")
    targets = _validate_external_targets(args.target_values, n)
    groups, train_groups = load_groups(args.decision_groups)
    if len(groups) != PARENTS:
        raise D1FitError("decision groups count drift")

    folder = ts.Folder("exact")
    tb = folder.TB
    ccounts = np.zeros(tb, dtype=np.int64)
    wmg_all = np.empty(n, dtype=np.float32)
    print(f"D1 arm={args.arm} lambda_decision={lam} records={n} holdout={HOLDOUT}", flush=True)
    for lo in range(0, n, CHUNK):
        hi = min(n, lo + CHUNK)
        rec = mm[lo:hi]
        wm = np.ascontiguousarray(rec["wm"]); bm = np.ascontiguousarray(rec["bm"])
        cols, _ = folder.cols_signs(bm, wm)
        ccounts += np.bincount(cols.ravel(), minlength=tb)
        wmg_all[lo:hi] = ts._tempo_wmg_bb(wm, bm).astype(np.float32)
    keep = np.flatnonzero(ccounts >= 1)
    keep = keep[np.argsort(ccounts[keep])[::-1]]
    remap = np.zeros(tb, dtype=np.int32)
    remap[keep] = np.arange(1, len(keep) + 1, dtype=np.int32)
    pat_n = len(keep) + 1
    n_cols = 2 * pat_n + 2 * extras_n
    del ccounts

    prior_mean, prior_scale = ts.project_champion_mean(
        str(args.prior), folder, keep, pat_n, extras_n)
    if prior_scale != SCALE or prior_mean.shape != (n_cols,):
        raise D1FitError("CURRICULUM prior projection/scale drift")
    prior_prec = np.full(n_cols, L2, dtype=np.float64)

    def wdl_design(sel: np.ndarray) -> sp.csr_matrix:
        lo = int(sel[0]); hi = int(sel[-1]) + 1
        if hi - lo != len(sel) or int(sel[-1]) != hi - 1:
            raise D1FitError("WDL chunk is not contiguous")
        rec = mm[lo:hi]
        wm = np.ascontiguousarray(rec["wm"]); bm = np.ascontiguousarray(rec["bm"])
        cols, signs = folder.cols_signs(bm, wm)
        cols = remap[cols]
        wmg = wmg_all[lo:hi].astype(np.float64); weg = 1.0 - wmg
        xpat = train.build_sparse_X_phased(cols, wmg, weg, pat_n, signs)
        xext = train.build_extras_phased(np.asarray(feat[lo:hi], dtype=np.float64), wmg, weg)
        return sp.hstack([xpat, xext], format="csr")

    decision_x = _decision_design(args.decision_data, args.decision_feat,
                                  folder, remap, pat_n, extras_n)
    eps = 1e-12
    train_idx = np.arange(TRAIN, dtype=np.int64)
    evals = 0

    def objective(w: np.ndarray) -> tuple[float, np.ndarray]:
        nonlocal evals
        evals += 1
        data_loss = 0.0
        grad = np.zeros(n_cols, dtype=np.float64)
        for i in range(0, TRAIN, CHUNK):
            sel = train_idx[i:i + CHUNK]
            x = wdl_design(sel)
            y = np.asarray(targets[sel], dtype=np.float64)
            z = np.asarray(x @ w).ravel()
            p = 0.5 * (np.tanh(0.5 * z) + 1.0)
            ce = -(y * np.log(p + eps) + (1.0 - y) * np.log(1.0 - p + eps))
            data_loss += float(np.sum(ce))
            grad += np.asarray(x.T @ (p - y)).ravel()
        data_loss /= TRAIN
        grad /= TRAIN
        diff = w - prior_mean
        reg = 0.5 * float(np.dot(prior_prec * diff, diff))
        grad += prior_prec * diff
        decision_loss, decision_grad, _ = listwise_loss_grad(w, decision_x, train_groups)
        loss = data_loss + reg + lam * decision_loss
        grad += lam * decision_grad
        if evals == 1 or evals % 10 == 0:
            print(f"objective eval={evals} total={loss:.9f} wdl={data_loss:.9f} "
                  f"decision={decision_loss:.9f} reg={reg:.9f}", flush=True)
        return loss, grad

    t0 = time.time()
    result = minimize(objective, prior_mean.copy(), jac=True, method="L-BFGS-B",
                      options={"maxiter": MAX_ITER, "maxcor": MAXCOR, "gtol": GTOL})
    fitted = np.asarray(result.x, dtype=np.float64)
    decision_loss, _decision_grad, decision_stats = listwise_loss_grad(
        fitted, decision_x, train_groups)

    def quant(block: np.ndarray) -> np.ndarray:
        q = np.round(block * SCALE).astype(np.int64)
        return np.clip(q, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)

    pat_mg_d = fitted[:pat_n]
    pat_eg_d = fitted[pat_n:2 * pat_n]
    canon_mg = np.zeros(tb, dtype=fitted.dtype)
    canon_eg = np.zeros(tb, dtype=fitted.dtype)
    kept = np.flatnonzero(remap > 0)
    canon_mg[kept] = pat_mg_d[remap[kept]]
    canon_eg[kept] = pat_eg_d[remap[kept]]
    pat_mg, pat_eg = ts.expand_pat(folder, canon_mg, canon_eg, SCALE)
    ext_mg = quant(fitted[2 * pat_n:2 * pat_n + extras_n])
    ext_eg = quant(fitted[2 * pat_n + extras_n:2 * pat_n + 2 * extras_n])
    if args.out.exists():
        raise D1FitError(f"output already exists: {args.out}")
    train.write_weights_v3(args.out, pat_mg, pat_eg, ext_mg, ext_eg, SCALE, king=False)

    report = {
        "arm": args.arm,
        "decision_train": {
            "lambda": lam,
            "listwise_cross_entropy": decision_loss,
            "selected_probability_mean": decision_stats["selected_probability_mean"],
            "top1": decision_stats["top1"],
            "parents": TRAIN_PARENTS,
        },
        "elapsed_seconds": time.time() - t0,
        "objective": {
            "fold": "exact",
            "holdout_records": HOLDOUT,
            "l2": L2,
            "loss": "external_logistic_plus_selected_action_listwise",
            "max_iter": MAX_ITER,
            "maxcor": MAXCOR,
            "gtol": GTOL,
            "prior": "CURRICULUM_uniform_l2_center",
            "records": RECORDS,
            "tempo_stage": True,
            "train_records": TRAIN,
        },
        "optimizer": {
            "final_objective": float(result.fun),
            "function_evaluations": int(result.nfev),
            "gradient_inf_norm": float(np.max(np.abs(result.jac))),
            "iterations": int(result.nit),
            "message": str(result.message),
            "status": int(result.status),
            "success": bool(result.success),
        },
        "output": {"path": str(args.out), "size_bytes": args.out.stat().st_size},
        "pruned_pattern_slots": pat_n,
        "schema": REPORT_SCHEMA,
    }
    _write_json(args.report, report)
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arm", choices=[ARM_CONTROL, ARM_LISTWISE], required=True)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--feat", type=Path, required=True)
    p.add_argument("--target-values", type=Path, required=True)
    p.add_argument("--prior", type=Path, required=True)
    p.add_argument("--decision-data", type=Path, required=True)
    p.add_argument("--decision-feat", type=Path, required=True)
    p.add_argument("--decision-groups", type=Path, required=True)
    p.add_argument("--holdout-count", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result = fit(parse_args(argv))
    except Exception as exc:
        print(f"d1_listwise_fit: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"arm": result["arm"], "optimizer": result["optimizer"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
