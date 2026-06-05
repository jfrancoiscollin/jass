#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Linear pattern-jass regression trainer.

Reads a JNNW master dataset (jass core format, cf src/main.cpp:220),
extracts per-sample pattern-jass indices, fits y_pred = Σ_p w[off_p + idx_p]
by L-BFGS minimisation of MSE + L2, then writes int32 weights to disk.

Output binary format (PJTW = "Pattern-Jass-Trained-Weights") :
   uint32_t magic     = 0x57544A50  ("PJTW")
   uint32_t version   = 1
   uint32_t count     = TOTAL_BUCKETS (472392)
   uint32_t scale     = quantisation factor (centi-piece units)
   int32_t  weights[count]

Target convention :
   * label = WDL from STM POV (-1 / 0 / +1)
   * eval_pred(b) = Σ w[idx[i]] computed on "black POV" indices, then
     sign-flipped if stm=white. Same convention as Othello POC.

  → For training we compute the prediction in "black POV" and the
    target is the WDL re-projected to black POV : `wdl_black =
    wdl_stm * (1 if stm==0 else -1)`. Wait : stm=0 = white-to-move
    (cf src/main.cpp:222). So black-POV wdl = wdl_stm if stm==1 else
    -wdl_stm.
"""

import argparse
import struct
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent))
import master_loader
import patterns

WEIGHTS_MAGIC   = 0x57544A50  # "PJTW" little-endian
WEIGHTS_VERSION = 1


def build_sparse_X(cols: np.ndarray, n_features: int) -> sp.csr_matrix:
    """Each row = exactly NUM_PATTERNS non-zeros at `cols[i]`, value 1."""
    n, npp = cols.shape
    data    = np.ones(n * npp, dtype=np.float64)
    indices = cols.reshape(-1)
    indptr  = np.arange(0, n * npp + 1, npp, dtype=np.int64)
    return sp.csr_matrix((data, indices, indptr),
                         shape=(n, n_features), dtype=np.float64)


def train_lbfgs(X: sp.csr_matrix, y: np.ndarray, l2: float,
                max_iter: int):
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


def write_weights(path: Path, w_int32: np.ndarray, scale: int) -> None:
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIII', WEIGHTS_MAGIC, WEIGHTS_VERSION,
                            len(w_int32), scale))
        f.write(w_int32.astype('<i4').tobytes())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', required=True, help='JNNW master dataset path')
    ap.add_argument('--out',  required=True, help='output PJTW weights path')
    ap.add_argument('--max-records', type=int, default=None,
                    help='cap on records loaded (for smoke runs)')
    ap.add_argument('--l2',   type=float, default=1e-5)
    ap.add_argument('--max-iter', type=int, default=200)
    ap.add_argument('--scale', type=int, default=1000)
    ap.add_argument('--val-frac', type=float, default=0.1)
    args = ap.parse_args()

    print(f'loading JNNW {args.data}')
    t0 = time.time()
    ds = master_loader.load(args.data, max_records=args.max_records)
    print(f'  {ds.n_records} records  ({time.time() - t0:.2f}s)')

    print('extracting pattern indices (men only)')
    t0 = time.time()
    idx = patterns.extract_indices(ds.black_men, ds.white_men)
    cols = patterns.flat_feature_columns(idx)
    print(f'  shape {cols.shape} buckets={patterns.TOTAL_BUCKETS}  '
          f'({time.time() - t0:.2f}s)')

    # Re-project WDL to black-POV (training convention).
    # JNNW stm: 0 = white-to-move, 1 = black-to-move (cf src/main.cpp:222).
    # wdl is from STM-POV. black-POV wdl = wdl if stm==1 else -wdl.
    wdl_black = ds.wdl.astype(np.float64)
    wdl_black = np.where(ds.stm == 1, wdl_black, -wdl_black)

    # Train/val split.
    n = ds.n_records
    rng = np.random.default_rng(seed=2026)
    perm = rng.permutation(n)
    n_val = int(n * args.val_frac)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]
    print(f'split : train={len(tr_idx)} val={len(val_idx)}')

    X_tr  = build_sparse_X(cols[tr_idx],  patterns.TOTAL_BUCKETS)
    X_val = build_sparse_X(cols[val_idx], patterns.TOTAL_BUCKETS)
    y_tr, y_val = wdl_black[tr_idx], wdl_black[val_idx]

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
