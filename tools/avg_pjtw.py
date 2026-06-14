#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Federated-averaging merge for PJTW v3 evals.

Averages N v3 .pjtw weight files ELEMENT-WISE into one — the merge step of
"train each box on a data half in parallel, then average the weights" (uses both
boxes without per-iteration gradient sync). Same geometry required (identical
header layout: the per-box prune sets differ but each .pjtw is expanded to the
full un-pruned 17M/12.75M layout, so columns align; an unvisited bucket is 0).

CAVEAT (measured by the 0245 federated test): a pattern bucket visited on only
ONE box gets its trained weight there and 0 on the others → the naive mean halves
it (vs the joint fit's full value). --counts <census.npy ...> does a VISIT-WEIGHTED
mean per pattern column to undo that bias; the dense extras (always visited) are
unaffected either way.

Usage:
   python3 tools/avg_pjtw.py --out merged.pjtw  a.pjtw b.pjtw [c.pjtw ...]
"""
from __future__ import annotations
import argparse, struct, sys
import numpy as np

HDR = 20  # magic, version, scale, n_pat, n_ext  (5 × uint32)


def load(path):
    b = open(path, 'rb').read()
    magic, ver, scale, n_pat, n_ext = struct.unpack('<5I', b[:HDR])
    if ver != 3:
        sys.exit(f'{path}: PJTW version {ver} (only v3 supported for averaging)')
    total = 2 * (n_pat + n_ext)
    w = np.frombuffer(b[HDR:HDR + total * 4], dtype='<i4').astype(np.float64)
    if b[HDR + total * 4:]:
        sys.exit(f'{path}: trailing bytes (v4/FM?) — averaging only plain v3')
    return (magic, ver, scale, n_pat, n_ext), w


def main(argv):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', required=True)
    p.add_argument('files', nargs='+', help='2+ v3 .pjtw to average')
    p.add_argument('--counts', nargs='*', default=None,
                   help='optional per-file pattern visit-count .npy (len=n_pat) '
                        'for a visit-weighted mean of the PATTERN columns')
    args = p.parse_args(argv)
    if len(args.files) < 2:
        sys.exit('need >=2 files to average')

    hdr0, w0 = load(args.files[0])
    ws = [w0]
    for f in args.files[1:]:
        h, w = load(f)
        if h[3:] != hdr0[3:]:        # n_pat, n_ext must match
            sys.exit(f'{f}: geometry {h[3:]} != {hdr0[3:]}')
        ws.append(w)
    W = np.stack(ws, 0)              # (N, total)
    n_pat, n_ext = hdr0[3], hdr0[4]

    if args.counts:
        if len(args.counts) != len(args.files):
            sys.exit('--counts must give one .npy per file')
        cts = [np.load(c).astype(np.float64) for c in args.counts]   # each (n_pat,)
        # per-pattern-column weights (mg & eg share the bucket's visit count);
        # extras get uniform weights (always visited).
        cw = np.stack(cts, 0)                                        # (N, n_pat)
        denom = cw.sum(0); denom[denom == 0] = 1.0
        merged = np.empty_like(w0)
        for blk, off in ((0, 0), (1, n_pat)):                       # pat_mg, pat_eg
            merged[off:off + n_pat] = (cw * W[:, off:off + n_pat]).sum(0) / denom
        e0 = 2 * n_pat
        merged[e0:] = W[:, e0:].mean(0)                             # extras: plain mean
        mode = 'visit-weighted (patterns) + mean (extras)'
    else:
        merged = W.mean(0)
        mode = 'naive element-wise mean'

    out = np.round(merged).clip(-(2**31), 2**31 - 1).astype('<i4')
    with open(args.out, 'wb') as o:
        o.write(struct.pack('<5I', *hdr0))
        o.write(out.tobytes())
    # report how much the naive mean would have shrunk one-box buckets
    nz_any = (W != 0).any(0)
    nz_one = ((W != 0).sum(0) == 1)
    print(f'averaged {len(args.files)} evals ({mode})')
    print(f'  pattern+extras cols={len(merged):,}  nonzero in >=1 box={int(nz_any.sum()):,}'
          f'  in exactly 1 box={int(nz_one.sum()):,} '
          f'({100*nz_one.sum()/max(nz_any.sum(),1):.1f}% — these the naive mean halves)')
    print(f'  wrote {args.out}')


if __name__ == '__main__':
    main(sys.argv[1:])
