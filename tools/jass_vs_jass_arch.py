#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Cross-architecture head-to-head : two DIFFERENT jass binaries (e.g. a 32-pattern
build vs an 8-pattern build), each with its own pattern eval (.pjtw), play a
colour-swapped match. `benchmark-nnue-vs-nnue` can't do this (it loads both
.pjtw in ONE binary, so same NUM_PATTERNS only) — this is how we judge two
ARCHITECTURES against each other (self-judge, no Scan).

    python3 tools/jass_vs_jass_arch.py \\
        --jass-a build32/jass --pattern-a eval32cf.pjtw \\
        --jass-b build8/jass  --pattern-b eval8cf.pjtw  \\
        --depth 9 --pairs 8

Reports A's score rate over the shared opening pool (>0.5 → A's arch stronger).
Reuses JassEngine / Referee / play_game / opening pool from calibrate_vs_scan.
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate_vs_scan import (JassEngine, Referee, play_game,
                               opening_pool_via_jass, estimate_elo)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--jass-a", required=True, help="binary A (e.g. 32-pattern build)")
    p.add_argument("--pattern-a", required=True, help="A's pattern eval .pjtw")
    p.add_argument("--jass-b", required=True, help="binary B (e.g. 8-pattern build)")
    p.add_argument("--pattern-b", required=True, help="B's pattern eval .pjtw")
    p.add_argument("--depth", type=int, default=9)
    p.add_argument("--pairs", type=int, default=8, help="colour-swap pairs per opening")
    p.add_argument("--max-plies", type=int, default=160)
    args = p.parse_args(argv)

    a = JassEngine(args.jass_a, label="A", pattern_path=args.pattern_a)
    b = JassEngine(args.jass_b, label="B", pattern_path=args.pattern_b)
    referee = JassEngine(args.jass_a, label="Referee")   # legality only; either binary works
    openings = opening_pool_via_jass(args.jass_a)

    a_wins = b_wins = draws = 0
    games = 0
    t0 = time.time()
    for opening in openings:
        for _ in range(args.pairs):
            for a_is_white in (True, False):
                white, black = (a, b) if a_is_white else (b, a)
                r = play_game(white, black, referee, opening,
                              depth=args.depth, max_plies=args.max_plies)
                games += 1
                if r.outcome == "D":
                    draws += 1
                elif (r.outcome == "W" and a_is_white) or (r.outcome == "L" and not a_is_white):
                    a_wins += 1
                else:
                    b_wins += 1
    a_score = a_wins + 0.5 * draws
    rate = a_score / games if games else 0.0
    print(f"\n  games={games}  A={a_wins}  B={b_wins}  Draws={draws}  ({time.time()-t0:.0f}s)")
    print(f"  A score rate: {rate:.3f} ({a_score:.1f} / {games})   elo(A-B) ~ {estimate_elo(rate):+.0f}")
    print(f"  >0.5 → A's architecture is stronger ; <0.5 → B's.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
