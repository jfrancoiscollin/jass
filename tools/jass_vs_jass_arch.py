#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Cross-architecture head-to-head : two DIFFERENT jass binaries (e.g. a 32-pattern
build vs an 8-pattern build), each with its own pattern eval (.pjtw), play a
colour-swapped match. `benchmark-nnue-vs-nnue` can't do this (it loads both
.pjtw in ONE binary, so same NUM_PATTERNS only) — this is how we judge two
ARCHITECTURES against each other (self-judge, no Scan). Same-arch works too
(pass the same binary twice) — used as the loop's fast parallel judge.

    python3 tools/jass_vs_jass_arch.py --jass-a A --pattern-a a.pjtw \\
        --jass-b B --pattern-b b.pjtw --depth 9 --pairs 28

Games are SEQUENTIAL within a process. For speed, SHARD across cores : run N
processes with --shard i --nshards N (each plays a disjoint slice) and sum the
machine-readable `RESULT <a_wins> <draws> <b_wins>` lines.

    for i in $(seq 0 $((NCPU-1))); do
      python3 tools/jass_vs_jass_arch.py ... --pairs 28 --shard $i --nshards $NCPU &
    done; wait     # then sum the RESULT lines
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate_vs_scan import (JassEngine, Referee, play_game,
                               opening_pool_via_jass, estimate_elo)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--jass-a", required=True)
    p.add_argument("--pattern-a", required=True)
    p.add_argument("--jass-b", required=True)
    p.add_argument("--pattern-b", required=True)
    p.add_argument("--depth", type=int, default=9)
    p.add_argument("--pairs", type=int, default=8, help="colour-swap pairs per opening")
    p.add_argument("--max-plies", type=int, default=160)
    p.add_argument("--shard", type=int, default=0, help="this shard index [0..nshards)")
    p.add_argument("--nshards", type=int, default=1, help="total shards (game-level parallelism)")
    p.add_argument("--quiet", action="store_true", help="only print the RESULT line")
    args = p.parse_args(argv)

    a = JassEngine(args.jass_a, label="A", pattern_path=args.pattern_a)
    b = JassEngine(args.jass_b, label="B", pattern_path=args.pattern_b)
    referee = Referee(args.jass_a)   # play_game needs a Referee (apply_move/legality), NOT a JassEngine
    openings = opening_pool_via_jass(args.jass_a)

    # Full deterministic game list, then take this shard's disjoint slice.
    specs = [(op, aw) for op in openings for _ in range(args.pairs) for aw in (True, False)]
    specs = specs[args.shard::args.nshards]

    a_wins = b_wins = draws = 0
    t0 = time.time()
    for opening, a_is_white in specs:
        white, black = (a, b) if a_is_white else (b, a)
        r = play_game(white, black, referee, opening, depth=args.depth, max_plies=args.max_plies)
        if r.outcome == "D":
            draws += 1
        elif (r.outcome == "W" and a_is_white) or (r.outcome == "L" and not a_is_white):
            a_wins += 1
        else:
            b_wins += 1
    # Machine-readable line for aggregation across shards.
    print(f"RESULT {a_wins} {draws} {b_wins}")
    if not args.quiet:
        g = a_wins + b_wins + draws
        rate = (a_wins + 0.5 * draws) / g if g else 0.0
        print(f"  shard {args.shard}/{args.nshards}  games={g}  A={a_wins} B={b_wins} D={draws}  ({time.time()-t0:.0f}s)")
        print(f"  A score rate: {rate:.3f}   elo(A-B) ~ {estimate_elo(rate):+.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
