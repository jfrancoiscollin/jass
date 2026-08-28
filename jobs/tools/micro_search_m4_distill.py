#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Preregistered M4 full-PatternEval pairwise distillation.

Consumes only the frozen M3 production design / B*=1000 top-vs-rest constraints
and byte-identical CURRICULUM.  Fits a residual in the exact writable PJTW v3
coordinate system, then shrinks that single residual direction against exactly
500000 target-blind zero-target M3 child states selected with seed 2026090212.
The anchor guard is evaluated by the production C++ evaluator after every
serialize/reload; no teacher/deep/WDL signal is consumed by anchor selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize
from scipy.special import expit

import sys
TOOLS = Path(__file__).resolve().parents[2] / "pattern_jass" / "tools"
sys.path.insert(0, str(TOOLS))
if os.environ.get("JASS_PATTERNS_DIR"):
    sys.path.insert(0, os.environ["JASS_PATTERNS_DIR"])
import train  # type: ignore  # noqa: E402

PAIR_SEED = 2026090211
ANCHOR_SEED = 2026090212
ROW_CAP = 1_000_000
ANCHOR_N = 500_000
L2 = 1e-5
MAX_ITER = 200              # production train.py default
MAXCOR = 5                  # production memory-bounded L-BFGS history
EXPECTED_EXTRAS = 120
EXPECTED_PATTERNS_PER_ROW = 8
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_pjtw(path: Path) -> tuple[tuple[int, int, int, int, int], np.ndarray]:
    raw = path.read_bytes()
    if len(raw) < 20:
        raise SystemExit("PJTW too short")
    header = struct.unpack_from("<IIIII", raw, 0)
    magic, version, scale, n_pat, n_ext = header
    if magic != train.WEIGHTS_MAGIC or (version & 0xFF) != train.WEIGHTS_VERSION_V3:
        raise SystemExit("expected production PJTW v3")
    total = 2 * (n_pat + n_ext)
    if len(raw) != 20 + 4 * total:
        raise SystemExit("PJTW layout/size drift")
    w = np.frombuffer(raw, dtype="<i4", offset=20, count=total).astype(np.int64)
    return tuple(map(int, header)), w


def write_candidate(path: Path, header: tuple[int, int, int, int, int], w: np.ndarray) -> None:
    magic, version, scale, n_pat, n_ext = header
    if len(w) != 2 * (n_pat + n_ext):
        raise SystemExit("candidate weight length drift")
    # Reuse the production writer rather than inventing a parallel PJTW format.
    train.write_weights_v3(
        path,
        w[:n_pat],
        w[n_pat:2*n_pat],
        w[2*n_pat:2*n_pat+n_ext],
        w[2*n_pat+n_ext:],
        scale,
        king=bool(version & train.PJTW_KING_BIT),
    )
    got = struct.unpack_from("<IIIII", path.read_bytes(), 0)
    if tuple(map(int, got)) != header:
        raise SystemExit(f"production writer header drift: {got} != {header}")


def select_anchor_states(src: Path, dst: Path) -> dict:
    raw = src.read_bytes()
    if raw[:4] != b"JNNW" or len(raw) < 8:
        raise SystemExit("anchor source is not counted JNNW")
    n = struct.unpack_from("<I", raw, 4)[0]
    rec_size = 38
    if len(raw) != 8 + rec_size * n:
        raise SystemExit("anchor source JNNW size drift")
    if n < ANCHOR_N:
        raise SystemExit(f"anchor source support {n} < {ANCHOR_N}")
    # Source is the zero-target M3 child corpus. Verify target bytes before any
    # selection; neither micro1000 teacher scores nor deep labels are in this file.
    for i in range(n):
        off = 8 + rec_size * i
        score = struct.unpack_from("<i", raw, off + 33)[0]
        wdl = struct.unpack_from("<b", raw, off + 37)[0]
        if score != 0 or wdl != 0:
            raise SystemExit(f"anchor source target bytes nonzero at row {i}")
    rng = np.random.Generator(np.random.PCG64(ANCHOR_SEED))
    chosen = np.sort(rng.choice(n, size=ANCHOR_N, replace=False).astype(np.int64))
    with dst.open("wb") as f:
        f.write(b"JNNW")
        f.write(struct.pack("<I", ANCHOR_N))
        for i in chosen:
            off = 8 + rec_size * int(i)
            f.write(raw[off:off+rec_size])
    sel_hash = hashlib.sha256(chosen.astype("<i8", copy=False).tobytes()).hexdigest()
    return {
        "seed": ANCHOR_SEED,
        "source_rows": int(n),
        "selected_rows": ANCHOR_N,
        "selection_index_sha256": sel_hash,
        "anchor_jnnw_sha256": sha256(dst),
        "source_labels_read": False,
        "deep_labels_read": 0,
    }


