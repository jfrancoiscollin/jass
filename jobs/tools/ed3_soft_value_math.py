#!/usr/bin/env python3
"""ED3-P1: one fixed soft-preference objective, in original ED2 coordinates.

The teacher scale is a TRAIN statistic defined by the ED3-P0 preregistration.
It is neither a fitted temperature nor a win probability. No held-out data
is accepted by this module.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

WIDTH = 240
RIDGE = 0.001
SOLVER = dict(method='trust-exact', maxiter=500, gtol=1e-6,
              initial_trust_radius=1.0, max_trust_radius=1000.0, eta=0.15)
TEMPERATURE_RULE = 'weighted_median_positive_train_gap_div_log3'
RECIPE = dict(schema='jass.ed3.soft_value_recipe.v1', width=WIDTH, l2=RIDGE,
              pair_coefficient=1.0, wdl_coefficient=1.0,
              solver=SOLVER, initialization='zero_residual',
              temperature_rule=TEMPERATURE_RULE, temperature_sweep=0,
              scientific_fits=1, fit_timeout_seconds=300,
              production_parent_normalizer=512)


class NumericalFailure(RuntimeError):
    """A technical/numerical failure, never a scientific negative."""


def recipe_sha256() -> str:
    raw = json.dumps(RECIPE, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def train_temperature(gaps: np.ndarray, masses: np.ndarray) -> float:
    gaps = np.asarray(gaps, dtype=np.float64)
    masses = np.asarray(masses, dtype=np.float64)
    if (gaps.ndim != 1 or not gaps.size or masses.shape != gaps.shape
            or not np.isfinite(gaps).all() or not np.isfinite(masses).all()
            or np.any(gaps <= 0) or np.any(masses <= 0)):
        raise ValueError('invalid TRAIN gaps or parent masses')
    order = np.argsort(gaps, kind='stable')
    cumulative = np.cumsum(masses[order])
    i = np.searchsorted(cumulative, masses.sum()/2, side='left')
    tau = float(gaps[order[i]] / np.log(3.0))
    if not np.isfinite(tau) or tau <= 0:
        raise ValueError('invalid TRAIN temperature')
    return tau


def design(phi, z, edges, replay_x, replay_z, y, tau):
    """Cache differences once. Sign is parent POV, not child side-to-move."""
    phi, z, rx, rz, y = (np.asarray(a, dtype=np.float64)
                         for a in (phi, z, replay_x, replay_z, y))
    win, lose, mass, sign, gaps = edges
    win, lose = np.asarray(win), np.asarray(lose)
    mass, sign, gaps = (np.asarray(a, dtype=np.float64) for a in (mass, sign, gaps))
    if (phi.ndim != 2 or phi.shape[1] != WIDTH or z.shape != (len(phi),)
            or y.ndim != 1 or not len(y) or rx.shape != (len(y), WIDTH)
            or rz.shape != y.shape or win.ndim != 1 or not win.size
            or any(a.shape != win.shape for a in (lose, mass, sign, gaps))
            or win.dtype.kind not in 'iu' or lose.dtype.kind not in 'iu'
            or np.any(win >= len(phi)) or np.any(lose >= len(phi))
            or np.any(win < 0) or np.any(lose < 0) or np.any(win == lose)
            or not all(np.isfinite(a).all() for a in (phi,z,rx,rz,y,mass,sign,gaps))
            or np.any((y < 0) | (y > 1)) or np.any(mass <= 0)
            or np.any(gaps <= 0) or np.any(~np.isin(sign, (-1.0, 1.0)))
            or not np.isfinite(tau) or tau <= 0):
        raise ValueError('ED3 dimensions/nonfinite/POV/support')
    dx = sign[:, None] * (phi[win] - phi[lose])
    d0 = sign * (z[win] - z[lose])
    probability = expit(gaps / tau)
    return dx, d0, mass, probability, rx, rz, y


def derivatives(beta, dx, d0, mass, probability, rx, rz, y):
    """Value, gradient, exact Hessian. Stable also when a target rounds to one."""
    beta = np.asarray(beta, dtype=np.float64)
    if beta.shape != (WIDTH,) or not np.isfinite(beta).all():
        raise ValueError('invalid residual')
    margin = d0 + dx @ beta
    pp, pn = expit(margin), expit(-margin)
    pred = rz + rx @ beta
    rp, rn = expit(pred), expit(-pred)
    pair_loss = probability * np.logaddexp(0, -margin) + (1-probability)*np.logaddexp(0, margin)
    # This form avoids cancellation in the hard-target limit p=1.
    force = (1-probability)*pp - probability*pn
    value = float(mass @ pair_loss + np.mean(np.logaddexp(0, pred)-y*pred)
                  + 0.5*RIDGE*(beta @ beta))
    grad = dx.T @ (mass*force) + rx.T @ (rp-y)/len(y) + RIDGE*beta
    hess = ((dx.T*(mass*pp*pn)) @ dx
            + (rx.T*(rp*rn/len(y))) @ rx + RIDGE*np.eye(WIDTH))
    return value, grad, hess


def fit(phi, z, edges, replay_x, replay_z, y, tau, report_path: Path | None = None):
    args = design(phi, z, edges, replay_x, replay_z, y, tau)
    # scipy may ask for value/gradient and Hessian at the same point; cache the
    # exact result without changing arithmetic, solver or convergence criteria.
    last_beta = None
    last = None
    def at(beta):
        nonlocal last_beta, last
        if last_beta is None or not np.array_equal(beta, last_beta):
            last = derivatives(beta, *args)
            last_beta = beta.copy()
        return last
    result = minimize(lambda b: at(b)[:2], np.zeros(WIDTH), jac=True,
                      hess=lambda b: at(b)[2], method=SOLVER['method'],
                      options={k:v for k,v in SOLVER.items() if k != 'method'})
    value, gradient, _ = derivatives(result.x, *args)
    norm = float(np.linalg.norm(gradient))
    report = dict(schema='jass.ed3.soft_value_fit.v1', recipe=RECIPE,
                  recipe_sha256=recipe_sha256(), tau=float(tau),
                  success=bool(result.success), status=int(result.status),
                  iterations=int(result.nit), function_calls=int(result.nfev),
                  hessian_calls=int(result.nhev), objective=float(value),
                  gradient_l2=norm, gradient_max=float(np.max(np.abs(gradient))),
                  objective_gap_upper_bound=float(gradient @ gradient/(2*RIDGE)),
                  zero_initialization=True, restarts=0,
                  train_rows=len(phi), replay_rows=len(y), pair_count=len(edges[0]))
    finite = np.isfinite(result.x).all() and np.isfinite(value) and np.isfinite(norm)
    if report_path is not None and finite:
        with Path(report_path).open('x') as out:
            json.dump(report, out, sort_keys=True, indent=2, allow_nan=False)
            out.write('\n')
    if not result.success or not finite or norm > 1e-6:
        raise NumericalFailure('ED3_SOFT_OPTIMIZER_DID_NOT_CONVERGE')
    return result.x, report
