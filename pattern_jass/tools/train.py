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


def build_sparse_X_phased(cols: np.ndarray, wmg: np.ndarray, weg: np.ndarray,
                          total_buckets: int) -> sp.csr_matrix:
    """Phase-split design matrix : 2× columns [mg block | eg block]. Each row
    has its NUM_PATTERNS buckets in the mg block (value wmg[i]) AND in the eg
    block at col+total_buckets (value weg[i]). prediction = wmg·(w_mg·φ) +
    weg·(w_eg·φ) = the game-stage interpolation the C++ eval must reproduce."""
    n, npp = cols.shape
    mg_idx = cols
    eg_idx = cols + total_buckets
    indices = np.concatenate([mg_idx, eg_idx], axis=1).reshape(-1)
    mg_data = np.repeat(wmg[:, None], npp, axis=1)
    eg_data = np.repeat(weg[:, None], npp, axis=1)
    data    = np.concatenate([mg_data, eg_data], axis=1).reshape(-1).astype(np.float64)
    indptr  = np.arange(0, n * 2 * npp + 1, 2 * npp, dtype=np.int64)
    return sp.csr_matrix((data, indices, indptr),
                         shape=(n, 2 * total_buckets), dtype=np.float64)


def piece_count(ds) -> np.ndarray:
    """Total pieces per record (men + kings, both sides), 0..40 — the game
    stage proxy. Vectorised popcount of the OR of the 4 bitboards."""
    allbb = (ds.white_men | ds.white_kings | ds.black_men | ds.black_kings)
    bits  = np.unpackbits(allbb.view(np.uint8)).reshape(ds.n_records, 64)
    return bits.sum(axis=1)



def king_onehot_block(black_kings: np.ndarray,
                      white_kings: np.ndarray) -> sp.csr_matrix:
    """100 extra linear features (king PST) in the fixed black-POV
    orientation matching the men-pattern features : black_kings one-hot on
    squares 0..49, white_kings on 50..99. Lets the fit-check see whether
    explicit KING-position info (which the men-only patterns are blind to)
    helps fit the Scan−handcrafted residual."""
    n = len(black_kings)
    sq = np.arange(50, dtype=np.uint64)
    bk = ((black_kings[:, None] >> sq) & 1).astype(np.float64)   # (n, 50)
    wk = ((white_kings[:, None] >> sq) & 1).astype(np.float64)
    return sp.csr_matrix(np.hstack([bk, wk]))                    # (n, 100)


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


