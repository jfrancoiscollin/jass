#!/usr/bin/env python3
"""JFI diagonal-identifiability report over a sparse PatternEval design.

The input is a NumPy ``.npz`` CSR archive containing ``indptr``, ``indices``,
``data`` and scalar ``n_cols``.  Optional ``probability`` and ``target`` arrays
enable logistic Fisher and gradient calculations.  Omitting ``target`` is the
fail-closed feature-only mode and is recorded as ``TARGET_READS=0``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def diagonal_statistics(indptr, indices, values, n_cols, probability=None, target=None):
    indptr = np.asarray(indptr, dtype=np.int64)
    indices = np.asarray(indices, dtype=np.int64)
    values = np.asarray(values, dtype=np.float64)
    if indptr.ndim != 1 or len(indptr) < 1 or indptr[0] != 0 or indptr[-1] != len(indices):
        raise ValueError("invalid CSR indptr")
    if indices.shape != values.shape or np.any(indices < 0) or np.any(indices >= n_cols):
        raise ValueError("invalid CSR indices/data")
    rows = len(indptr) - 1
    row_index = np.repeat(np.arange(rows, dtype=np.int64), np.diff(indptr))
    visits = np.bincount(indices, minlength=n_cols).astype(np.int64)
    squared_design = np.bincount(indices, weights=values * values, minlength=n_cols)
    if probability is None:
        probability = np.full(rows, 0.5, dtype=np.float64)
    probability = np.asarray(probability, dtype=np.float64)
    if probability.shape != (rows,) or np.any(~np.isfinite(probability)):
        raise ValueError("probability must be a finite vector aligned to rows")
    fisher_weight = probability * (1.0 - probability)
    fisher = np.bincount(
        indices,
        weights=values * values * fisher_weight[row_index],
        minlength=n_cols,
    )
    gradient = None
    if target is not None:
        target = np.asarray(target, dtype=np.float64)
        if target.shape != (rows,) or np.any(~np.isfinite(target)):
            raise ValueError("target must be a finite vector aligned to rows")
        gradient = np.bincount(
            indices,
            weights=values * (probability[row_index] - target[row_index]),
            minlength=n_cols,
        )
    return visits, squared_design, fisher, gradient


def summarize(fisher, visits, l2):
    fisher = np.asarray(fisher, dtype=np.float64)
    visits = np.asarray(visits, dtype=np.int64)
    if l2 < 0 or np.any(fisher < 0) or fisher.shape != visits.shape:
        raise ValueError("invalid Fisher/visits/l2")
    unseen = visits == 0
    if l2 == 0:
        variance = np.full_like(fisher, np.inf)
        positive = fisher > 0
        variance[positive] = 1.0 / fisher[positive]
        effective = positive.astype(np.float64)
        ratio = np.where(positive, np.inf, 0.0)
    else:
        variance = 1.0 / (fisher + l2)
        effective = fisher / (fisher + l2)
        ratio = fisher / l2
    classes = np.full(len(fisher), "MIXED", dtype="U15")
    classes[unseen] = "UNSEEN"
    classes[(~unseen) & (ratio < 0.1)] = "PRIOR_DOMINATED"
    classes[ratio > 10.0] = "DATA_DOMINATED"
    return variance, effective, ratio, classes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--design", required=True)
    ap.add_argument("--l2", required=True, type=float)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    with np.load(args.design, allow_pickle=False) as archive:
        required = {"indptr", "indices", "data", "n_cols"}
        missing = required.difference(archive.files)
        if missing:
            raise SystemExit(f"design archive missing: {sorted(missing)}")
        probability = archive["probability"] if "probability" in archive.files else None
        target = archive["target"] if "target" in archive.files else None
        visits, squared, fisher, gradient = diagonal_statistics(
            archive["indptr"], archive["indices"], archive["data"],
            int(archive["n_cols"]), probability, target,
        )
        rows = int(len(archive["indptr"]) - 1)
    variance, effective, ratio, classes = summarize(fisher, visits, args.l2)
    finite_variance = variance[np.isfinite(variance)]
    report = {
        "schema": "jass.jfi.identifiability.v1",
        "rows": rows,
        "coordinates": int(len(visits)),
        "l2": args.l2,
        "TARGET_READS": int(target is not None),
        "SCAN_READS": 0,
        "class_counts": {name: int(np.count_nonzero(classes == name)) for name in
                         ("UNSEEN", "PRIOR_DOMINATED", "MIXED", "DATA_DOMINATED")},
        "effective_df": float(np.sum(effective)),
        "fisher_quantiles": np.quantile(fisher, [0, .25, .5, .75, 1]).tolist(),
        "posterior_variance_finite_quantiles": (
            np.quantile(finite_variance, [0, .25, .5, .75, 1]).tolist()
            if len(finite_variance) else []
        ),
        "infinite_posterior_variance": int(np.count_nonzero(~np.isfinite(variance))),
        "visit_sum": int(np.sum(visits)),
        "squared_design_sum": float(np.sum(squared)),
        "data_gradient_norm": float(np.linalg.norm(gradient)) if gradient is not None else None,
    }
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
