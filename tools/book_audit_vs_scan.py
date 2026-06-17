#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# Offline QUALITY audit of a Scan-style opening book, using Scan as a strong
# oracle. Consumes the two TSVs emitted by `jass --book-audit`:
#
#   <prefix>.moves.tsv   internal nodes : fen, book_move, score, n_children,
#                        n_within_margin, ply
#   <prefix>.leaves.tsv  frontier leaves: fen, score, ply
#
# Two measures, both independent of jass's own eval strength:
#
#   1. MOVE AGREEMENT — for a sample of internal nodes, does the book's
#      recommended move match Scan's best move at fixed depth? (broken down by
#      ply). High agreement = the book recommends moves a strong engine endorses.
#
#   2. LEAF VALUE CALIBRATION — for a sample of leaves, correlate the book's
#      stored score with Scan's eval (Spearman, scale-free + sign agreement),
#      and flag TRAPS: leaves the book thinks are fine for the side to move
#      (score >= +50cp) but Scan judges lost (score < 0). A trap is a hole an
#      opponent can steer into.
#
# usage:
#   python3 tools/book_audit_vs_scan.py --moves P.moves.tsv --leaves P.leaves.tsv \
#       --scan /root/jass-scan/scan_linux [--scan-depth 13] [--sample-moves 300] \
#       [--sample-leaves 300] [--scan-bb-size 0]

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from calibrate_vs_scan import ScanEngine, parse_scan_move  # noqa: E402
from game_autopsy import scan_oracle                        # noqa: E402


def read_tsv(path):
    rows = []
    with open(path) as f:
        for ln in f:
            ln = ln.rstrip("\n")
            if not ln or ln.startswith("#"):
                continue
            rows.append(ln.split("\t"))
    return rows


def main(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--moves")
    p.add_argument("--leaves")
    p.add_argument("--scan", required=True)
    p.add_argument("--scan-depth", type=int, default=13)
    p.add_argument("--scan-bb-size", type=int, default=0)
    p.add_argument("--sample-moves", type=int, default=300)
    p.add_argument("--sample-leaves", type=int, default=300)
    p.add_argument("--seed", type=int, default=12345)
    a = p.parse_args(argv)
    random.seed(a.seed)

    scan = ScanEngine(a.scan, label="Scan-oracle",
                      no_book=True, bb_size=a.scan_bb_size)

    if a.moves:
        rows = read_tsv(a.moves)
        if len(rows) > a.sample_moves:
            rows = random.sample(rows, a.sample_moves)
        agree = tot = 0
        by_ply = {}
        for r in rows:
            if len(r) < 2:
                continue
            fen, bmove = r[0], r[1]
            ply = int(r[5]) if len(r) > 5 else -1
            mv, _ = scan_oracle(scan, fen, a.scan_depth)
            if mv is None:
                continue
            bm = parse_scan_move(bmove)
            ok = int(mv.frm == bm.frm and mv.to == bm.to)
            agree += ok
            tot += 1
            d = by_ply.setdefault(ply, [0, 0])
            d[0] += ok
            d[1] += 1
        pct = agree / max(1, tot) * 100
        print(f"MOVE AGREEMENT vs Scan@depth{a.scan_depth}: "
              f"{agree}/{tot} = {pct:.1f}%")
        for ply in sorted(by_ply):
            ok, n = by_ply[ply]
            print(f"   ply {ply:2d}: {ok}/{n} = {ok / max(1, n) * 100:.0f}%")
        print("   (>~85% = excellent ; <70% = book recommends moves Scan dislikes)")

    if a.leaves:
        rows = read_tsv(a.leaves)
        if len(rows) > a.sample_leaves:
            rows = random.sample(rows, a.sample_leaves)
        bs, ss, recs = [], [], []
        for r in rows:
            if len(r) < 2:
                continue
            fen = r[0]
            try:
                bscore = float(r[1])
            except ValueError:
                continue
            mv, sc = scan_oracle(scan, fen, a.scan_depth)
            if sc is None:
                continue
            bs.append(bscore)
            ss.append(sc)
            recs.append((bscore, sc, fen))
        if len(bs) > 2:
            import numpy as np
            from scipy.stats import spearmanr
            bsa, ssa = np.array(bs), np.array(ss)
            rho, _ = spearmanr(bsa, ssa)
            sign_ok = float(np.mean(
                (np.sign(bsa) == np.sign(ssa)) | (bsa == 0) | (ssa == 0))) * 100
            print(f"LEAF VALUE CALIBRATION (n={len(bs)}): "
                  f"spearman(book,scan)={rho:.3f}  sign-agreement={sign_ok:.0f}%")
            traps = [(b, s, f) for (b, s, f) in recs if b >= 50 and s < 0]
            traps.sort(key=lambda t: (t[0] - t[1] * 100), reverse=True)
            print(f"   potential traps (book>=+50cp but Scan<0): "
                  f"{len(traps)}/{len(bs)}")
            for b, s, f in traps[:8]:
                print(f"     book={b:+.0f} scan={s:+.2f}  {f}")
            print("   (high spearman + high sign-agreement + few traps = sound valuations)")

    try:
        scan.close()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
