#!/usr/bin/env python3
"""Frozen D2 separate-policy adapter preflight, fit, and terminal readout.

D2 leaves the authenticated D1 WDL_CONTROL value model byte-identical.  The
only trainable object is one 240-parameter float64 linear ranker over the
existing 120 production extras split by the production tempo MG/EG weights.
No WDL fit, target score, value/policy blend, runtime scale, search, strength
game, promotion, or bake is implemented here.
"""
from __future__ import annotations

import argparse
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
TOOLS = ROOT / "pattern_jass" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import patterns  # noqa: E402
import train  # noqa: E402
import train_stream as ts  # noqa: E402
from jobs.tools import d1_listwise_fit as dfit  # noqa: E402
from jobs.tools import d1_postfit_readout as d1readout  # noqa: E402

PREFLIGHT_SCHEMA = "jass.d2.policy_adapter_preflight.v1"
FIT_SCHEMA = "jass.d2.policy_adapter_fit.v1"
READOUT_SCHEMA = "jass.d2.policy_transfer_readout.v1"
PREFLIGHT_VERDICT = "D2_POLICY_ADAPTER_PREFLIGHT_COMPLETE_V1"
VERDICT_PASS = "D2_POLICY_TRANSFER_ESTABLISHED_V1"
VERDICT_FAIL = "D2_POLICY_TRANSFER_NOT_ESTABLISHED_V1"
VERDICT_INVALID = "D2_POLICY_TRANSFER_INVALID_V1"

PARENTS = 4_000
ACTIONS = 38_053
SPLITS = {"train": 3_200, "valid": 400, "test": 400}
EXTRAS = 120
WIDTH = 240
L2 = 1e-3
MAX_ITER = 500
MAXCOR = 10
GTOL = 1e-6
BOOTSTRAPS = 200_000
SEED = 2026111001
CELL_RE = re.compile(r"^P([0-3])_stm([01])$")


