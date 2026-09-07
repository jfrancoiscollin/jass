#!/usr/bin/env python3
"""Diagnostic-only terminal autopsy for frozen D1 WDL+listwise failure."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import struct
from typing import Any, Mapping, Sequence

import numpy as np

from jobs.tools import d1_listwise_fit as dfit
from jobs.tools.d1_listwise_fit_historical_split import HISTORICAL_HOLDOUT, HISTORICAL_TRAIN

# The terminal D1 fit used the immutable historical CURRENT split. Patch the
# compatibility counts before importing the terminal readout validator, exactly
# as d1_postfit_readout_historical_split.py does.
dfit.HOLDOUT = HISTORICAL_HOLDOUT
dfit.TRAIN = HISTORICAL_TRAIN

from jobs.tools import d1_postfit_readout as readout  # noqa: E402

SCHEMA = "jass.d1.terminal_autopsy.v1"
VERDICT = "D1_TERMINAL_AUTOPSY_COMPLETE_V1"
EXPECTED_D1_VERDICT = "D1_DECISION_TRANSFER_NOT_ESTABLISHED_V1"


class AutopsyError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AutopsyError(f"cannot read {path}: {exc}") from exc
    if type(value) is not dict:
        raise AutopsyError(f"JSON object required: {path}")
    return value


def _q(values: np.ndarray, probability: float) -> float:
    return float(np.quantile(values, probability, method="linear"))


def _parent_metrics(z_black: np.ndarray, group: Mapping[str, Any]) -> dict[str, float | int]:
    start = int(group["start"])
    count = int(group["count"])
    selected = int(group["selected_local_action_index"])
    pov = 1.0 if int(group["parent_stm"]) == 1 else -1.0
    q = pov * z_black[start:start + count]
    qmax = float(np.max(q))
    ex = np.exp(q - qmax)
    probs = ex / float(np.sum(ex))
    order = np.argsort(-q, kind="stable")
    rank = int(np.flatnonzero(order == selected)[0]) + 1
    ce = (qmax + math.log(float(np.sum(ex)))) - float(q[selected])
    return {
        "cross_entropy": float(ce),
        "selected_probability": float(probs[selected]),
        "rank": rank,
        "top1": int(rank == 1),
        "top2": int(rank <= 2),
    }


def parent_rows(z_control: np.ndarray, z_listwise: np.ndarray,
                groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        a = _parent_metrics(z_control, group)
        b = _parent_metrics(z_listwise, group)
        count = int(group["count"])
        rows.append({
            "parent_id": int(group["parent_id"]),
            "split": str(group["split"]),
            "cell": str(group["cell"]),
            "parent_stm": int(group["parent_stm"]),
            "actions": count,
            "action_band": "2-4" if count <= 4 else ("5-8" if count <= 8 else "9-16"),
            "control": a,
            "listwise": b,
            "delta_ce_control_minus_listwise": float(a["cross_entropy"] - b["cross_entropy"]),
        })
    return rows


def _aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise AutopsyError("cannot aggregate empty parent group")
    delta = np.asarray([r["delta_ce_control_minus_listwise"] for r in rows], dtype=np.float64)
    ce_a = np.asarray([r["control"]["cross_entropy"] for r in rows], dtype=np.float64)
    ce_b = np.asarray([r["listwise"]["cross_entropy"] for r in rows], dtype=np.float64)
    p_a = np.asarray([r["control"]["selected_probability"] for r in rows], dtype=np.float64)
    p_b = np.asarray([r["listwise"]["selected_probability"] for r in rows], dtype=np.float64)
    t1a = np.asarray([r["control"]["top1"] for r in rows], dtype=np.float64)
    t1b = np.asarray([r["listwise"]["top1"] for r in rows], dtype=np.float64)
    t2a = np.asarray([r["control"]["top2"] for r in rows], dtype=np.float64)
    t2b = np.asarray([r["listwise"]["top2"] for r in rows], dtype=np.float64)
    return {
        "parents": len(rows),
        "control_cross_entropy": float(np.mean(ce_a)),
        "listwise_cross_entropy": float(np.mean(ce_b)),
        "delta_ce_mean": float(np.mean(delta)),
        "delta_ce_median": float(np.median(delta)),
        "delta_ce_q05": _q(delta, 0.05),
        "delta_ce_q25": _q(delta, 0.25),
        "delta_ce_q75": _q(delta, 0.75),
        "delta_ce_q95": _q(delta, 0.95),
        "fraction_improved": float(np.mean(delta > 0.0)),
        "catastrophic_regression_rate_delta_lt_minus1": float(np.mean(delta < -1.0)),
        "large_improvement_rate_delta_gt_plus1": float(np.mean(delta > 1.0)),
        "control_selected_probability_mean": float(np.mean(p_a)),
        "listwise_selected_probability_mean": float(np.mean(p_b)),
        "selected_probability_delta": float(np.mean(p_b) - np.mean(p_a)),
        "control_top1": float(np.mean(t1a)),
        "listwise_top1": float(np.mean(t1b)),
        "top1_delta": float(np.mean(t1b) - np.mean(t1a)),
        "control_top2": float(np.mean(t2a)),
        "listwise_top2": float(np.mean(t2b)),
        "top2_delta": float(np.mean(t2b) - np.mean(t2a)),
    }


def grouped(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    buckets: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row[key])].append(row)
    return {name: _aggregate(items) for name, items in sorted(buckets.items())}


def _load_pjtw(path: Path) -> tuple[dict[str, int], np.ndarray]:
    raw = path.read_bytes()
    if len(raw) < 20:
        raise AutopsyError(f"{path}: PJTW too short")
    magic, version, scale, n_pat, n_ext = struct.unpack_from("<5I", raw, 0)
    if magic != 0x57544A50 or (version & 0xFF) != 3 or scale <= 0:
        raise AutopsyError(f"{path}: PJTW header drift")
    expected = 20 + 8 * (n_pat + n_ext)
    if len(raw) != expected:
        raise AutopsyError(f"{path}: PJTW size drift {len(raw)} != {expected}")
    weights = np.frombuffer(raw, dtype="<i4", offset=20).astype(np.int64, copy=True)
    return {"magic": magic, "version": version, "scale": scale,
            "n_patterns": n_pat, "n_extras": n_ext}, weights


def _drift_stats(a: np.ndarray, b: np.ndarray, scale: int) -> dict[str, Any]:
    if a.shape != b.shape:
        raise AutopsyError("weight block shape mismatch")
    d = b - a
    absd = np.abs(d)
    both_nonzero = (a != 0) & (b != 0)
    sign_flip = both_nonzero & ((a < 0) != (b < 0))
    denominator = int(np.sum(both_nonzero))
    rms = float(np.sqrt(np.mean(d.astype(np.float64) ** 2))) if d.size else 0.0
    mean_abs = float(np.mean(absd)) if d.size else 0.0
    p95 = float(np.quantile(absd, 0.95, method="linear")) if d.size else 0.0
    maximum = int(np.max(absd)) if d.size else 0
    return {
        "weights": int(d.size),
        "changed": int(np.sum(d != 0)),
        "changed_fraction": float(np.mean(d != 0)) if d.size else 0.0,
        "mean_abs_delta_quantized": mean_abs,
        "rms_delta_quantized": rms,
        "p95_abs_delta_quantized": p95,
        "max_abs_delta_quantized": maximum,
        "mean_abs_delta_eval_units": mean_abs / scale,
        "rms_delta_eval_units": rms / scale,
        "p95_abs_delta_eval_units": p95 / scale,
        "max_abs_delta_eval_units": maximum / scale,
        "sign_flips": int(np.sum(sign_flip)),
        "sign_flip_fraction_among_both_nonzero": (float(np.sum(sign_flip)) / denominator if denominator else 0.0),
    }


def model_displacement(control_path: Path, listwise_path: Path) -> dict[str, Any]:
    ha, a = _load_pjtw(control_path)
    hb, b = _load_pjtw(listwise_path)
    if ha != hb:
        raise AutopsyError(f"A/B PJTW header mismatch: {ha} vs {hb}")
    n_pat = ha["n_patterns"]
    n_ext = ha["n_extras"]
    scale = ha["scale"]
    slices = {
        "pattern_mg": slice(0, n_pat),
        "pattern_eg": slice(n_pat, 2 * n_pat),
        "extras_mg": slice(2 * n_pat, 2 * n_pat + n_ext),
        "extras_eg": slice(2 * n_pat + n_ext, 2 * n_pat + 2 * n_ext),
    }
    blocks = {name: _drift_stats(a[sl], b[sl], scale) for name, sl in slices.items()}
    blocks["all"] = _drift_stats(a, b, scale)
    return {"header": ha, "blocks": blocks}


def _worst_best(rows: Sequence[Mapping[str, Any]], n: int = 20) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda r: float(r["delta_ce_control_minus_listwise"]))
    def compact(r: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "parent_id": r["parent_id"], "split": r["split"], "cell": r["cell"],
            "actions": r["actions"],
            "delta_ce": r["delta_ce_control_minus_listwise"],
            "control_ce": r["control"]["cross_entropy"],
            "listwise_ce": r["listwise"]["cross_entropy"],
            "control_selected_probability": r["control"]["selected_probability"],
            "listwise_selected_probability": r["listwise"]["selected_probability"],
            "control_rank": r["control"]["rank"], "listwise_rank": r["listwise"]["rank"],
        }
    return {
        "worst_regressions": [compact(r) for r in ordered[:n]],
        "largest_improvements": [compact(r) for r in reversed(ordered[-n:])],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    terminal = _load_json(args.readout)
    if (terminal.get("schema") != readout.SCHEMA
            or terminal.get("verdict") != EXPECTED_D1_VERDICT
            or terminal.get("equal_node_gate_authorized") is not False
            or terminal.get("next_stage") != "STOP"):
        raise AutopsyError("terminal D1 failure contract drift")

    fit_a = readout.load_fit_report(args.control_fit, dfit.ARM_CONTROL)
    fit_b = readout.load_fit_report(args.listwise_fit, dfit.ARM_LISTWISE)
    groups = readout.load_groups(args.decision_groups)
    z_a = readout._predict(args.decision_data, args.decision_feat, args.control_model)
    z_b = readout._predict(args.decision_data, args.decision_feat, args.listwise_model)
    rows = parent_rows(z_a, z_b, groups)
    if len(rows) != dfit.PARENTS:
        raise AutopsyError("parent cardinality drift")

    by_split = {split: _aggregate([r for r in rows if r["split"] == split])
                for split in ("train", "valid", "test")}
    train_report_check = {
        "WDL_CONTROL": {
            "fit_report_ce": float(fit_a["decision_train"]["listwise_cross_entropy"]),
            "recomputed_quantized_model_ce": by_split["train"]["control_cross_entropy"],
        },
        "WDL_LISTWISE": {
            "fit_report_ce": float(fit_b["decision_train"]["listwise_cross_entropy"]),
            "recomputed_quantized_model_ce": by_split["train"]["listwise_cross_entropy"],
        },
    }
    for item in train_report_check.values():
        item["absolute_difference"] = abs(item["fit_report_ce"] - item["recomputed_quantized_model_ce"])
        item["within_0p05_nat"] = item["absolute_difference"] <= 0.05

    cells = grouped(rows, "cell")
    bands = grouped(rows, "action_band")
    train_delta = by_split["train"]["delta_ce_mean"]
    valid_delta = by_split["valid"]["delta_ce_mean"]
    test_delta = by_split["test"]["delta_ce_mean"]
    delta_wdl = float(terminal["delta_wdl"])
    wdl_tol = float(terminal["wdl_noninferiority_tolerance"])
    teacher_train_fit = train_delta > 0.0
    heldout_reversal = teacher_train_fit and valid_delta < 0.0 and test_delta < 0.0
    wdl_conflict = delta_wdl > wdl_tol
    mean_probability_up_ce_worse = all(
        by_split[s]["selected_probability_delta"] > 0.0 and by_split[s]["delta_ce_mean"] < 0.0
        for s in ("valid", "test")
    )
    failure_across_both_stm = len(cells) == 8 and all(v["delta_ce_mean"] < 0.0 for v in cells.values())
    classification = (
        "TRAIN_FIT_WITH_HELDOUT_REVERSAL_AND_WDL_CONFLICT"
        if teacher_train_fit and heldout_reversal and wdl_conflict
        else "D1_FAILURE_SHAPE_OTHER"
    )

    publication = {
        "schema": SCHEMA,
        "verdict": VERDICT,
        "source_terminal_verdict": EXPECTED_D1_VERDICT,
        "classification": classification,
        "flags": {
            "teacher_train_fit": teacher_train_fit,
            "heldout_reversal": heldout_reversal,
            "wdl_conflict": wdl_conflict,
            "mean_probability_up_ce_worse": mean_probability_up_ce_worse,
            "failure_across_both_stm": failure_across_both_stm,
        },
        "decision": {
            "by_split": by_split,
            "by_cell": cells,
            "by_action_band": bands,
            "train_report_consistency": train_report_check,
            "tails": _worst_best(rows),
        },
        "wdl": {
            "control": terminal["wdl_holdout"]["WDL_CONTROL"],
            "listwise": terminal["wdl_holdout"]["WDL_LISTWISE"],
            "delta_wdl": delta_wdl,
            "noninferiority_tolerance": wdl_tol,
        },
        "model_displacement": model_displacement(args.control_model, args.listwise_model),
        "fits": 0,
        "model_searches": 0,
        "teacher_searches": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "equal_node_gate_authorized": False,
        "next_stage": "STOP_DIAGNOSTIC_REVIEW",
    }
    if args.out.exists() or args.out.is_symlink():
        raise AutopsyError(f"refusing existing output: {args.out}")
    args.out.write_text(json.dumps(publication, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8")
    return publication


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control-fit", type=Path, required=True)
    p.add_argument("--listwise-fit", type=Path, required=True)
    p.add_argument("--readout", type=Path, required=True)
    p.add_argument("--decision-data", type=Path, required=True)
    p.add_argument("--decision-feat", type=Path, required=True)
    p.add_argument("--decision-groups", type=Path, required=True)
    p.add_argument("--control-model", type=Path, required=True)
    p.add_argument("--listwise-model", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run(args)
    except (AutopsyError, readout.ReadoutError, dfit.D1FitError, OSError, ValueError) as exc:
        print(f"D1_TERMINAL_AUTOPSY_INVALID: {exc}")
        return 2
    print(result["verdict"])
    print(f"classification={result['classification']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
