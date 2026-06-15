#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Search-stability label filter — does score STABILITY predict label CORRECTNESS?

Idea (cf. the noisy-endgame-label problem): a search score that OSCILLATES across
depths (d8=+0.2, d10=-0.1, d12=+0.35) has not converged → unreliable label ; a
score that is STABLE (same sign, small Δ) across depths is trustworthy even at a
modest depth. So instead of trusting one deep score, keep only positions where the
iterative-deepening search is stable, and mark the rest "uncertain".

This validates the idea against GROUND TRUTH (Scan-d10 in the master): among the
ENDGAME positions, do the STABLE ones agree with Scan far more than the UNSTABLE
ones? If yes, the stability filter cleanly extracts the reliable labels from our
(weak) search → train the endgame eval on those.

Inputs (all the SAME positions, same order):
  --base   master subset JNNW (Scan-d10 score = GROUND TRUTH + bitboards for popcount)
  --scored d8.jnnw d10.jnnw d12.jnnw  (our search scores at each depth)

Usage:
  python3 tools/stability_filter.py --base endg.jnnw \\
      --scored endg-d8.jnnw endg-d10.jnnw endg-d12.jnnw \\
      --depths 8 10 12 --delta 30 --pieces-max 14 [--score-drop 4900] [--out report.txt]
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "pattern_jass" / "tools"))
import master_loader            # noqa: E402
from eval_proxy import read_scores  # noqa: E402


def popcount64(a: np.ndarray) -> np.ndarray:
    return np.unpackbits(a.view(np.uint8)).reshape(len(a), 64).sum(axis=1)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base", required=True, help="master subset JNNW (Scan ground-truth scores)")
    p.add_argument("--scored", nargs="+", required=True, help="our search-scored JNNWs, one per depth")
    p.add_argument("--depths", nargs="+", type=int, required=True)
    p.add_argument("--delta", type=float, default=30.0, help="|s_top - s_prev| <= this cp = converged")
    p.add_argument("--pieces-max", type=int, default=14, help="endgame = popcount <= this")
    p.add_argument("--score-drop", type=float, default=4900, help="drop |Scan|>this (won/lost sentinels)")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    assert len(args.scored) == len(args.depths) >= 2, "need >=2 (scored, depth) pairs"

    ds = master_loader.load(args.base)
    scan = ds.score.astype(np.float64)                       # ground truth (STM-POV cp)
    pieces = (popcount64(ds.white_men) + popcount64(ds.white_kings)
              + popcount64(ds.black_men) + popcount64(ds.black_kings))
    has_king = (ds.white_kings | ds.black_kings) != 0
    S = np.stack([read_scores(f, 0, 0) for f in args.scored], axis=0)  # (D, n) our scores
    n = len(scan)
    for row in S:
        assert len(row) == n, f"length mismatch {len(row)} vs {n}"

    # --- stability across depths (use all depths for sign, top two for Δ) ---
    signs = np.sign(S)
    sign_stable = np.all(signs == signs[-1], axis=0)         # same sign at every depth
    delta_ok = np.abs(S[-1] - S[-2]) <= args.delta           # converged at the top
    stable = sign_stable & delta_ok

    # --- restrict to endgames, drop Scan sentinels & near-zero (no meaningful sign) ---
    keep = (pieces <= args.pieces_max) & (np.abs(scan) <= args.score_drop) & (np.abs(scan) > 20)
    agree = np.sign(S[-1]) == np.sign(scan)                  # our top-depth sign vs Scan

    def rate(mask):
        m = mask & keep
        return int(m.sum()), (float(agree[m].mean()) if m.any() else float("nan"))

    out = []
    out.append("=" * 66)
    out.append(f"  STABILITÉ → JUSTESSE  (finale popcount<={args.pieces_max}, depths {args.depths}, "
               f"Δ<={int(args.delta)}cp)")
    out.append(f"  base={args.base}")
    out.append("=" * 66)
    nE = int(keep.sum())
    nS, aS = rate(stable)
    nU, aU = rate(~stable)
    out.append(f"  finales jugeables    : {nE}")
    out.append(f"  STABLES              : n={nS} ({100*nS/max(nE,1):.1f}%)  accord-Scan={aS:.3f}")
    out.append(f"  INSTABLES            : n={nU} ({100*nU/max(nE,1):.1f}%)  accord-Scan={aU:.3f}")
    out.append(f"  GAIN du filtre       : {aS-aU:+.3f}  (stable − instable)")
    out.append("\n-- STABLES, par rois --")
    for kk, lab in ((False, "no-king"), (True, "kings")):
        nk, ak = rate(stable & (has_king == kk))
        out.append(f"  {lab:8s} n={nk:6d}  accord-Scan={ak:.3f}")
    out.append("\n-- accord global (toutes finales, sans filtre) vs STABLES --")
    nA, aA = rate(np.ones(n, bool))
    out.append(f"  sans filtre : accord={aA:.3f} (n={nA})   |   stables : accord={aS:.3f} (n={nS})")
    out.append("")
    out.append(f"  accord(stable) >> accord(instable) → la STABILITÉ prédit la JUSTESSE :")
    out.append(f"  garder les stables extrait les labels fiables de notre recherche (filtre VALIDE).")
    out.append(f"  accord(stable) ≈ accord(instable) → la stabilité ne discrimine pas (filtre INUTILE ici).")
    rep = "\n".join(out)
    print(rep)
    if args.out:
        Path(args.out).write_text(rep + "\n")
        print(f"\nrapport: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
