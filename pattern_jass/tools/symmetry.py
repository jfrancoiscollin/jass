# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Symmetry weight-sharing canonicalisation for the pattern table (Scan brick).

The board's exact symmetry is rot180 ∘ colour-swap (rotate 180° + swap colours =
same position from the other side → eval NEGATES). Pure colour-swap and pure rot180
are approximate (men have a direction) but pool data and empirically help.

This builds, for every (pattern p, config c), a CANONICAL column + a sign so that all
orbit members under the group G = {id, cs, rot, rot∘cs} SHARE one antisymmetric weight:
    W_full[p][c] = sign[p][c] · w_canon[canon_col[p][c]]
with the exact identity  W[rot∘cs·(p,c)] = -W[p][c]  guaranteed. rot/rot∘cs apply only
where rot180(p) is itself a pattern (13 pairs + diag_3 self); the 5 horiz orphans fall
back to {id, cs} (colour-fold). Trains over the (sparse) canonical column space; --prune
compresses it; output is EXPANDED to a standard 17M v3 .pjtw (C++ eval unchanged)."""
import numpy as np
import patterns as P

NB   = 3 ** P.PATTERN_SIZE          # 531441 configs / pattern
SIZE = P.PATTERN_SIZE               # 12
POW3 = (3 ** np.arange(SIZE)).astype(np.int64)


def colorswap_map():
    """u -> config with black(1)/white(2) swapped per square (empty stays)."""
    tmp = np.arange(NB, dtype=np.int64).copy()
    cs = np.zeros(NB, dtype=np.int64)
    for k in range(SIZE):
        cell = tmp % 3; tmp //= 3
        cs += np.where(cell == 1, 2, np.where(cell == 2, 1, 0)) * POW3[k]
    return cs


def rot_structure():
    """rp[p] = index of rot180(pattern p) in the set, or -1 (orphan).
    rotperm[p][k] = position (in rp[p]'s square order) of p's square k under s->51-s."""
    pat = [list(p) for p in P.PATTERNS]
    idx = {tuple(sorted(q)): i for i, q in enumerate(pat)}
    rp = [-1] * P.NUM_PATTERNS
    rotperm = [None] * P.NUM_PATTERNS
    for i, q in enumerate(pat):
        key = tuple(sorted(51 - s for s in q))
        if key in idx:
            j = idx[key]; tgt = list(key)
            rotperm[i] = [tgt.index(51 - q[k]) for k in range(SIZE)]
            rp[i] = j
    return rp, rotperm


def translate_classes():
    """tc[p] = representative pattern index of p's translation class (patterns that
    are (row,file)-translates of each other with the same square k-ordering, so their
    config index is shared directly). 32 patterns -> 7 classes. APPROXIMATE prior:
    absolute board position (advancement, promotion rows) genuinely matters, so this
    pools positions that differ — test by Elo, not assumed correct."""
    def coord(n):
        r = (n - 1) // 5
        return (r, 2 * ((n - 1) % 5) + (1 if r % 2 == 0 else 0))
    co = [[coord(s) for s in pat] for pat in P.PATTERNS]
    def is_trans(a, b):
        d = (b[0][0] - a[0][0], b[0][1] - a[0][1])
        return all((b[k][0] - a[k][0], b[k][1] - a[k][1]) == d for k in range(len(a)))
    par = list(range(P.NUM_PATTERNS))
    def find(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    for i in range(P.NUM_PATTERNS):
        for j in range(i + 1, P.NUM_PATTERNS):
            if is_trans(co[i], co[j]):
                par[find(i)] = find(j)
    return [min(k for k in range(P.NUM_PATTERNS) if find(k) == find(p))
            for p in range(P.NUM_PATTERNS)]


def _reorder_all(perm):
    """For every config c, the config whose digit at perm[k] equals c's digit k."""
    tmp = np.arange(NB, dtype=np.int64).copy()
    out = np.zeros(NB, dtype=np.int64)
    p3 = 3 ** np.asarray(perm, dtype=np.int64)
    for k in range(SIZE):
        d = tmp % 3; tmp //= 3
        out += d * p3[k]
    return out


def build_canon(translate=False):
    """Returns (canon_col, sign): int64 (NP, NB) canonical 17M-space column, and
    int8 (NP, NB) sign∈{-1,0,+1} (0 = antisymmetry fixpoint → weight pinned to 0).
    translate=True ALSO folds the translation classes (approximate; Phase 3) by
    mapping every orbit pattern through its translate representative — composes with
    the exact colour+rot180 group (which is preserved)."""
    cs = colorswap_map()
    rp, rotperm = rot_structure()
    tc = translate_classes() if translate else list(range(P.NUM_PATTERNS))
    NP = P.NUM_PATTERNS
    canon_col = np.empty((NP, NB), dtype=np.int64)
    sign = np.empty((NP, NB), dtype=np.int8)
    c = np.arange(NB, dtype=np.int64)
    for p in range(NP):
        # orbit candidates: (pattern, config, intrinsic eval-sign σ); patterns are
        # mapped through tc[] so translates collapse (config index is preserved).
        cand = [(tc[p], c, 1), (tc[p], cs, -1)]
        if rp[p] >= 0:
            rc = _reorder_all(rotperm[p])
            cand += [(tc[rp[p]], rc, 1), (tc[rp[p]], cs[rc], -1)]
        g = [pp * NB + cc for (pp, cc, s) in cand]          # global indices
        best = g[0].copy()
        best_s = np.full(NB, cand[0][2], dtype=np.int64)
        for (pp, cc, s), gi in zip(cand[1:], g[1:]):
            take = gi < best
            best = np.where(take, gi, best)
            best_s = np.where(take, s, best_s)
        # fixpoint detection: an orbit element equals the id candidate (tc[p],c)
        # with σ=-1 forces that weight = 0.
        self_g = tc[p] * NB + c
        fix = np.zeros(NB, dtype=bool)
        for (pp, cc, s), gi in zip(cand, g):
            fix |= (gi == self_g) & (s == -1)
        canon_col[p] = best
        sign[p] = np.where(fix, 0, best_s).astype(np.int8)   # store-sign = σ_canonical
    return canon_col, sign
