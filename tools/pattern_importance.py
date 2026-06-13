#!/usr/bin/env python3
"""Per-pattern (and per-symmetry-orbit) importance of a trained PJTW v3 eval.

Goal: data-driven GEOMETRY selection — find which patterns earn their keep so we can
prune to a lean set (fewer lookups → faster eval, toward Scan's leanness) WITHOUT
losing strength. Pairs with the symmetry fold (which makes weights dense): folding
finds the right weights, this finds the right SHAPES.

For each pattern p its contribution to the (black-POV) eval on a position is
    c_p(pos) = wmg·W_mg[off_p + idx_p] + weg·W_eg[off_p + idx_p]
(idx_p = base-3 men occupancy of p's squares; wmg=stage/40). Over a held-out set we
report, per pattern:
  * std(c_p)         — how much it MOVES the eval (≈0 → does nothing → prune)
  * corr(c_p, ref)   — alignment with the reference score (Scan-d10 / WDL); low → noise
  * max |corr(c_p,c_q)| — redundancy with another pattern (high → one is droppable)
Rank by std·|corr_ref| (moves the eval AND aligns with truth). Confirm any prune by
Elo (RFE), not by this score alone — same discipline as the proxy (cf B4).

Usage: python3 tools/pattern_importance.py --eval eval.pjtw --data set.jnnw \
         [--target score|wdl] [--max 50000] [--offset 0]
"""
import argparse, struct, sys
import numpy as np
sys.path.insert(0, 'pattern_jass/tools')
import patterns as P

REC = 38
NB = 3 ** P.PATTERN_SIZE          # 531441
MAX_PIECES = 40


def load_pjtw_v3(path):
    b = open(path, 'rb').read()
    magic, ver, scale, n_pat, n_ext = struct.unpack_from('<IIIII', b, 0)
    a = np.frombuffer(b, dtype='<i4', offset=20, count=2 * n_pat + 2 * n_ext)
    npat = n_pat // NB
    pat_mg = a[0:n_pat].reshape(npat, NB)
    pat_eg = a[n_pat:2 * n_pat].reshape(npat, NB)
    return scale, npat, pat_mg, pat_eg


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--eval', required=True, help='trained PJTW v3 .pjtw')
    ap.add_argument('--data', required=True, help='held-out JNNW position set')
    ap.add_argument('--target', choices=['score', 'wdl'], default='score')
    ap.add_argument('--max', type=int, default=50000)
    ap.add_argument('--offset', type=int, default=0)
    a = ap.parse_args()

    scale, npat, pat_mg, pat_eg = load_pjtw_v3(a.eval)
    if npat != P.NUM_PATTERNS:
        sys.exit(f"geometry mismatch: .pjtw has {npat} patterns but patterns.py has "
                 f"{P.NUM_PATTERNS}. Run with the MATCHING geometry checked out.")

    raw = open(a.data, 'rb').read()
    assert raw[:4] == b'JNNW'
    n = struct.unpack('<I', raw[4:8])[0]
    rec = np.frombuffer(raw[8:8 + n * REC], dtype=np.uint8).reshape(n, REC)
    rec = rec[a.offset:a.offset + a.max] if a.max else rec[a.offset:]
    bb = rec[:, 0:32].copy().view('<u8').reshape(-1, 4)   # wm,wk,bm,bk
    stm = rec[:, 32]
    score = rec[:, 33:37].copy().view('<i4').ravel().astype(np.float64)
    wdl = rec[:, 37].astype(np.int8).astype(np.float64)
    m = len(rec)

    # phase weight per position
    pieces = np.zeros(m, np.int64)
    for k in range(4):
        pieces += np.array([bin(int(x)).count('1') for x in bb[:, k]], np.int64)
    wmg = np.clip(pieces / MAX_PIECES, 0, 1); weg = 1 - wmg

    # reference target in BLACK-POV (contributions c_p are black-POV)
    tgt_stm = score if a.target == 'score' else wdl
    ref = np.where(stm == 1, -tgt_stm, tgt_stm)          # stm 1 = black ... flip to black-POV
    ref = ref - ref.mean()

    idx = P.extract_indices(bb[:, 2], bb[:, 0])          # (m, npat) men-only base-3
    C = np.empty((npat, m), np.float64)
    for p in range(npat):
        ip = idx[:, p]
        C[p] = wmg * pat_mg[p][ip] + weg * pat_eg[p][ip]

    std = C.std(axis=1)
    Cc = C - C.mean(axis=1, keepdims=True)
    rstd = ref.std() or 1.0
    corr_ref = (Cc @ ref) / (m * (std + 1e-9) * rstd)
    # redundancy: max |corr| with any OTHER pattern
    Cn = Cc / (std[:, None] * np.sqrt(m) + 1e-9)
    R = Cn @ Cn.T
    np.fill_diagonal(R, 0.0)
    red = np.abs(R).max(axis=1)
    red_with = np.abs(R).argmax(axis=1)

    imp = std * np.abs(corr_ref)                          # moves eval AND aligns with truth
    order = np.argsort(imp)[::-1]
    names = getattr(P, 'PATTERN_NAMES', [f'p{p}' for p in range(npat)])
    print(f"eval={a.eval}  patterns={npat}  positions={m}  target={a.target}  scale={scale}")
    print(f"{'rank':>4} {'pattern':<10} {'std':>9} {'corr_ref':>9} {'importance':>11} "
          f"{'redund':>7} {'with':<10}")
    for r, p in enumerate(order):
        print(f"{r:>4} {names[p]:<10} {std[p]:>9.2f} {corr_ref[p]:>+9.3f} "
              f"{imp[p]:>11.1f} {red[p]:>7.2f} {names[red_with[p]]:<10}")
    print(f"\nlow-importance tail (prune candidates): "
          f"{[names[p] for p in order[-max(1, npat//4):]]}")
    print("→ confirm any prune by Elo (RFE), not this score alone (cf B4).")


if __name__ == "__main__":
    main()