class D2Error(RuntimeError):
    pass


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _write_json_new(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise D2Error(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        raise D2Error(f"refusing existing temporary {tmp}")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _write_adapter_new(path: Path, beta: np.ndarray) -> dict[str, Any]:
    if path.suffix != ".npy":
        raise D2Error("adapter output must be an .npy file")
    if path.exists() or path.is_symlink():
        raise D2Error(f"refusing existing adapter {path}")
    if beta.dtype != np.dtype(np.float64) or beta.shape != (WIDTH,) or not np.all(np.isfinite(beta)):
        raise D2Error("adapter must be finite float64 width 240")
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
        raise D2Error("adapter serialization round-trip drift")
    return {
        "dtype": "float64",
        "format": "npy",
        "sha256": sha_file(path),
        "size_bytes": path.stat().st_size,
        "width": WIDTH,
    }


def load_groups(path: Path) -> list[dict[str, Any]]:
    groups, _ = dfit.load_groups(path)
    counts = {name: 0 for name in SPLITS}
    cells = {f"P{phase}_stm{stm}": 0 for phase in range(4) for stm in range(2)}
    for group in groups:
        split = str(group["split"])
        counts[split] += 1
        cell = group.get("cell")
        match = CELL_RE.fullmatch(cell) if isinstance(cell, str) else None
        if match is None:
            raise D2Error(f"invalid D2 phase/stm cell: {cell!r}")
        if int(match.group(2)) != int(group["parent_stm"]):
            raise D2Error("cell STM and parent_stm drift")
        cells[cell] += 1
    if counts != SPLITS:
        raise D2Error(f"D2 split count drift: {counts}")
    if any(value <= 0 for value in cells.values()):
        raise D2Error(f"D2 requires all eight phase/stm cells: {cells}")
    return groups


def _action_band(count: int) -> str:
    if 2 <= count <= 4:
        return "2-4"
    if 5 <= count <= 8:
        return "5-8"
    if 9 <= count <= 16:
        return "9-16"
    raise D2Error(f"action count outside frozen bands: {count}")


def build_phi_from_arrays(extras: np.ndarray, wmg: np.ndarray, weg: np.ndarray) -> tuple[np.ndarray, bool]:
    extras64 = np.asarray(extras, dtype=np.float64)
    wmg64 = np.asarray(wmg, dtype=np.float64)
    weg64 = np.asarray(weg, dtype=np.float64)
    if extras64.ndim != 2 or extras64.shape[1] != EXTRAS:
        raise D2Error(f"D2 requires exactly {EXTRAS} production extras")
    if wmg64.shape != (extras64.shape[0],) or weg64.shape != (extras64.shape[0],):
        raise D2Error("tempo vector shape drift")
    if not np.array_equal(weg64, 1.0 - wmg64):
        raise D2Error("tempo MG/EG complement drift")

    # Production build_extras_phased casts the raw extras and each phase weight
    # to float32 before multiplication. Replay that boundary operation exactly,
    # prove the manual 120xMG + 120xEG construction is byte-identical, then
    # promote those exact production values to float64 for the frozen optimizer.
    production32 = np.asarray(
        train.build_extras_phased(extras64, wmg64, weg64).toarray(),
        dtype=np.float32,
    )
    ex32 = extras64.astype(np.float32, copy=False)
    wmg32 = wmg64.astype(np.float32)
    weg32 = weg64.astype(np.float32)
    manual32 = np.hstack([
        ex32 * wmg32[:, None],
        ex32 * weg32[:, None],
    ]).astype(np.float32, copy=False)
    replay_equal = bool(np.array_equal(production32, manual32))
    if production32.shape != (extras64.shape[0], WIDTH) or not replay_equal:
        raise D2Error("production build_extras_phased replay mismatch")
    phi = production32.astype(np.float64)
    return phi, replay_equal


def build_policy_features(data: Path, feat_path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    mm, n = ts.open_jnnw(str(data))
    feat, k = ts.open_feat(str(feat_path), n)
    if n != ACTIONS or k != EXTRAS:
        raise D2Error(f"D2 feature cardinality drift records={n} extras={k}")
    wm = np.ascontiguousarray(mm["wm"])
    bm = np.ascontiguousarray(mm["bm"])
    wmg = ts._tempo_wmg_bb(wm, bm).astype(np.float64)
    weg = 1.0 - wmg
    phi, replay_equal = build_phi_from_arrays(np.asarray(feat, dtype=np.float64), wmg, weg)
    contiguous = np.ascontiguousarray(phi)
    return phi, {
        "actions": ACTIONS,
        "extras": EXTRAS,
        "feature_replay_equality": replay_equal,
        "phi_sha256_float64_c": hashlib.sha256(contiguous.tobytes(order="C")).hexdigest(),
        "tempo_stage": True,
        "width": WIDTH,
    }


def listwise_loss_grad(beta: np.ndarray, phi: np.ndarray,
                       groups: Sequence[Mapping[str, Any]]) -> tuple[float, np.ndarray, dict[str, float]]:
    if beta.shape != (phi.shape[1],):
        raise D2Error("beta/phi width mismatch")
    if not groups:
        raise D2Error("empty D2 parent group set")
    z_black = np.asarray(phi @ beta, dtype=np.float64).ravel()
    residual = np.zeros(phi.shape[0], dtype=np.float64)
    total = 0.0
    psel = 0.0
    top1 = 0
    for group in groups:
        start = int(group["start"])
        count = int(group["count"])
        selected = int(group["selected_local_action_index"])
        pov = 1.0 if int(group["parent_stm"]) == 1 else -1.0
        q = pov * z_black[start:start + count]
        qmax = float(np.max(q))
        ex = np.exp(q - qmax)
        denom = float(np.sum(ex))
        probs = ex / denom
        total += (qmax + math.log(denom)) - float(q[selected])
        psel += float(probs[selected])
        top1 += int(int(np.argmax(q)) == selected)
        r = probs.copy()
        r[selected] -= 1.0
        residual[start:start + count] = pov * r
    n = len(groups)
    grad = np.asarray(phi.T @ residual, dtype=np.float64).ravel() / n
    return total / n, grad, {
        "parents": float(n),
        "selected_probability_mean": psel / n,
        "top1": top1 / n,
    }


def _objective(beta: np.ndarray, phi: np.ndarray,
               groups: Sequence[Mapping[str, Any]]) -> tuple[float, np.ndarray]:
    ce, grad, _ = listwise_loss_grad(beta, phi, groups)
    reg = 0.5 * L2 * float(np.dot(beta, beta))
    return ce + reg, grad + L2 * beta


def fit_adapter(phi: np.ndarray, groups: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, dict[str, Any]]:
    train_groups = [group for group in groups if group["split"] == "train"]
    if len(train_groups) != SPLITS["train"]:
        raise D2Error("D2 train parent count drift")
    initial = np.zeros(WIDTH, dtype=np.float64)
    result = minimize(
        _objective,
        initial,
        args=(phi, train_groups),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": MAX_ITER, "maxcor": MAXCOR, "gtol": GTOL},
    )
    beta = np.asarray(result.x, dtype=np.float64)
    final_ce, final_grad, stats = listwise_loss_grad(beta, phi, train_groups)
    return beta, {
        "fit_count": 1,
        "final_policy_cross_entropy": final_ce,
        "gradient_inf_norm": float(np.max(np.abs(final_grad + L2 * beta))),
        "initial_beta": "all_zeros",
        "l2": L2,
        "max_iter": MAX_ITER,
        "maxcor": MAXCOR,
        "gtol": GTOL,
        "message": str(result.message),
        "method": "L-BFGS-B",
        "nit": int(result.nit),
        "nfev": int(result.nfev),
        "njev": int(getattr(result, "njev", result.nfev)),
        "selected_probability_mean": stats["selected_probability_mean"],
        "success": bool(result.success),
        "top1": stats["top1"],
    }


def _parent_rows(z_black: np.ndarray, groups: Sequence[Mapping[str, Any]], split: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in groups:
        if group["split"] != split:
            continue
        start = int(group["start"])
        count = int(group["count"])
        selected = int(group["selected_local_action_index"])
        stm = int(group["parent_stm"])
        pov = 1.0 if stm == 1 else -1.0
        q = pov * z_black[start:start + count]
        qmax = float(np.max(q))
        ex = np.exp(q - qmax)
        probs = ex / float(np.sum(ex))
        order = np.argsort(-q, kind="stable")
        cell = str(group["cell"])
        phase = cell.split("_", 1)[0]
        rows.append({
            "action_band": _action_band(count),
            "cell": cell,
            "ce": (qmax + math.log(float(np.sum(ex)))) - float(q[selected]),
            "count": count,
            "parent_id": int(group["parent_id"]),
            "phase": phase,
            "selected_probability": float(probs[selected]),
            "stm": stm,
            "top1": int(order[0] == selected),
            "top2": int(selected in order[:2]),
        })
    if len(rows) != SPLITS[split]:
        raise D2Error(f"D2 split {split} parent count drift: {len(rows)}")
    return rows


def _basic(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise D2Error("empty metric cell")
    ce = np.asarray([float(row["ce"]) for row in rows], dtype=np.float64)
    return {
        "cross_entropy": float(np.mean(ce)),
        "parents": len(rows),
        "selected_probability_mean": float(np.mean([float(row["selected_probability"]) for row in rows])),
        "top1": float(np.mean([int(row["top1"]) for row in rows])),
        "top2": float(np.mean([int(row["top2"]) for row in rows])),
    }


def _paired(control_rows: Sequence[Mapping[str, Any]], adapter_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(control_rows) != len(adapter_rows) or not control_rows:
        raise D2Error("paired metric cardinality drift")
    for left, right in zip(control_rows, adapter_rows):
        if int(left["parent_id"]) != int(right["parent_id"]):
            raise D2Error("paired parent ordering drift")
    delta = np.asarray(
        [float(left["ce"]) - float(right["ce"]) for left, right in zip(control_rows, adapter_rows)],
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
        "parents": int(delta.size),
    }


def _subset(rows: Sequence[Mapping[str, Any]], key: str, value: object) -> list[Mapping[str, Any]]:
    return [row for row in rows if row[key] == value]


def split_metrics(control_z: np.ndarray, adapter_z: np.ndarray,
                  groups: Sequence[Mapping[str, Any]], split: str) -> tuple[dict[str, Any], np.ndarray]:
    control = _parent_rows(control_z, groups, split)
    adapter = _parent_rows(adapter_z, groups, split)
    delta = np.asarray(
        [float(left["ce"]) - float(right["ce"]) for left, right in zip(control, adapter)],
        dtype=np.float64,
    )

    def grouped(key: str, values: Sequence[object]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for value in values:
            c = _subset(control, key, value)
            a = _subset(adapter, key, value)
            if not c or not a:
                raise D2Error(f"empty mandatory diagnostic {key}={value}")
            out[str(value)] = {
                "D2_POLICY_ADAPTER": _basic(a),
                "WDL_CONTROL": _basic(c),
                "paired": _paired(c, a),
            }
        return out

    cells = [f"P{phase}_stm{stm}" for phase in range(4) for stm in range(2)]
    publication = {
        "D2_POLICY_ADAPTER": _basic(adapter),
        "WDL_CONTROL": _basic(control),
        "by_action_count": grouped("action_band", ["2-4", "5-8", "9-16"]),
        "by_cell": grouped("cell", cells),
        "by_phase": grouped("phase", ["P0", "P1", "P2", "P3"]),
        "by_stm": grouped("stm", [0, 1]),
        "paired": _paired(control, adapter),
    }
    return publication, delta


def bootstrap_delta(delta: np.ndarray) -> dict[str, Any]:
    delta = np.asarray(delta, dtype=np.float64)
    if delta.shape != (SPLITS["test"],):
        raise D2Error(f"D2 test bootstrap requires 400 parents, got {delta.shape}")
    rng = np.random.default_rng(SEED)
    values = np.empty(BOOTSTRAPS, dtype=np.float64)
    cursor = 0
    batch = 1_000
    while cursor < BOOTSTRAPS:
        take = min(batch, BOOTSTRAPS - cursor)
        idx = rng.integers(0, delta.size, size=(take, delta.size), endpoint=False)
        values[cursor:cursor + take] = np.mean(delta[idx], axis=1)
        cursor += take
    return {
        "lcb95": float(np.quantile(values, 0.025, method="linear")),
        "mean": float(np.mean(delta)),
        "replications": BOOTSTRAPS,
        "seed": SEED,
        "ucb95": float(np.quantile(values, 0.975, method="linear")),
    }


def _open_control_layout(path: Path) -> dict[str, Any]:
    weights, scale, n_pat, n_ext = train.load_v3_weights_float(str(path))
    if scale != dfit.SCALE:
        raise D2Error(f"WDL_CONTROL scale drift: {scale}")
    if n_pat != patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN:
        raise D2Error("WDL_CONTROL pattern layout drift")
    if n_ext != EXTRAS:
        raise D2Error(f"WDL_CONTROL extras drift: {n_ext}")
    return {
        "extras": int(n_ext),
        "pattern_weights_per_phase": int(n_pat),
        "scale": int(scale),
        "weights": int(np.asarray(weights).size),
    }


def _preflight_contract(phi_report: Mapping[str, Any], control_sha: str,
                        control_layout: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "adapter_width": WIDTH,
        "bootstrap_replications": BOOTSTRAPS,
        "bootstrap_seed": SEED,
        "control_model_sha256": control_sha,
        "feature_replay_equality": bool(phi_report["feature_replay_equality"]),
        "gtol": GTOL,
        "l2": L2,
        "max_iter": MAX_ITER,
        "maxcor": MAXCOR,
        "optimizer": "L-BFGS-B",
        "phi_sha256_float64_c": str(phi_report["phi_sha256_float64_c"]),
        "production_extras": EXTRAS,
        "value_layout": dict(control_layout),
    }


def run_preflight(args: argparse.Namespace) -> dict[str, Any]:
    groups = load_groups(args.decision_groups)
    phi, phi_report = build_policy_features(args.decision_data, args.decision_feat)
    if phi.shape != (ACTIONS, WIDTH):
        raise D2Error("D2 phi shape drift")
    control_sha = sha_file(args.control_model)
    layout = _open_control_layout(args.control_model)
    publication = {
        "contract": _preflight_contract(phi_report, control_sha, layout),
        "data": {"actions": ACTIONS, "parents": PARENTS, "split_parents": SPLITS},
        "fits": 0,
        "forbidden_fit_inputs_read": 0,
        "hyperparameter_sweeps": 0,
        "model_searches": 0,
        "new_teacher_searches": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
        "runtime_experiment_authorized": False,
        "schema": PREFLIGHT_SCHEMA,
        "state": "completed",
        "strength_games": 0,
        "test_metrics_read": 0,
        "valid_metrics_read": 0,
        "verdict": PREFLIGHT_VERDICT,
    }
    _write_json_new(args.out, publication)
    return publication


def _load_preflight(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise D2Error(f"cannot read D2 preflight: {exc}") from exc
    if type(value) is not dict or value.get("schema") != PREFLIGHT_SCHEMA \
            or value.get("verdict") != PREFLIGHT_VERDICT or value.get("fits") != 0:
        raise D2Error("D2 preflight contract drift")
    contract = value.get("contract")
    if not isinstance(contract, Mapping):
        raise D2Error("D2 preflight contract missing")
    expected = {
        "adapter_width": WIDTH,
        "bootstrap_replications": BOOTSTRAPS,
        "bootstrap_seed": SEED,
        "gtol": GTOL,
        "l2": L2,
        "max_iter": MAX_ITER,
        "maxcor": MAXCOR,
        "optimizer": "L-BFGS-B",
        "production_extras": EXTRAS,
    }
    for key, item in expected.items():
        if contract.get(key) != item:
            raise D2Error(f"D2 preflight frozen field drift: {key}")
    return value


def run_fit(args: argparse.Namespace) -> dict[str, Any]:
    preflight = _load_preflight(args.preflight)
    groups = load_groups(args.decision_groups)
    phi, phi_report = build_policy_features(args.decision_data, args.decision_feat)
    control_before = sha_file(args.control_model)
    layout = _open_control_layout(args.control_model)
    pre_contract = preflight["contract"]
    if pre_contract.get("control_model_sha256") != control_before:
        raise D2Error("WDL_CONTROL bytes differ from authenticated preflight")
    if pre_contract.get("phi_sha256_float64_c") != phi_report["phi_sha256_float64_c"]:
        raise D2Error("D2 production feature replay differs from preflight")

    beta, optimizer = fit_adapter(phi, groups)
    adapter_artifact = _write_adapter_new(args.adapter_out, beta)
    beta_sealed = np.load(args.adapter_out, allow_pickle=False)
    adapter_z = np.asarray(phi @ beta_sealed, dtype=np.float64).ravel()
    control_z = d1readout._predict(args.decision_data, args.decision_feat, args.control_model)

    train_metrics, _ = split_metrics(control_z, adapter_z, groups, "train")
    valid_metrics, _ = split_metrics(control_z, adapter_z, groups, "valid")
    test_metrics, test_delta = split_metrics(control_z, adapter_z, groups, "test")
    boot = bootstrap_delta(test_delta)
    control_after = sha_file(args.control_model)

    support = {
        "adapter_fit_count_eq_1": optimizer["fit_count"] == 1,
        "exact_dataset_counts": len(groups) == PARENTS and phi.shape == (ACTIONS, WIDTH),
        "feature_replay_equality": bool(phi_report["feature_replay_equality"]),
        "forbidden_fit_inputs_read_eq_0": True,
        "hyperparameter_sweeps_eq_0": True,
        "model_searches_eq_0": True,
        "new_teacher_searches_eq_0": True,
        "optimizer_success": bool(optimizer["success"]),
        "value_model_byte_drift_eq_0": control_before == control_after,
    }
    support_pass = all(support.values())

    transfer = {
        "test_bootstrap_lcb95_delta_gt_0": boot["lcb95"] > 0.0,
        "test_each_phase_delta_gt_0": all(
            test_metrics["by_phase"][phase]["paired"]["delta_decision_mean"] > 0.0
            for phase in ("P0", "P1", "P2", "P3")
        ),
        "test_each_stm_delta_gt_0": all(
            test_metrics["by_stm"][str(stm)]["paired"]["delta_decision_mean"] > 0.0
            for stm in (0, 1)
        ),
        "test_point_delta_gt_0": test_metrics["paired"]["delta_decision_mean"] > 0.0,
        "test_top1_adapter_ge_control": (
            test_metrics["D2_POLICY_ADAPTER"]["top1"] >= test_metrics["WDL_CONTROL"]["top1"]
        ),
        "valid_point_delta_gt_0": valid_metrics["paired"]["delta_decision_mean"] > 0.0,
    }
    transfer_pass = support_pass and all(transfer.values())
    if not support_pass:
        verdict = VERDICT_INVALID
    elif transfer_pass:
        verdict = VERDICT_PASS
    else:
        verdict = VERDICT_FAIL

    fit_report = {
        "adapter": adapter_artifact,
        "adapter_stats": {
            "l2_norm": float(np.linalg.norm(beta_sealed)),
            "max_abs": float(np.max(np.abs(beta_sealed))),
            "nonzero_count": int(np.count_nonzero(beta_sealed)),
        },
        "contract": _preflight_contract(phi_report, control_before, layout),
        "forbidden_fit_inputs_read": 0,
        "hyperparameter_sweeps": 0,
        "model_searches": 0,
        "new_teacher_searches": 0,
        "optimizer": optimizer,
        "schema": FIT_SCHEMA,
        "value_model_after_sha256": control_after,
        "value_model_before_sha256": control_before,
    }
    _write_json_new(args.fit_report, fit_report)

    publication = {
        "adapter": adapter_artifact,
        "bake_authorized": False,
        "bootstrap": boot,
        "decision": {
            "test": test_metrics,
            "train": train_metrics,
            "valid": valid_metrics,
        },
        "equal_node_authorized": False,
        "equal_time_authorized": False,
        "fits": 1,
        "forbidden_fit_inputs_read": 0,
        "gates": {"support": support, "support_pass": support_pass, "transfer": transfer, "transfer_pass": transfer_pass},
        "hyperparameter_sweeps": 0,
        "model_searches": 0,
        "new_teacher_searches": 0,
        "next_stage": "D2_RUNTIME_MOVE_ORDERING_PREREGISTRATION_ONLY" if verdict == VERDICT_PASS else "STOP",
        "optimizer": optimizer,
        "promotion_authorized": False,
        "runtime_preregistration_authorized": verdict == VERDICT_PASS,
        "schema": READOUT_SCHEMA,
        "state": "completed",
        "strength_games": 0,
        "value_model_after_sha256": control_after,
        "value_model_before_sha256": control_before,
        "verdict": verdict,
    }
    _write_json_new(args.out, publication)
    return publication


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    pre = sub.add_parser("preflight", help="Authenticate D2 inputs and production feature replay; zero fits")
    pre.add_argument("--decision-data", type=Path, required=True)
    pre.add_argument("--decision-feat", type=Path, required=True)
    pre.add_argument("--decision-groups", type=Path, required=True)
    pre.add_argument("--control-model", type=Path, required=True)
    pre.add_argument("--out", type=Path, required=True)

    fit = sub.add_parser("fit", help="Run the single frozen D2 fit and terminal readout")
    fit.add_argument("--decision-data", type=Path, required=True)
    fit.add_argument("--decision-feat", type=Path, required=True)
    fit.add_argument("--decision-groups", type=Path, required=True)
    fit.add_argument("--control-model", type=Path, required=True)
    fit.add_argument("--preflight", type=Path, required=True)
    fit.add_argument("--adapter-out", type=Path, required=True)
    fit.add_argument("--fit-report", type=Path, required=True)
    fit.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        result = run_preflight(args) if args.command == "preflight" else run_fit(args)
    except Exception as exc:
        print(f"d2_policy_adapter: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"state": result["state"], "verdict": result["verdict"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
