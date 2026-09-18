#!/usr/bin/env python3
"""Frozen CLS-L V1 LOCAL/WDL/MIXED three-arm fitter.

This is the execution harness authorized by
L3_CLS_L_OBJECTIVE_ATTRIBUTION_V1_20260916 after a green source/normalization
preflight.  It varies exactly one factor, the learning objective.  Source rows,
train/holdout split, 8cf exact-fold tempo representation, CURRICULUM parent,
L2, optimizer controls, pruning and serialization are common to all arms.

The harness never runs search, games, confirmation targets, promotion or bake.
Holdout readouts are descriptive only and never select an arm.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "pattern_jass" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import cls_l_objective as objective  # noqa: E402
import train  # noqa: E402
import train_stream as stream  # noqa: E402

SCHEMA = "jass.cls_l_three_arm_fit.v1"
TERMINAL = "CLS_L_THREE_ARM_FITS_READY_V1"
RECOVERY_TERMINAL = "CLS_L_VALID_ARMS_RECOVERED_V1"
ARMS = ("LOCAL", "WDL", "MIXED")
RECOVERY_ARMS = ("LOCAL", "WDL")
RECOVERY_2038_JOB = "cpx62-2038-l3-cls-l-three-arm-fit-rehearsal-v2"
RECOVERY_2038_ATTEMPT = "20260917T201315Z-d29e2c49"
RECOVERY_2040_TERMINAL = "CLS_L_2038_FIT_LOG_DIAGNOSTIC_COMPLETE_V1"
RECOVERY_2038_ERROR = (
    "FitError: MIXED optimizer failure status=1 "
    "message=STOP: TOTAL NO. OF ITERATIONS REACHED LIMIT"
)
RECORDS = 2_000_000
TRAIN_RECORDS = 1_800_796
HOLDOUT_RECORDS = 199_204
EXTRAS = 120
CHUNK = 20_000
L2 = 1e-5
MAX_ITER = 2_000
MAXCOR = 20
GTOL = 1e-4
FOLD = "exact"
PRUNE_MIN_VISITS = 1
SCALE = 1000
EXPECTED_PARENT_SHA256 = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
EXPECTED_NORMALIZATION_TERMINAL = "CLS_L_SOURCE_NORMALIZATION_PREFLIGHT_READY_V1"


class FitError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    if path.exists() or path.is_symlink():
        raise FitError(f"no-clobber:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FitError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FitError(f"JSON object required: {path}")
    return value


def validate_local_targets(path: Path, records: int) -> np.ndarray:
    try:
        values = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise FitError(f"local_target_load:{exc}") from exc
    if not isinstance(values, np.ndarray) or values.shape != (records,):
        raise FitError(f"local_target_shape:{getattr(values, 'shape', None)}")
    if values.dtype != np.dtype(np.float32):
        raise FitError(f"local_target_dtype:{values.dtype}")
    for start in range(0, records, CHUNK):
        block = np.asarray(values[start:start + CHUNK])
        if not bool(np.all(np.isfinite(block))):
            raise FitError("local_target_nonfinite")
        if bool(np.any(block < 0.0)) or bool(np.any(block > 1.0)):
            raise FitError("local_target_range")
    return values


def wdl_black_probability(wdl: np.ndarray, stm: np.ndarray) -> np.ndarray:
    w = np.asarray(wdl, dtype=np.float64)
    s = np.asarray(stm)
    if w.shape != s.shape:
        raise FitError("wdl_stm_shape")
    black = np.where(s == 1, w, -w)
    return (black + 1.0) * 0.5


def coordinate_identity(keep: np.ndarray, pat_n: int, n_cols: int) -> str:
    h = hashlib.sha256()
    h.update(np.asarray(keep, dtype="<i8").tobytes())
    h.update(f"{FOLD}|{pat_n}|{EXTRAS}|{n_cols}|tempo|prune1".encode())
    return h.hexdigest()


def validate_normalization_receipt(
    receipt: dict[str, Any], *, data_sha: str, feat_sha: str,
    local_sha: str, parent_sha: str, coordinate_sha: str,
    pat_n: int, n_cols: int,
) -> dict[str, float]:
    if receipt.get("terminal") != EXPECTED_NORMALIZATION_TERMINAL or receipt.get("state") != "completed":
        raise FitError("normalization receipt terminal/state drift")
    if receipt.get("records") != RECORDS or receipt.get("train_records") != TRAIN_RECORDS \
            or receipt.get("holdout_records") != HOLDOUT_RECORDS:
        raise FitError("normalization receipt cardinality drift")
    if receipt.get("normalization_scope") != "TRAIN_ONLY" \
            or receipt.get("holdout_rows_used_for_normalization") != 0 \
            or receipt.get("normalization_point") != "projected_CURRICULUM_w0":
        raise FitError("normalization scope drift")
    if receipt.get("lambda_normalized_gradient") != objective.FROZEN_LAMBDA:
        raise FitError("normalization lambda drift")
    if receipt.get("fits") != 0 or receipt.get("strength_games") != 0 \
            or receipt.get("confirmation_target_reads") != 0:
        raise FitError("normalization receipt side-effect drift")
    common = receipt.get("common_recipe")
    if not isinstance(common, dict):
        raise FitError("normalization common recipe missing")
    expected_common = {
        "fold": FOLD,
        "tempo_stage": True,
        "extras": EXTRAS,
        "prune_min_visits": PRUNE_MIN_VISITS,
        "l2": L2,
        "chunk": CHUNK,
        "parent_scale": SCALE,
        "pattern_slots": pat_n,
        "trainable_coordinates": n_cols,
        "coordinate_identity_sha256": coordinate_sha,
    }
    for key, expected in expected_common.items():
        if common.get(key) != expected:
            raise FitError(f"normalization common recipe drift:{key}")
    inputs = receipt.get("inputs")
    if not isinstance(inputs, dict) or inputs != {
        "data_sha256": data_sha,
        "feat_sha256": feat_sha,
        "local_targets_sha256": local_sha,
        "parent_sha256": parent_sha,
    }:
        raise FitError("normalization input identity drift")
    norms = receipt.get("gradient_norms")
    if not isinstance(norms, dict) or set(norms) != {"LOCAL", "WDL"}:
        raise FitError("normalization norms drift")
    out: dict[str, float] = {}
    for name in ("LOCAL", "WDL"):
        value = norms.get(name)
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0.0:
            raise FitError(f"invalid frozen {name} gradient norm")
        out[name] = float(value)
    return out


def validate_recovery_2038_summary(path: Path) -> dict[str, Any]:
    summary = load_json(path)
    required = {
        "terminal": RECOVERY_2040_TERMINAL,
        "state": "completed",
        "classification": "TECHNICAL_DIAGNOSTIC",
        "scientific_verdict": None,
        "failed_job_id": RECOVERY_2038_JOB,
        "failed_attempt_id": RECOVERY_2038_ATTEMPT,
        "primary_mechanical_error": RECOVERY_2038_ERROR,
        "target_reads": 0,
        "fits": 0,
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise FitError(f"2038 recovery evidence drift:{key}")
    if summary.get("next_stage") != "REPAIR_PROVEN_2038_FIT_MECHANICS_ONLY":
        raise FitError("2038 recovery next-stage drift")
    return summary


def serialize_weights(
    out: Path, fitted: np.ndarray, folder: Any, remap: np.ndarray,
    pat_n: int, extras_n: int,
) -> None:
    if out.exists() or out.is_symlink():
        raise FitError(f"output exists:{out}")
    tb = folder.TB

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
    pat_mg, pat_eg = stream.expand_pat(folder, canon_mg, canon_eg, SCALE)
    ext_mg = quant(fitted[2 * pat_n:2 * pat_n + extras_n])
    ext_eg = quant(fitted[2 * pat_n + extras_n:2 * pat_n + 2 * extras_n])
    train.write_weights_v3(out, pat_mg, pat_eg, ext_mg, ext_eg, SCALE, king=False)


def run(args: argparse.Namespace) -> dict[str, Any]:
    recovery = (
        validate_recovery_2038_summary(args.recovery_2038_summary)
        if args.recovery_2038_summary is not None else None
    )
    fit_arms = RECOVERY_ARMS if recovery is not None else ARMS
    terminal = RECOVERY_TERMINAL if recovery is not None else TERMINAL
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    mm, records = stream.open_jnnw(str(args.data))
    feat, extras = stream.open_feat(str(args.feat), records)
    if records != RECORDS:
        raise FitError(f"record_count:{records}")
    if extras != EXTRAS:
        raise FitError(f"extras:{extras}")
    local = validate_local_targets(args.local_targets, records)
    parent_sha = sha256(args.parent)
    if parent_sha != EXPECTED_PARENT_SHA256:
        raise FitError("CURRICULUM parent SHA drift")

    folder = stream.Folder(FOLD)
    tb = folder.TB
    counts = np.zeros(tb, dtype=np.int64)
    wmg_all = np.empty(records, dtype=np.float32)
    weg_all = np.empty(records, dtype=np.float32)
    wdl_targets = np.empty(records, dtype=np.float64)
    for start in range(0, records, CHUNK):
        stop = min(start + CHUNK, records)
        rec = mm[start:stop]
        wm = np.ascontiguousarray(rec["wm"])
        bm = np.ascontiguousarray(rec["bm"])
        stm = np.ascontiguousarray(rec["stm"])
        wdl = np.ascontiguousarray(rec["wdl"])
        cols, _signs = folder.cols_signs(bm, wm)
        counts += np.bincount(cols.ravel(), minlength=tb)
        wmg = stream._tempo_wmg_bb(wm, bm)
        wmg_all[start:stop] = np.asarray(wmg, dtype=np.float32)
        weg_all[start:stop] = np.asarray(1.0 - wmg, dtype=np.float32)
        wdl_targets[start:stop] = wdl_black_probability(wdl, stm)

    keep = np.flatnonzero(counts >= PRUNE_MIN_VISITS)
    keep = keep[np.argsort(counts[keep])[::-1]]
    remap = np.zeros(tb, dtype=np.int32)
    remap[keep] = np.arange(1, len(keep) + 1, dtype=np.int32)
    pat_n = len(keep) + 1
    n_cols = 2 * pat_n + 2 * EXTRAS
    parent, parent_scale = stream.project_champion_mean(
        str(args.parent), folder, keep, pat_n, EXTRAS
    )
    if parent_scale != SCALE or parent.shape != (n_cols,):
        raise FitError("CURRICULUM parent projection/scale drift")
    coord_sha = coordinate_identity(keep, pat_n, n_cols)

    data_sha = sha256(args.data)
    feat_sha = sha256(args.feat)
    local_sha = sha256(args.local_targets)
    normalization = load_json(args.normalization_receipt)
    norms = validate_normalization_receipt(
        normalization,
        data_sha=data_sha, feat_sha=feat_sha, local_sha=local_sha,
        parent_sha=parent_sha, coordinate_sha=coord_sha,
        pat_n=pat_n, n_cols=n_cols,
    )

    def build_fn(selected: np.ndarray):
        if len(selected) == 0:
            raise FitError("empty design selection")
        lo = int(selected[0]); hi = int(selected[-1]) + 1
        if hi - lo != len(selected) or int(selected[-1]) != hi - 1:
            raise FitError("noncontiguous design chunk")
        rec = mm[lo:hi]
        wm = np.ascontiguousarray(rec["wm"])
        bm = np.ascontiguousarray(rec["bm"])
        cols, signs = folder.cols_signs(bm, wm)
        cols = remap[cols]
        wmg = wmg_all[lo:hi].astype(np.float64)
        weg = weg_all[lo:hi].astype(np.float64)
        xpat = stream.build_sparse_X_phased(cols, wmg, weg, pat_n, signs)
        extras_block = np.ascontiguousarray(feat[lo:hi]).astype(np.float64)
        xext = stream.build_extras_phased(extras_block, wmg, weg)
        return stream.sp.hstack([xpat, xext], format="csr")

    train_rows = np.arange(TRAIN_RECORDS, dtype=np.int64)
    holdout_rows = np.arange(TRAIN_RECORDS, RECORDS, dtype=np.int64)
    arm_terms = {
        "LOCAL": (objective.DataTerm("LOCAL", local, 1.0, 1.0),),
        "WDL": (objective.DataTerm("WDL", wdl_targets, 1.0, 1.0),),
        "MIXED": objective.mixed_terms(local, wdl_targets, norms),
    }
    arms: dict[str, Any] = {}
    for arm in fit_arms:
        terms = arm_terms[arm]
        evaluations = 0

        def fn(w: np.ndarray):
            nonlocal evaluations
            evaluations += 1
            loss, grad = objective.objective_loss_grad(
                build_fn, train_rows, w, terms, parent=parent, l2=L2, batch=CHUNK
            )
            if evaluations == 1 or evaluations % 10 == 0:
                print(f"arm={arm} eval={evaluations} loss={loss:.10f} grad_inf={float(np.max(np.abs(grad))):.8g}", flush=True)
            return loss, grad

        t0 = time.time()
        result = minimize(
            fn, parent.copy(), jac=True, method="L-BFGS-B",
            options={"maxiter": MAX_ITER, "maxcor": MAXCOR, "gtol": GTOL},
        )
        fitted = np.asarray(result.x, dtype=np.float64)
        if fitted.shape != parent.shape or not bool(np.all(np.isfinite(fitted))):
            raise FitError(f"{arm} optimizer produced invalid weights")
        if not bool(result.success):
            raise FitError(f"{arm} optimizer failure status={result.status} message={result.message}")

        model = out_dir / f"{arm}.pjtw"
        serialize_weights(model, fitted, folder, remap, pat_n, EXTRAS)
        local_holdout, _ = objective.logistic_data_loss_grad(
            build_fn, holdout_rows, local, fitted, batch=CHUNK
        )
        wdl_holdout, _ = objective.logistic_data_loss_grad(
            build_fn, holdout_rows, wdl_targets, fitted, batch=CHUNK
        )
        mixed_holdout = (
            objective.FROZEN_LAMBDA * local_holdout / norms["LOCAL"]
            + (1.0 - objective.FROZEN_LAMBDA) * wdl_holdout / norms["WDL"]
        )
        drift = fitted - parent
        arms[arm] = {
            "arm": arm,
            "model": model.name,
            "model_sha256": sha256(model),
            "model_size_bytes": model.stat().st_size,
            "coordinate_identity_sha256": coord_sha,
            "trainable_coordinates": n_cols,
            "optimizer": {
                "success": bool(result.success),
                "status": int(result.status),
                "message": str(result.message),
                "iterations": int(result.nit),
                "function_evaluations": int(result.nfev),
                "final_objective": float(result.fun),
                "gradient_inf_norm": float(np.max(np.abs(result.jac))),
                "max_iterations": MAX_ITER,
                "maxcor": MAXCOR,
                "gtol": GTOL,
                "elapsed_seconds": time.time() - t0,
            },
            "holdout_descriptive_only": {
                "LOCAL_logistic_loss": float(local_holdout),
                "WDL_logistic_loss": float(wdl_holdout),
                "MIXED_normalized_data_loss": float(mixed_holdout),
                "rms_parameter_drift_from_CURRICULUM": float(np.sqrt(np.mean(drift * drift))),
                "max_abs_parameter_drift_from_CURRICULUM": float(np.max(np.abs(drift))),
                "selection_authorized": False,
            },
        }
        atomic_json(out_dir / f"{arm}-fit-receipt.json", arms[arm])

    if {arms[a]["coordinate_identity_sha256"] for a in fit_arms} != {coord_sha}:
        raise FitError("cross-arm coordinate identity drift")
    if len({arms[a]["trainable_coordinates"] for a in fit_arms}) != 1:
        raise FitError("cross-arm trainable-coordinate count drift")

    report = {
        "schema": SCHEMA,
        "terminal": terminal,
        "state": "completed",
        "arms": arms,
        "arm_order": list(fit_arms),
        "varied_factor": "learning_objective",
        "all_other_axes_fixed": True,
        "attribution_complete": recovery is None,
        "technical_failed_arms": [] if recovery is None else ["MIXED"],
        "recovery_2038": None if recovery is None else {
            "failed_job_id": RECOVERY_2038_JOB,
            "failed_attempt_id": RECOVERY_2038_ATTEMPT,
            "diagnostic_terminal": recovery["terminal"],
            "primary_mechanical_error": recovery["primary_mechanical_error"],
            "max_iterations_unchanged": MAX_ITER,
            "retuning_performed": False,
        },
        "records": RECORDS,
        "train_records": TRAIN_RECORDS,
        "holdout_records": HOLDOUT_RECORDS,
        "common_recipe": {
            "fold": FOLD,
            "tempo_stage": True,
            "extras": EXTRAS,
            "prune_min_visits": PRUNE_MIN_VISITS,
            "l2": L2,
            "chunk": CHUNK,
            "max_iterations": MAX_ITER,
            "maxcor": MAXCOR,
            "gtol": GTOL,
            "parent_sha256": parent_sha,
            "parent_scale": SCALE,
            "pattern_slots": pat_n,
            "trainable_coordinates": n_cols,
            "coordinate_identity_sha256": coord_sha,
        },
        "normalization": {
            "terminal": normalization["terminal"],
            "normalization_scope": "TRAIN_ONLY",
            "gradient_norms": norms,
            "lambda_normalized_gradient": objective.FROZEN_LAMBDA,
            "receipt_sha256": sha256(args.normalization_receipt),
        },
        "inputs": {
            "data_sha256": data_sha,
            "feat_sha256": feat_sha,
            "local_targets_sha256": local_sha,
            "parent_sha256": parent_sha,
        },
        "fits": len(fit_arms),
        "new_jass_searches": 0,
        "new_scan_searches": 0,
        "strength_games": 0,
        "selfplay_games": 0,
        "confirmation_target_reads": 0,
        "alpha_spent": 0,
        "promotions": 0,
        "bakes": 0,
        "scientific_verdict": None,
        "next_stage": "RUN_FROZEN_CLS_G0_PER_TECHNICALLY_VALID_ARM",
    }
    atomic_json(out_dir / "fit-report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--feat", required=True, type=Path)
    ap.add_argument("--local-targets", required=True, type=Path)
    ap.add_argument("--parent", required=True, type=Path)
    ap.add_argument("--normalization-receipt", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--recovery-2038-summary", type=Path)
    args = ap.parse_args(argv)
    report = run(args)
    print(json.dumps({"terminal": report["terminal"], "arms": report["arm_order"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
