#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Linear pattern regression trainer for the Othello POC.

Reads a gen-data WDL binary, computes per-sample pattern indices for
the 10 PATTERNS, fits y_pred = sum_p(w[offset_p + idx_p]) by L-BFGS
minimisation of MSE + L2, then writes int32 weights to disk.

Output binary format :
   uint32_t magic     = 0x4F544857  ("OTHW")
   uint32_t version   = 1
   uint32_t count     = TOTAL_BUCKETS (39690)
   uint32_t scale     = scale factor (centi-piece units, e.g. 1000)
   int32_t  weights[count]
"""

import argparse
import struct
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset
import patterns

WEIGHT_MAGIC   = 0x4F544857  # "OTHW"
WEIGHT_VERSION = 1


def build_sparse_X(cols: np.ndarray, n_features: int) -> sp.csr_matrix:
    """Build the N × n_features sparse one-hot feature matrix.

    Each row has exactly NUM_PATTERNS = 10 non-zero entries (value 1)
    at the columns given by `cols[i]`. CSR layout for efficient
    matvec / vmatvec.
    """
    n = cols.shape[0]
    npp = cols.shape[1]
    data = np.ones(n * npp, dtype=np.float64)
    indices = cols.reshape(-1)
    indptr = np.arange(0, n * npp + 1, npp, dtype=np.int64)
    return sp.csr_matrix((data, indices, indptr),
                         shape=(n, n_features), dtype=np.float64)


def train_lbfgs(X: sp.csr_matrix, y: np.ndarray, l2: float,
                max_iter: int) -> np.ndarray:
    n_features = X.shape[1]
    XT = X.T.tocsr()

    def loss_and_grad(w):
        pred = X @ w
        resid = pred - y
        loss = 0.5 * float(np.dot(resid, resid)) / len(y)
        loss += 0.5 * l2 * float(np.dot(w, w))
        grad = (XT @ resid) / len(y) + l2 * w
        return loss, grad

    w0 = np.zeros(n_features, dtype=np.float64)
    res = minimize(loss_and_grad, w0, jac=True, method='L-BFGS-B',
                   options={'maxiter': max_iter})
    return res.x, float(res.fun), int(res.nit)


def write_weights(path: Path, w_int32: np.ndarray, scale: int) -> None:
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIII', WEIGHT_MAGIC, WEIGHT_VERSION,
                            len(w_int32), scale))
        f.write(w_int32.astype('<i4').tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', required=True, help='gen-data binary path')
    ap.add_argument('--out',  required=True, help='output weights path')
    ap.add_argument('--l2',   type=float, default=1e-5,
                    help='L2 regularisation (default 1e-5)')
    ap.add_argument('--max-iter', type=int, default=200,
                    help='L-BFGS max iterations (default 200)')
    ap.add_argument('--scale', type=int, default=1000,
                    help='quantisation scale, float→int32 (default 1000)')
    ap.add_argument('--val-frac', type=float, default=0.1,
                    help='validation fraction (default 0.1)')
    args = ap.parse_args()

    print(f'loading dataset {args.data}')
    t0 = time.time()
    ds = dataset.load(args.data)
    print(f'  {ds.n_records} records  ({time.time() - t0:.2f}s)')

    print('extracting pattern indices')
    t0 = time.time()
    idx = patterns.extract_indices(ds.black, ds.white)
    cols = patterns.flat_feature_columns(idx)
    print(f'  shape {cols.shape} buckets={patterns.TOTAL_BUCKETS}  '
          f'({time.time() - t0:.2f}s)')

    # Train/val split
    n = ds.n_records
    rng = np.random.default_rng(seed=2026)
    perm = rng.permutation(n)
    n_val = int(n * args.val_frac)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]
    print(f'split : train={len(tr_idx)} val={len(val_idx)}')

    y_all = ds.label.astype(np.float64)
    X_tr = build_sparse_X(cols[tr_idx], patterns.TOTAL_BUCKETS)
    X_val = build_sparse_X(cols[val_idx], patterns.TOTAL_BUCKETS)
    y_tr, y_val = y_all[tr_idx], y_all[val_idx]

    print(f'L-BFGS  l2={args.l2}  max_iter={args.max_iter}')
    t0 = time.time()
    w_float, train_loss, n_iter = train_lbfgs(X_tr, y_tr, args.l2, args.max_iter)
    print(f'  train_loss={train_loss:.6f}  iters={n_iter}  '
          f'({time.time() - t0:.2f}s)')

    # Val metrics
    val_pred = X_val @ w_float
    val_mse = float(np.mean((val_pred - y_val) ** 2))
    val_sign_acc = float(np.mean(np.sign(val_pred) == y_val))
    print(f'val   : mse={val_mse:.6f}  sign_acc={val_sign_acc:.4f}')

    # Quantise to int32 in scale units.
    w_scaled = np.round(w_float * args.scale).astype(np.int64)
    # Clamp to int32 range (paranoid).
    w_scaled = np.clip(w_scaled, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)
    print(f'quant : scale={args.scale}  '
          f'range=[{int(w_scaled.min())},{int(w_scaled.max())}]  '
          f'nnz={int((w_scaled != 0).sum())}')

    write_weights(Path(args.out), w_scaled, args.scale)
    print(f'wrote {args.out}  ({len(w_scaled)} weights, '
          f'{16 + 4 * len(w_scaled)} bytes)')


if __name__ == '__main__':
    main()
