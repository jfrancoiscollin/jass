#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mechanical score-proof repair for frozen M3 PatternEval design.

Science is unchanged.  The v1 design builder used a BLAS extras dot-product and
`100 * eval / scale`, while production ScanEvalNetwork accumulates dense extras
in ascending feature order and computes `(eval / scale) * 100`.  On the frozen
M3 corpus this changed only floating-point operation order, producing 197
one-centipawn truncation mismatches out of 928639 rows.  This wrapper reuses the
entire frozen v1 design implementation and replaces only the audit scalar with
production operation order.  The proof remains exact: any mismatch is fatal.
"""
from __future__ import annotations

import numpy as np

import micro_search_m3_design as base


def production_score_check_exact(ds, extras: np.ndarray,
                                 groups: dict[str, np.ndarray],
                                 raw_cols: np.ndarray, wmg: np.ndarray,
                                 scale: int, n_pat: int, n_ext: int,
                                 w: np.ndarray) -> dict:
    pat_mg = w[:n_pat]
    pat_eg = w[n_pat:2 * n_pat]
    ext_mg = w[2 * n_pat:2 * n_pat + n_ext]
    ext_eg = w[2 * n_pat + n_ext:]
    n, npat = raw_cols.shape

    # Production accumulates pattern weights as int64 before conversion.
    smg = np.zeros(n, dtype=np.int64)
    seg = np.zeros(n, dtype=np.int64)
    for p in range(npat):
        smg += pat_mg[raw_cols[:, p]]
        seg += pat_eg[raw_cols[:, p]]

    # Production compute_extras returns float32 and ScanEvalNetwork then adds
    # each dense term in ascending feature-index order.  Vectorise across rows,
    # never across features, so every row sees byte-equivalent add ordering.
    emg = np.zeros(n, dtype=np.float64)
    eeg = np.zeros(n, dtype=np.float64)
    for e in range(n_ext):
        x = extras[:, e].astype(np.float64, copy=False)
        emg += float(ext_mg[e]) * x
        eeg += float(ext_eg[e]) * x

    weg = 1.0 - wmg
    eval_black = (wmg * (smg.astype(np.float64) + emg)
                  + weg * (seg.astype(np.float64) + eeg))
    # Match C++ exactly: pu_black = eval_black / scale; cp_black=pu_black*100.
    pu_black = eval_black / float(scale)
    black_cp = pu_black * 100.0
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
            f"production design equivalence failed after exact-order repair: "
            f"{mism}/{n} rows, max_abs_cp={max_abs}, first={first} "
            f"pred={pred[first]} t0={target[first]}"
        )
    return {
        "rows_checked": int(n),
        "rows_exact": int(n),
        "mismatches": 0,
        "max_abs_cp": 0,
        "production_t0_integer_score_exact": True,
        "audit_operation_order": "ScanEvalNetwork_v3_exact",
        "mechanical_repair_from_v1": "sequential_extras_and_divide_then_multiply",
    }


base.production_score_check = production_score_check_exact

if __name__ == "__main__":
    base.main()
