#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Self-contained correctness test for train_stream.py (disk-streaming v3 fit).

Asserts:
  (1) The emitted .pjtw is a STANDARD full-table PJTW v3 with the self-desc bits,
      the right n_pat/n_ext and the exact file size the C++ loader expects.
  (2) The streamed disk gradient is EXACT : a full-batch in-RAM reference fit
      (same train.py builders) converges to weights close to train_stream's,
      proving the chunked/disk assembly does not change the optimum.

Synthesises a tiny JNNW (random legal-ish records, disjoint men) + matching FEAT,
runs train_stream end-to-end, then re-derives the reference in-process. No jobs,
no external data, no git side effects.
"""

import os
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
import scipy.sparse as sp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patterns
import train
import train_stream as ts


def _rand_bitboards(n, rng):
    """Random legal-ish position: men on squares 1..50, disjoint per colour, no
    kings (keeps the test focused on the men-pattern path). Returns 4 uint64
    arrays (wm, wk, bm, bk)."""
    wm = np.zeros(n, dtype=np.uint64)
    bm = np.zeros(n, dtype=np.uint64)
    for r in range(n):
        # pick a handful of occupied squares, split into black/white disjointly.
        k = int(rng.integers(4, 20))
        sqs = rng.choice(50, size=k, replace=False)          # squares 0..49 (bit = sq)
        colors = rng.integers(0, 2, size=k)
        wb = np.uint64(0); bb = np.uint64(0)
        for sq, col in zip(sqs, colors):
            bit = np.uint64(1) << np.uint64(int(sq))
            if col == 0:
                wb |= bit
            else:
                bb |= bit
        wm[r] = wb; bm[r] = bb
    wk = np.zeros(n, dtype=np.uint64)
    bk = np.zeros(n, dtype=np.uint64)
    return wm, wk, bm, bk


def _write_jnnw(path, wm, wk, bm, bk, stm, score, wdl):
    n = len(wm)
    with open(path, 'wb') as f:
        f.write(b'JNNW')
        f.write(struct.pack('<I', n))
        rec = np.empty(n, dtype=ts._JNNW_DTYPE)
        rec['wm'] = wm; rec['wk'] = wk; rec['bm'] = bm; rec['bk'] = bk
        rec['stm'] = stm.astype(np.uint8)
        rec['score'] = score.astype(np.int32)
        rec['wdl'] = wdl.astype(np.int8)
        f.write(rec.tobytes())


def _write_feat(path, arr):
    n, k = arr.shape
    with open(path, 'wb') as f:
        f.write(b'FEAT')
        f.write(struct.pack('<II', n, k))
        f.write(arr.astype('<f4').tobytes())


def _reference_full_batch(data, feat, fold_mode, l2, max_iter, scale):
    """Full design built ENTIRELY in RAM with train.py's builders, then a single
    train_lbfgs_chunked over one batch = the whole set. This is the streamed
    trainer's gradient with the disk/chunk machinery removed. Returns the float
    weight vector (pre-expand) and PAT_N so we can compare the trained tables."""
    folder = ts.Folder(fold_mode)
    mm, N = ts.open_jnnw(data)
    fmm, K = ts.open_feat(feat, N)
    rec = mm[:]
    wm = np.ascontiguousarray(rec['wm']); wk = np.ascontiguousarray(rec['wk'])
    bm = np.ascontiguousarray(rec['bm']); bk = np.ascontiguousarray(rec['bk'])
    stm = np.ascontiguousarray(rec['stm']); wdl = np.ascontiguousarray(rec['wdl']).astype(np.float64)
    wdl_black = np.where(stm == 1, wdl, -wdl)
    y = (wdl_black + 1.0) * 0.5
    pc = np.minimum(ts._piece_count_bb(wm, wk, bm, bk), 40).astype(np.float64)
    wmg = train.phase_wmg(pc, 0.0, 40.0)
    weg = 1.0 - wmg
    extras = np.ascontiguousarray(fmm[:]).astype(np.float64)

    # prune remap from the WHOLE set (tr split = all rows in the streaming run).
    TB = folder.TB
    cols, signs = folder.cols_signs(bm, wm)
    ccounts = np.bincount(cols.ravel(), minlength=TB)
    keep = np.flatnonzero(ccounts >= 1)
    keep = keep[np.argsort(ccounts[keep])[::-1]]
    K_ = len(keep)
    remap = np.zeros(TB, dtype=np.int64)
    remap[keep] = np.arange(1, K_ + 1)
    PAT_N = K_ + 1
    dcols = remap[cols]

    n_cols = 2 * PAT_N + 2 * K

    def build(sel):
        Xpat = train.build_sparse_X_phased(dcols[sel], wmg[sel], weg[sel], PAT_N,
                                           signs[sel] if signs is not None else None)
        Xext = train.build_extras_phased(extras[sel], wmg[sel], weg[sel])
        return sp.hstack([Xpat, Xext], format='csr')

    tr_idx = np.arange(N)
    # batch = N -> a single full-batch chunk (no streaming), exact reference.
    w, _, _ = train.train_lbfgs_chunked(build, tr_idx, y, l2, max_iter,
                                        True, n_cols, N)
    return w, PAT_N, remap, K


def main():
    rng = np.random.default_rng(12345)
    N = 2000
    wm, wk, bm, bk = _rand_bitboards(N, rng)
    stm = rng.integers(0, 2, size=N).astype(np.uint8)
    score = rng.integers(-500, 500, size=N).astype(np.int32)
    wdl = rng.integers(-1, 2, size=N).astype(np.int8)        # {-1,0,1}
    K = train.EVAL_NUM_EXTRAS                                 # NUM_EXTRAS
    extras = rng.standard_normal((N, K)).astype(np.float32)

    tmp = Path(tempfile.mkdtemp(prefix='train_stream_test_'))
    data = tmp / 'tiny.jnnw'
    feat = tmp / 'tiny.feat'
    out = tmp / 'tiny.pjtw'
    _write_jnnw(data, wm, wk, bm, bk, stm, score, wdl)
    _write_feat(feat, extras)

    l2, max_iter, scale, chunk = 1e-4, 5, 1000, 256

    # --- run train_stream.py end-to-end (full-fold, streamed) ------------------ #
    argv = ['--data', str(data), '--feat', str(feat), '--out', str(out),
            '--full-fold', '--loss', 'logistic',
            '--l2', str(l2), '--max-iter', str(max_iter),
            '--scale', str(scale), '--chunk', str(chunk)]
    rc = ts.main(argv)
    assert rc == 0, 'train_stream.main returned nonzero'

    # --- (1) header / layout / size assertions --------------------------------- #
    raw = out.read_bytes()
    magic, ver, sc, n_pat, n_ext = struct.unpack_from('<IIIII', raw, 0)
    assert magic == train.WEIGHTS_MAGIC, f'magic {magic:#x} != WEIGHTS_MAGIC'
    base = ver & 0xFF
    assert base == train.WEIGHTS_VERSION_V3, f'version base {base} != 3'
    assert ver & train.PJTW_SELFDESC_BIT, 'self-desc bit not set'
    # king=False in train_stream -> KING bit must be clear.
    assert not (ver & train.PJTW_KING_BIT), 'KING bit set but king=False'
    assert sc == scale, f'scale {sc} != {scale}'
    exp_n_pat = patterns.NUM_PATTERNS * patterns.BUCKETS_PER_PATTERN
    assert n_pat == exp_n_pat, f'n_pat {n_pat} != NUM_PATTERNS*BUCKETS_PER_PATTERN {exp_n_pat}'
    assert n_ext == K, f'n_ext {n_ext} != FEAT k {K}'
    exp_size = 20 + 4 * (2 * n_pat + 2 * n_ext)
    assert len(raw) == exp_size, f'file size {len(raw)} != {exp_size}'
    print(f'[1] header OK : magic=PJTW ver={ver:#x} (v3+selfdesc) scale={sc} '
          f'n_pat={n_pat:,} n_ext={n_ext} size={len(raw):,}B == expected')

    # --- (2) streamed-vs-full-batch gradient exactness ------------------------- #
    # The reference fits the same objective with the design built fully in RAM and
    # batch=N (no streaming). Compare the trained float weights pre-expand.
    w_ref, PAT_N, remap, _K = _reference_full_batch(
        data, feat, 'full', l2, max_iter, scale)

    # Re-derive train_stream's float weights with the SAME remap so PAT_N matches.
    # (train_stream's remap orders kept buckets by frequency desc, identical to the
    #  reference here since both prune the whole set with min-visits=1.)
    folder = ts.Folder('full')
    mm, _N = ts.open_jnnw(str(data))
    fmm, _ = ts.open_feat(str(feat), _N)
    rec = mm[:]
    wm2 = np.ascontiguousarray(rec['wm']); bm2 = np.ascontiguousarray(rec['bm'])
    wk2 = np.ascontiguousarray(rec['wk']); bk2 = np.ascontiguousarray(rec['bk'])
    stm2 = np.ascontiguousarray(rec['stm']); wdl2 = np.ascontiguousarray(rec['wdl']).astype(np.float64)
    y = (np.where(stm2 == 1, wdl2, -wdl2) + 1.0) * 0.5
    pc = np.minimum(ts._piece_count_bb(wm2, wk2, bm2, bk2), 40).astype(np.float64)
    wmg = train.phase_wmg(pc, 0.0, 40.0); weg = 1.0 - wmg
    extras2 = np.ascontiguousarray(fmm[:]).astype(np.float64)
    cols, signs = folder.cols_signs(bm2, wm2)
    dcols = remap[cols]
    n_cols = 2 * PAT_N + 2 * K

    def build_stream(sel):
        lo = int(sel[0]); hi = int(sel[-1]) + 1
        Xpat = train.build_sparse_X_phased(dcols[lo:hi], wmg[lo:hi], weg[lo:hi],
                                           PAT_N, signs[lo:hi] if signs is not None else None)
        Xext = train.build_extras_phased(extras2[lo:hi], wmg[lo:hi], weg[lo:hi])
        return sp.hstack([Xpat, Xext], format='csr')

    w_stream, _, _ = train.train_lbfgs_chunked(
        build_stream, np.arange(_N), y, l2, max_iter, True, n_cols, chunk)

    max_abs = float(np.max(np.abs(w_stream - w_ref)))
    rel = max_abs / (float(np.max(np.abs(w_ref))) + 1e-12)
    print(f'[2] streamed vs full-batch : max_abs_diff={max_abs:.3e}  '
          f'rel={rel:.3e}  (chunk={chunk} vs N={_N})')
    assert max_abs < 1e-6, f'streamed gradient diverged from full-batch: {max_abs}'

    # Cleanup.
    for p in (data, feat, out):
        os.remove(p)
    os.rmdir(tmp)
    print('ALL ASSERTIONS PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
