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

# Full Scan-style structured eval (v3). The dense "extras" vector is produced
# by `jass --dump-eval-features` and MUST match src/scan_eval.hpp NUM_EXTRAS
# and its layout exactly (king PST 0..99, men counts 100/101, mobility
# 102/103, balance 104/105). The trainer consumes that dump verbatim — there
# is no second implementation here, so the playable eval and the training
# features are identical by construction.
WEIGHTS_VERSION_V3 = 3
EVAL_NUM_EXTRAS    = 106


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
    # float32 design matrix : halves memory (critical for multi-M datasets);
    # ample precision for a least-squares fit on cp-scale targets.
    data    = np.concatenate([mg_data, eg_data], axis=1).reshape(-1).astype(np.float32)
    indptr  = np.arange(0, n * 2 * npp + 1, 2 * npp, dtype=np.int64)
    return sp.csr_matrix((data, indices, indptr),
                         shape=(n, 2 * total_buckets), dtype=np.float32)


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


def load_feature_file(path: str, n_expected: int,
                      standardise: bool = True) -> np.ndarray:
    """Load a "FEAT" file from `jass --dump-features` / `--dump-eval-features`.
    Returns (n, K) float64. For FIT-CHECK use (standardise=True) the columns
    are z-standardised so the L2 penalty is scale-fair vs the 0/1 pattern
    features. For a PLAYABLE eval (standardise=False) the RAW values are kept
    so the learned weights apply to the exact same feature values the C++
    eval (ScanEvalNetwork) computes — standardising here would silently
    rescale the eval at inference."""
    raw = Path(path).read_bytes()
    if raw[:4] != b'FEAT':
        raise SystemExit(f'{path}: not a FEAT file')
    cnt, k = struct.unpack_from('<II', raw, 4)
    if cnt != n_expected:
        raise SystemExit(f'feature count {cnt} != data {n_expected}')
    arr = np.frombuffer(raw, dtype='<f4', offset=12,
                        count=cnt * k).reshape(cnt, k).astype(np.float64)
    if not standardise:
        return arr
    std = arr.std(axis=0)
    std[std == 0] = 1.0
    return (arr - arr.mean(axis=0)) / std


def load_quiet_flags(path: str, n_expected: int) -> np.ndarray:
    """Load a "QIET" sidecar from `jass --dump-quiet-flags` : one uint8 per
    record, 1 = quiet (side to move has no mandatory capture), 0 = tactical.
    Returns a boolean mask of length n_expected."""
    raw = Path(path).read_bytes()
    if raw[:4] != b'QIET':
        raise SystemExit(f'{path}: not a QIET file')
    cnt = struct.unpack_from('<I', raw, 4)[0]
    if cnt != n_expected:
        raise SystemExit(f'quiet-flag count {cnt} != data {n_expected}')
    flags = np.frombuffer(raw, dtype=np.uint8, offset=8, count=cnt)
    return flags.astype(bool)


def build_extras_phased(extras: np.ndarray, wmg: np.ndarray,
                        weg: np.ndarray) -> sp.csr_matrix:
    """Phase-split dense extras : [ext*wmg | ext*weg]. Row prediction
    contributes wmg·(w_ext_mg·x) + weg·(w_ext_eg·x) — the same MG/EG
    interpolation ScanEvalNetwork::evaluate() applies to the extras."""
    # float32 throughout : the dense (n, 2·NUM_EXTRAS) intermediate is the peak
    # allocation at multi-M rows — float32 halves it (~8GB→4GB at 4.7M).
    ex = extras.astype(np.float32, copy=False)
    mg = ex * wmg[:, None].astype(np.float32)
    eg = ex * weg[:, None].astype(np.float32)
    return sp.csr_matrix(np.hstack([mg, eg]), dtype=np.float32)


def write_weights_v3(path: Path, pat_mg: np.ndarray, pat_eg: np.ndarray,
                     ext_mg: np.ndarray, ext_eg: np.ndarray,
                     scale: int) -> None:
    """PJTW v3 : magic, version=3, scale, n_pat, n_ext, then int32 weights
    ordered [pat_mg | pat_eg | ext_mg | ext_eg] (cf src/scan_eval.hpp)."""
    n_pat = len(pat_mg)
    n_ext = len(ext_mg)
    assert len(pat_eg) == n_pat and len(ext_eg) == n_ext
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIIII', WEIGHTS_MAGIC, WEIGHTS_VERSION_V3,
                            scale, n_pat, n_ext))
        for blk in (pat_mg, pat_eg, ext_mg, ext_eg):
            f.write(blk.astype('<i4').tobytes())


