#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Phase-broken agreement of an eval's STATIC scores vs a reference set.

This is `eval_proxy.py` sliced BY GAME PHASE (piece count) and king-presence.
It answers ONE diagnostic question, not a selection one:

    Where, along the men-count / king axis, does the eval's ranking of
    positions diverge from the reference (Scan-d10 master labels) ?

Used to disambiguate the endgame bleed seen in game autopsies (jobs 0249/0250 :
opening eval-loss ~0.05, endgame+king ~3.6). Train the BEST linear distillation
on the perfect Scan-d10 labels, then run this :

  * if the distilled eval ALSO collapses in the endgame (low spearman / high
    RMSE in the few-piece buckets) → the LINEAR CLASS cannot represent endgames
    even with perfect labels = class limit in the endgame.
  * if the distilled eval stays accurate per phase but the SELF-PLAY eval (0249)
    bleeds → the loop is DATA-FAMINE-limited in the endgame (recipe = feed more
    endgame/king labels), not class-limited.

NB this is a descriptive measurement (spearman/RMSE per bucket), NOT a model
selection criterion — the retired strength "proxy" was retired AS A SELECTOR
(use val-loss to pick, real games to judge). A per-phase residual map is a
legitimate microscope on WHERE a fitted model fails.

Pipeline mirrors eval_proxy.py : `jass --rewrite-scores-with-nnue` produces the
eval's static score per position; we read both the eval's and the master's
scores, bucket by piece count (from the master bitboards), and report per bucket
spearman + RMSE (cp) on the kept (non-sentinel) rows, plus the bucket sizes so
the famine itself (how few endgame/king labels exist) is visible.

Usage:
  python3 tools/phase_proxy.py --jass build/jass --eval distilled.pjtw \\
      --testset master-clean-scan-d10.jnnw [--offset 1300000] [--max 100000] \\
      [--score-drop 4900] [--out phase-ceiling.txt]
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "pattern_jass" / "tools"))
import master_loader  # noqa: E402
from eval_proxy import read_scores  # noqa: E402  (same byte layout, same slicing)

# Same phase boundaries as tools/game_autopsy.py so the two microscopes line up.
PHASES = [("opening", 30, 99), ("midgame", 22, 29), ("late-mid", 15, 21),
          ("endgame", 8, 14), ("deep-eg", 0, 7)]


def _popcount64(a: np.ndarray) -> np.ndarray:
    """Vectorised popcount of a uint64 array (no np.bitwise_count on older numpy)."""
    return np.unpackbits(a.view(np.uint8)).reshape(len(a), 64).sum(axis=1)


def phase_names(pieces: np.ndarray) -> np.ndarray:
    out = np.empty(len(pieces), dtype=object)
    for name, lo, hi in PHASES:
        out[(pieces >= lo) & (pieces <= hi)] = name
    return out


def bucket_stats(ref: np.ndarray, cand: np.ndarray):
    """spearman (rank agreement) + RMSE in cp (magnitude agreement) on a bucket."""
    n = len(ref)
    if n < 2 or ref.std() == 0 or cand.std() == 0:
        return n, float("nan"), float("nan")
    rho, _ = spearmanr(cand, ref)
    rmse = float(np.sqrt(np.mean((cand - ref) ** 2)))
    return n, rho, rmse


def main(argv):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--jass", required=True)
    p.add_argument("--eval", required=True, help="eval to score (.pjtw or .bin)")
    p.add_argument("--testset", required=True, help="JNNW set with reference scores")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--max", type=int, default=0, help="0 = all")
    p.add_argument("--score-drop", type=float, default=4900,
                   help="drop |ref|>this (won/lost sentinels) from agreement; 0=keep all")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    # --- reference scores + bitboards (master), sliced exactly like read_scores ---
    ds = master_loader.load(args.testset)
    sl = slice(args.offset, (args.offset + args.max) if args.max else None)
    ref = ds.score[sl].astype(np.float64)
    pieces = (_popcount64(ds.white_men[sl]) + _popcount64(ds.white_kings[sl])
              + _popcount64(ds.black_men[sl]) + _popcount64(ds.black_kings[sl]))
    has_king = (ds.white_kings[sl] | ds.black_kings[sl]) != 0

    # --- candidate (eval) static scores via the same pipeline as eval_proxy ---
    import subprocess, tempfile, os
    with tempfile.TemporaryDirectory() as td:
        scored = os.path.join(td, "scored.jnnw")
        r = subprocess.run([args.jass, "--rewrite-scores-with-nnue",
                            args.testset, scored, "--nnue", args.eval],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit(f"rewrite failed: {r.stderr.strip() or r.stdout.strip()}")
        cand = read_scores(scored, args.offset, args.max)
    if len(cand) != len(ref):
        sys.exit(f"length mismatch cand={len(cand)} ref={len(ref)}")

    keep = np.ones(len(ref), bool)
    if args.score_drop and args.score_drop > 0:
        keep = np.abs(ref) <= args.score_drop

    names = phase_names(pieces)
    out = []
    out.append("=" * 70)
    out.append(f"  PLAFOND PAR PHASE — accord éval-statique vs master (n={keep.sum()} "
               f"gardés / {len(ref)}, score-drop={int(args.score_drop)})")
    out.append(f"  eval={args.eval}")
    out.append("=" * 70)

    def row(label, mask):
        n_tot = int(mask.sum())
        m = mask & keep
        n, rho, rmse = bucket_stats(ref[m], cand[m])
        frac = 100.0 * n_tot / len(ref)
        rs = f"{rho:.3f}" if rho == rho else "  —"
        es = f"{rmse:7.0f}" if rmse == rmse else "    —"
        return (f"  {label:12s} n={n_tot:7d} ({frac:5.1f}%)  kept={n:7d}  "
                f"spearman={rs}  RMSE_cp={es}")

    out.append(line := row("GLOBAL", np.ones(len(ref), bool)))
    out.append("\n-- par PHASE (nb de pièces) --")
    for name, _lo, _hi in PHASES:
        out.append(row(name, names == name))
    out.append("\n-- par ROIS (confondu avec la phase) --")
    out.append(row("no-kings", ~has_king))
    out.append(row("kings", has_king))
    out.append("\n-- PHASE × ROIS (isole la part rois dans une même phase) --")
    for name, _lo, _hi in PHASES:
        for kk, lab in ((False, "no-king"), (True, "kings")):
            mask = (names == name) & (has_king == kk)
            if mask.any():
                out.append(row(f"{name}/{lab}", mask))
    out.append("\n-- DISTRIBUTION DES LABELS (famine = combien de positions par bucket) --")
    for name, _lo, _hi in PHASES:
        nk = int(((names == name) & ~has_king).sum())
        kg = int(((names == name) & has_king).sum())
        out.append(f"  {name:12s} no-king={nk:7d}  king={kg:7d}  total={nk+kg:7d}")
    out.append("")
    out.append("  LECTURE : spearman tombe / RMSE explose dans les buckets finale =")
    out.append("  la CLASSE linéaire ne sait pas représenter la finale (même labels parfaits).")
    out.append("  spearman reste haut partout = la classe tient ; le saignement en partie")
    out.append("  (autopsie 0249/0250) vient alors de la DONNÉE (famine finale) ou de la recherche.")

    report = "\n".join(out)
    print(report)
    if args.out:
        Path(args.out).write_text(report + "\n")
        print(f"\nrapport écrit : {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
