#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Disk-streaming logistic-regression trainer for the Scan-style pattern eval
(PJTW v3). The "Tier 2" fit: scales to tens-to-hundreds of millions of self-play
positions WITHOUT loading them into RAM.

Where the in-RAM trainers cap out:
  * train.py --lowmem    keeps the whole pattern sparse + raw extras in RAM  (~2.4M)
  * train.py --minibatch keeps the per-row data arrays (cols, extras) in RAM (~10-15M)
Both hold O(N) design data in memory. This trainer keeps in RAM ONLY tiny
per-row arrays (wdl/stm/phase, a few bytes each) plus a 68MB prune remap, and
RE-READS the bitboards + extras FROM DISK in `--chunk`-row blocks each L-BFGS
iteration. So peak RAM is ~O(chunk), independent of N; the cost is ~max_iter
full disk passes over --data + --feat.

It REUSES train.py's exact builders / fold logic / chunked-L-BFGS / expand /
writer, so the output .pjtw is byte-identical in layout to train.py's
`--scan-eval` output and the C++ ScanEvalNetwork loader accepts it unchanged.

JNNW record  : 38B = 4×uint64 (wm,wk,bm,bk) + uint8 stm + int32 score + int8 wdl
FEAT (extras): magic 'FEAT', uint32 cnt, uint32 k(=NUM_EXTRAS), float32[cnt*k]
"""

import argparse
import json
import os
import struct
import sys
import time
from pathlib import Path

import numpy as np
import scipy.sparse as sp

# Same sys.path dance as train.py: tools dir for master_loader/patterns/symmetry,
# plus the reset-proof external geometry dir if pinned.
sys.path.insert(0, str(Path(__file__).resolve().parent))
_pgd = os.environ.get("JASS_PATTERNS_DIR")
if _pgd:
    sys.path.insert(0, _pgd)
import patterns                                    # noqa: E402
import train                                       # noqa: E402  (reuse builders/expand/writer)
from train import (                                # noqa: E402
    CF_BUCKETS, colorfold_maps,
    build_sparse_X_phased, build_extras_phased,
    train_lbfgs_chunked, write_weights_v3,
    load_v3_weights_float,
    phase_wmg, _TEMPO_WW, _TEMPO_BW,
)

# JNNW / FEAT on-disk geometry.
JNNW_MAGIC = b'JNNW'
JNNW_HEADER_SIZE = 8
JNNW_RECORD_SIZE = 38
# np structured dtype matching the 38B record (little-endian, packed).
_JNNW_DTYPE = np.dtype([
    ('wm', '<u8'), ('wk', '<u8'), ('bm', '<u8'), ('bk', '<u8'),
    ('stm', 'u1'), ('score', '<i4'), ('wdl', 'i1'),
])
assert _JNNW_DTYPE.itemsize == JNNW_RECORD_SIZE

FEAT_MAGIC = b'FEAT'
FEAT_HEADER_SIZE = 12


# --------------------------------------------------------------------------- #
#  On-disk readers : seek + read a contiguous [i:i+n) row range, never the whole
#  file. memmap gives us cheap random-access slices without a full read.
# --------------------------------------------------------------------------- #
def open_jnnw(path: str):
    """Validate the JNNW header and return (memmap_of_records, n_records).
    The memmap is over the record body only; slicing it reads just those rows."""
    with open(path, 'rb') as f:
        head = f.read(JNNW_HEADER_SIZE)
    if head[:4] != JNNW_MAGIC:
        raise SystemExit(f'{path}: not a JNNW file (magic {head[:4]!r})')
    count = struct.unpack_from('<I', head, 4)[0]
    fsize = os.path.getsize(path)
    body = fsize - JNNW_HEADER_SIZE
    if body % JNNW_RECORD_SIZE != 0:
        raise SystemExit(f'{path}: body {body} not a multiple of {JNNW_RECORD_SIZE}')
    derived = body // JNNW_RECORD_SIZE
    if count != derived:
        raise SystemExit(f'{path}: header count {count} != file-derived {derived}')
    mm = np.memmap(path, dtype=_JNNW_DTYPE, mode='r',
                   offset=JNNW_HEADER_SIZE, shape=(count,))
    return mm, count


def open_feat(path: str, n_expected: int):
    """Validate the FEAT header (and alignment to --data) and return
    (memmap (n,k) float32, k). Values stay RAW (the playable-eval convention)."""
    with open(path, 'rb') as f:
        head = f.read(FEAT_HEADER_SIZE)
    if head[:4] != FEAT_MAGIC:
        raise SystemExit(f'{path}: not a FEAT file (magic {head[:4]!r})')
    cnt, k = struct.unpack_from('<II', head, 4)
    if cnt != n_expected:
        raise SystemExit(f'{path}: feature count {cnt} != data {n_expected}')
    fsize = os.path.getsize(path)
    need = FEAT_HEADER_SIZE + cnt * k * 4
    if fsize < need:
        raise SystemExit(f'{path}: file {fsize}B < expected {need}B (cnt={cnt} k={k})')
    mm = np.memmap(path, dtype='<f4', mode='r',
                   offset=FEAT_HEADER_SIZE, shape=(cnt, k))
    return mm, int(k)


# --------------------------------------------------------------------------- #
#  Per-chunk popcount helpers (replicate train.py's piece_count / tempo_wmg but
#  on raw bitboard arrays rather than a MasterDataset, so they work on a slice).
# --------------------------------------------------------------------------- #
def _piece_count_bb(wm, wk, bm, bk):
    """Total pieces (men+kings, both sides) per row : popcount(OR of 4 boards)."""
    allbb = (wm | wk | bm | bk)
    bits = np.unpackbits(allbb.view(np.uint8)).reshape(len(allbb), 64)
    return bits.sum(axis=1)


def _tempo_wmg_bb(wm, bm):
    """Scan tempo midgame weight = clip(tempo/300), men only. Matches train.py."""
    w = np.unpackbits(wm.view(np.uint8)).reshape(len(wm), 64).astype(np.float64)
    b = np.unpackbits(bm.view(np.uint8)).reshape(len(bm), 64).astype(np.float64)
    tempo = w.dot(_TEMPO_WW) + b.dot(_TEMPO_BW)
    return np.clip(tempo / 300.0, 0.0, 1.0)


# --------------------------------------------------------------------------- #
#  Fold (cols/signs) for one chunk's bitboards. Replicates train.py's cols/signs
#  logic for the chosen fold (--full-fold vs --color-fold vs none).
# --------------------------------------------------------------------------- #
class Folder:
    """Maps a chunk's (black_men, white_men) -> (cols, signs) in the TRAINING
    layout (PAT_BUCKETS buckets/pattern), and carries the fold maps needed to
    EXPAND the trained canonical block back to the full 17M v3 table."""

    def __init__(self, mode: str):
        self.mode = mode
        NP = patterns.NUM_PATTERNS
        self.cf_U2C = self.cf_U2S = None        # --color-fold expand maps
        self.rf_canon = self.rf_sign = None     # --full-fold expand maps
        if mode == 'full':
            import symmetry
            # FULL stack : colour + rot180 + translation + reflection (train.py).
            self.rf_canon, self.rf_sign = symmetry.build_canon(translate=True,
                                                               reflect=True)
            self.PAT_BUCKETS = patterns.BUCKETS_PER_PATTERN   # canonical = 17M index space
        elif mode == 'color':
            self.cf_U2C, self.cf_U2S = colorfold_maps()
            self.PAT_BUCKETS = CF_BUCKETS
        elif mode == 'none':
            self.PAT_BUCKETS = patterns.BUCKETS_PER_PATTERN
        else:
            raise SystemExit(f'unknown fold {mode!r}')
        self.NP = NP
        self.TB = self.PAT_BUCKETS * NP

    def cols_signs(self, black_men, white_men):
        """(n,NP) int64 columns in [0,TB) and (n,NP) float32 signs (or None)."""
        idx = patterns.extract_indices(black_men, white_men)
        NP = self.NP
        if self.mode == 'full':
            cols = self.rf_canon[np.arange(NP)[None, :], idx]          # canonical 17M-space col
            signs = self.rf_sign[np.arange(NP)[None, :], idx].astype(np.float32)
        elif self.mode == 'color':
            canon = self.cf_U2C[idx]                                   # [0,CF_HALF]
            signs = self.cf_U2S[idx].astype(np.float32)               # ±1
            cols = canon + (np.arange(NP, dtype=np.int64) * self.PAT_BUCKETS)[None, :]
        else:
            cols = patterns.flat_feature_columns(idx)
            signs = None
        return cols, signs


def expand_pat(folder: Folder, canon_mg, canon_eg, scale):
    """EXPAND the trained canonical pattern block (TB-sized, possibly un-pruned)
    back to the standard full 17M v3 table, quantised to int32. Copies train.py's
    train_scan_eval expand logic exactly (color-fold / full-fold / none)."""
    def quant(block):
        q = np.round(block * scale).astype(np.int64)
        return np.clip(q, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)

    if folder.rf_canon is not None:
        # --full-fold (rot/trans/refl) : full[p*NB+c] = sign[p][c]·w_canon[canon_col[p][c]].
        rf_canon = folder.rf_canon
        rf_sign = folder.rf_sign
        full_mg = (rf_sign.ravel().astype(canon_mg.dtype) * canon_mg[rf_canon.ravel()])
        full_eg = (rf_sign.ravel().astype(canon_eg.dtype) * canon_eg[rf_canon.ravel()])
        return quant(full_mg), quant(full_eg)
    if folder.cf_U2C is not None:
        # --color-fold : W_full[u] = sign(u)·w_canon[|signed(u)|], per pattern.
        NB = patterns.BUCKETS_PER_PATTERN                  # 531441
        NP = patterns.NUM_PATTERNS
        TBfull = NB * NP
        cf_U2C, cf_U2S = folder.cf_U2C, folder.cf_U2S
        # canonical bucket 0 (all-empty, colour-swap fixpoint) -> antisymmetric weight 0.
        canon_mg = canon_mg.copy(); canon_eg = canon_eg.copy()
        canon_mg[np.arange(NP) * CF_BUCKETS] = 0
        canon_eg[np.arange(NP) * CF_BUCKETS] = 0
        full_mg = np.empty(TBfull, dtype=canon_mg.dtype)
        full_eg = np.empty(TBfull, dtype=canon_eg.dtype)
        for p in range(NP):
            cb_mg = canon_mg[p * CF_BUCKETS:(p + 1) * CF_BUCKETS]
            cb_eg = canon_eg[p * CF_BUCKETS:(p + 1) * CF_BUCKETS]
            full_mg[p * NB:(p + 1) * NB] = cf_U2S * cb_mg[cf_U2C]
            full_eg[p * NB:(p + 1) * NB] = cf_U2S * cb_eg[cf_U2C]
        return quant(full_mg), quant(full_eg)
    # no fold : the canonical block IS the 17M table.
    return quant(canon_mg), quant(canon_eg)


# --------------------------------------------------------------------------- #
#  Champion projection shared by two deliberately different continuation modes:
#    * --prior-mean : Gaussian ridge toward the previous champion;
#    * --warm-start : optimiser initialisation only, ordinary L2 remains centred 0.
#  Both fold a standard full-table PJTW back into the CURRENT pruned layout.
# --------------------------------------------------------------------------- #
def project_champion_mean(path, folder, keep, PAT_N, E):
    w_champ, scale_c, n_pat_c, n_ext_c = load_v3_weights_float(path)
    if n_ext_c != E:
        raise SystemExit(f'champion n_ext {n_ext_c} != current extras {E} '
                         '(champion built with different feature flags)')
    NP = patterns.NUM_PATTERNS
    NB = patterns.BUCKETS_PER_PATTERN
    if n_pat_c != NP * NB:
        raise SystemExit(f'champion n_pat {n_pat_c} != {NP * NB} (full table v3 expected)')
    cm_full = w_champ[0:n_pat_c]
    ce_full = w_champ[n_pat_c:2 * n_pat_c]
    ext_mg_c = w_champ[2 * n_pat_c:2 * n_pat_c + n_ext_c]
    ext_eg_c = w_champ[2 * n_pat_c + n_ext_c:2 * n_pat_c + 2 * n_ext_c]
    # --- fold-back full -> canonical training block (p*PAT_BUCKETS + cc) ---
    if folder.mode == 'color':
        U2C, U2S = colorfold_maps()
        rep_b = np.empty(CF_BUCKETS, dtype=np.int64)
        rep_b[U2C] = np.arange(NB, dtype=np.int64)          # any representative per canonical
        srb = U2S[rep_b].astype(np.float64)
        canon_mg = (cm_full.reshape(NP, NB)[:, rep_b] * srb[None, :]).reshape(NP * CF_BUCKETS)
        canon_eg = (ce_full.reshape(NP, NB)[:, rep_b] * srb[None, :]).reshape(NP * CF_BUCKETS)
    elif folder.mode == 'none':
        canon_mg, canon_eg = cm_full, ce_full               # canonical == full
    else:
        raise SystemExit(f'champion continuation unsupported for fold={folder.mode!r} '
                         '(color/none only)')
    # --- prune-align : dense slot s(1..K) -> canonical bucket keep[s-1] ; slot0=fallback(0) ---
    mu_pat_mg = np.zeros(PAT_N, dtype=np.float64)
    mu_pat_eg = np.zeros(PAT_N, dtype=np.float64)
    mu_pat_mg[1:] = canon_mg[keep]
    mu_pat_eg[1:] = canon_eg[keep]
    mu = np.concatenate([mu_pat_mg, mu_pat_eg, ext_mg_c, ext_eg_c])
    return mu, scale_c


# --------------------------------------------------------------------------- #
#  Sequential-Bayesian prior : project the previous champion as a Gaussian
#  prior.  This is stronger than --warm-start because it changes the objective.
# --------------------------------------------------------------------------- #
def build_sequential_prior(args, folder, keep, kept_counts, PAT_N, E, N, l2):
    mu, scale_c = project_champion_mean(
        args.prior_mean, folder, keep, PAT_N, E)
    lam = float(args.prior_visit_scale); dec = float(args.prior_decay)
    prec_pat = np.full(PAT_N, l2, dtype=np.float64)
    prec_pat[1:] = l2 + dec * lam * (kept_counts.astype(np.float64) / max(N, 1))
    prec_ext_val = l2 + dec * lam                            # extras active every row (visits/N=1)
    prec = np.concatenate([prec_pat, prec_pat,
                           np.full(E, prec_ext_val), np.full(E, prec_ext_val)])
    print(f'prior : champion={args.prior_mean} (scale={scale_c})  λ={lam} decay={dec}  '
          f'prec[pat] med={np.median(prec_pat[1:]):.3e} max={prec_pat[1:].max():.3e} '
          f'prec[ext]={prec_ext_val:.3e}  warm-start at μ')
    return mu, prec


# --------------------------------------------------------------------------- #
#  The streaming trainer.
# --------------------------------------------------------------------------- #
def train_stream(args):
    t_start = time.time()
    fold_mode = 'full' if args.full_fold else ('color' if args.color_fold else 'none')
    folder = Folder(fold_mode)

    mm, N = open_jnnw(args.data)
    feat, K = open_feat(args.feat, N)
    EVAL_NUM_EXTRAS = K
    print(f'JNNW {args.data} : {N:,} records')
    print(f'FEAT {args.feat} : k={K} extras')
    print(f'fold : {fold_mode}  ({folder.PAT_BUCKETS:,} buckets/pattern, '
          f'TB={folder.TB:,})')
    print(f'occupancy : {"men|kings (king-aware, Scan-style)" if args.king_patterns else "men only"}')

    chunk = int(args.chunk)
    TB = folder.TB

    # --- Pass A : stream once to build the tiny per-row arrays (wdl/stm/phase) and
    #     the prune visit-count remap. Bitboards + extras are NOT kept; only O(N)
    #     bytes of wdl/stm/phase + the O(TB) int counts survive this pass. ------- #
    print(f'pass A (phase + prune scan, chunk={chunk:,}) ...')
    tA = time.time()
    y_all = np.empty(N, dtype=np.float64)        # black-POV win-prob target {0,.5,1}
    wmg_all = np.empty(N, dtype=np.float32)
    weg_all = np.empty(N, dtype=np.float32)
    do_prune = bool(args.prune)
    ccounts = np.zeros(TB, dtype=np.int64) if do_prune else None
    n_win = n_draw = n_loss = 0
    for i in range(0, N, chunk):
        j = min(i + chunk, N)
        rec = mm[i:j]
        wm = np.ascontiguousarray(rec['wm']); wk = np.ascontiguousarray(rec['wk'])
        bm = np.ascontiguousarray(rec['bm']); bk = np.ascontiguousarray(rec['bk'])
        stm = np.ascontiguousarray(rec['stm'])
        wdl = np.ascontiguousarray(rec['wdl']).astype(np.float64)
        if args.target == 'value':
            # Independent value-target distillation (option B) : regress on the
            # DEEP-search value stored in `score` (STM-POV), mapped to a black-POV
            # win-prob via a sigmoid so it stays in the same [0,1] regime as the
            # WDL-logistic champions. score_black = score if stm==1 else -score.
            score = np.ascontiguousarray(rec['score']).astype(np.float64)
            score_black = np.where(stm == 1, score, -score)
            y_all[i:j] = 1.0 / (1.0 + np.exp(-score_black / float(args.value_scale)))
        else:
            # black-POV WDL target y = (wdl_black+1)/2, wdl_black = wdl if stm==1 else -wdl.
            wdl_black = np.where(stm == 1, wdl, -wdl)
            y_all[i:j] = (wdl_black + 1.0) * 0.5
        n_win += int((wdl > 0).sum()); n_loss += int((wdl < 0).sum())
        n_draw += int((wdl == 0).sum())
        # phase weights (same as train.py : tempo-stage or piece-count ramp).
        if args.tempo_stage:
            wmg = _tempo_wmg_bb(wm, bm)
        else:
            pc = np.minimum(_piece_count_bb(wm, wk, bm, bk), 40).astype(np.float64)
            wmg = phase_wmg(pc, args.phase_lo, args.phase_hi)
        wmg_all[i:j] = wmg.astype(np.float32)
        weg_all[i:j] = (1.0 - wmg).astype(np.float32)
        if do_prune:
            pb = (bm | bk) if args.king_patterns else bm
            pw = (wm | wk) if args.king_patterns else wm
            cols, _ = folder.cols_signs(pb, pw)
            ccounts += np.bincount(cols.ravel(), minlength=TB)
    if args.target == 'value':
        print(f'  target=VALUE (deep-search score, scale={args.value_scale})  '
              f'y mean={y_all.mean():.3f} std={y_all.std():.3f}  ({time.time()-tA:.1f}s)')
    else:
        print(f'  target=WDL  win={n_win} draw={n_draw} loss={n_loss} '
              f'({100*n_draw/max(N,1):.1f}% draws)  ({time.time()-tA:.1f}s)')

    # --- Prune remap : bucket(0..TB) -> dense slot. Lossless at min-visits=1 (every
    #     visited bucket gets a slot 1..K; slot 0 = unseen fallback, stays 0). ----- #
    remap = None
    PAT_N = TB
    if do_prune:
        keep = np.flatnonzero(ccounts >= args.prune_min_visits)
        keep = keep[np.argsort(ccounts[keep])[::-1]]     # common buckets -> low slots
        K = len(keep)
        # int32 remap : TB=17M < 2^31 so slots fit; 17M*4 = 68MB (vs 136MB int64).
        remap = np.zeros(TB, dtype=np.int32)             # 0 = fallback/unseen
        remap[keep] = np.arange(1, K + 1, dtype=np.int32)
        PAT_N = K + 1
        kept_counts = ccounts[keep].copy() if args.prior_mean else None  # per-slot visits for prior
        print(f'prune : keep {K:,} buckets (>= {args.prune_min_visits} visits) '
              f'-> {2*PAT_N:,} pattern cols vs {2*TB:,}  ({TB/max(PAT_N,1):.1f}x fewer); '
              f'remap RAM={remap.nbytes/1e6:.0f}MB')
        if args.prune_min_visits > 1:
            print('  WARNING: --prune-min-visits>1 pools low-count buckets into the '
                  'fallback slot 0, which is DROPPED at deploy -> the played eval '
                  'differs slightly from the trained model. Use 1 for a lossless prune.',
                  file=sys.stderr)
        del ccounts
    if (args.prior_mean or args.warm_start) and not do_prune:
        raise SystemExit('--prior-mean/--warm-start require --prune '
                         '(champion must be aligned to the visited dense slots)')

    n_cols = 2 * PAT_N + 2 * EVAL_NUM_EXTRAS
    print(f'design : {n_cols:,} columns (2x{PAT_N:,} pat + 2x{EVAL_NUM_EXTRAS} ext)')

    # --- Disk-backed build_fn : sel is a CONTIGUOUS row range produced by
    #     train_lbfgs_chunked's tr_idx[i:i+batch]. We require contiguity so we can
    #     seek the memmaps; assert it to fail loud if that ever changes. --------- #
    logistic = (args.loss == 'logistic')

    def build_fn(sel):
        lo = int(sel[0]); hi = int(sel[-1]) + 1
        # tr_idx = arange(N) so a chunk slice is contiguous & sorted.
        assert hi - lo == len(sel) and sel[0] == lo and sel[-1] == hi - 1, \
            'build_fn expects a contiguous row range (tr_idx must be arange(N))'
        rec = mm[lo:hi]
        wm = np.ascontiguousarray(rec['wm']); bm = np.ascontiguousarray(rec['bm'])
        if args.king_patterns:
            wk = np.ascontiguousarray(rec['wk']); bk = np.ascontiguousarray(rec['bk'])
            pb = bm | bk; pw = wm | wk
        else:
            pb = bm; pw = wm
        cols, signs = folder.cols_signs(pb, pw)
        if remap is not None:
            cols = remap[cols]                            # (n,NP) in [0,K]
        wmg = wmg_all[lo:hi].astype(np.float64)
        weg = weg_all[lo:hi].astype(np.float64)
        Xpat = build_sparse_X_phased(cols, wmg, weg, PAT_N, signs)
        extras = np.ascontiguousarray(feat[lo:hi]).astype(np.float64)
        Xext = build_extras_phased(extras, wmg, weg)
        return sp.hstack([Xpat, Xext], format='csr')      # [pat_mg|pat_eg|ext_mg|ext_eg]

    # --- L-BFGS over the FULL dataset, streamed from disk each iteration. tr_idx is
    #     arange(N) so train_lbfgs_chunked re-reads every chunk per gradient eval
    #     (~max_iter disk passes). The accumulated gradient is the EXACT full-batch
    #     gradient (only the assembly is streamed). ----------------------------- #
    print(f'L-BFGS  loss={args.loss}  l2={args.l2}  max_iter={args.max_iter}  '
          f'chunk={chunk:,}  (~{args.max_iter} disk passes over data+feat)')
    # --holdout-frac F : fit on the first (1-F)*N rows, evaluate log-loss on the
    #   last F*N rows (held out, never seen at fit). Both are CONTIGUOUS ranges so
    #   build_fn (which seeks memmaps by lo:hi) works unchanged. F=0 => arange(N)
    #   = byte-identical to before. Prune/remap stay computed over full N (bucket
    #   selection only, identical across compared archs — the WEIGHTS are train-only).
    hold_frac = float(getattr(args, 'holdout_frac', 0.0) or 0.0)
    hold_count = int(getattr(args, 'holdout_count', 0) or 0)
    if hold_count < 0 or hold_count >= N:
        raise SystemExit(f'--holdout-count must be in [0,{max(0, N-1)}], got {hold_count}')
    if hold_count:
        train_N = N - hold_count
        print(f'holdout : exact tail count={hold_count:,} -> fit on {train_N:,} rows')
    else:
        train_N = int(round(N * (1.0 - hold_frac))) if hold_frac > 0.0 else N
        hold_count = N - train_N
        if hold_frac > 0.0:
            print(f'holdout : frac={hold_frac} -> fit on {train_N:,} rows, '
                  f'val on {hold_count:,} rows')
    tr_idx = np.arange(train_N, dtype=np.int64)
    # Hierarchical-shrinkage grouping : slot -> parent pattern id (-1 = unseen fallback).
    slot_pattern = None
    if args.hier_l2 > 0.0:
        PB = folder.PAT_BUCKETS
        if remap is None:                               # no prune : PAT_N == TB, dense grid
            slot_pattern = (np.arange(PAT_N, dtype=np.int64) // PB).astype(np.int32)
        else:                                           # pruned : slot 0 = fallback, 1..K = keep
            slot_pattern = np.full(PAT_N, -1, dtype=np.int32)
            slot_pattern[1:K + 1] = (keep // PB).astype(np.int32)
        print(f'hier-l2 : {args.hier_l2}  (backoff vers la moyenne du pattern parent, '
              f'{patterns.NUM_PATTERNS} patterns)')
    # Sequential-Bayesian prior (opt-in) : project the previous champion into the
    # training layout as a per-weight precision-weighted Gaussian prior. OFF
    # (--prior-mean unset) => exact plain-L2 behaviour, byte-identical output.
    prior_mean = prior_prec = initial_mean = None
    if args.prior_mean:
        prior_mean, prior_prec = build_sequential_prior(
            args, folder, keep, kept_counts, PAT_N, EVAL_NUM_EXTRAS, N, args.l2)
    elif args.warm_start:
        initial_mean, scale_c = project_champion_mean(
            args.warm_start, folder, keep, PAT_N, EVAL_NUM_EXTRAS)
        print(f'warm-start : champion={args.warm_start} (scale={scale_c}) ; '
              'initialisation only, objective keeps ordinary zero-centred L2')
    t0 = time.time()
    optimizer_diagnostics = {}
    w_float, train_loss, n_iter = train_lbfgs_chunked(
        build_fn, tr_idx, y_all, args.l2, args.max_iter,
        logistic, n_cols, chunk, sw_all=None,
        hier_l2=args.hier_l2, slot_pattern=slot_pattern,
        pat_n=PAT_N, n_patterns=patterns.NUM_PATTERNS,
        prior_mean=prior_mean, prior_prec=prior_prec, initial_mean=initial_mean,
        optimizer_diagnostics=optimizer_diagnostics, maxcor=args.lbfgs_maxcor)
    print(f'  train_loss={train_loss:.6f}  iters={n_iter}  ({time.time()-t0:.1f}s)')
    print('OPTIMIZER ' + json.dumps(optimizer_diagnostics, sort_keys=True))
    if args.optimizer_report:
        Path(args.optimizer_report).write_text(
            json.dumps(optimizer_diagnostics, indent=2, sort_keys=True) + '\n',
            encoding='utf-8',
        )

    # --- HOLDOUT log-loss : same forward pass (build_fn + sigmoid CE) as the fit,
    #     on the held-out tail rows [train_N, N), at the fitted weights. Pure data
    #     cross-entropy (no L2/prior term) => a clean generalisation estimate. ---- #
    if hold_count > 0 and train_N < N:
        _eps = 1e-12; _vl = 0.0; _nv = 0
        for i in range(train_N, N, chunk):
            _sel = np.arange(i, min(i + chunk, N), dtype=np.int64)
            _z = build_fn(_sel) @ w_float
            _p = 0.5 * (np.tanh(0.5 * _z) + 1.0)
            _yc = y_all[_sel]
            _vl += float(-np.sum(_yc * np.log(_p + _eps) + (1.0 - _yc) * np.log(1.0 - _p + _eps)))
            _nv += len(_sel)
        print(f'HOLDOUT_LOGLOSS {_vl/max(_nv,1):.6f}  '
              f'(frac={_nv/max(N,1):.8f} n_val={_nv})')

    # --- Un-prune to the TB-sized training block, then fold-EXPAND to the full 17M
    #     v3 table and write a standard PJTW v3 (byte-compatible with the C++ loader). #
    def quant(block):
        q = np.round(block * args.scale).astype(np.int64)
        return np.clip(q, -(2 ** 31), 2 ** 31 - 1).astype(np.int32)

    E = EVAL_NUM_EXTRAS
    pat_mg_d = w_float[0:PAT_N]
    pat_eg_d = w_float[PAT_N:2 * PAT_N]
    ext_mg = quant(w_float[2 * PAT_N:2 * PAT_N + E])
    ext_eg = quant(w_float[2 * PAT_N + E:2 * PAT_N + 2 * E])
    # (1) un-prune to the TB-sized training-layout block.
    if remap is not None:
        canon_mg = np.zeros(TB, dtype=w_float.dtype)
        canon_eg = np.zeros(TB, dtype=w_float.dtype)
        kept = np.flatnonzero(remap > 0)
        canon_mg[kept] = pat_mg_d[remap[kept]]
        canon_eg[kept] = pat_eg_d[remap[kept]]
    else:
        canon_mg, canon_eg = np.asarray(pat_mg_d), np.asarray(pat_eg_d)
    # (2) fold-expand to the standard 17M men-only layout (quantised int32).
    pat_mg, pat_eg = expand_pat(folder, canon_mg, canon_eg, args.scale)
    print(f'quant : scale={args.scale}  '
          f'pat range=[{int(pat_mg.min())},{int(pat_mg.max())}] '
          f'ext_mg range=[{int(ext_mg.min())},{int(ext_mg.max())}]')

    write_weights_v3(Path(args.out), pat_mg, pat_eg, ext_mg, ext_eg, args.scale,
                     king=args.king_patterns)
    total = 2 * (len(pat_mg) + E)
    print(f'wrote {args.out}  (v3, {total:,} weights, {20 + 4 * total:,} bytes)  '
          f'[total {time.time()-t_start:.1f}s]')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', required=True, help='JNNW master dataset on disk (can be huge)')
    ap.add_argument('--feat', required=True,
                    help='FEAT file of raw extras aligned 1:1 to --data, on disk')
    ap.add_argument('--out', required=True, help='output PJTW v3 weights path')
    ap.add_argument('--loss', choices=['logistic', 'ls'], default='logistic',
                    help="logistic regression on WDL outcomes (Scan's objective, "
                         "default) or least-squares on the WDL target.")
    ap.add_argument('--target', choices=['wdl', 'value'], default='wdl',
                    help="wdl (default) = train on the game/egdb outcome label. "
                         "value = independent value-target distillation : train on the "
                         "DEEP-search value in the `score` field (via --deep-relabel), "
                         "mapped to a win-prob with --value-scale.")
    ap.add_argument('--value-scale', type=float, default=200.0,
                    help="sigmoid scale (eval units) mapping deep-search score → win-prob "
                         "when --target value. Larger = softer targets. Default 200.")
    fold = ap.add_mutually_exclusive_group()
    fold.add_argument('--full-fold', action='store_true',
                      help='FULL symmetry fold (colour+rot180+translation+reflection); '
                           'expanded back to the standard 17M v3 .pjtw.')
    fold.add_argument('--color-fold', action='store_true',
                      help='colour-antisymmetry fold (17M->8.5M); expanded to 17M v3 .pjtw.')
    ap.add_argument('--tempo-stage', action='store_true',
                    help="Scan tempo (men-advancement) phase blend instead of the "
                         "piece-count ramp. MUST pair with the C++ -DJASS_TEMPO_STAGE.")
    ap.add_argument('--phase-lo', type=float, default=0.0,
                    help='phase ramp low (pieces); wmg=0 at/below. MUST match C++ '
                         '-DJASS_PHASE_LO. Ignored under --tempo-stage.')
    ap.add_argument('--phase-hi', type=float, default=40.0,
                    help='phase ramp high (pieces); wmg=1 at/above. MUST match C++ '
                         '-DJASS_PHASE_HI. Ignored under --tempo-stage.')
    ap.add_argument('--l2', type=float, default=1e-4)
    ap.add_argument('--hier-l2', type=float, default=0.0,
                    help='Hierarchical shrinkage (backoff) : penalise each pattern bucket toward its '
                         'PARENT pattern mean (λ·Σ(w_b−μ_p)²) instead of 0. Rare buckets inherit the '
                         'pattern mean, not neutral. 0 = off (legacy L2→0). Pairs with a small --l2.')
    continuation = ap.add_mutually_exclusive_group()
    continuation.add_argument('--prior-mean', type=str, default=None,
                    help='SEQUENTIAL-BAYESIAN prior : PJTW v3 of the PREVIOUS champion. When set, the '
                         'ridge toward 0 is replaced by a Gaussian prior toward this champion, with '
                         'per-weight precision = l2 + decay·λ·(visits/N) (extras: visits=N), warm-started '
                         'at μ. Carries acquired knowledge across generations (anti-forgetting of rare '
                         'buckets). OFF (default) = plain L2, byte-identical. Requires --prune ; '
                         '--color-fold or none only.')
    continuation.add_argument('--warm-start', type=str, default=None,
                    help='PJTW v3 of the previous student used ONLY as the L-BFGS starting point. '
                         'Unlike --prior-mean, this does not anchor the objective to the parent: '
                         'the ordinary --l2 penalty remains centred on zero. Requires --prune and '
                         '--color-fold or no fold.')
    ap.add_argument('--prior-visit-scale', type=float, default=0.25,
                    help='λ : prior evidence per accumulated visit (dimensionless ; ~0.25 balances the '
                         'prior against the logistic data-Fisher). Only with --prior-mean.')
    ap.add_argument('--prior-decay', type=float, default=1.0,
                    help='discount on the prior precision (0..1). 1 = full visit-weighting ; 0 = plain '
                         'ridge toward the champion (uniform l2, μ=champion). Only with --prior-mean.')
    ap.add_argument('--max-iter', type=int, default=25,
                    help='L-BFGS iters; EACH is ~one disk pass over data+feat. Keep small.')
    ap.add_argument('--optimizer-report', type=str, default=None,
                    help='optional JSON report with SciPy success/status/message and gradient norm')
    ap.add_argument('--lbfgs-maxcor', type=int, default=5,
                    help='L-BFGS correction history size; larger values use more RAM but improve curvature')
    ap.add_argument('--scale', type=int, default=1000, help='quantisation factor')
    holdout = ap.add_mutually_exclusive_group()
    holdout.add_argument('--holdout-frac', type=float, default=0.0,
                    help='fraction (0..1) of the tail rows held out from the fit to report a '
                         'HOLDOUT_LOGLOSS generalisation estimate. 0 = off (byte-identical). '
                         'Data must be pre-shuffled for the split to be representative.')
    holdout.add_argument('--holdout-count', type=int, default=0,
                    help='exact number of tail rows held out. Intended for a game/opening-level '
                         'split assembled by tools/selfplay_frontier.py; avoids fractional rounding.')
    ap.add_argument('--chunk', type=int, default=500000,
                    help='rows/chunk read from disk per gradient sub-step.')
    ap.add_argument('--prune', dest='prune', action='store_true', default=True,
                    help='(default on) train over a collision-free dense remap of '
                         'the pattern table; scatter back to a standard 17M .pjtw.')
    ap.add_argument('--no-prune', dest='prune', action='store_false',
                    help='disable pruning (train the full TB-sized pattern table).')
    ap.add_argument('--prune-min-visits', type=int, default=1,
                    help='with --prune : keep a bucket only if visited >= this many '
                         'times (1 = lossless).')
    ap.add_argument('--king-patterns', action='store_true',
                    help='PIECE-PRESENCE occupancy includes kings (men|kings, '
                         'Scan-style) for the pattern buckets, exactly like '
                         'train.py --king-patterns and a -DJASS_KING_PATTERNS build. '
                         'Records king=True in the PJTW v3 marker (rejected by a '
                         'men-only binary). Default OFF = men-only occupancy.')
    args = ap.parse_args(argv)
    return train_stream(args)


if __name__ == '__main__':
    raise SystemExit(main())
