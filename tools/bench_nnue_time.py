#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Bench a Jass NNUE vs the handcrafted eval at a fixed movetime.

Sister of `tools/calibrate_vs_scan.py`, but instead of pitting Jass
against Scan we pit Jass-with-NNUE against Jass-without-NNUE. The
two players run the same binary, same search code, same time
control — the only difference is the leaf evaluation function.

Why this exists
---------------
The Scan-anchored calibrate (`calibrate_vs_scan.py`) is the project's
ultimate KPI but it clamps at 0/N (ELO -800) whenever Jass is more
than ~400 ELO weaker than Scan, which has been the case for every
single NNUE training run so far. That makes it useless as a *progress*
metric — every cycle reports the same -800 number, which doesn't tell
us whether a given training iteration moved the needle.

This bench gives a much finer signal. The handcrafted eval is a
stable reference point (it's been frozen since well before NNUE
training started). NNUE strength relative to it grew from 0.639 in
the legacy `train_mlp.py` era to 0.917 with the post-PR-#45 fix at
**depth 6 fixed**. Running the same comparison at **1.0 s/move** gives
us the strength delta in the real time control the engine is
expected to play under — and that delta is sensitive to every
training change.

Output
------
Same shape as calibrate_vs_scan.py, just labelled NNUE / Handcrafted:

    === NNUE vs Handcrafted, movetime 1.0s, 54 games ===
      NNUE=33  Handcrafted=11  Draws=10
      NNUE score rate: 0.704 (38.0 / 54)
      ELO estimate:    +151 (95% CI ≈ ±109)

The ELO estimate here is a *relative* ELO between the two players,
not an absolute FMJD strength. Useful for tracking improvements
between cycles; not directly comparable to Scan or external rating
scales.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Reuse the heavy lifting from calibrate_vs_scan: HUB protocol
# wrapper, game-play orchestrator, opening pool, ELO formula.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate_vs_scan import (         # noqa: E402  (deliberate side-import)
    JassEngine,
    Referee,
    play_game,
    opening_pool_via_jass,
    estimate_elo,
)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--jass", required=True,
                   help="path to the Jass binary used for both players "
                        "and the referee")
    p.add_argument("--nnue", required=True,
                   help="weights file (JNNM/JNNQ) passed to the NNUE "
                        "player via `--nnue`. The handcrafted player "
                        "always uses `--no-nnue`.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--depth",    type=int,
                   help="fixed search depth (plies)")
    g.add_argument("--movetime", type=float,
                   help="per-move time budget in seconds")
    p.add_argument("--pairs", type=int, default=3,
                   help="colour-swap pairs per opening "
                        "(total games = 9 openings × pairs × 2 colours)")
    p.add_argument("--max-plies", type=int, default=200)
    args = p.parse_args(argv)
    if args.depth is None and args.movetime is None:
        args.movetime = 1.0   # the production-grade default — the whole
                              # point of this bench is the time-controlled
                              # signal that --benchmark-nnue can't give us
    budget_str = (f"depth {args.depth}" if args.depth is not None
                  else f"movetime {args.movetime}s")

    openings = opening_pool_via_jass(args.jass)
    print(f"opening pool: {len(openings)} positions")
    print(f"NNUE under test: {args.nnue}")

    nnue_player = JassEngine(args.jass, label="NNUE",
                             nnue_path=args.nnue)
    hand_player = JassEngine(args.jass, label="Handcrafted",
                             no_nnue=True)
    referee     = Referee(args.jass)

    nnue_wins = hand_wins = draws = 0
    games = 0
    t0 = time.time()
    try:
        for opening in openings:
            for _pair in range(args.pairs):
                # Each pair: NNUE plays once as white, once as black.
                for nnue_is_white in (True, False):
                    if nnue_is_white:
                        r = play_game(nnue_player, hand_player, referee,
                                      opening,
                                      depth=args.depth,
                                      movetime=args.movetime,
                                      max_plies=args.max_plies)
                    else:
                        r = play_game(hand_player, nnue_player, referee,
                                      opening,
                                      depth=args.depth,
                                      movetime=args.movetime,
                                      max_plies=args.max_plies)
                    games += 1
                    # Map W/L (white-POV) to NNUE's POV.
                    if r.outcome == "D":
                        draws += 1
                        nnue_pts = 0.5
                    elif (r.outcome == "W" and nnue_is_white) or \
                         (r.outcome == "L" and not nnue_is_white):
                        nnue_wins += 1
                        nnue_pts = 1.0
                    else:
                        hand_wins += 1
                        nnue_pts = 0.0
                    elapsed = time.time() - t0
                    print(f"  game {games:3d}: "
                          f"{'NNUE' if nnue_is_white else 'Hand'}=W "
                          f"{'Hand' if nnue_is_white else 'NNUE'}=B "
                          f"→ {r.outcome} ({r.reason}, {r.plies} plies)  "
                          f"NNUE +{nnue_pts:.1f}  [{elapsed:.0f}s]")
    finally:
        nnue_player.close()
        hand_player.close()
        referee.close()

    nnue_score = nnue_wins + 0.5 * draws
    rate = nnue_score / games if games else 0.0
    elo  = estimate_elo(rate)

    print()
    print(f"=== NNUE vs Handcrafted, {budget_str}, {games} games ===")
    print(f"  NNUE={nnue_wins}  Handcrafted={hand_wins}  Draws={draws}")
    print(f"  NNUE score rate: {rate:.3f} ({nnue_score:.1f} / {games})")
    print(f"  ELO estimate:    {elo:+.0f} (95% CI ≈ ±{800/(games**0.5):.0f})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