def build_pair_design(design: dict[str, np.ndarray], constraints: dict[str, np.ndarray],
                      header: tuple[int, int, int, int, int], w0: np.ndarray):
    _, _, scale, n_pat, n_ext = header
    cols = np.asarray(design["canonical_cols"], dtype=np.int64)
    signs = np.asarray(design["signs"], dtype=np.float64)
    wmg = np.asarray(design["tempo_wmg"], dtype=np.float64)
    extras = np.asarray(design["extras"], dtype=np.float32)
    pov = np.asarray(design["parent_pov_sign"], dtype=np.float64)
    parent = np.asarray(design["parent_id"], dtype=np.int64)
    if cols.ndim != 2 or cols.shape[1] != EXPECTED_PATTERNS_PER_ROW:
        raise SystemExit(f"M3 pattern-row geometry drift: {cols.shape}")
    n = cols.shape[0]
    if signs.shape != cols.shape or wmg.shape != (n,) or extras.shape != (n, n_ext) or pov.shape != (n,):
        raise SystemExit("M3 compact production design alignment drift")
    if n_ext != EXPECTED_EXTRAS:
        raise SystemExit(f"dense extras drift {n_ext} != {EXPECTED_EXTRAS}")
    if np.any(cols < 0) or np.any(cols >= n_pat) or np.any((signs != -1) & (signs != 1)):
        raise SystemExit("invalid exact-fold pattern row")
    if np.any((pov != -1) & (pov != 1)) or np.any(wmg < 0) or np.any(wmg > 1):
        raise SystemExit("invalid parent POV / tempo phase")

    good0 = np.asarray(constraints["good"], dtype=np.int64)
    bad0 = np.asarray(constraints["bad"], dtype=np.int64)
    cparent0 = np.asarray(constraints["parent_id"], dtype=np.int64)
    m0 = len(good0)
    if bad0.shape != (m0,) or cparent0.shape != (m0,) or m0 <= 0:
        raise SystemExit("constraint alignment drift")
    if np.any(good0 < 0) or np.any(good0 >= n) or np.any(bad0 < 0) or np.any(bad0 >= n):
        raise SystemExit("constraint row index outside design")
    if np.any(parent[good0] != cparent0) or np.any(parent[bad0] != cparent0):
        raise SystemExit("constraint parent/design alignment drift")
    if np.any(pov[good0] != pov[bad0]):
        raise SystemExit("pair changed parent POV sign")

    rng = np.random.Generator(np.random.PCG64(PAIR_SEED))
    order = rng.permutation(m0)
    if m0 > ROW_CAP:
        order = order[:ROW_CAP]
    good = good0[order]
    bad = bad0[order]
    m = len(good)
    order_hash = hashlib.sha256(order.astype("<i8", copy=False).tobytes()).hexdigest()

    # Inactive pattern coordinates have zero logistic gradient and a zero residual
    # prior, hence remain exactly zero under global residual L2. Optimising only
    # the union touched by the frozen constraints is algebraically identical to
    # the full 2*n_pat problem while keeping L-BFGS bounded.
    active = np.unique(np.concatenate((cols[good].reshape(-1), cols[bad].reshape(-1))))
    amap = np.full(n_pat, -1, dtype=np.int32)
    amap[active] = np.arange(len(active), dtype=np.int32)
    a = len(active)

    r = np.repeat(np.arange(m, dtype=np.int32), cols.shape[1])
    gcol = amap[cols[good]].reshape(-1).astype(np.int64, copy=False)
    bcol = amap[cols[bad]].reshape(-1).astype(np.int64, copy=False)
    sg = signs[good].reshape(-1)
    sb = signs[bad].reshape(-1)
    factor = 100.0 / float(scale)
    pg = pov[good]
    pb = pov[bad]
    gmg = np.repeat(pg * wmg[good] * factor, cols.shape[1]) * sg
    bmg = -np.repeat(pb * wmg[bad] * factor, cols.shape[1]) * sb
    geg = np.repeat(pg * (1.0 - wmg[good]) * factor, cols.shape[1]) * sg
    beg = -np.repeat(pb * (1.0 - wmg[bad]) * factor, cols.shape[1]) * sb
    rows = np.concatenate((r, r, r, r))
    pcols = np.concatenate((gcol, bcol, gcol + a, bcol + a))
    pdata = np.concatenate((gmg, bmg, geg, beg)).astype(np.float64, copy=False)
    P = sp.coo_matrix((pdata, (rows, pcols)), shape=(m, 2*a), dtype=np.float64).tocsr()
    P.sum_duplicates()

    # Dense production extras remain dense; materialise only the pair difference,
    # never good and bad full copies simultaneously.
    E = np.empty((m, 2*n_ext), dtype=np.float32)
    chunk = 50_000
    for lo in range(0, m, chunk):
        hi = min(m, lo + chunk)
        gg = good[lo:hi]; bb = bad[lo:hi]
        cmg_g = (pov[gg] * wmg[gg] * factor).astype(np.float32)
        cmg_b = (pov[bb] * wmg[bb] * factor).astype(np.float32)
        ceg_g = (pov[gg] * (1.0-wmg[gg]) * factor).astype(np.float32)
        ceg_b = (pov[bb] * (1.0-wmg[bb]) * factor).astype(np.float32)
        E[lo:hi, :n_ext] = extras[gg] * cmg_g[:, None] - extras[bb] * cmg_b[:, None]
        E[lo:hi, n_ext:] = extras[gg] * ceg_g[:, None] - extras[bb] * ceg_b[:, None]

    pat0 = np.concatenate((w0[active], w0[n_pat + active])).astype(np.float64)
    ext0 = np.concatenate((w0[2*n_pat:2*n_pat+n_ext], w0[2*n_pat+n_ext:])).astype(np.float64)
    z0 = np.asarray(P.dot(pat0), dtype=np.float64) + np.asarray(E.dot(ext0), dtype=np.float64)
    if not np.all(np.isfinite(z0)):
        raise SystemExit("non-finite baseline pair scores")
    meta = {
        "source_constraints": int(m0),
        "fit_constraints": int(m),
        "row_cap": ROW_CAP,
        "pair_seed": PAIR_SEED,
        "pair_order_index_sha256": order_hash,
        "active_pattern_buckets": int(a),
        "full_pattern_buckets": int(n_pat),
        "pattern_pair_nnz": int(P.nnz),
        "dense_pair_columns": int(2*n_ext),
        "design_operation": "X_good_minus_X_bad",
    }
    return P, E, z0, active.astype(np.int64), meta


