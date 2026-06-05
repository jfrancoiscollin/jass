#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Trainer pour pattern_jass_kings (Variant C, 5-state encoding).

Pareil que pattern_jass/tools/train.py mais utilise les patterns 5-state
incluant kings. Output PJTW count = 3 125 000.
"""

import argparse
import struct
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize

# Reuse the master_loader from pattern_jass/tools.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / 'pattern_jass' / 'tools'))
import master_loader  # noqa: E402
import patterns        # noqa: E402  -- this directory's patterns

WEIGHTS_MAGIC   = 0x57544A50  # "PJTW"
WEIGHTS_VERSION = 1


def build_sparse_X(cols: np.ndarray, n_features: int) -> sp.csr_matrix:
    n, npp = cols.shape
    data    = np.ones(n * npp, dtype=np.float64)
    indices = cols.reshape(-1)
    indptr  = np.arange(0, n * npp + 1, npp, dtype=np.int64)
    return sp.csr_matrix((data, indices, indptr),
                         shape=(n, n_features), dtype=np.float64)


def train_lbfgs(X, y, l2, max_iter):
    XT = X.T.tocsr()

    def loss_and_grad(w):
        pred = X @ w
        resid = pred - y
        loss = 0.5 * float(np.dot(resid, resid)) / len(y)
        loss += 0.5 * l2 * float(np.dot(w, w))
        grad = (XT @ resid) / len(y) + l2 * w
        return loss, grad

    w0 = np.zeros(X.shape[1], dtype=np.float64)
    res = minimize(loss_and_grad, w0, jac=True, method='L-BFGS-B',
                   options={'maxiter': max_iter})
    return res.x, float(res.fun), int(res.nit)


def write_weights(path, w_int32, scale):
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIII', WEIGHTS_MAGIC, WEIGHTS_VERSION,
                            len(w_int32), scale))
        f.write(w_int32.astype('<i4').tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', required=True)
    ap.add_argument('--out',  required=True)
    ap.add_argument('--max-records', type=int, default=None)
    ap.add_argument('--l2',   type=float, default=1e-5)
    ap.add_argument('--max-iter', type=int, default=200)
    ap.add_argument('--scale', type=int, default=1000)
    ap.add_argument('--val-frac', type=float, default=0.1)
    ap.add_argument('--target', choices=['wdl', 'score'], default='score')
    ap.add_argument('--score-clip', type=float, default=2000.0)
    args = ap.parse_args()

    print(f'loading JNNW {args.data}')
    t0 = time.time()
    ds = master_loader.load(args.data, max_records=args.max_records)
    print(f'  {ds.n_records} records  ({time.time() - t0:.2f}s)')

    print('extracting 5-state pattern indices (men + kings)')
    t0 = time.time()
    idx = patterns.extract_indices(
        ds.black_men, ds.black_kings, ds.white_men, ds.white_kings)
    cols = patterns.flat_feature_columns(idx)
    print(f'  shape {cols.shape} buckets={patterns.TOTAL_BUCKETS}'
          f'  ({time.time() - t0:.2f}s)')

    if args.target == 'wdl':
        target_stm = ds.wdl.astype(np.float64)
    else:
        clipped = np.clip(ds.score.astype(np.float64),
                          -args.score_clip, args.score_clip)
        target_stm = clipped / 100.0
    print(f'target={args.target}  std={target_stm.std():.3f}')
    y_black = np.where(ds.stm == 1, target_stm, -target_stm)

    n = ds.n_records
    rng = np.random.default_rng(seed=2026)
    perm = rng.permutation(n)
    n_val = int(n * args.val_frac)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]
    print(f'split : train={len(tr_idx)} val={len(val_idx)}')

    X_tr  = build_sparse_X(cols[tr_idx],  patterns.TOTAL_BUCKETS)
    X_val = build_sparse_X(cols[val_idx], patterns.TOTAL_BUCKETS)
    y_tr, y_val = y_black[tr_idx], y_black[val_idx]

    print(f'L-BFGS  l2={args.l2}  max_iter={args.max_iter}')
    t0 = time.time()
    w_float, train_loss, n_iter = train_lbfgs(X_tr, y_tr, args.l2, args.max_iter)
    print(f'  train_loss={train_loss:.6f}  iters={n_iter}  '
          f'({time.time() - t0:.2f}s)')

    val_pred = X_val @ w_float
    val_mse = float(np.mean((val_pred - y_val) ** 2))
    val_sign_acc = float(np.mean(np.sign(val_pred) == y_val))
    print(f'val   : mse={val_mse:.6f}  sign_acc={val_sign_acc:.4f}')

    w_scaled = np.round(w_float * args.scale).astype(np.int64)
    w_scaled = np.clip(w_scaled, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)
    print(f'quant : scale={args.scale}  '
          f'range=[{int(w_scaled.min())},{int(w_scaled.max())}]  '
          f'nnz={int((w_scaled != 0).sum())}')

    write_weights(Path(args.out), w_scaled, args.scale)
    print(f'wrote {args.out}  ({len(w_scaled)} weights, '
          f'{16 + 4 * len(w_scaled)} bytes)')


if __name__ == '__main__':
    main()
