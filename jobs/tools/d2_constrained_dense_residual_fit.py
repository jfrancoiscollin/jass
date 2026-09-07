#!/usr/bin/env python3
"""Fit and seal the preregistered D2 constrained 240-parameter dense residual.

Decision optimization consumes C-train survived5 groups only. The single raw
residual is then scaled solely by exact CURRENT_2M WDL-train feasibility after
production int32 quantization. C valid/test and WDL holdout are never read here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
from typing import Any, Mapping, Sequence

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize
from scipy.special import expit

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "pattern_jass" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import patterns  # noqa: E402
import train  # noqa: E402
import train_stream as ts  # noqa: E402

GROUP_SCHEMA = "jass.d2.survived5_groups.v1"
REPORT_SCHEMA = "jass.d2.constrained_dense_residual_fit.v1"
SEAL_SCHEMA = "jass.d2.candidate_seal.v1"
RECORDS = 2_000_000
TRAIN = 1_800_796
HOLDOUT = 199_204
ACTIONS = 38_053
PARENTS = 4_000
TRAIN_PARENTS = 3_200
EXTRAS = 120
RESIDUAL_COLS = 240
L2 = 1e-5
CHUNK = 20_000
MAX_ITER = 2_000
MAXCOR = 20
GTOL = 1e-4
SCALE = 1000
WDL_TOLERANCE = 0.002
BISECTION_STEPS = 32
MAGIC = 0x57544A50


class D2FitError(RuntimeError):
    pass


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise D2FitError(f"cannot read JSON {path}: {exc}") from exc
    if type(value) is not dict:
        raise D2FitError(f"JSON object required: {path}")
    return value


def _write_json(path: Path, value: object) -> None:
    if path.exists() or path.is_symlink():
        raise D2FitError(f"refusing existing output {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def _validate_targets(path: Path) -> np.ndarray:
    try:
        arr = np.load(path, allow_pickle=False, mmap_mode="r")
    except (OSError, ValueError) as exc:
        raise D2FitError(f"cannot load target sidecar: {exc}") from exc
    if not isinstance(arr, np.ndarray) or arr.dtype != np.dtype(np.float32) or arr.shape != (RECORDS,):
        raise D2FitError("target sidecar must be float32 CURRENT_2M vector")
    # Deliberately inspect TRAIN only. Holdout is sealed for terminal readout.
    tr = np.asarray(arr[:TRAIN], dtype=np.float64)
    if not bool(np.all(np.isfinite(tr))) or float(np.min(tr)) < 0.0 or float(np.max(tr)) > 1.0:
        raise D2FitError("WDL train target outside [0,1]")
    return arr


def load_groups(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = _json(path)
    if payload.get("schema") != GROUP_SCHEMA or payload.get("parents") != PARENTS or payload.get("actions") != ACTIONS:
        raise D2FitError("D2 group identity/count drift")
    if payload.get("split_parents") != {"train": 3200, "valid": 400, "test": 400}:
        raise D2FitError("D2 split parent counts drift")
    groups = payload.get("groups")
    if not isinstance(groups, list) or len(groups) != PARENTS:
        raise D2FitError("D2 group list drift")
    cursor = 0
    train_groups: list[dict[str, Any]] = []
    for parent_id, group in enumerate(groups):
        if type(group) is not dict or group.get("parent_id") != parent_id:
            raise D2FitError("D2 parent ordering drift")
        start = group.get("start"); count = group.get("count"); sel = group.get("selected_local_action_index")
        split = group.get("split"); stm = group.get("parent_stm")
        if type(start) is not int or start != cursor or type(count) is not int or not 2 <= count <= 16:
            raise D2FitError("D2 action span drift")
        if type(sel) is not int or not 0 <= sel < count or split not in {"train", "valid", "test"}:
            raise D2FitError("D2 selected/split drift")
        if type(stm) is not int or stm not in (0, 1):
            raise D2FitError("D2 stm drift")
        eligible = group.get("d2_eligible")
        hard = group.get("hard_competitor_local_action_indices")
        s5 = group.get("survived5_local_action_indices")
        if type(eligible) is not bool or not isinstance(hard, list) or not isinstance(s5, list):
            raise D2FitError("D2 allocation group drift")
        if any(type(x) is not int or not 0 <= x < count for x in hard + s5):
            raise D2FitError("D2 allocation index drift")
        if hard != sorted(set(hard)) or s5 != sorted(set(s5)):
            raise D2FitError("D2 allocation index ordering/duplicate drift")
        if eligible != (sel in s5 and len(hard) >= 1):
            raise D2FitError("D2 eligibility rule drift")
        if eligible and (sel in hard or any(x not in s5 for x in hard)):
            raise D2FitError("D2 hard competitor rule drift")
        cursor += count
        if split == "train" and eligible:
            train_groups.append(group)
    if cursor != ACTIONS:
        raise D2FitError("D2 action cardinality drift")
    if not train_groups:
        raise D2FitError("no D2-eligible train parents")
    return groups, train_groups


def train_rows_and_local_groups(train_groups: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, list[dict[str, Any]]]:
    rows: list[int] = []
    local_groups: list[dict[str, Any]] = []
    cursor = 0
    for g in train_groups:
        start = int(g["start"]); count = int(g["count"])
        rows.extend(range(start, start + count))
        local_groups.append({
            "count": count,
            "hard_competitor_local_action_indices": list(g["hard_competitor_local_action_indices"]),
            "parent_stm": int(g["parent_stm"]),
            "selected_local_action_index": int(g["selected_local_action_index"]),
            "start": cursor,
        })
        cursor += count
    return np.asarray(rows, dtype=np.int64), local_groups


def _open_model(path: Path) -> tuple[np.ndarray, int, int, int]:
    weights, scale, n_pat, n_ext = train.load_v3_weights_float(str(path))
    if scale != SCALE or n_ext != EXTRAS or n_pat != patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN:
        raise D2FitError("base PatternEval layout/scale drift")
    return np.asarray(weights, dtype=np.float64), int(scale), int(n_pat), int(n_ext)


def _predict_rows(data: Path, feat_path: Path, model: Path, rows: np.ndarray) -> np.ndarray:
    mm, n = ts.open_jnnw(str(data)); feat, k = ts.open_feat(str(feat_path), n)
    weights, _scale, n_pat, n_ext = _open_model(model)
    if k != n_ext:
        raise D2FitError("feature/model extras drift")
    rec = mm[rows]
    wm = np.ascontiguousarray(rec["wm"]); bm = np.ascontiguousarray(rec["bm"])
    folder = ts.Folder("none")
    cols, signs = folder.cols_signs(bm, wm)
    wmg = ts._tempo_wmg_bb(wm, bm).astype(np.float64); weg = 1.0 - wmg
    xpat = train.build_sparse_X_phased(cols, wmg, weg, n_pat, signs)
    xext = train.build_extras_phased(np.asarray(feat[rows], dtype=np.float64), wmg, weg)
    x = sp.hstack([xpat, xext], format="csr")
    return np.asarray(x @ weights).ravel()


def _dense_residual_rows(data: Path, feat_path: Path, rows: np.ndarray) -> np.ndarray:
    mm, n = ts.open_jnnw(str(data)); feat, k = ts.open_feat(str(feat_path), n)
    if k != EXTRAS:
        raise D2FitError(f"D2 requires {EXTRAS} production extras, got {k}")
    rec = mm[rows]
    wm = np.ascontiguousarray(rec["wm"]); bm = np.ascontiguousarray(rec["bm"])
    wmg = ts._tempo_wmg_bb(wm, bm).astype(np.float64); weg = 1.0 - wmg
    x = train.build_extras_phased(np.asarray(feat[rows], dtype=np.float64), wmg, weg)
    out = np.asarray(x.toarray(), dtype=np.float64)
    if out.shape != (len(rows), RESIDUAL_COLS):
        raise D2FitError("D2 residual design shape drift")
    return out


def pairwise_loss_grad(delta: np.ndarray, x: np.ndarray, base_z: np.ndarray,
                       groups: Sequence[Mapping[str, Any]]) -> tuple[float, np.ndarray, dict[str, float]]:
    if delta.shape != (RESIDUAL_COLS,) or x.shape[1] != RESIDUAL_COLS or x.shape[0] != base_z.shape[0]:
        raise D2FitError("D2 pairwise design shape drift")
    z = base_z + x @ delta
    residual = np.zeros_like(z)
    total = 0.0
    correct = 0
    pairs = 0
    for g in groups:
        start = int(g["start"]); selected = int(g["selected_local_action_index"])
        hard = list(g["hard_competitor_local_action_indices"])
        if not hard:
            raise D2FitError("eligible D2 group without competitor")
        pov = 1.0 if int(g["parent_stm"]) == 1 else -1.0
        q = pov * z[start:start + int(g["count"])]
        margins = np.asarray([q[selected] - q[j] for j in hard], dtype=np.float64)
        losses = np.logaddexp(0.0, -margins)
        total += float(np.mean(losses))
        correct += int(np.sum(margins > 0.0)); pairs += len(hard)
        s = expit(-margins) / len(hard)
        r = np.zeros(int(g["count"]), dtype=np.float64)
        r[selected] -= float(np.sum(s))
        for j, sj in zip(hard, s):
            r[j] += float(sj)
        residual[start:start + int(g["count"])] += pov * r
    n = len(groups)
    decision = total / n
    grad = (x.T @ residual) / n
    reg = 0.5 * L2 * float(np.dot(delta, delta))
    grad = grad + L2 * delta
    return decision + reg, grad, {
        "decision_loss": decision,
        "eligible_parents": float(n),
        "pairwise_accuracy": correct / pairs if pairs else 0.0,
        "pairs": float(pairs),
        "regularizer": reg,
    }


def _read_raw_pjtw(path: Path) -> tuple[tuple[int, int, int, int, int], np.ndarray]:
    raw = path.read_bytes()
    if len(raw) < 20:
        raise D2FitError("base PJTW truncated")
    header = struct.unpack_from("<IIIII", raw, 0)
    magic, version, scale, n_pat, n_ext = header
    if magic != MAGIC or (version & 0xFF) != 3 or scale != SCALE or n_ext != EXTRAS:
        raise D2FitError("base PJTW header drift")
    total = 2 * (n_pat + n_ext)
    if len(raw) != 20 + total * 4:
        raise D2FitError("base PJTW size drift")
    ints = np.frombuffer(raw, dtype="<i4", offset=20, count=total).astype(np.int64)
    return header, ints


def _candidate_ints(base_ints: np.ndarray, n_pat: int, delta_raw: np.ndarray, alpha: float) -> tuple[np.ndarray, np.ndarray]:
    inc = np.rint(alpha * delta_raw * SCALE).astype(np.int64)
    if inc.shape != (RESIDUAL_COLS,):
        raise D2FitError("D2 residual increment shape drift")
    out = base_ints.copy()
    ext0 = 2 * n_pat
    out[ext0:ext0 + EXTRAS] += inc[:EXTRAS]
    out[ext0 + EXTRAS:ext0 + 2 * EXTRAS] += inc[EXTRAS:]
    if np.any(out < -(2 ** 31)) or np.any(out > 2 ** 31 - 1):
        raise D2FitError("candidate int32 overflow")
    return out, inc


def _write_raw_pjtw(path: Path, header: tuple[int, int, int, int, int], ints: np.ndarray) -> None:
    if path.exists() or path.is_symlink():
        raise D2FitError(f"refusing existing candidate {path}")
    with path.open("wb") as f:
        f.write(struct.pack("<IIIII", *header))
        f.write(ints.astype("<i4").tobytes())


def _base_train_logits(data: Path, feat_path: Path, model: Path) -> np.ndarray:
    mm, n = ts.open_jnnw(str(data)); feat, k = ts.open_feat(str(feat_path), n)
    if n != RECORDS or k != EXTRAS:
        raise D2FitError("CURRENT_2M data/feature drift")
    weights, _scale, n_pat, n_ext = _open_model(model)
    folder = ts.Folder("none")
    out = np.empty(TRAIN, dtype=np.float64)
    for lo in range(0, TRAIN, CHUNK):
        hi = min(TRAIN, lo + CHUNK); rec = mm[lo:hi]
        wm = np.ascontiguousarray(rec["wm"]); bm = np.ascontiguousarray(rec["bm"])
        cols, signs = folder.cols_signs(bm, wm)
        wmg = ts._tempo_wmg_bb(wm, bm).astype(np.float64); weg = 1.0 - wmg
        xpat = train.build_sparse_X_phased(cols, wmg, weg, n_pat, signs)
        xext = train.build_extras_phased(np.asarray(feat[lo:hi], dtype=np.float64), wmg, weg)
        out[lo:hi] = np.asarray(sp.hstack([xpat, xext], format="csr") @ weights).ravel()
    return out


def _wdl_train_loss(base_z: np.ndarray, targets: np.ndarray, data: Path, feat_path: Path,
                    residual_ints: np.ndarray) -> float:
    mm, n = ts.open_jnnw(str(data)); feat, k = ts.open_feat(str(feat_path), n)
    if n != RECORDS or k != EXTRAS or residual_ints.shape != (RESIDUAL_COLS,):
        raise D2FitError("WDL feasibility input drift")
    d = residual_ints.astype(np.float64) / SCALE
    eps = 1e-12; total = 0.0
    for lo in range(0, TRAIN, CHUNK):
        hi = min(TRAIN, lo + CHUNK); rec = mm[lo:hi]
        wm = np.ascontiguousarray(rec["wm"]); bm = np.ascontiguousarray(rec["bm"])
        wmg = ts._tempo_wmg_bb(wm, bm).astype(np.float64); weg = 1.0 - wmg
        xext = train.build_extras_phased(np.asarray(feat[lo:hi], dtype=np.float64), wmg, weg)
        z = base_z[lo:hi] + np.asarray(xext @ d).ravel()
        p = 0.5 * (np.tanh(0.5 * z) + 1.0)
        y = np.asarray(targets[lo:hi], dtype=np.float64)
        total += float(np.sum(-(y * np.log(p + eps) + (1.0 - y) * np.log(1.0 - p + eps))))
    return total / TRAIN


def _plain_logloss(z: np.ndarray, y: np.ndarray) -> float:
    p = 0.5 * (np.tanh(0.5 * z) + 1.0); eps = 1e-12
    return float(np.mean(-(y * np.log(p + eps) + (1.0 - y) * np.log(1.0 - p + eps))))


def fit(args: argparse.Namespace) -> dict[str, Any]:
    t0 = time.time()
    if args.holdout_count != HOLDOUT:
        raise D2FitError(f"D2 holdout must be exactly {HOLDOUT}")
    targets = _validate_targets(args.target_values)
    groups, eligible_train = load_groups(args.decision_groups)
    train_rows, local_groups = train_rows_and_local_groups(eligible_train)
    # Only C-train rows are materialized before candidate seal.
    decision_x = _dense_residual_rows(args.decision_data, args.decision_feat, train_rows)
    decision_base = _predict_rows(args.decision_data, args.decision_feat, args.base_model, train_rows)

    def objective(delta: np.ndarray) -> tuple[float, np.ndarray]:
        loss, grad, _ = pairwise_loss_grad(delta, decision_x, decision_base, local_groups)
        return loss, grad

    raw = minimize(objective, np.zeros(RESIDUAL_COLS, dtype=np.float64), jac=True,
                   method="L-BFGS-B",
                   options={"maxiter": MAX_ITER, "maxcor": MAXCOR, "gtol": GTOL})
    delta_raw = np.asarray(raw.x, dtype=np.float64)
    _raw_loss, _raw_grad, raw_stats = pairwise_loss_grad(delta_raw, decision_x, decision_base, local_groups)
    if not bool(raw.success) or not bool(np.all(np.isfinite(delta_raw))):
        raise D2FitError(f"raw residual optimizer failed: {raw.message}")

    header, base_ints = _read_raw_pjtw(args.base_model)
    n_pat = int(header[3])
    base_z = _base_train_logits(args.wdl_data, args.wdl_feat, args.base_model)
    base_loss = _plain_logloss(base_z, np.asarray(targets[:TRAIN], dtype=np.float64))
    trace: list[dict[str, float]] = []

    def evaluate(alpha: float) -> tuple[float, np.ndarray, np.ndarray]:
        cand_ints, inc = _candidate_ints(base_ints, n_pat, delta_raw, alpha)
        loss = _wdl_train_loss(base_z, targets, args.wdl_data, args.wdl_feat, inc)
        trace.append({"alpha": float(alpha), "delta_wdl_train": float(loss - base_loss), "wdl_train_logloss": float(loss)})
        return loss, cand_ints, inc

    loss1, ints1, inc1 = evaluate(1.0)
    if loss1 - base_loss <= WDL_TOLERANCE:
        alpha = 1.0; final_loss = loss1; final_ints = ints1; final_inc = inc1
    else:
        low = 0.0; high = 1.0
        final_ints = base_ints.copy(); final_inc = np.zeros(RESIDUAL_COLS, dtype=np.int64); final_loss = base_loss
        for _ in range(BISECTION_STEPS):
            mid = (low + high) / 2.0
            loss, cand_ints, inc = evaluate(mid)
            if loss - base_loss <= WDL_TOLERANCE:
                low = mid; final_loss = loss; final_ints = cand_ints; final_inc = inc
            else:
                high = mid
        alpha = low
    if final_loss - base_loss > WDL_TOLERANCE + 1e-12:
        raise D2FitError("final quantized candidate violates WDL train feasibility")

    # Pattern blocks must remain integer-identical; only dense extras may change.
    if not np.array_equal(final_ints[:2 * n_pat], base_ints[:2 * n_pat]):
        raise D2FitError("D2 changed a pattern coefficient")
    changed_patterns = int(np.count_nonzero(final_ints[:2 * n_pat] - base_ints[:2 * n_pat]))
    changed_extras = int(np.count_nonzero(final_inc))
    _write_raw_pjtw(args.out, header, final_ints)

    seal = {
        "alpha": float(alpha),
        "base_model_sha256": sha_file(args.base_model),
        "candidate_sha256": sha_file(args.out),
        "changed_extra_slots": changed_extras,
        "changed_pattern_slots": changed_patterns,
        "decision_test_reads": 0,
        "decision_valid_reads": 0,
        "pattern_coefficients_identical": True,
        "schema": SEAL_SCHEMA,
        "wdl_holdout_reads": 0,
        "wdl_train_delta": float(final_loss - base_loss),
        "wdl_train_logloss_base": float(base_loss),
        "wdl_train_logloss_candidate": float(final_loss),
    }
    _write_json(args.seal, seal)
    report = {
        "candidate": seal,
        "elapsed_seconds": time.time() - t0,
        "fit": {
            "eligible_train_parents": len(eligible_train),
            "gtol": GTOL,
            "l2": L2,
            "max_iter": MAX_ITER,
            "maxcor": MAXCOR,
            "optimizer_function_evaluations": int(raw.nfev),
            "optimizer_iterations": int(raw.nit),
            "optimizer_message": str(raw.message),
            "optimizer_success": bool(raw.success),
            "raw_decision_stats": raw_stats,
            "residual_parameters": RESIDUAL_COLS,
        },
        "forbidden_reads": {"decision_valid": 0, "decision_test": 0, "wdl_holdout": 0, "qscore": 0, "full_ladder_1843": 0},
        "projection": {"iterations": BISECTION_STEPS, "trace": trace, "wdl_train_tolerance": WDL_TOLERANCE},
        "schema": REPORT_SCHEMA,
    }
    _write_json(args.report, report)
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--wdl-data", type=Path, required=True)
    p.add_argument("--wdl-feat", type=Path, required=True)
    p.add_argument("--target-values", type=Path, required=True)
    p.add_argument("--base-model", type=Path, required=True)
    p.add_argument("--decision-data", type=Path, required=True)
    p.add_argument("--decision-feat", type=Path, required=True)
    p.add_argument("--decision-groups", type=Path, required=True)
    p.add_argument("--holdout-count", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--seal", type=Path, required=True)
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result = fit(parse_args(argv))
    except (D2FitError, OSError, ValueError, MemoryError) as exc:
        print(f"D2_CONSTRAINED_DENSE_RESIDUAL_INVALID: {exc}", file=sys.stderr)
        return 2
    print(f"D2_CANDIDATE_SEALED alpha={result['candidate']['alpha']:.12g} "
          f"wdl_train_delta={result['candidate']['wdl_train_delta']:.9g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