def fit_residual(P: sp.csr_matrix, E: np.ndarray, z0: np.ndarray) -> tuple[np.ndarray, dict]:
    n_pat_active2 = P.shape[1]
    n_ext2 = E.shape[1]
    n = len(z0)
    theta0 = np.zeros(n_pat_active2 + n_ext2, dtype=np.float64)
    evals = 0
    t0 = time.time()

    def loss_grad(theta: np.ndarray):
        nonlocal evals
        evals += 1
        zp = np.asarray(P.dot(theta[:n_pat_active2]), dtype=np.float64)
        ze = np.asarray(E.dot(theta[n_pat_active2:]), dtype=np.float64)
        z = z0 + zp + ze
        loss_data = float(np.logaddexp(0.0, -z).mean())
        # d/dz log(1+exp(-z)) = -sigmoid(-z)
        q = -expit(-z) / float(n)
        gp = np.asarray(P.T.dot(q), dtype=np.float64)
        ge = np.asarray(E.T.dot(q), dtype=np.float64)
        loss = loss_data + 0.5 * L2 * float(np.dot(theta, theta))
        grad = np.concatenate((gp, ge)) + L2 * theta
        if not math.isfinite(loss) or not np.all(np.isfinite(grad)):
            raise FloatingPointError("non-finite M4 objective")
        return loss, grad

    initial_loss, initial_grad = loss_grad(theta0)
    res = minimize(
        loss_grad,
        theta0,
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": MAX_ITER, "maxcor": MAXCOR},
    )
    elapsed = time.time() - t0
    grad_inf = float(np.max(np.abs(res.jac))) if len(res.jac) else 0.0
    receipt = {
        "optimizer": "scipy_L-BFGS-B_production_family",
        "success": bool(res.success),
        "status": int(res.status),
        "message": str(res.message),
        "iterations": int(res.nit),
        "function_evaluations": int(res.nfev),
        "objective_evaluations_observed": int(evals),
        "initial_loss": float(initial_loss),
        "initial_gradient_inf_norm": float(np.max(np.abs(initial_grad))),
        "final_loss": float(res.fun),
        "gradient_inf_norm": grad_inf,
        "max_iterations": MAX_ITER,
        "maxcor": MAXCOR,
        "residual_l2": L2,
        "elapsed_seconds": float(elapsed),
    }
    if not res.success:
        raise SystemExit("M4 production-family optimizer did not converge: " + json.dumps(receipt, sort_keys=True))
    return np.asarray(res.x, dtype=np.float64), receipt


