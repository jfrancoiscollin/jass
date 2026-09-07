#!/usr/bin/env python3
"""Frozen D3 relational action-residual preflight, fit, and terminal readout.

D3 keeps the authenticated WDL_CONTROL value model byte-identical. Its policy
ordering score is the fixed parent-POV WDL_CONTROL child logit plus one
632-parameter phase-gated residual over authenticated C move semantics.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TOOLS = ROOT / "pattern_jass" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from jobs.tools import d1_listwise_fit as dfit  # noqa: E402
from jobs.tools import d1_postfit_readout as d1readout  # noqa: E402

PARENT_SCHEMA = "jass.sibling_dataset_v2.parent.v1"
PREFLIGHT_SCHEMA = "jass.d3.relational_action_preflight.v1"
FIT_SCHEMA = "jass.d3.relational_action_fit.v1"
READOUT_SCHEMA = "jass.d3.relational_action_transfer_readout.v1"
PREFLIGHT_VERDICT = "D3_RELATIONAL_ACTION_PREFLIGHT_COMPLETE_V1"
VERDICT_PASS = "D3_RELATIONAL_ACTION_TRANSFER_ESTABLISHED_V1"
VERDICT_FAIL = "D3_RELATIONAL_ACTION_TRANSFER_NOT_ESTABLISHED_V1"
VERDICT_INVALID = "D3_RELATIONAL_ACTION_TRANSFER_INVALID_V1"

PARENTS = 4_000
ACTIONS = 38_053
SPLITS = {"train": 3_200, "valid": 400, "test": 400}
BASE_WIDTH = 158
PHASES = 4
WIDTH = 632
L2 = 1e-3
MAX_ITER = 500
MAXCOR = 10
GTOL = 1e-6
BOOTSTRAPS = 200_000
SEED = 2026111201
CELL_RE = re.compile(r"^P([0-3])_stm([01])$")


class D3Error(RuntimeError):
    pass


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("ascii")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise D3Error(f"cannot read JSON {path}: {exc}") from exc
    if type(value) is not dict:
        raise D3Error(f"JSON object required: {path}")
    return value


def _write_json_new(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise D3Error(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise D3Error(f"refusing existing temporary {tmp}")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _write_adapter_new(path: Path, beta: np.ndarray) -> dict[str, Any]:
    if path.suffix != ".npy":
        raise D3Error("adapter output must be .npy")
    if path.exists() or path.is_symlink():
        raise D3Error(f"refusing existing adapter {path}")
    if beta.dtype != np.dtype(np.float64) or beta.shape != (WIDTH,) or not np.all(np.isfinite(beta)):
        raise D3Error("adapter must be finite float64 width 632")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("wb") as handle:
            np.save(handle, beta, allow_pickle=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    sealed = np.load(path, allow_pickle=False)
    if sealed.dtype != np.dtype(np.float64) or sealed.shape != (WIDTH,) or not np.array_equal(sealed, beta):
        raise D3Error("adapter serialization round-trip drift")
    return {
        "dtype": "float64",
        "format": "npy",
        "sha256": sha_file(path),
        "size_bytes": path.stat().st_size,
        "width": WIDTH,
    }


def read_dataset(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise D3Error("C dataset must be LF terminated")
    parents: list[dict[str, Any]] = []
    actions = 0
    split_counts = {k: 0 for k in SPLITS}
    for number, line in enumerate(raw.splitlines(keepends=True), 1):
        try:
            parent = json.loads(line.decode("ascii"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise D3Error(f"C dataset parse failure line {number}") from exc
        if type(parent) is not dict or parent.get("schema") != PARENT_SCHEMA or _canonical(parent) != line:
            raise D3Error(f"C dataset canonical/schema failure line {number}")
        if parent.get("parent_id") != len(parents):
            raise D3Error("C parent ordering drift")
        split = parent.get("split")
        if split not in SPLITS:
            raise D3Error("C split drift")
        parent_actions = parent.get("actions")
        if not isinstance(parent_actions, list) or not 2 <= len(parent_actions) <= 16:
            raise D3Error("C action list drift")
        actions += len(parent_actions)
        split_counts[str(split)] += 1
        parents.append(parent)
    if len(parents) != PARENTS or actions != ACTIONS or split_counts != SPLITS:
        raise D3Error(f"C cardinality drift parents={len(parents)} actions={actions} splits={split_counts}")
    return parents


def load_groups(path: Path) -> list[dict[str, Any]]:
    groups, _ = dfit.load_groups(path)
    if len(groups) != PARENTS:
        raise D3Error("decision group parent count drift")
    return groups


def canonical_square(square: int, parent_stm: int) -> int:
    if type(square) is not int or not 1 <= square <= 50:
        raise D3Error(f"square outside 1..50: {square!r}")
    if parent_stm not in (0, 1):
        raise D3Error("parent STM outside {0,1}")
    return square if parent_stm == 1 else 51 - square


def canonical_capture_mask(bitboard: int, parent_stm: int) -> np.ndarray:
    if type(bitboard) is not int or bitboard < 0 or bitboard >= (1 << 50):
        raise D3Error("captured_square_bitboard outside 50 squares")
    mask = np.zeros(50, dtype=np.float64)
    for square in range(1, 51):
        if bitboard & (1 << (square - 1)):
            canonical = canonical_square(square, parent_stm)
            mask[canonical - 1] = 1.0
    return mask


def _scalar_int(action: Mapping[str, Any], key: str, lo: int, hi: int) -> int:
    value = action.get(key)
    if type(value) is not int or not lo <= value <= hi:
        raise D3Error(f"{key} outside [{lo},{hi}]")
    return value


def _scalar_bool(action: Mapping[str, Any], key: str) -> bool:
    value = action.get(key)
    if type(value) is not bool:
        raise D3Error(f"{key} must be bool")
    return value


def base_action_vector(action: Mapping[str, Any], parent_stm: int) -> np.ndarray:
    frm = _scalar_int(action, "from", 1, 50)
    to = _scalar_int(action, "to", 1, 50)
    captured = _scalar_int(action, "captured_square_bitboard", 0, (1 << 50) - 1)
    num_captures = _scalar_int(action, "num_captures", 0, 20)
    captured_kings = _scalar_int(action, "captured_kings", 0, 20)
    material_delta = _scalar_int(action, "material_count_delta_parent", -20, 20)
    child_pieces = _scalar_int(action, "child_pieces", 0, 40)
    child_legal = _scalar_int(action, "child_legal_moves", 0, 64)
    promotes = _scalar_bool(action, "promotes")
    moving_king = _scalar_bool(action, "moving_king")
    forced = _scalar_bool(action, "child_forced_capture")
    if captured.bit_count() != num_captures:
        raise D3Error("capture bitboard/popcount drift")
    if captured_kings > num_captures:
        raise D3Error("captured_kings exceeds num_captures")

    vec = np.zeros(BASE_WIDTH, dtype=np.float64)
    vec[canonical_square(frm, parent_stm) - 1] = 1.0
    vec[50 + canonical_square(to, parent_stm) - 1] = 1.0
    vec[100:150] = canonical_capture_mask(captured, parent_stm)
    vec[150] = num_captures / 20.0
    vec[151] = float(promotes)
    vec[152] = float(moving_king)
    vec[153] = captured_kings / 20.0
    vec[154] = material_delta / 20.0
    vec[155] = child_pieces / 40.0
    vec[156] = child_legal / 64.0
    vec[157] = float(forced)
    return vec


def build_relational_features(parents: Sequence[Mapping[str, Any]],
                              groups: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, dict[str, Any]]:
    if len(parents) != PARENTS or len(groups) != PARENTS:
        raise D3Error("D3 parent cardinality drift")
    phi = np.zeros((ACTIONS, WIDTH), dtype=np.float64)
    cursor = 0
    phase_counts = {f"P{i}": 0 for i in range(PHASES)}
    for parent_id, (parent, group) in enumerate(zip(parents, groups)):
        if int(parent["parent_id"]) != parent_id or int(group["parent_id"]) != parent_id:
            raise D3Error("D3 parent identity drift")
        actions = parent["actions"]
        if int(group["start"]) != cursor or int(group["count"]) != len(actions):
            raise D3Error("D3 action span drift")
        stm = parent.get("stm")
        if type(stm) is not int or stm not in (0, 1) or int(group["parent_stm"]) != stm:
            raise D3Error("D3 parent STM drift")
        phase = parent.get("phase")
        if not isinstance(phase, str) or not re.fullmatch(r"P[0-3]", phase):
            raise D3Error(f"D3 phase drift: {phase!r}")
        phase_idx = int(phase[1])
        cell = group.get("cell")
        match = CELL_RE.fullmatch(cell) if isinstance(cell, str) else None
        if match is None or int(match.group(1)) != phase_idx or int(match.group(2)) != stm:
            raise D3Error("D3 phase/cell drift")
        block = slice(phase_idx * BASE_WIDTH, (phase_idx + 1) * BASE_WIDTH)
        for local, action in enumerate(actions):
            if type(action) is not dict or action.get("local_action_index") != local:
                raise D3Error("D3 action ordering drift")
            phi[cursor + local, block] = base_action_vector(action, stm)
        cursor += len(actions)
        phase_counts[phase] += 1
    if cursor != ACTIONS:
        raise D3Error("D3 action count drift")
    contiguous = np.ascontiguousarray(phi)
    return phi, {
        "base_width": BASE_WIDTH,
        "feature_sha256_float64_c": hashlib.sha256(contiguous.tobytes(order="C")).hexdigest(),
        "phase_blocks": PHASES,
        "phase_parent_counts": phase_counts,
        "width": WIDTH,
    }


def base_parent_scores(base_black: np.ndarray,
                       groups: Sequence[Mapping[str, Any]]) -> np.ndarray:
    if base_black.shape != (ACTIONS,):
        raise D3Error("base prediction cardinality drift")
    out = np.empty(ACTIONS, dtype=np.float64)
    for group in groups:
        start = int(group["start"])
        count = int(group["count"])
        pov = 1.0 if int(group["parent_stm"]) == 1 else -1.0
        out[start:start + count] = pov * base_black[start:start + count]
    return out


def listwise_loss_grad(beta: np.ndarray, phi: np.ndarray, base_parent: np.ndarray,
                       groups: Sequence[Mapping[str, Any]]) -> tuple[float, np.ndarray, dict[str, float]]:
    if beta.shape != (WIDTH,) or phi.shape != (ACTIONS, WIDTH) or base_parent.shape != (ACTIONS,):
        raise D3Error("D3 objective shape drift")
    if not groups:
        raise D3Error("empty D3 group set")
    score = base_parent + phi @ beta
    residual = np.zeros(ACTIONS, dtype=np.float64)
    total = 0.0
    top1 = 0
    psel = 0.0
    for group in groups:
        start = int(group["start"])
        count = int(group["count"])
        selected = int(group["selected_local_action_index"])
        q = score[start:start + count]
        qmax = float(np.max(q))
        ex = np.exp(q - qmax)
        denom = float(np.sum(ex))
        probs = ex / denom
        total += (qmax + math.log(denom)) - float(q[selected])
        psel += float(probs[selected])
        top1 += int(int(np.argmax(q)) == selected)
        r = probs.copy()
        r[selected] -= 1.0
        residual[start:start + count] = r
    n = len(groups)
    ce = total / n
    grad = np.asarray(phi.T @ residual, dtype=np.float64).ravel() / n
    reg = 0.5 * L2 * float(np.dot(beta, beta))
    return ce + reg, grad + L2 * beta, {
        "cross_entropy": ce,
        "parents": float(n),
        "regularizer": reg,
        "selected_probability_mean": psel / n,
        "top1": top1 / n,
    }


def fit_beta(phi: np.ndarray, base_parent: np.ndarray,
             groups: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, dict[str, Any]]:
    train_groups = [g for g in groups if g["split"] == "train"]
    if len(train_groups) != SPLITS["train"]:
        raise D3Error("D3 train parent count drift")
    initial = np.zeros(WIDTH, dtype=np.float64)
    result = minimize(
        lambda beta: listwise_loss_grad(beta, phi, base_parent, train_groups)[:2],
        initial,
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": MAX_ITER, "maxcor": MAXCOR, "gtol": GTOL},
    )
    beta = np.asarray(result.x, dtype=np.float64)
    final_loss, final_grad, stats = listwise_loss_grad(beta, phi, base_parent, train_groups)
    return beta, {
        "fit_count": 1,
        "final_objective": float(final_loss),
        "gradient_inf_norm": float(np.max(np.abs(final_grad))),
        "initial_beta": "all_zeros",
        "l2": L2,
        "max_iter": MAX_ITER,
        "maxcor": MAXCOR,
        "gtol": GTOL,
        "message": str(result.message),
        "method": "L-BFGS-B",
        "nfev": int(result.nfev),
        "nit": int(result.nit),
        "njev": int(getattr(result, "njev", result.nfev)),
        "success": bool(result.success),
        "train_cross_entropy": stats["cross_entropy"],
        "train_selected_probability_mean": stats["selected_probability_mean"],
        "train_top1": stats["top1"],
    }


def _action_band(count: int) -> str:
    if 2 <= count <= 4:
        return "2-4"
    if 5 <= count <= 8:
        return "5-8"
    if 9 <= count <= 16:
        return "9-16"
    raise D3Error("action count outside frozen bands")


def parent_rows(score: np.ndarray, groups: Sequence[Mapping[str, Any]],
                split: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        if group["split"] != split:
            continue
        start = int(group["start"])
        count = int(group["count"])
        selected = int(group["selected_local_action_index"])
        q = score[start:start + count]
        qmax = float(np.max(q))
        ex = np.exp(q - qmax)
        probs = ex / float(np.sum(ex))
        order = np.argsort(-q, kind="stable")
        cell = str(group["cell"])
        rows.append({
            "action_band": _action_band(count),
            "ce": (qmax + math.log(float(np.sum(ex)))) - float(q[selected]),
            "cell": cell,
            "parent_id": int(group["parent_id"]),
            "phase": cell.split("_", 1)[0],
            "selected_probability": float(probs[selected]),
            "stm": int(group["parent_stm"]),
            "top1": int(order[0] == selected),
            "top2": int(selected in order[:2]),
        })
    if len(rows) != SPLITS[split]:
        raise D3Error(f"D3 {split} parent count drift")
    return rows


def _basic(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise D3Error("empty D3 metric cell")
    return {
        "cross_entropy": float(np.mean([float(r["ce"]) for r in rows])),
        "parents": len(rows),
        "selected_probability_mean": float(np.mean([float(r["selected_probability"]) for r in rows])),
        "top1": float(np.mean([int(r["top1"]) for r in rows])),
        "top2": float(np.mean([int(r["top2"]) for r in rows])),
    }


def _paired(control: Sequence[Mapping[str, Any]],
            candidate: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(control) != len(candidate) or not control:
        raise D3Error("paired metric cardinality drift")
    for left, right in zip(control, candidate):
        if int(left["parent_id"]) != int(right["parent_id"]):
            raise D3Error("paired parent identity drift")
    delta = np.asarray(
        [float(left["ce"]) - float(right["ce"]) for left, right in zip(control, candidate)],
        dtype=np.float64,
    )
    return {
        "catastrophic_regression_rate_delta_lt_minus1": float(np.mean(delta < -1.0)),
        "delta_decision_mean": float(np.mean(delta)),
        "delta_decision_median": float(np.median(delta)),
        "delta_decision_q05": float(np.quantile(delta, 0.05, method="linear")),
        "delta_decision_q25": float(np.quantile(delta, 0.25, method="linear")),
        "delta_decision_q75": float(np.quantile(delta, 0.75, method="linear")),
        "delta_decision_q95": float(np.quantile(delta, 0.95, method="linear")),
        "fraction_ce_improved": float(np.mean(delta > 0.0)),
        "large_improvement_rate_delta_gt_plus1": float(np.mean(delta > 1.0)),
        "parents": len(delta),
    }


def _grouped(control: Sequence[Mapping[str, Any]],
             candidate: Sequence[Mapping[str, Any]], key: str) -> dict[str, Any]:
    c0: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    c1: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in control:
        c0[str(row[key])].append(row)
    for row in candidate:
        c1[str(row[key])].append(row)
    if c0.keys() != c1.keys():
        raise D3Error(f"group key drift for {key}")
    return {
        k: {"WDL_CONTROL": _basic(c0[k]), "D3": _basic(c1[k]), "paired": _paired(c0[k], c1[k])}
        for k in sorted(c0)
    }


def split_report(control_score: np.ndarray, candidate_score: np.ndarray,
                 groups: Sequence[Mapping[str, Any]], split: str) -> dict[str, Any]:
    control = parent_rows(control_score, groups, split)
    candidate = parent_rows(candidate_score, groups, split)
    return {
        "WDL_CONTROL": _basic(control),
        "D3": _basic(candidate),
        "paired": _paired(control, candidate),
        "by_phase": _grouped(control, candidate, "phase"),
        "by_stm": _grouped(control, candidate, "stm"),
        "by_action_count": _grouped(control, candidate, "action_band"),
    }


def bootstrap_test(control_score: np.ndarray, candidate_score: np.ndarray,
                   groups: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    control = parent_rows(control_score, groups, "test")
    candidate = parent_rows(candidate_score, groups, "test")
    delta = np.asarray(
        [float(left["ce"]) - float(right["ce"]) for left, right in zip(control, candidate)],
        dtype=np.float64,
    )
    rng = np.random.default_rng(SEED)
    vals = np.empty(BOOTSTRAPS, dtype=np.float64)
    cursor = 0
    batch = 1000
    while cursor < BOOTSTRAPS:
        take = min(batch, BOOTSTRAPS - cursor)
        idx = rng.integers(0, len(delta), size=(take, len(delta)), endpoint=False)
        vals[cursor:cursor + take] = np.mean(delta[idx], axis=1)
        cursor += take
    return {
        "lcb95": float(np.quantile(vals, 0.025, method="linear")),
        "mean": float(np.mean(delta)),
        "replications": BOOTSTRAPS,
        "seed": SEED,
        "ucb95": float(np.quantile(vals, 0.975, method="linear")),
    }


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    parents = read_dataset(args.dataset)
    groups = load_groups(args.groups)
    phi1, meta1 = build_relational_features(parents, groups)
    phi2, meta2 = build_relational_features(parents, groups)
    deterministic = bool(np.array_equal(phi1, phi2) and meta1 == meta2)
    if not deterministic:
        raise D3Error("D3 relational feature replay mismatch")
    base_black = d1readout._predict(args.decision_data, args.decision_feat, args.base_model)
    base_parent = base_parent_scores(base_black, groups)
    zero_score = base_parent + phi1 @ np.zeros(WIDTH, dtype=np.float64)
    zero_identity = bool(np.array_equal(zero_score, base_parent))
    if not zero_identity:
        raise D3Error("D3 beta=0 base identity failed")
    result = {
        "actions": ACTIONS,
        "base_model_sha256": sha_file(args.base_model),
        "beta_zero_base_identity": zero_identity,
        "feature": {**meta1, "deterministic": deterministic},
        "fits": 0,
        "model_searches": 0,
        "parents": PARENTS,
        "schema": PREFLIGHT_SCHEMA,
        "splits": SPLITS,
        "strength_games": 0,
        "test_metrics_read": 0,
        "valid_metrics_read": 0,
        "forbidden_reads": {
            "full_ladder_1843": 0,
            "qscore": 0,
            "search_decision_trace": 0,
            "wdl_targets": 0,
        },
        "verdict": PREFLIGHT_VERDICT,
    }
    _write_json_new(args.out, result)
    return result


def fit_and_readout(args: argparse.Namespace) -> dict[str, Any]:
    pf = _read_json(args.preflight)
    if (pf.get("schema") != PREFLIGHT_SCHEMA or pf.get("verdict") != PREFLIGHT_VERDICT
            or pf.get("fits") != 0 or pf.get("valid_metrics_read") != 0
            or pf.get("test_metrics_read") != 0):
        raise D3Error("D3 preflight contract drift")
    value_before = sha_file(args.base_model)
    if pf.get("base_model_sha256") != value_before:
        raise D3Error("D3 base model SHA differs from preflight")

    parents = read_dataset(args.dataset)
    groups = load_groups(args.groups)
    phi, feature_meta = build_relational_features(parents, groups)
    if feature_meta.get("feature_sha256_float64_c") != pf.get("feature", {}).get("feature_sha256_float64_c"):
        raise D3Error("D3 feature hash differs from preflight")
    base_black = d1readout._predict(args.decision_data, args.decision_feat, args.base_model)
    base_parent = base_parent_scores(base_black, groups)
    if not np.array_equal(base_parent + phi @ np.zeros(WIDTH, dtype=np.float64), base_parent):
        raise D3Error("D3 beta=0 identity drift at fit")

    beta, optimizer = fit_beta(phi, base_parent, groups)
    if not optimizer["success"]:
        raise D3Error(f"D3 optimizer failed: {optimizer['message']}")
    adapter_desc = _write_adapter_new(args.adapter, beta)
    sealed = np.load(args.adapter, allow_pickle=False)
    candidate_score = base_parent + phi @ sealed
    value_after = sha_file(args.base_model)
    if value_before != value_after:
        raise D3Error("D3 value model byte drift")

    train = split_report(base_parent, candidate_score, groups, "train")
    valid = split_report(base_parent, candidate_score, groups, "valid")
    test = split_report(base_parent, candidate_score, groups, "test")
    boot = bootstrap_test(base_parent, candidate_score, groups)
    phase_pass = all(float(v["paired"]["delta_decision_mean"]) > 0.0 for v in test["by_phase"].values())
    stm_pass = all(float(v["paired"]["delta_decision_mean"]) > 0.0 for v in test["by_stm"].values())
    support = bool(
        optimizer["success"]
        and adapter_desc["width"] == WIDTH
        and pf.get("feature", {}).get("deterministic") is True
        and pf.get("beta_zero_base_identity") is True
        and value_before == value_after
        and all(int(x) == 0 for x in pf.get("forbidden_reads", {}).values())
    )
    established = bool(
        support
        and float(valid["paired"]["delta_decision_mean"]) > 0.0
        and float(boot["lcb95"]) > 0.0
        and float(test["D3"]["top1"]) >= float(test["WDL_CONTROL"]["top1"])
        and phase_pass
        and stm_pass
    )
    verdict = VERDICT_PASS if established else VERDICT_FAIL
    fit_report = {
        "adapter": adapter_desc,
        "feature": feature_meta,
        "forbidden_reads": {
            "full_ladder_1843": 0,
            "qscore": 0,
            "search_decision_trace": 0,
            "wdl_targets": 0,
        },
        "model_searches": 0,
        "optimizer": optimizer,
        "schema": FIT_SCHEMA,
        "teacher_searches": 0,
        "value_model_after_sha256": value_after,
        "value_model_before_sha256": value_before,
    }
    _write_json_new(args.fit_report, fit_report)
    publication = {
        "adapter": adapter_desc,
        "bake_authorized": False,
        "bootstrap": boot,
        "decision": {"train": train, "valid": valid, "test": test},
        "equal_node_authorized": False,
        "equal_time_authorized": False,
        "feature": feature_meta,
        "fits": 1,
        "gates": {
            "phase_all_positive": phase_pass,
            "stm_both_positive": stm_pass,
            "support": support,
            "test_bootstrap_lcb_positive": float(boot["lcb95"]) > 0.0,
            "test_top1_noninferior": float(test["D3"]["top1"]) >= float(test["WDL_CONTROL"]["top1"]),
            "valid_delta_positive": float(valid["paired"]["delta_decision_mean"]) > 0.0,
        },
        "model_searches": 0,
        "next_stage": "D3_RUNTIME_MOVE_ORDERING_PREREGISTRATION" if established else "STOP",
        "optimizer": optimizer,
        "promotion_authorized": False,
        "schema": READOUT_SCHEMA,
        "state": "completed",
        "strength_games": 0,
        "teacher_searches": 0,
        "value_model_after_sha256": value_after,
        "value_model_before_sha256": value_before,
        "verdict": verdict,
    }
    _write_json_new(args.out, publication)
    return publication


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preflight")
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--groups", type=Path, required=True)
    p.add_argument("--decision-data", type=Path, required=True)
    p.add_argument("--decision-feat", type=Path, required=True)
    p.add_argument("--base-model", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    f = sub.add_parser("fit")
    f.add_argument("--preflight", type=Path, required=True)
    f.add_argument("--dataset", type=Path, required=True)
    f.add_argument("--groups", type=Path, required=True)
    f.add_argument("--decision-data", type=Path, required=True)
    f.add_argument("--decision-feat", type=Path, required=True)
    f.add_argument("--base-model", type=Path, required=True)
    f.add_argument("--adapter", type=Path, required=True)
    f.add_argument("--fit-report", type=Path, required=True)
    f.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            result = preflight(args)
        else:
            result = fit_and_readout(args)
    except (D3Error, OSError, ValueError, MemoryError) as exc:
        print(f"{VERDICT_INVALID}: {exc}", file=sys.stderr)
        return 2
    print(result["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
