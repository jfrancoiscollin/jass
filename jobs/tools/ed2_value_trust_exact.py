#!/usr/bin/env python3
"""ED2-N1 numerical solver: unchanged convex objective, exact Hessian.

This is an explicitly versioned optimizer amendment, not a retune of labels,
loss weights or held-out gates. The frozen ED2-P1 implementation stays intact.
"""
from __future__ import annotations
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

SOLVER = dict(method='trust-exact', maxiter=500, gtol=1e-6,
              initial_trust_radius=1.0, max_trust_radius=1000.0, eta=0.15)


def derivatives(beta, phi, z, edges, replay_x, replay_z, y, ridge=0.001):
    """Exact gradient and Hessian of the frozen, unscaled-coordinate objective."""
    win, lose, weight, sign = edges
    dx = sign[:, None] * (phi[win] - phi[lose])
    margin = sign * (z[win] - z[lose]) + dx @ beta
    pp = expit(margin)
    pred = replay_z + replay_x @ beta
    rp = expit(pred)
    value = (float(weight @ np.logaddexp(0.0, -margin))
             + float(np.mean(np.logaddexp(0.0, pred) - y * pred))
             + 0.5 * ridge * float(beta @ beta))
    gradient = (dx.T @ (-weight * expit(-margin))
                + replay_x.T @ (rp - y) / len(y) + ridge * beta)
    hessian = ((dx.T * (weight * pp * expit(-margin))) @ dx
               + (replay_x.T * (rp * expit(-pred) / len(y))) @ replay_x
               + ridge * np.eye(beta.size))
    return value, gradient, hessian


def fit(phi, z, edges, replay_x, replay_z, y):
    from jobs.tools import ed2_value_math as original
    arrays = (phi, z, replay_x, replay_z, y, *edges)
    if (phi.ndim != 2 or phi.shape[1] != original.WIDTH
            or replay_x.shape != (len(y), original.WIDTH) or not len(y)
            or not all(np.all(np.isfinite(x)) for x in arrays)):
        raise ValueError('ED2-N1 dimensions/nonfinite/support')
    if np.any(edges[2] < 0) or original.L2 != 0.001:
        raise ValueError('ED2-N1 frozen convex objective drift')
    args = (phi, z, edges, replay_x, replay_z, y)
    # Use the ORIGINAL function/gradient, not a replacement training objective.
    def hess(beta, *_args):
        return derivatives(beta, *args, ridge=original.L2)[2]
    result = minimize(original.objective, np.zeros(original.WIDTH), args=args,
                      method='trust-exact', jac=True, hess=hess,
                      options={k: v for k, v in SOLVER.items() if k != 'method'})
    value, gradient = original.objective(result.x, *args)
    norm = float(np.linalg.norm(gradient))
    report = dict(schema='jass.ed2.numerical_solver_n1.v1', solver=SOLVER,
                  success=bool(result.success), iterations=int(result.nit),
                  function_calls=int(result.nfev), hessian_calls=int(result.nhev),
                  message=str(result.message), objective=float(value),
                  gradient_l2=norm, gradient_max=float(np.max(np.abs(gradient))),
                  # L2-strong convexity gives this analytic objective-gap bound.
                  objective_gap_upper_bound=float(gradient @ gradient / (2 * original.L2)),
                  zero_initialization=True, restarts=0)
    if (not result.success or not np.all(np.isfinite(result.x))
            or not np.isfinite(value) or not np.isfinite(norm) or norm > 1e-6):
        raise ValueError('ED2-N1 optimizer failure: ' + str(report))
    return result.x, report
