#!/usr/bin/env python3
"""Frozen CLS-L multi-objective optimisation kernel.

This module implements only the algebra preregistered by
``L3_CLS_L_OBJECTIVE_ATTRIBUTION_V1_20260916``.  It deliberately does not know
how to fetch campaign inputs, choose arms, inspect holdout metrics, run search,
or promote a model.

The two data terms are ordinary mean logistic cross-entropies over one identical
TRAIN row set and one identical design matrix.  MIXED normalises the unregularised
TRAIN gradients at the projected CURRICULUM point ``w0`` and freezes lambda=0.5:

    0.5 * L_LOCAL / ||g_LOCAL(w0)||_2
  + 0.5 * L_WDL   / ||g_WDL(w0)||_2
  + 0.5 * l2 * ||w - w0||_2^2

The parent-centred regulariser is therefore applied exactly once.  Holdout rows
are not accepted by the normalisation API: callers pass the exact TRAIN index
vector explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Mapping, Sequence

import numpy as np
from scipy.optimize import minimize

Array = np.ndarray
BuildFn = Callable[[Array], object]
EPS = 1e-12
FROZEN_LAMBDA = 0.5


class ObjectiveError(ValueError):
    """Fail-closed contract error for the CLS-L objective kernel."""


@dataclass(frozen=True)
class DataTerm:
    name: str
    targets: Array
    coefficient: float
    gradient_norm: float = 1.0

    @property
    def scale(self) -> float:
        return self.coefficient / self.gradient_norm


def _rows(rows: Sequence[int] | Array) -> Array:
    out = np.asarray(rows, dtype=np.int64)
    if out.ndim != 1 or len(out) == 0:
        raise ObjectiveError("TRAIN rows must be a non-empty 1-D index vector")
    if np.any(out < 0):
        raise ObjectiveError("TRAIN rows contain a negative index")
    if len(np.unique(out)) != len(out):
        raise ObjectiveError("TRAIN rows contain duplicates")
    return out


def _targets(values: Array, *, name: str, max_row: int) -> Array:
    out = np.asarray(values, dtype=np.float64)
    if out.ndim != 1:
        raise ObjectiveError(f"{name} targets must be 1-D")
    if len(out) <= max_row:
        raise ObjectiveError(f"{name} targets do not cover the TRAIN rows")
    if not bool(np.all(np.isfinite(out))):
        raise ObjectiveError(f"{name} targets contain NaN/inf")
    if bool(np.any(out < 0.0)) or bool(np.any(out > 1.0)):
        raise ObjectiveError(f"{name} targets must lie in [0,1]")
    return out


def logistic_data_loss_grad(
    build_fn: BuildFn,
    rows: Sequence[int] | Array,
    targets: Array,
    weights: Array,
    *,
    batch: int,
) -> tuple[float, Array]:
    """Exact mean logistic data loss/gradient over the supplied TRAIN rows.

    This intentionally mirrors ``train.train_lbfgs_chunked``: same tanh sigmoid,
    epsilon and full-batch averaging.  No regularisation is included here.
    """
    tr = _rows(rows)
    if batch <= 0:
        raise ObjectiveError("batch must be positive")
    w = np.asarray(weights, dtype=np.float64)
    if w.ndim != 1 or len(w) == 0 or not bool(np.all(np.isfinite(w))):
        raise ObjectiveError("weights must be a finite non-empty 1-D vector")
    y = _targets(targets, name="data", max_row=int(tr.max()))

    total = 0.0
    grad = np.zeros_like(w)
    for start in range(0, len(tr), batch):
        selected = tr[start:start + batch]
        X = build_fn(selected)
        if getattr(X, "shape", None) != (len(selected), len(w)):
            raise ObjectiveError(
                f"design shape drift: got {getattr(X, 'shape', None)}, "
                f"expected {(len(selected), len(w))}"
            )
        z = np.asarray(X @ w, dtype=np.float64)
        yc = y[selected]
        p = 0.5 * (np.tanh(0.5 * z) + 1.0)
        ce = -(yc * np.log(p + EPS) + (1.0 - yc) * np.log(1.0 - p + EPS))
        resid = p - yc
        total += float(np.sum(ce))
        grad += np.asarray(X.T @ resid, dtype=np.float64).reshape(-1)
    n = float(len(tr))
    return total / n, grad / n


def frozen_gradient_norms(
    build_fn: BuildFn,
    train_rows: Sequence[int] | Array,
    local_targets: Array,
    wdl_targets: Array,
    w0: Array,
    *,
    batch: int,
) -> dict[str, float]:
    """Compute the preregistered TRAIN-only unregularised norms at ``w0``."""
    tr = _rows(train_rows)
    local = _targets(local_targets, name="LOCAL", max_row=int(tr.max()))
    wdl = _targets(wdl_targets, name="WDL", max_row=int(tr.max()))
    _, gl = logistic_data_loss_grad(build_fn, tr, local, w0, batch=batch)
    _, gw = logistic_data_loss_grad(build_fn, tr, wdl, w0, batch=batch)
    norms = {
        "LOCAL": float(np.linalg.norm(gl, ord=2)),
        "WDL": float(np.linalg.norm(gw, ord=2)),
    }
    for name, value in norms.items():
        if not math.isfinite(value) or value <= 0.0:
            raise ObjectiveError(f"{name} TRAIN gradient norm must be finite and >0, got {value}")
    return norms


def objective_loss_grad(
    build_fn: BuildFn,
    train_rows: Sequence[int] | Array,
    weights: Array,
    terms: Sequence[DataTerm],
    *,
    parent: Array,
    l2: float,
    batch: int,
) -> tuple[float, Array]:
    """Combine frozen data terms and apply the common parent ridge exactly once."""
    tr = _rows(train_rows)
    w = np.asarray(weights, dtype=np.float64)
    w0 = np.asarray(parent, dtype=np.float64)
    if w.shape != w0.shape or w.ndim != 1:
        raise ObjectiveError("weights/parent geometry mismatch")
    if not math.isfinite(float(l2)) or l2 < 0.0:
        raise ObjectiveError("l2 must be finite and non-negative")
    if not terms:
        raise ObjectiveError("at least one data term is required")

    loss = 0.0
    grad = np.zeros_like(w)
    for term in terms:
        if not term.name:
            raise ObjectiveError("data term name must be non-empty")
        if not math.isfinite(term.coefficient) or term.coefficient < 0.0:
            raise ObjectiveError(f"{term.name} coefficient is invalid")
        if not math.isfinite(term.gradient_norm) or term.gradient_norm <= 0.0:
            raise ObjectiveError(f"{term.name} gradient norm is invalid")
        target = _targets(term.targets, name=term.name, max_row=int(tr.max()))
        term_loss, term_grad = logistic_data_loss_grad(
            build_fn, tr, target, w, batch=batch
        )
        loss += term.scale * term_loss
        grad += term.scale * term_grad

    diff = w - w0
    loss += 0.5 * float(l2) * float(np.dot(diff, diff))
    grad += float(l2) * diff
    return loss, grad


def mixed_terms(local_targets: Array, wdl_targets: Array, norms: Mapping[str, float]) -> tuple[DataTerm, DataTerm]:
    """Construct the only allowed MIXED V1 data-term pair."""
    if set(norms) != {"LOCAL", "WDL"}:
        raise ObjectiveError("mixed norms must contain exactly LOCAL and WDL")
    return (
        DataTerm("LOCAL", np.asarray(local_targets), FROZEN_LAMBDA, float(norms["LOCAL"])),
        DataTerm("WDL", np.asarray(wdl_targets), 1.0 - FROZEN_LAMBDA, float(norms["WDL"])),
    )


def fit_mixed(
    build_fn: BuildFn,
    train_rows: Sequence[int] | Array,
    local_targets: Array,
    wdl_targets: Array,
    parent: Array,
    *,
    l2: float,
    batch: int,
    max_iter: int,
    maxcor: int,
    gtol: float,
) -> tuple[Array, dict[str, object]]:
    """Fit the frozen MIXED V1 objective from the projected CURRICULUM point."""
    tr = _rows(train_rows)
    w0 = np.asarray(parent, dtype=np.float64)
    if w0.ndim != 1 or len(w0) == 0 or not bool(np.all(np.isfinite(w0))):
        raise ObjectiveError("parent must be a finite non-empty 1-D vector")
    if max_iter <= 0 or maxcor <= 0 or not math.isfinite(gtol) or gtol <= 0.0:
        raise ObjectiveError("invalid L-BFGS controls")

    norms = frozen_gradient_norms(
        build_fn, tr, local_targets, wdl_targets, w0, batch=batch
    )
    terms = mixed_terms(local_targets, wdl_targets, norms)

    def fn(w: Array) -> tuple[float, Array]:
        return objective_loss_grad(
            build_fn, tr, w, terms, parent=w0, l2=l2, batch=batch
        )

    result = minimize(
        fn,
        w0.copy(),
        jac=True,
        method="L-BFGS-B",
        options={"maxiter": int(max_iter), "maxcor": int(maxcor), "gtol": float(gtol)},
    )
    receipt: dict[str, object] = {
        "schema": "jass.cls_l_mixed_normalization.v1",
        "normalization_scope": "TRAIN_ONLY",
        "normalization_point": "projected_CURRICULUM_w0",
        "regularization": "CURRICULUM_centered_once",
        "lambda_normalized_gradient": FROZEN_LAMBDA,
        "train_rows": int(len(tr)),
        "gradient_norms": norms,
        "optimizer": {
            "success": bool(result.success),
            "status": int(result.status),
            "message": str(result.message),
            "iterations": int(result.nit),
            "function_evaluations": int(result.nfev),
            "final_objective": float(result.fun),
            "gradient_inf_norm": float(np.max(np.abs(result.jac))),
            "max_iterations": int(max_iter),
            "maxcor": int(maxcor),
            "gtol": float(gtol),
        },
    }
    return np.asarray(result.x, dtype=np.float64), receipt