def write_weights(path: Path, w_int32: np.ndarray, scale: int,
                  version: int = WEIGHTS_VERSION) -> None:
    # version 1 = mono-phase (count = TOTAL_BUCKETS) ; version 2 = phase-split
    # (count = 2×TOTAL_BUCKETS, [mg | eg] ; stage = piece count / 40).
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIII', WEIGHTS_MAGIC, version,
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
    ap.add_argument('--target', choices=['wdl', 'score'], default='wdl',
                    help='training target : "wdl" (ternary {-1,0,1}) or '
                         '"score" (centipawn clipped to ±2000 / 100 → piece units)')
    ap.add_argument('--score-clip', type=float, default=2000.0,
                    help='clip score to ±N cp before scaling (default 2000)')
    ap.add_argument('--skeleton-data', default=None,
                    help='optional path to a sibling JNNW whose score field '
                         'contains the handcrafted skeleton eval per record. '
                         'When set with --target score, the actual training '
                         'target becomes (score - skeleton_score) — the pattern '
                         'learns the RESIDUAL on top of the skeleton (Scan-style '
                         'hybrid). Records must align 1-to-1 with --data.')
    ap.add_argument('--phase-split', action='store_true',
                    help='train 2 weight banks (mg/eg) interpolated by piece '
                         'count → PJTW v2. Rend le pattern game-stage aware '
                         '(comme Scan), lève le plafond mono-phase.')
    ap.add_argument('--king-features', action='store_true',
                    help='FIT-CHECK only : append 100 king-PST one-hot features '
                         '(the men-only patterns are blind to kings). The '
                         'output .pjtw is then NON-standard (not playable) — '
                         'use only to read val_mse and test if king info helps.')
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

    # Re-project the chosen target to black-POV.
    # JNNW stm: 0 = white-to-move, 1 = black-to-move (cf src/main.cpp:222).
    # WDL and score are both STM-POV in the file.
    # black-POV value = stm-POV if stm==1 else -(stm-POV).
    if args.target == 'wdl':
        target_stm = ds.wdl.astype(np.float64)
        # Diagnostic : WDL distribution (helps catch sparse/all-zero datasets).
        n_pos = int((ds.wdl > 0).sum()); n_neg = int((ds.wdl < 0).sum())
        n_zero = int((ds.wdl == 0).sum())
        print(f'target=wdl  pos={n_pos} neg={n_neg} zero={n_zero}'
              f'  ({n_zero/ds.n_records*100:.1f}% draws)')
    else:  # score
        clipped = np.clip(ds.score.astype(np.float64), -args.score_clip, args.score_clip)
        target_stm = clipped / 100.0  # centipawn → piece units
        print(f'target=score  range=[{int(ds.score.min())},{int(ds.score.max())}]'
              f'  clipped±{int(args.score_clip)}cp / 100 → piece units'
              f'  std={target_stm.std():.3f}')

        if args.skeleton_data is not None:
            print(f'loading skeleton {args.skeleton_data}')
            sk_ds = master_loader.load(args.skeleton_data, max_records=args.max_records)
            if sk_ds.n_records != ds.n_records:
                raise SystemExit(f'skeleton record count {sk_ds.n_records} != '
                                 f'data {ds.n_records}')
            sk_clipped = np.clip(sk_ds.score.astype(np.float64),
                                 -args.score_clip, args.score_clip)
            skeleton_stm = sk_clipped / 100.0
            residual = target_stm - skeleton_stm
            print(f'skeleton std={skeleton_stm.std():.3f}  '
                  f'residual std={residual.std():.3f}  '
                  f'(corr score↔skel = {np.corrcoef(target_stm, skeleton_stm)[0,1]:.3f})')
            target_stm = residual
    y_black = np.where(ds.stm == 1, target_stm, -target_stm)
    wdl_black = y_black  # keep variable name for downstream code

    # Train/val split.
    n = ds.n_records
    rng = np.random.default_rng(seed=2026)
    perm = rng.permutation(n)
    n_val = int(n * args.val_frac)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]
    print(f'split : train={len(tr_idx)} val={len(val_idx)}')

    out_version = WEIGHTS_VERSION
    if args.phase_split:
        pc  = np.minimum(piece_count(ds), 40).astype(np.float64)
        wmg = pc / 40.0
        weg = 1.0 - wmg
        print(f'phase-split : piece-count mean={pc.mean():.1f}  '
              f'wmg mean={wmg.mean():.3f} (1=tout midgame, 0=tout endgame)')
        X_tr  = build_sparse_X_phased(cols[tr_idx],  wmg[tr_idx],  weg[tr_idx],  patterns.TOTAL_BUCKETS)
        X_val = build_sparse_X_phased(cols[val_idx], wmg[val_idx], weg[val_idx], patterns.TOTAL_BUCKETS)
        out_version = 2
    else:
        X_tr  = build_sparse_X(cols[tr_idx],  patterns.TOTAL_BUCKETS)
        X_val = build_sparse_X(cols[val_idx], patterns.TOTAL_BUCKETS)
    y_tr, y_val = wdl_black[tr_idx], wdl_black[val_idx]

    if args.king_features:
        kb = king_onehot_block(ds.black_kings, ds.white_kings)
        X_tr  = sp.hstack([X_tr,  kb[tr_idx]],  format='csr')
        X_val = sp.hstack([X_val, kb[val_idx]], format='csr')
        print(f'king-features : +{kb.shape[1]} king-PST features '
              f'(men-patterns + kings ; fit-check, non-jouable)')

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

    write_weights(Path(args.out), w_scaled, args.scale, version=out_version)
    print(f'wrote {args.out}  (v{out_version}, {len(w_scaled)} weights, '
          f'{16 + 4 * len(w_scaled)} bytes)')


if __name__ == '__main__':
    main()
