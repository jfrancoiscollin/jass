#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Frozen PatternLatent-8 listwise optimizer and Boundary-A fit sizer.

The feature matrix is exported by the exact C++ PL8 extractor (PL8X), so this
module contains no parallel board/pattern/extras implementation. Standardisation
is target-free and computed before teacher utilities enter the optimizer.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import struct
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

INPUT_WIDTH = 138
LATENT = 8
PARAMS = 1121
TEMPERATURE = 100.0
FIT_SEED = 2026103101
L2 = 1.0e-5
CURRICULUM_SHA = "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1"
PL8X_HEADER = 28


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def open_pl8x(path: Path) -> tuple[np.memmap, int, int]:
    with path.open("rb") as f:
        h = f.read(PL8X_HEADER)
    if len(h) != PL8X_HEADER or h[:4] != b"PL8X":
        raise ValueError("bad PL8X header")
    version = struct.unpack_from("<I", h, 4)[0]
    rows = struct.unpack_from("<Q", h, 8)[0]
    width = struct.unpack_from("<I", h, 16)[0]
    start = struct.unpack_from("<Q", h, 20)[0]
    if version != 1 or width != INPUT_WIDTH or rows <= 0:
        raise ValueError("PL8X contract drift")
    expected = PL8X_HEADER + rows * width * 8
    if path.stat().st_size != expected:
        raise ValueError("PL8X size drift")
    mm = np.memmap(path, dtype="<f8", mode="r", offset=PL8X_HEADER,
                   shape=(rows, width))
    return mm, int(start), int(rows)


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", newline="") if path.suffix == ".gz" \
        else path.open("r", encoding="utf-8", newline="")


def load_groups(path: Path) -> dict[str, np.ndarray]:
    columns = {k: [] for k in ("row_index", "parent_id", "parent_stm", "parent_pieces",
                                "micro1000_parent", "t0_parent")}
    with open_text(path) as f:
        rd = csv.DictReader(f, delimiter="\t")
        if rd.fieldnames is None or not set(columns).issubset(rd.fieldnames):
            raise ValueError("M3 groups columns drift")
        for r in rd:
            for k in columns:
                columns[k].append(int(r[k]))
    dtypes = {"row_index": np.int64, "parent_id": np.int32,
              "parent_stm": np.int8, "parent_pieces": np.int16,
              "micro1000_parent": np.float64, "t0_parent": np.int32}
    return {k: np.asarray(v, dtype=dtypes[k]) for k, v in columns.items()}


def phase_id(pieces: np.ndarray) -> np.ndarray:
    out = np.full(len(pieces), -1, dtype=np.int8)
    out[(pieces >= 30) & (pieces <= 40)] = 0
    out[(pieces >= 20) & (pieces <= 29)] = 1
    out[(pieces >= 12) & (pieces <= 19)] = 2
    out[(pieces >= 9) & (pieces <= 11)] = 3
    if np.any(out < 0):
        raise ValueError("M3 parent phase support drift")
    return out


