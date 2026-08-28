#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mechanical exact-score proof repair for frozen M3 PatternEval design.

Science is unchanged. v2 matched production summation order but still left a
small number of 1-cp audit mismatches because the Release C++ evaluator is built
with GCC's default FP contraction: dense-tail `acc += w*x` and the final
`wmg*A + weg*B` compile to scalar FMA on cpx62. This wrapper reuses the entire
frozen v1 design implementation and changes only the audit arithmetic so it
matches the production Release operation sequence exactly. Any mismatch remains
fatal; no tolerance is introduced.
"""
from __future__ import annotations

import math
import numpy as np

import micro_search_m3_design as base


def production_score_check_fma(ds, extras: np.ndarray,
                               groups: dict[str, np.ndarray],
                               raw_cols: np.ndarray, wmg: np.ndarray,
                               scale: int, n_pat: int, n_ext: int,
                               w: np.ndarray) -> dict:
    pat_mg = w[:n_pat]
    pat_eg = w[n_pat:2 * n_pat]
    ext_mg = w[2 * n_pat:2 * n_pat + n_ext]
    ext_eg = w[2 * n_pat + n_ext:]
    n, npat = raw_cols.shape

    # Production pattern accumulator is signed int64, then converted to double.
    smg = np.zeros(n, dtype=np.int64)
    seg = np.zeros(n, dtype=np.int64)
    for p in range(npat):
        smg += pat_mg[raw_cols[:, p]]
        seg += pat_eg[raw_cols[:, p]]

    # Reproduce ScanEvalNetwork::evaluate exactly. King PST one-hots are added
    # (not multiplied) in ascending index order. Dense tail e>=100 is compiled
    # from `acc += weight*x` to scalar FMA in the Release build.
    if n_ext < 100:
        raise SystemExit(f"production extras layout drift: n_ext={n_ext}")
    emg = np.zeros(n, dtype=np.float64)
    eeg = np.zeros(n, dtype=np.float64)
    for e in range(min(100, n_ext)):
        mask = extras[:, e] != 0.0
        if np.any(extras[mask, e] != 1.0):
            raise SystemExit(f"king PST extra {e} is not one-hot")
        if np.any(mask):
            emg[mask] += float(ext_mg[e])
            eeg[mask] += float(ext_eg[e])

    # Scalar loops are deliberate: Python math.fma specifies the same one-round
    # fused multiply-add semantics as the vfmadd used by GCC -O2 -march=native.
    tail0 = 100
    black_cp = np.empty(n, dtype=np.float64)
    for i in range(n):
        amg = float(emg[i]); aeg = float(eeg[i])
        for e in range(tail0, n_ext):
            x = float(extras[i, e])
            amg = math.fma(float(ext_mg[e]), x, amg)
            aeg = math.fma(float(ext_eg[e]), x, aeg)
        a = float(smg[i]) + amg
        b = float(seg[i]) + aeg
        wm = float(wmg[i]); we = 1.0 - wm
        # GCC emits: tmp = weg*b; eval = fma(wmg, a, tmp).
        eval_black = math.fma(wm, a, we * b)
        pu_black = eval_black / float(scale)
        black_cp[i] = pu_black * 100.0

    parent_sign = np.where(groups["parent_stm"] == 1, 1.0, -1.0)
    pred = np.trunc(parent_sign * black_cp).astype(np.int64)
    pred = np.clip(pred, -20000, 20000)
    target = groups["t0_parent"].astype(np.int64)
    diff = pred - target
    mism = int(np.count_nonzero(diff))
    max_abs = int(np.max(np.abs(diff))) if n else 0
    if mism:
        first = int(np.flatnonzero(diff)[0])
        raise SystemExit(
            f"production design equivalence failed after exact-FMA repair: "
            f"{mism}/{n} rows, max_abs_cp={max_abs}, first={first} "
            f"pred={pred[first]} t0={target[first]}"
        )
    return {
        "rows_checked": int(n),
        "rows_exact": int(n),
        "mismatches": 0,
        "max_abs_cp": 0,
        "production_t0_integer_score_exact": True,
        "audit_operation_order": "ScanEvalNetwork_v3_release_exact_fma",
        "mechanical_repair_from_v2": "release_fp_contraction_exact",
    }


base.production_score_check = production_score_check_fma

if __name__ == "__main__":
    base.main()
