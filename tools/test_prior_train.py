#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Unit tests for the sequential-Bayesian prior in train_stream / train_lbfgs_chunked.

Covers the correctness-critical pieces:
  (1) color-fold FOLD-BACK round-trips (full -> canonical -> full is identity), so
      the prior mean μ projected from a champion PJTW matches the champion exactly ;
  (2) train_lbfgs_chunked with prior OFF == an INDEPENDENT plain-L2 reference
      (the refactor did not change the default path) ;
  (3) prior reduces to plain L2 when prec=l2 (uniform) and μ=0 ;
  (4) a strong prior (huge precision) pulls the solution to μ.
  (5) warm-start changes only x0: with the same plain-L2 objective it converges
      to the same optimum as the zero-started fit.
"""
import os
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'pattern_jass' / 'tools'))
import patterns                                             # noqa: E402
from train import (CF_BUCKETS, PJTW_SELFDESC_BIT, WEIGHTS_MAGIC,
                   colorfold_maps, load_v3_weights_float,
                   train_lbfgs_chunked)  # noqa: E402


def test_self_describing_v3_loader():
    """The Python continuation loader accepts the v3 files emitted today."""
    n_pat, n_ext, scale = 2, 1, 1000
    weights = np.arange(2 * (n_pat + n_ext), dtype='<i4')
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'selfdesc-v3.pjtw'
        path.write_bytes(
            struct.pack('<IIIII', WEIGHTS_MAGIC,
                        3 | PJTW_SELFDESC_BIT, scale, n_pat, n_ext)
            + weights.tobytes())
        loaded, got_scale, got_n_pat, got_n_ext = load_v3_weights_float(str(path))
        assert got_scale == scale
        assert got_n_pat == n_pat and got_n_ext == n_ext
        assert np.array_equal(loaded, weights.astype(np.float64) / scale)

        bad = Path(td) / 'selfdesc-v4.pjtw'
        bad.write_bytes(
            struct.pack('<IIIII', WEIGHTS_MAGIC,
                        4 | PJTW_SELFDESC_BIT, scale, n_pat, n_ext)
            + weights.tobytes())
        try:
            load_v3_weights_float(str(bad))
        except SystemExit:
            pass
        else:
            raise AssertionError('v3 loader accepted a self-describing v4 file')
    print('  [ok] loader accepts self-describing v3 and rejects v4')


def test_colorfold_foldback_roundtrip():
    """full = expand(canon) ; foldback(full) must recover canon (per pattern)."""
    U2C, U2S = colorfold_maps()
    NB = patterns.BUCKETS_PER_PATTERN
    assert len(U2C) == NB
    rng = np.random.default_rng(1)
    canon = rng.standard_normal(CF_BUCKETS)
    canon[0] = 0.0                                          # colour-swap fixpoint weight
    # forward expand (one pattern) : full[b] = sign[b]·canon[|signed(b)|]
    full = U2S.astype(np.float64) * canon[U2C]
    # fold-back : rep bucket per canonical class, canon[cc] = full[rep]·sign[rep]
    rep_b = np.empty(CF_BUCKETS, dtype=np.int64)
    rep_b[U2C] = np.arange(NB, dtype=np.int64)
    recovered = full[rep_b] * U2S[rep_b].astype(np.float64)
    assert np.allclose(recovered, canon, atol=1e-12), \
        f'fold-back mismatch : max |Δ|={np.abs(recovered-canon).max():.2e}'
    print('  [ok] color-fold fold-back round-trips exactly')


def _toy_problem(seed=0, n=300, ncols=6):
    rng = np.random.default_rng(seed)
    X = (rng.standard_normal((n, ncols)) * (rng.random((n, ncols)) < 0.5)).astype(np.float64)
    w_true = rng.standard_normal(ncols)
    p = 1.0 / (1.0 + np.exp(-(X @ w_true)))
    y = (rng.random(n) < p).astype(np.float64)
    Xcsr = sp.csr_matrix(X)
    tr_idx = np.arange(n, dtype=np.int64)

    def build_fn(sel):
        lo = int(sel[0]); hi = int(sel[-1]) + 1
        return Xcsr[lo:hi]
    return build_fn, tr_idx, y, X, ncols


def _ref_plain_l2(X, y, l2, max_iter):
    """Independent full-batch reference of the DEFAULT objective (prior OFF)."""
    n, ncols = X.shape; eps = 1e-12

    def lg(w):
        z = X @ w
        p = 0.5 * (np.tanh(0.5 * z) + 1.0)
        ce = -(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
        g = X.T @ (p - y)
        return ce.sum() / n + 0.5 * l2 * w @ w, g / n + l2 * w
    r = minimize(lg, np.zeros(ncols), jac=True, method='L-BFGS-B',
                 options={'maxiter': max_iter, 'maxcor': 5})
    return r.x


def test_prior_off_matches_plain_l2():
    build_fn, tr_idx, y, X, nc = _toy_problem(seed=2)
    l2 = 1e-2
    w_off, _, _ = train_lbfgs_chunked(build_fn, tr_idx, y, l2, 200, True, nc, 128)
    w_ref = _ref_plain_l2(X, y, l2, 200)
    assert np.allclose(w_off, w_ref, atol=1e-6), \
        f'prior-OFF drifted from plain-L2 reference : max|Δ|={np.abs(w_off-w_ref).max():.2e}'
    print('  [ok] prior OFF == independent plain-L2 reference')


def test_prior_uniform_prec_equals_l2():
    build_fn, tr_idx, y, X, nc = _toy_problem(seed=3)
    l2 = 1e-2
    w_off, _, _ = train_lbfgs_chunked(build_fn, tr_idx, y, l2, 200, True, nc, 128)
    mu = np.zeros(nc); prec = np.full(nc, l2)               # μ=0, uniform prec=l2 == ridge
    w_prior, _, _ = train_lbfgs_chunked(build_fn, tr_idx, y, l2, 200, True, nc, 128,
                                        prior_mean=mu, prior_prec=prec)
    assert np.allclose(w_off, w_prior, atol=1e-6), \
        f'prior(μ=0,prec=l2) != plain L2 : max|Δ|={np.abs(w_off-w_prior).max():.2e}'
    print('  [ok] prior with μ=0, prec=l2 reduces to plain L2')


def test_strong_prior_pulls_to_mu():
    build_fn, tr_idx, y, X, nc = _toy_problem(seed=4)
    rng = np.random.default_rng(9)
    mu = rng.standard_normal(nc)
    prec = np.full(nc, 1e6)                                 # overwhelming prior
    w_prior, _, _ = train_lbfgs_chunked(build_fn, tr_idx, y, 1e-2, 300, True, nc, 128,
                                        prior_mean=mu, prior_prec=prec)
    assert np.allclose(w_prior, mu, atol=1e-2), \
        f'strong prior did not pull to μ : max|Δ|={np.abs(w_prior-mu).max():.2e}'
    print('  [ok] strong prior pulls the solution to μ')


def test_warm_start_keeps_plain_l2_objective():
    build_fn, tr_idx, y, _X, nc = _toy_problem(seed=8)
    l2 = 1e-2
    w_zero, _, _ = train_lbfgs_chunked(
        build_fn, tr_idx, y, l2, 300, True, nc, 128)
    initial = np.linspace(-3.0, 3.0, nc)
    w_warm, _, _ = train_lbfgs_chunked(
        build_fn, tr_idx, y, l2, 300, True, nc, 128,
        initial_mean=initial)
    assert np.allclose(w_zero, w_warm, atol=2e-4), \
        f'warm-start changed plain-L2 optimum : max|Δ|={np.abs(w_zero-w_warm).max():.2e}'
    print('  [ok] warm-start converges to the same plain-L2 optimum')


if __name__ == '__main__':
    test_self_describing_v3_loader()
    test_colorfold_foldback_roundtrip()
    test_prior_off_matches_plain_l2()
    test_prior_uniform_prec_equals_l2()
    test_strong_prior_pulls_to_mu()
    test_warm_start_keeps_plain_l2_objective()
    print('ALL PRIOR TESTS PASS')