def boundaries(parent: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(parent) == 0:
        raise ValueError("empty M3 groups")
    starts = np.r_[0, np.flatnonzero(parent[1:] != parent[:-1]) + 1].astype(np.int64)
    ends = np.r_[starts[1:], len(parent)].astype(np.int64)
    counts = ends - starts
    if np.any(counts < 2) or np.any(counts > 16):
        raise ValueError("M3 sibling count outside 2..16")
    return starts, counts


def standardize(x: np.ndarray, chunk: int = 65536) -> tuple[np.ndarray, np.ndarray, float]:
    # Deterministic two-moment pass in original row order. Teacher values are not
    # an input to this function and are not used until after it returns.
    t0 = time.perf_counter()
    n = len(x)
    total = np.zeros(INPUT_WIDTH, dtype=np.longdouble)
    total2 = np.zeros(INPUT_WIDTH, dtype=np.longdouble)
    for a in range(0, n, chunk):
        b = min(n, a + chunk)
        q = np.asarray(x[a:b], dtype=np.longdouble)
        total += q.sum(axis=0, dtype=np.longdouble)
        total2 += np.square(q, dtype=np.longdouble).sum(axis=0, dtype=np.longdouble)
    mu_ld = total / np.longdouble(n)
    var_ld = np.maximum(np.longdouble(0), total2 / np.longdouble(n) - mu_ld * mu_ld)
    sigma_ld = np.sqrt(var_ld)
    sigma_ld[sigma_ld < np.longdouble(1.0e-6)] = np.longdouble(1.0)
    return np.asarray(mu_ld, dtype=np.float64), np.asarray(sigma_ld, dtype=np.float64), time.perf_counter() - t0


def softmax_segments(values: np.ndarray, starts: np.ndarray, counts: np.ndarray) -> np.ndarray:
    maxima = np.maximum.reduceat(values, starts)
    expanded_max = np.repeat(maxima, counts)
    e = np.exp(values - expanded_max)
    sums = np.add.reduceat(e, starts)
    return e / np.repeat(sums, counts)


def prepare_training(groups: dict[str, np.ndarray], start: int, rows: int,
                     t0_child: np.ndarray, sizer: bool) -> dict[str, np.ndarray]:
    all_rows = groups["row_index"]
    if not np.array_equal(all_rows, np.arange(len(all_rows), dtype=np.int64)):
        raise ValueError("M3 row_index alignment drift")
    stop = start + rows
    if stop > len(all_rows):
        raise ValueError("PL8X outside M3 groups")
    sl = slice(start, stop)
    parent = groups["parent_id"][sl].copy()
    stm = groups["parent_stm"][sl].copy()
    pieces = groups["parent_pieces"][sl].copy()
    teacher = groups["micro1000_parent"][sl].copy()
    t0_parent = groups["t0_parent"][sl].copy()
    if np.any(stm < 0) or np.any(stm > 1):
        raise ValueError("parent STM drift")
    if not np.array_equal(np.rint(t0_child).astype(np.int32), -t0_parent):
        raise ValueError("PL8X T0 / M3 parent-POV equivalence failure")

    # Sizer slices may end in the middle of one parent. Drop only that consumed
    # trailing partial parent; a scientific fit must cover the complete corpus.
    if sizer and stop < len(all_rows) and len(parent) and parent[-1] == groups["parent_id"][stop]:
        last = parent[-1]
        keep = int(np.flatnonzero(parent == last)[0])
        parent, stm, pieces, teacher, t0_parent = (a[:keep] for a in (parent, stm, pieces, teacher, t0_parent))
        t0_child = t0_child[:keep]
    if not sizer and (start != 0 or stop != len(all_rows)):
        raise ValueError("scientific PL8 fit requires complete M3 corpus")

    starts, counts = boundaries(parent)
    p_parent = parent[starts]
    if len(np.unique(p_parent)) != len(p_parent):
        raise ValueError("M3 parent blocks not unique")
    phases = phase_id(pieces[starts])
    colors = stm[starts].astype(np.int8)
    strata = phases * 2 + colors
    parent_weight = np.zeros(len(starts), dtype=np.float64)
    stratum_counts = np.bincount(strata, minlength=8)
    if np.any(stratum_counts == 0):
        raise ValueError("empty phase-colour stratum")
    for s in range(8):
        parent_weight[strata == s] = (1.0 / 8.0) / float(stratum_counts[s])
    row_weight = np.repeat(parent_weight, counts)
    q = softmax_segments(teacher / TEMPERATURE, starts, counts)
    return {"parent": parent, "teacher": teacher, "t0": np.asarray(t0_child, dtype=np.float64),
            "starts": starts, "counts": counts, "q": q, "row_weight": row_weight,
            "strata": strata, "stratum_counts": stratum_counts}


def init_params() -> np.ndarray:
    rng = np.random.Generator(np.random.PCG64(FIT_SEED))
    lim1 = math.sqrt(6.0 / (INPUT_WIDTH + LATENT))
    lim2 = math.sqrt(6.0 / (LATENT + 1))
    w1 = rng.uniform(-lim1, lim1, size=(LATENT, INPUT_WIDTH))
    b1 = np.zeros(LATENT, dtype=np.float64)
    w2 = rng.uniform(-lim2, lim2, size=LATENT)
    b2 = np.zeros(1, dtype=np.float64)
    p = np.concatenate([w1.ravel(), b1, w2, b2])
    if len(p) != PARAMS:
        raise AssertionError(len(p))
    return p


def unpack(theta: np.ndarray):
    n1 = LATENT * INPUT_WIDTH
    w1 = theta[:n1].reshape(LATENT, INPUT_WIDTH)
    b1 = theta[n1:n1+LATENT]
    w2 = theta[n1+LATENT:n1+2*LATENT]
    b2 = float(theta[-1])
    return w1, b1, w2, b2


def objective(theta: np.ndarray, x: np.ndarray, mu: np.ndarray, sigma: np.ndarray,
              tr: dict[str, np.ndarray], max_batch_rows: int = 65536) -> tuple[float, np.ndarray]:
    w1, b1, w2, b2 = unpack(theta)
    g1 = np.zeros_like(w1); gb1 = np.zeros_like(b1); g2 = np.zeros_like(w2); gb2 = 0.0
    loss = 0.0
    starts = tr["starts"]; counts = tr["counts"]
    # Batches contain complete parents and preserve original M3 order.
    pi = 0
    while pi < len(starts):
        row_a = int(starts[pi]); pj = pi + 1
        while pj < len(starts) and int(starts[pj] + counts[pj] - row_a) <= max_batch_rows:
            pj += 1
        row_b = int(starts[pj-1] + counts[pj-1])
        xb = (np.asarray(x[row_a:row_b], dtype=np.float64) - mu) / sigma
        a = xb @ w1.T + b1
        z = np.tanh(a)
        residual = z @ w2 + b2
        # L-BFGS-B differentiates the frozen pre-round expression. The C++
        # serializer/runtime applies llround/clamp; all confirmation metrics are
        # computed after serialize/reload with that exact inference contract.
        student_parent = -(tr["t0"][row_a:row_b] + residual)
        local_starts = starts[pi:pj] - row_a
        local_counts = counts[pi:pj]
        p = softmax_segments(student_parent / TEMPERATURE, local_starts, local_counts)
        q = tr["q"][row_a:row_b]
        rw = tr["row_weight"][row_a:row_b]
        loss += float(np.sum(rw * (-q * np.log(np.maximum(p, 1e-300)))))
        # dCE/d(student_parent) = parent_weight * (p-q)/T; parent utility is
        # negative child score, hence the minus into residual_raw.
        gr = -rw * (p - q) / TEMPERATURE
        g2 += z.T @ gr; gb2 += float(gr.sum())
        ga = (gr[:, None] * w2[None, :]) * (1.0 - z*z)
        g1 += ga.T @ xb; gb1 += ga.sum(axis=0)
        pi = pj
    loss += L2 * (float(np.sum(w1*w1)) + float(np.sum(w2*w2)))
    g1 += 2.0 * L2 * w1; g2 += 2.0 * L2 * w2
    grad = np.concatenate([g1.ravel(), gb1, g2, np.asarray([gb2])])
    return loss, grad


def write_model(path: Path, theta: np.ndarray, mu: np.ndarray, sigma: np.ndarray,
                shrink: float = 1.0) -> None:
    w1,b1,w2,b2 = unpack(theta)
    if not (0.0 <= shrink <= 1.0):
        raise ValueError("bad shrink")
    with path.open("wb") as f:
        f.write(b"PL8P")
        f.write(struct.pack("<IIII", 1, INPUT_WIDTH, LATENT, PARAMS))
        f.write(CURRICULUM_SHA.encode("ascii"))
        f.write(struct.pack("<d", shrink))
        for a in (mu, sigma, w1.ravel(), b1, w2, np.asarray([b2])):
            f.write(np.asarray(a, dtype="<f8").tobytes(order="C"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--mode", choices=("sizer", "fit"), required=True)
    ap.add_argument("--model-out", type=Path)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--sizer-max-rows", type=int, default=65536)
    args = ap.parse_args()

    x, source_start, rows = open_pl8x(args.features)
    if args.mode == "sizer" and rows > args.sizer_max_rows:
        rows = args.sizer_max_rows
        x = x[:rows]
    if args.mode == "fit" and args.model_out is None:
        raise ValueError("--model-out required for fit")

    # Mandatory target-free pass happens first.
    mu, sigma, standardize_s = standardize(x)
    groups = load_groups(args.groups)
    tr = prepare_training(groups, source_start, rows, np.asarray(x[:,137]), args.mode == "sizer")
    used_rows = len(tr["parent"])
    x_used = x[:used_rows]
    if used_rows != len(x):
        mu, sigma, standardize_s = standardize(x_used)

    theta0 = init_params()
    t0 = time.perf_counter(); loss0, grad0 = objective(theta0, x_used, mu, sigma, tr); gradient_s = time.perf_counter()-t0
    payload: dict[str, object] = {
        "schema": "jass.pl8_listwise_fit.v1",
        "mode": args.mode,
        "input_width": INPUT_WIDTH, "latent_width": LATENT, "learned_params": PARAMS,
        "temperature_cp": TEMPERATURE, "fit_seed": FIT_SEED, "l2": L2,
        "optimizer": {"name":"L-BFGS-B","maxiter":300,"maxcor":10,"gtol":1e-6,"ftol":1e-12},
        "rows": used_rows, "parents": int(len(tr["starts"])),
        "stratum_parent_counts": [int(v) for v in tr["stratum_counts"]],
        "standardization_target_free": True, "standardization_seconds": standardize_s,
        "initial_loss": float(loss0), "initial_gradient_l2": float(np.linalg.norm(grad0)),
        "gradient_seconds": gradient_s,
        "gradient_rows_per_second": used_rows / gradient_s if gradient_s else 0.0,
        "features_sha256": sha256(args.features), "groups_sha256": sha256(args.groups),
        "curriculum_sha256": CURRICULUM_SHA,
        "fit_runs": 0 if args.mode == "sizer" else 1,
        "fresh_labels": 0, "strength_games": 0, "promotion_authorized": False,
    }
    if args.mode == "sizer":
        payload["verdict"] = "PL8_FIT_SIZER_READY"
        payload["scientific_fit_performed"] = False
    else:
        calls = 0
        def fg(t):
            nonlocal calls
            calls += 1
            return objective(t, x_used, mu, sigma, tr)
        start_fit = time.perf_counter()
        result = minimize(fg, theta0, method="L-BFGS-B", jac=True,
                          options={"maxiter":300,"maxcor":10,"gtol":1e-6,"ftol":1e-12})
        fit_s = time.perf_counter()-start_fit
        if not result.success:
            payload.update({"verdict":"PL8_FIT_TECHNICAL_FAILED","optimizer_success":False,
                            "optimizer_message":str(result.message),"iterations":int(result.nit),
                            "function_gradient_calls":calls,"fit_seconds":fit_s})
            args.report.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
            return 3
        write_model(args.model_out, np.asarray(result.x,dtype=np.float64), mu, sigma, 1.0)
        payload.update({"verdict":"PL8_FIT_COMPLETE_NONTERMINAL","optimizer_success":True,
                        "optimizer_message":str(result.message),"iterations":int(result.nit),
                        "function_gradient_calls":calls,"fit_seconds":fit_s,"final_loss":float(result.fun),
                        "final_gradient_l2":float(np.linalg.norm(result.jac)),
                        "model_sha256":sha256(args.model_out),"scientific_fit_performed":True})
    args.report.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(payload,sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