def run_anchor(binary: Path, states: Path, t0: Path, t1: Path, report: Path) -> dict:
    subprocess.run([str(binary), str(states), str(t0), str(t1), str(report)], check=True)
    out = json.loads(report.read_text())
    if out.get("schema") != "jass.micro_search_m4_anchor_drift.v1" or out.get("states") != ANCHOR_N:
        raise SystemExit("anchor evaluator report contract drift")
    if out.get("serialize_reload") is not True:
        raise SystemExit("anchor evaluator did not prove serialize/reload")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--constraints", required=True)
    ap.add_argument("--m3-proof", required=True)
    ap.add_argument("--children", required=True)
    ap.add_argument("--curriculum", required=True)
    ap.add_argument("--anchor-binary", required=True)
    ap.add_argument("--anchor-out", required=True)
    ap.add_argument("--t1-out", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    design_path = Path(args.design); constraints_path = Path(args.constraints)
    proof_path = Path(args.m3_proof); children_path = Path(args.children)
    curriculum = Path(args.curriculum); anchor_binary = Path(args.anchor_binary)
    anchor_out = Path(args.anchor_out); t1_out = Path(args.t1_out); report_out = Path(args.report)
    if sha256(curriculum) != CURRICULUM_SHA:
        raise SystemExit("CURRICULUM raw SHA mismatch")
    proof = json.loads(proof_path.read_text())
    if proof.get("passed") is not True:
        raise SystemExit("M3 design proof is not PASS")
    psp = proof.get("production_score_proof", {})
    pwm = proof.get("pairwise_mapping", {})
    if psp.get("mismatches") != 0 or psp.get("production_t0_integer_score_exact") is not True:
        raise SystemExit("M3 exact production score proof not zero-mismatch")
    if pwm.get("operation") != "X_good_minus_X_bad" or pwm.get("algebraically_exact_from_proven_rows") is not True:
        raise SystemExit("M3 exact pairwise mapping proof absent")

    header, w0 = load_pjtw(curriculum)
    _, version, _, n_pat, n_ext = header
    if n_ext != EXPECTED_EXTRAS:
        raise SystemExit("CURRICULUM dense-extra geometry drift")
    dnpz = np.load(design_path, allow_pickle=False)
    cnpz = np.load(constraints_path, allow_pickle=False)
    design = {k: dnpz[k] for k in dnpz.files}
    constraints = {k: cnpz[k] for k in cnpz.files}

    P, E, z0, active, pair_meta = build_pair_design(design, constraints, header, w0)
    theta, opt = fit_residual(P, E, z0)
    a = len(active)
    delta = np.zeros_like(w0, dtype=np.float64)
    delta[active] = theta[:a]
    delta[n_pat + active] = theta[a:2*a]
    delta[2*n_pat:2*n_pat+n_ext] = theta[2*a:2*a+n_ext]
    delta[2*n_pat+n_ext:] = theta[2*a+n_ext:]
    if not np.all(np.isfinite(delta)):
        raise SystemExit("non-finite fitted residual")

    anchor_meta = select_anchor_states(children_path, anchor_out)
    if not anchor_binary.is_file():
        raise SystemExit("missing production anchor evaluator binary")

    history = []
    with tempfile.TemporaryDirectory(prefix="jass-m4-shrink-") as td:
        td = Path(td)
        def evaluate_s(s: float) -> tuple[bool, dict, Path]:
            candidate = td / f"candidate-{s:.12f}.pjtw"
            wi = np.rint(w0.astype(np.float64) + float(s) * delta).astype(np.int64)
            if np.any(wi < np.iinfo(np.int32).min) or np.any(wi > np.iinfo(np.int32).max):
                raise SystemExit("M4 candidate int32 overflow")
            write_candidate(candidate, header, wi)
            ar = run_anchor(anchor_binary, anchor_out, curriculum, candidate, td / f"anchor-{s:.12f}.json")
            ok = float(ar["rms_abs_cp"]) <= 12.0 and float(ar["p99_abs_cp"]) <= 35.0
            history.append({"s": float(s), "rms_abs_cp": float(ar["rms_abs_cp"]),
                            "p99_abs_cp": float(ar["p99_abs_cp"]), "pass": bool(ok)})
            return ok, ar, candidate

        ok1, ar1, cand1 = evaluate_s(1.0)
        if ok1:
            s_final = 1.0
        else:
            lo, hi = 0.0, 1.0
            # s=0 is byte-identical in coefficients and must pass.
            ok0, _, _ = evaluate_s(0.0)
            if not ok0:
                raise SystemExit("anchor evaluator says byte-identical s=0 fails guards")
            for _ in range(26):
                mid = (lo + hi) / 2.0
                ok, _, _ = evaluate_s(mid)
                if ok:
                    lo = mid
                else:
                    hi = mid
            s_final = lo

        final_w = np.rint(w0.astype(np.float64) + s_final * delta).astype(np.int64)
        write_candidate(t1_out, header, final_w)
        final_anchor = run_anchor(anchor_binary, anchor_out, curriculum, t1_out, td / "anchor-final.json")

    if float(final_anchor["rms_abs_cp"]) > 12.0 or float(final_anchor["p99_abs_cp"]) > 35.0:
        raise SystemExit("final serialized T1 violates preregistered anchor guards")
    changed = int(np.count_nonzero(final_w != w0))
    if changed == 0:
        raise SystemExit("M4 converged/shrank to byte-identical T0; no T1 residual remains")

    report = {
        "schema": "jass.micro_search_m4_pattern_distillation.v1",
        "passed": True,
        "verdict": "MICRO_SEARCH_M4_T1_FROZEN",
        "next_stage": "M5_fresh_deep_transfer_confirmation",
        "prereg_pair_seed": PAIR_SEED,
        "prereg_anchor_seed": ANCHOR_SEED,
        "selected_budget_nodes": 1000,
        "objective": "pairwise_logistic_top_vs_rest_full_production_PatternEval",
        "residual_l2": L2,
        "pair_design": pair_meta,
        "optimizer": opt,
        "design_equivalence": {
            "m3_proof_sha256": sha256(proof_path),
            "production_rows_exact": int(psp.get("rows_exact", 0)),
            "production_score_mismatches": 0,
            "pairwise_operation": "X_good_minus_X_bad",
            "algebraically_exact": True,
        },
        "anchor": {
            **anchor_meta,
            "guard_rms_abs_cp_max": 12.0,
            "guard_p99_abs_cp_max": 35.0,
            "final_rms_abs_cp": float(final_anchor["rms_abs_cp"]),
            "final_p99_abs_cp": float(final_anchor["p99_abs_cp"]),
            "final_max_abs_cp": int(final_anchor["max_abs_cp"]),
            "serialize_reload": bool(final_anchor["serialize_reload"]),
            "shrink_binary_search_iterations": 26 if s_final < 1.0 else 0,
        },
        "residual_scale": float(s_final),
        "changed_int32_coefficients": changed,
        "curriculum_raw_sha256": sha256(curriculum),
        "t1_raw_sha256": sha256(t1_out),
        "pjtw_header": {
            "magic": int(header[0]), "version": int(version), "scale": int(header[2]),
            "n_pattern": int(n_pat), "n_extras": int(n_ext),
        },
        "inputs": {
            "m3_design_sha256": sha256(design_path),
            "m3_constraints_sha256": sha256(constraints_path),
            "m3_children_sha256": sha256(children_path),
        },
        "shrink_evaluations": history,
        "source_labels_read": False,
        "deep_scores_read": 0,
        "wdl_read": 0,
        "fits": 1,
        "pattern_eval_fits": 1,
        "t_refits": 1,
        "strength_games": 0,
        "runtime_micro_search": False,
        "micro_search_present_at_inference": False,
        "d_present_at_inference": False,
        "promotion_authorized": False,
        "automatic_promotion": False,
    }
    report_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