def train_lbfgs(X: sp.csr_matrix, y: np.ndarray, l2: float,
                max_iter: int, prior: np.ndarray = None,
                anchor_l2=0.0):
    """Least-squares fit with L2 toward 0 (`l2`) and, optionally, an extra
    L2 pulling the weights toward a `prior`. `anchor_l2` is either a scalar
    (uniform anchor — the anti-forgetting term for TD-leaf fine-tuning) OR a
    per-column array (used to pin specific features, e.g. material extras, to
    sane target values while leaving the rest free). anchor_l2=0 (or
    prior=None) → pure fit."""
    XT = X.T            # CSC view sharing X's data — no copy (was .tocsr() = a
                        # full duplicate, ~doubling memory on multi-M datasets)
    a = np.asarray(anchor_l2, dtype=np.float64)
    anchored = prior is not None and bool(np.any(a > 0.0))

    def loss_and_grad(w):
        pred = X @ w
        resid = pred - y
        loss = 0.5 * float(np.dot(resid, resid)) / len(y)
        loss += 0.5 * l2 * float(np.dot(w, w))
        grad = (XT @ resid) / len(y) + l2 * w
        if anchored:
            d = w - prior
            loss += 0.5 * float(np.sum(a * d * d))   # scalar or per-column
            grad += a * d
        return loss, grad

    # Warm-start at the prior when anchoring (faster, stays in its basin).
    w0 = prior.copy() if anchored else np.zeros(X.shape[1], dtype=np.float64)
    # maxcor caps the L-BFGS history : its internal storage is ~(2·maxcor+5)·n
    # float64. At n=42.5M (40-pattern v5) the default maxcor=10 is ~8GB on its
    # own → OOM once the design matrix is added. maxcor=5 halves it with
    # negligible convergence cost for this least-squares fit.
    res = minimize(loss_and_grad, w0, jac=True, method='L-BFGS-B',
                   options={'maxiter': max_iter, 'maxcor': 5})
    return res.x, float(res.fun), int(res.nit)


def material_anchor(n_cols: int, TB: int, E: int, strength: float,
                    man_pu: float = 1.0, king_pu: float = 3.0):
    """Per-column anchor that pins the MATERIAL extras to sane piece-unit
    values, breaking the men-count↔patterns collinearity that scrambled the
    sign of material in the standalone fit (cf 0151). Column order is
    [pat_mg | pat_eg | ext_mg | ext_eg]; extras layout matches scan_eval.hpp:
    bk-PST 0..49, wk-PST 50..99, black_men 100, white_men 101 (mob/bal 102-105
    left free). Black-POV: black material positive, white negative.

    Returns (prior, anchor) float arrays of length n_cols (0 everywhere except
    the material columns, which get `strength` and their target value)."""
    prior  = np.zeros(n_cols, dtype=np.float64)
    anchor = np.zeros(n_cols, dtype=np.float64)
    ext_mg0 = 2 * TB           # first ext_mg column
    ext_eg0 = 2 * TB + E       # first ext_eg column
    for base in (ext_mg0, ext_eg0):
        # men material
        prior[base + 100] = +man_pu;  anchor[base + 100] = strength   # black men
        prior[base + 101] = -man_pu;  anchor[base + 101] = strength   # white men
        # king material (PST one-hots) — kings are NOT in patterns, so this is
        # the only king signal; pin every square to ±king_pu.
        for sq in range(50):
            prior[base + sq]      = +king_pu;  anchor[base + sq]      = strength
            prior[base + 50 + sq] = -king_pu;  anchor[base + 50 + sq] = strength
    return prior, anchor


def load_v3_weights_float(path: str):
    """Read a PJTW v3 file into a float weight vector aligned to the
    [pat_mg | pat_eg | ext_mg | ext_eg] design-matrix column order, plus its
    (scale, n_pat, n_ext). Used as the anchor prior for fine-tuning."""
    raw = Path(path).read_bytes()
    magic, ver, scale, n_pat, n_ext = struct.unpack_from('<IIIII', raw, 0)
    if magic != WEIGHTS_MAGIC or ver != WEIGHTS_VERSION_V3:
        raise SystemExit(f'{path}: not a PJTW v3 file (magic/ver)')
    total = 2 * (n_pat + n_ext)
    arr = np.frombuffer(raw, dtype='<i4', offset=20, count=total).astype(np.float64)
    return arr / float(scale), int(scale), int(n_pat), int(n_ext)


