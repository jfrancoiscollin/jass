#!/usr/bin/env python3
"""Terminal offline readout for frozen D1 WDL_CONTROL vs WDL_LISTWISE."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "pattern_jass" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import patterns  # noqa: E402
import train  # noqa: E402
import train_stream as ts  # noqa: E402

from jobs.tools import d1_listwise_fit as dfit  # noqa: E402

SCHEMA = "jass.d1.transfer_readout.v1"
VERDICT_PASS = "D1_DECISION_TRANSFER_ESTABLISHED_V1"
VERDICT_FAIL = "D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1"
SEED = 2026110901
BOOTSTRAPS = 200_000
WDL_TOLERANCE = 0.002


class ReadoutError(RuntimeError):
    pass


def load_fit_report(path: Path, arm: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadoutError(f"cannot read fit report {path}: {exc}") from exc
    if type(value) is not dict or value.get("schema") != dfit.REPORT_SCHEMA or value.get("arm") != arm:
        raise ReadoutError("fit report schema/arm drift")
    obj = value.get("objective"); opt = value.get("optimizer")
    if not isinstance(obj, Mapping) or not isinstance(opt, Mapping):
        raise ReadoutError("fit report objective/optimizer missing")
    expected = {
        "fold": "exact", "holdout_records": dfit.HOLDOUT, "l2": dfit.L2,
        "max_iter": dfit.MAX_ITER, "maxcor": dfit.MAXCOR, "gtol": dfit.GTOL,
        "records": dfit.RECORDS, "tempo_stage": True, "train_records": dfit.TRAIN,
    }
    for key, item in expected.items():
        if obj.get(key) != item:
            raise ReadoutError(f"fit recipe drift {arm}: {key}")
    decision = value.get("decision_train")
    if not isinstance(decision, Mapping) or decision.get("lambda") != dfit.LAMBDA[arm]:
        raise ReadoutError("fit treatment lambda drift")
    if opt.get("success") is not True:
        raise ReadoutError(f"optimizer did not converge for {arm}: {opt}")
    return value


def _open_model(path: Path) -> tuple[np.ndarray, int, int]:
    weights, scale, n_pat, n_ext = train.load_v3_weights_float(str(path))
    if scale != dfit.SCALE or n_pat != patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN:
        raise ReadoutError("model PatternEval layout/scale drift")
    return np.asarray(weights, dtype=np.float64), int(n_pat), int(n_ext)


def _predict(data: Path, feat_path: Path, model: Path, chunk: int = 20_000) -> np.ndarray:
    mm, n = ts.open_jnnw(str(data))
    feat, k = ts.open_feat(str(feat_path), n)
    weights, n_pat, n_ext = _open_model(model)
    if k != n_ext:
        raise ReadoutError("model/extras feature count drift")
    folder = ts.Folder("none")
    pred = np.empty(n, dtype=np.float64)
    for lo in range(0, n, chunk):
        hi = min(n, lo + chunk)
        rec = mm[lo:hi]
        wm = np.ascontiguousarray(rec["wm"]); bm = np.ascontiguousarray(rec["bm"])
        cols, signs = folder.cols_signs(bm, wm)
        wmg = ts._tempo_wmg_bb(wm, bm).astype(np.float64); weg = 1.0 - wmg
        xpat = train.build_sparse_X_phased(cols, wmg, weg, n_pat, signs)
        xext = train.build_extras_phased(np.asarray(feat[lo:hi], dtype=np.float64), wmg, weg)
        x = sp.hstack([xpat, xext], format="csr")
        pred[lo:hi] = np.asarray(x @ weights).ravel()
    return pred


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 0.5 * (np.tanh(0.5 * z) + 1.0)


def wdl_metrics(data: Path, feat: Path, targets_path: Path, model: Path) -> dict[str, float]:
    pred = _predict(data, feat, model)
    targets = np.load(targets_path, allow_pickle=False, mmap_mode="r")
    if targets.dtype != np.dtype(np.float32) or targets.shape != (dfit.RECORDS,):
        raise ReadoutError("WDL target sidecar drift")
    y = np.asarray(targets[dfit.TRAIN:], dtype=np.float64)
    p = _sigmoid(pred[dfit.TRAIN:])
    eps = 1e-12
    ce = -(y * np.log(p + eps) + (1.0 - y) * np.log(1.0 - p + eps))
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "logloss": float(np.mean(ce)),
        "prediction_mean": float(np.mean(p)),
        "target_mean": float(np.mean(y)),
    }


def load_groups(path: Path) -> list[dict[str, Any]]:
    groups, _ = dfit.load_groups(path)
    return groups


def decision_metrics(z_black: np.ndarray, groups: Sequence[Mapping[str, Any]],
                     split: str) -> tuple[dict[str, Any], np.ndarray]:
    ces: list[float] = []
    top1 = top2 = 0
    psel = 0.0
    per_cell: dict[str, list[tuple[float, int, int, float]]] = defaultdict(list)
    for group in groups:
        if group["split"] != split:
            continue
        start = int(group["start"]); count = int(group["count"]); selected = int(group["selected_local_action_index"])
        pov = 1.0 if int(group["parent_stm"]) == 1 else -1.0
        q = pov * z_black[start:start + count]
        qmax = float(np.max(q)); ex = np.exp(q - qmax); denom = float(np.sum(ex)); probs = ex / denom
        ce = (qmax + math.log(denom)) - float(q[selected])
        order = np.argsort(-q, kind="stable")
        hit1 = int(order[0] == selected); hit2 = int(selected in order[:2])
        prob = float(probs[selected])
        ces.append(ce); top1 += hit1; top2 += hit2; psel += prob
        per_cell[str(group["cell"])].append((ce, hit1, hit2, prob))
    if not ces:
        raise ReadoutError(f"empty decision split {split}")
    n = len(ces)
    cells = {}
    for cell, rows in sorted(per_cell.items()):
        a = np.asarray(rows, dtype=np.float64)
        cells[cell] = {
            "cross_entropy": float(np.mean(a[:, 0])),
            "parents": int(len(rows)),
            "selected_probability_mean": float(np.mean(a[:, 3])),
            "top1": float(np.mean(a[:, 1])),
            "top2": float(np.mean(a[:, 2])),
        }
    return ({
        "cells": cells,
        "cross_entropy": float(np.mean(ces)),
        "parents": n,
        "selected_probability_mean": psel / n,
        "top1": top1 / n,
        "top2": top2 / n,
    }, np.asarray(ces, dtype=np.float64))


def bootstrap_delta(delta: np.ndarray) -> dict[str, float]:
    if delta.shape != (400,):
        raise ReadoutError(f"D1 test delta must contain 400 parents, got {delta.shape}")
    rng = np.random.default_rng(SEED)
    values = np.empty(BOOTSTRAPS, dtype=np.float64)
    batch = 1000
    cursor = 0
    while cursor < BOOTSTRAPS:
        take = min(batch, BOOTSTRAPS - cursor)
        idx = rng.integers(0, delta.size, size=(take, delta.size), endpoint=False)
        values[cursor:cursor + take] = np.mean(delta[idx], axis=1)
        cursor += take
    return {
        "mean": float(np.mean(delta)),
        "lcb95": float(np.quantile(values, 0.025, method="linear")),
        "ucb95": float(np.quantile(values, 0.975, method="linear")),
        "replications": BOOTSTRAPS,
        "seed": SEED,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    load_fit_report(args.control_report, dfit.ARM_CONTROL)
    load_fit_report(args.listwise_report, dfit.ARM_LISTWISE)
    groups = load_groups(args.decision_groups)
    wdl_a = wdl_metrics(args.wdl_data, args.wdl_feat, args.target_values, args.control_model)
    wdl_b = wdl_metrics(args.wdl_data, args.wdl_feat, args.target_values, args.listwise_model)
    z_a = _predict(args.decision_data, args.decision_feat, args.control_model)
    z_b = _predict(args.decision_data, args.decision_feat, args.listwise_model)
    valid_a, _ = decision_metrics(z_a, groups, "valid")
    valid_b, _ = decision_metrics(z_b, groups, "valid")
    test_a, ce_a = decision_metrics(z_a, groups, "test")
    test_b, ce_b = decision_metrics(z_b, groups, "test")
    boot = bootstrap_delta(ce_a - ce_b)
    delta_wdl = wdl_b["logloss"] - wdl_a["logloss"]
    established = boot["lcb95"] > 0.0 and test_b["top1"] >= test_a["top1"] and delta_wdl <= WDL_TOLERANCE
    verdict = VERDICT_PASS if established else VERDICT_FAIL
    publication = {
        "bake_authorized": False,
        "bootstrap": boot,
        "decision_test": {"WDL_CONTROL": test_a, "WDL_LISTWISE": test_b},
        "decision_valid": {"WDL_CONTROL": valid_a, "WDL_LISTWISE": valid_b},
        "delta_wdl": delta_wdl,
        "equal_node_gate_authorized": bool(established),
        "fits": 2,
        "lambda_sweeps": 0,
        "model_searches": 0,
        "next_stage": "D1_EQUAL_NODE_CAUSAL_PREREGISTRATION" if established else "STOP",
        "promotion_authorized": False,
        "schema": SCHEMA,
        "state": "completed",
        "strength_games": 0,
        "verdict": verdict,
        "wdl_holdout": {"WDL_CONTROL": wdl_a, "WDL_LISTWISE": wdl_b},
        "wdl_noninferiority_tolerance": WDL_TOLERANCE,
    }
    if args.out.exists():
        raise ReadoutError(f"output already exists: {args.out}")
    args.out.write_text(json.dumps(publication, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    return publication


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wdl-data", type=Path, required=True)
    p.add_argument("--wdl-feat", type=Path, required=True)
    p.add_argument("--target-values", type=Path, required=True)
    p.add_argument("--decision-data", type=Path, required=True)
    p.add_argument("--decision-feat", type=Path, required=True)
    p.add_argument("--decision-groups", type=Path, required=True)
    p.add_argument("--control-model", type=Path, required=True)
    p.add_argument("--listwise-model", type=Path, required=True)
    p.add_argument("--control-report", type=Path, required=True)
    p.add_argument("--listwise-report", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result = run(parse_args(argv))
    except Exception as exc:
        print(f"d1_postfit_readout: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"verdict": result["verdict"], "next_stage": result["next_stage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