def write_weights(path: Path, w_int32: np.ndarray, scale: int,
                  version: int = WEIGHTS_VERSION) -> None:
    # version 1 = mono-phase (count = TOTAL_BUCKETS) ; version 2 = phase-split
    # (count = 2×TOTAL_BUCKETS, [mg | eg] ; stage = piece count / 40).
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIII', WEIGHTS_MAGIC, version,
                            len(w_int32), scale))
        f.write(w_int32.astype('<i4').tobytes())


def train_scan_eval(args):
    """Train the full Scan-style phase-split structured eval → PJTW v3.

    Feature vector per position (all interpolated MG/EG by piece count) :
      [ men patterns (8×12 ternary, sparse) | extras (dense, raw) ]
    where extras = material + king PST + mobility + balance, dumped by
    `jass --dump-eval-features` (single source of truth shared with the C++
    eval). Standalone : the target is the score itself (no skeleton residual).
    """
    if not args.eval_features_file:
        raise SystemExit('--scan-eval requires --eval-features-file '
                         '(raw extras from `jass --dump-eval-features`)')
    if args.skeleton_data:
        print('note: --skeleton-data ignored under --scan-eval '
              '(standalone eval, target = score)')

    print(f'loading JNNW {args.data}')
    t0 = time.time()
    ds = master_loader.load(args.data, max_records=args.max_records)
    print(f'  {ds.n_records} records  ({time.time() - t0:.2f}s)')

    print('extracting pattern indices (men only)')
    idx  = patterns.extract_indices(ds.black_men, ds.white_men)
    cols = patterns.flat_feature_columns(idx)

    print(f'loading raw extras {args.eval_features_file}')
    extras = load_feature_file(args.eval_features_file, ds.n_records,
                               standardise=False)
    if extras.shape[1] != EVAL_NUM_EXTRAS:
        raise SystemExit(f'extras K={extras.shape[1]} != expected '
                         f'{EVAL_NUM_EXTRAS} (rebuild with --dump-eval-features)')
    print(f'  extras shape {extras.shape}  '
          f'(mean mob b/w={extras[:, 102].mean():.1f}/{extras[:, 103].mean():.1f})')

    # Standalone target (STM-POV), reprojected to black-POV. Default = the
    # Scan teacher score (distillation) ; --target wdl fits the game outcome
    # ternary {-1,0,1} instead (Scan-style logistic-ish, least-squares here).
    if args.target == 'wdl':
        target_stm = ds.wdl.astype(np.float64)
        n_pos = int((ds.wdl > 0).sum()); n_neg = int((ds.wdl < 0).sum())
        n_zero = int((ds.wdl == 0).sum())
        print(f'target=wdl  pos={n_pos} neg={n_neg} zero={n_zero} '
              f'({n_zero/ds.n_records*100:.1f}% draws)')
    else:
        clipped = np.clip(ds.score.astype(np.float64), -args.score_clip, args.score_clip)
        target_stm = clipped / 100.0
        print(f'target=score  clipped±{int(args.score_clip)}cp / 100  '
              f'std={target_stm.std():.3f}')
    y_black = np.where(ds.stm == 1, target_stm, -target_stm)

    # Game stage : piece count / 40 (matches scan_eval::game_stage).
    pc  = np.minimum(piece_count(ds), 40).astype(np.float64)
    wmg = pc / 40.0
    weg = 1.0 - wmg
    print(f'phase : piece-count mean={pc.mean():.1f}  wmg mean={wmg.mean():.3f}')

    # Row selection : drop extreme teacher scores (the ±9989 "won/lost"
    # verdicts whose squared loss dominates the least-squares fit and poisons
    # it — cf the score-drop breakthrough) and optionally restrict to quiet
    # (non-capture) positions. Both filters AND together; the train/val split
    # is then drawn from the kept rows only.
    n = ds.n_records
    # --score-drop : DROP rows whose |raw score| exceeds the threshold (the
    # ±9989 "won/lost" Scan verdicts) instead of clipping them. In least-squares
    # an extreme target dominates the loss even after a ±5000 clip (5000²=25M vs
    # ~90K for a normal ±300 position), so ~2% of extremes poison the fit (cf
    # 0169: dropping them took val_mse 38.7→1.8 and play 0.42→0.83). 0 = keep.
    # Row selection : drop extreme teacher scores (score-drop) and optionally
    # restrict to quiet (non-capture) positions. Both filters AND together; the
    # split is drawn from the kept rows only.
    keep = np.ones(n, dtype=bool)
    if getattr(args, 'score_drop', 0) and args.score_drop > 0:
        sd = np.abs(ds.score.astype(np.float64)) <= args.score_drop
        keep &= sd
        print(f'score-drop : keep |score|<={int(args.score_drop)}cp → '
              f'{int(sd.sum())}/{n} ({100*sd.mean():.1f}%)')
    if args.quiet_flags_file:
        q = load_quiet_flags(args.quiet_flags_file, n)
        keep &= q
        print(f'quiet-only : keep quiet positions → '
              f'{int(q.sum())}/{n} ({100*q.mean():.1f}%)')
    kept = np.flatnonzero(keep)
    rng = np.random.default_rng(seed=2026)
    perm = rng.permutation(kept)
    n_val = int(len(kept) * args.val_frac)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]
    print(f'split : train={len(tr_idx)} val={len(val_idx)}')

    TB = patterns.TOTAL_BUCKETS

    def build(sel):
        xp = build_sparse_X_phased(cols[sel], wmg[sel], weg[sel], TB)
        xe = build_extras_phased(extras[sel], wmg[sel], weg[sel])
        return sp.hstack([xp, xe], format='csr')   # [pat_mg|pat_eg|ext_mg|ext_eg]

    X_tr, X_val = build(tr_idx), build(val_idx)
    y_tr, y_val = y_black[tr_idx], y_black[val_idx]
    print(f'design : {X_tr.shape[1]} columns '
          f'(2×{TB} pat + 2×{EVAL_NUM_EXTRAS} ext)')

    n_cols = X_tr.shape[1]
    # Anchors COMBINE (per-column): a uniform anti-forgetting pull toward a v3
    # prior (--anchor-weights, keeps a TD/WDL re-fit from drifting away from a
    # known-good model — cf the 0149 collapse) PLUS a strong per-column pin of
    # the material extras to sane piece-units (--material-anchor, cf 0151). The
    # material overlay overrides the uniform anchor on the material columns.
    prior  = np.zeros(n_cols, dtype=np.float64)
    anchor = np.zeros(n_cols, dtype=np.float64)
    if args.anchor_weights:
        wprior, pscale, pnp, pne = load_v3_weights_float(args.anchor_weights)
        if pnp != TB or pne != EVAL_NUM_EXTRAS:
            raise SystemExit(f'anchor shape ({pnp},{pne}) != ({TB},{EVAL_NUM_EXTRAS})')
        prior = np.asarray(wprior, dtype=np.float64).copy()
        anchor[:] = args.anchor_l2
        print(f'anti-forget : L2={args.anchor_l2} toward prior {args.anchor_weights}')
    if args.material_anchor > 0:
        mprior, manchor = material_anchor(n_cols, TB, EVAL_NUM_EXTRAS,
                                          args.material_anchor,
                                          man_pu=args.man_pu, king_pu=args.king_pu)
        mask = manchor > 0
        prior[mask] = mprior[mask]; anchor[mask] = manchor[mask]
        print(f'material-anchor : strength={args.material_anchor} '
              f'man=±{args.man_pu} king=±{args.king_pu} '
              f'(pinned columns={int(mask.sum())})')
    use_anchor = bool(np.any(anchor > 0.0))

    print(f'L-BFGS  l2={args.l2}  max_iter={args.max_iter}'
          f'{"  (anchored)" if use_anchor else "  (pure)"}')
    t0 = time.time()
    w_float, train_loss, n_iter = train_lbfgs(X_tr, y_tr, args.l2, args.max_iter,
                                              prior=prior if use_anchor else None,
                                              anchor_l2=anchor)
    print(f'  train_loss={train_loss:.6f}  iters={n_iter}  ({time.time() - t0:.2f}s)')

    val_pred = X_val @ w_float
    val_mse = float(np.mean((val_pred - y_val) ** 2))
    val_sign_acc = float(np.mean(np.sign(val_pred) == y_val))
    print(f'val   : mse={val_mse:.6f}  sign_acc={val_sign_acc:.4f}')

    def quant(block):
        q = np.round(block * args.scale).astype(np.int64)
        return np.clip(q, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)

    E = EVAL_NUM_EXTRAS
    pat_mg = quant(w_float[0:TB])
    pat_eg = quant(w_float[TB:2 * TB])
    ext_mg = quant(w_float[2 * TB:2 * TB + E])
    ext_eg = quant(w_float[2 * TB + E:2 * TB + 2 * E])
    print(f'quant : scale={args.scale}  '
          f'pat range=[{int(pat_mg.min())},{int(pat_mg.max())}] '
          f'ext_mg range=[{int(ext_mg.min())},{int(ext_mg.max())}]')

    write_weights_v3(Path(args.out), pat_mg, pat_eg, ext_mg, ext_eg, args.scale)
    total = 2 * (TB + E)
    print(f'wrote {args.out}  (v3, {total} weights, {20 + 4 * total} bytes)')
    return 0


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
    ap.add_argument('--score-drop', type=float, default=0.0,
                    help='DROP rows with |raw score| > N cp (extreme won/lost '
                         'verdicts that dominate the LS loss). 0 = keep all. '
                         'Try 4900 (cf 0169: val_mse 38→1.8, play 0.42→0.83).')
    ap.add_argument('--quiet-flags-file', default=None,
                    help='(scan-eval) path to a "QIET" sidecar from '
                         '--dump-quiet-flags ; restrict the fit to quiet '
                         '(non-capture) positions.')
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
    ap.add_argument('--features-file', default=None,
                    help='FIT-CHECK only : a "FEAT" file from `jass '
                         '--dump-features` (mobility / balance the static '
                         'men-patterns cannot see). Appended as standardised '
                         'extra columns to test if DYNAMIC info explains the '
                         'residual. Output .pjtw non-playable.')
    ap.add_argument('--scan-eval', action='store_true',
                    help='Train the FULL Scan-style structured eval → PJTW v3 '
                         '(PLAYABLE). Phase-split men patterns + dense extras '
                         '(material + king PST + mobility + balance, all '
                         'MG/EG). Requires --eval-features-file (the raw '
                         'extras from `jass --dump-eval-features`). Implies '
                         'phase-split; target is the score as-is (standalone '
                         'eval, no skeleton residual).')
    ap.add_argument('--eval-features-file', default=None,
                    help='RAW "FEAT" file from `jass --dump-eval-features` '
                         f'({EVAL_NUM_EXTRAS} Scan-style extras). Used with '
                         '--scan-eval to build the playable v3 eval. Values '
                         'are kept RAW (not standardised) so the weights apply '
                         'to the exact features the C++ eval computes.')
    ap.add_argument('--anchor-weights', default=None,
                    help='TD-leaf fine-tuning : a prior v3 PJTW (the Scan-'
                         'distilled eval) toward which the fit is L2-'
                         'regularised. Anti-forgetting anchor. Omit for a '
                         'PURE (unanchored) fine-tune.')
    ap.add_argument('--anchor-l2', type=float, default=0.0,
                    help='Strength of the --anchor-weights pull (0 = off).')
    ap.add_argument('--material-anchor', type=float, default=0.0,
                    help='STANDALONE FIX (cf 0151): per-column L2 pinning the '
                         'material extras (men count, king PST) to sane '
                         'piece-units so the men-count/patterns collinearity '
                         'cannot scramble material. 0 = off. Try ~0.5-2.0.')
    ap.add_argument('--man-pu',  type=float, default=1.0,
                    help='Target piece-units for a man (material anchor).')
    ap.add_argument('--king-pu', type=float, default=3.0,
                    help='Target piece-units for a king (material anchor).')
    args = ap.parse_args()

    if args.scan_eval:
        return train_scan_eval(args)

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

    if args.features_file:
        ef = sp.csr_matrix(load_feature_file(args.features_file, ds.n_records))
        X_tr  = sp.hstack([X_tr,  ef[tr_idx]],  format='csr')
        X_val = sp.hstack([X_val, ef[val_idx]], format='csr')
        print(f'features-file : +{ef.shape[1]} dynamic/global features '
              f'(mobility, balance ; fit-check, non-jouable)')

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
