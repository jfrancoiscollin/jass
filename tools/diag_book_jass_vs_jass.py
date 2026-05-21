#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""Book-bug diagnostic: jass+book vs jass-no-book, jass-vs-jass match.

0019, 0022 and 0023 all finalised at score rate 0.009 (= 0/53/1 = -812
ELO) against Scan, regardless of which book or Scan-book setting. That
identical result strongly suggests the failure is internal to jass's
`--book` codepath, not a function of book quality or of Scan's strength.

This harness isolates that hypothesis: same jass binary on BOTH sides,
same NNUE on both sides, the ONLY difference is one side has `--book
PATH` loaded and the other doesn't. Both sides play through the same
opening pool with colour swap, so any systematic deficit comes from the
book itself.

We log EVERY move so when jass+book loses (or wins), we can trace the
moment in each game where the book-side commits to a losing line.

Output:
  * stdout / -o file: a per-game move trace + an aggregate W/L/D table.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Reuse JassEngine + opening pool + parse helpers from the calibrate
# harness; the only thing that changes here is "Scan is replaced by a
# second JassEngine with --no-book / no --book".
sys.path.insert(0, str(Path(__file__).parent))
from calibrate_vs_scan import (  # noqa: E402
    JassEngine,
    Move,
    Referee,
    opening_pool_via_jass,
    estimate_elo,
)


def play_one_game(book_eng: JassEngine,
                  nobook_eng: JassEngine,
                  referee: Referee,
                  opening_fen: str,
                  book_plays_white: bool,
                  movetime: float,
                  max_plies: int,
                  log) -> tuple[str, int, str]:
    """Play one game; return (outcome_for_book_side, plies, reason).

    outcome_for_book_side ∈ {"W","L","D"} — i.e. always reported from
    the perspective of the side carrying the loaded book, regardless of
    which colour it played.
    """
    referee.set_position_fen(opening_fen)
    for eng in (book_eng, nobook_eng):
        eng.new_game()
        eng.set_position_fen(opening_fen)

    side_to_move = "W" if opening_fen.startswith("W") else "B"
    book_is_white = book_plays_white
    book_label = f"book(W)" if book_plays_white else f"book(B)"
    nobook_label = f"nobook(B)" if book_plays_white else f"nobook(W)"

    log(f"  opening {opening_fen}, book_side={book_label}, "
        f"nobook_side={nobook_label}")
    halfmove_counter = 0

    for ply in range(1, max_plies + 1):
        side_is_book = (side_to_move == "W") == book_is_white
        current = book_eng if side_is_book else nobook_eng
        clabel  = book_label if side_is_book else nobook_label

        mv = current.go(movetime=movetime)
        if mv is None or (mv.frm == 0 and mv.to == 0):
            outcome_white = "L" if side_to_move == "W" else "W"
            book_outcome = (outcome_white == "W") == book_is_white
            res = "W" if book_outcome else "L"
            log(f"  ply {ply}: {clabel} has no legal move → "
                f"{side_to_move} loses ({res} for book-side)")
            return res, ply, f"no legal move from {clabel}"

        if not referee.apply_move(mv):
            outcome_white = "L" if side_to_move == "W" else "W"
            book_outcome = (outcome_white == "W") == book_is_white
            res = "W" if book_outcome else "L"
            log(f"  ply {ply}: {clabel} → illegal {mv.jass_str()} → "
                f"forfeits ({res} for book-side)")
            return res, ply, f"illegal move {mv.jass_str()} from {clabel}"

        # Echo the move to both engines so their internal positions
        # stay in sync with the referee.
        for eng in (book_eng, nobook_eng):
            eng._send(f"apply {mv.jass_str()}")
            eng._read_until(lambda l: l == "ok" or l.startswith("error"))

        log(f"  ply {ply:3d}: {clabel} plays {mv.jass_str()}"
            + (f" (capture, x{mv.is_capture})" if mv.is_capture else ""))

        if mv.is_capture:
            halfmove_counter = 0
        else:
            halfmove_counter += 1
        if halfmove_counter >= 50:
            log(f"  ply {ply}: 25-move rule, declaring draw")
            return "D", ply, "25-move rule"

        side_to_move = "B" if side_to_move == "W" else "W"

    log(f"  ply {max_plies}: ply cap reached, declaring draw")
    return "D", max_plies, "ply cap"


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--jass",     required=True)
    p.add_argument("--book",     required=True,
                   help="JBOK book to load on ONE side only")
    p.add_argument("--nnue",     default=None,
                   help="custom NNUE weights for BOTH sides (default: embedded)")
    p.add_argument("--movetime", type=float, default=1.0)
    p.add_argument("--pairs",    type=int, default=1,
                   help="colour-swap pairs per opening; total games = 18×pairs")
    p.add_argument("--max-plies", type=int, default=200)
    p.add_argument("-o", "--output", default=None,
                   help="trace file (defaults to stdout)")
    args = p.parse_args(argv)

    log_file = open(args.output, "w") if args.output else sys.stdout
    def log(msg):
        print(msg, file=log_file, flush=True)

    log(f"=== diag_book_jass_vs_jass ===")
    log(f"  jass={args.jass}")
    log(f"  book={args.book}")
    log(f"  nnue={args.nnue or '(default embedded)'}")
    log(f"  movetime={args.movetime}s  pairs={args.pairs}")

    # Opening pool — reuse the 9-position default that calibrate uses.
    pool = opening_pool_via_jass(args.jass)
    log(f"  opening pool: {len(pool)} positions")

    nnue_path = args.nnue
    book_eng = JassEngine(args.jass, label="book",
                          no_book=False,
                          nnue_path=nnue_path,
                          book_path=args.book)
    nobook_eng = JassEngine(args.jass, label="nobook",
                            no_book=True,
                            nnue_path=nnue_path,
                            book_path=None)
    referee = Referee(args.jass)

    wins = losses = draws = 0
    games = []
    game_idx = 0
    for opening in pool:
        for pair in range(args.pairs):
            for book_white in (True, False):
                game_idx += 1
                log(f"\n=== game {game_idx} "
                    f"(opening={opening[:30]}..., "
                    f"book={'W' if book_white else 'B'}) ===")
                outcome, plies, reason = play_one_game(
                    book_eng, nobook_eng, referee, opening,
                    book_white, args.movetime, args.max_plies, log)
                games.append((game_idx, opening, book_white,
                              outcome, plies, reason))
                if   outcome == "W": wins   += 1
                elif outcome == "L": losses += 1
                else:                draws  += 1
                log(f"  game {game_idx}: {outcome} ({reason}, {plies} plies)  "
                    f"running W={wins} L={losses} D={draws}")

    book_eng.close()
    nobook_eng.close()
    referee.close()

    total = wins + losses + draws
    score = wins + 0.5 * draws
    rate  = score / total if total else 0.0
    elo   = estimate_elo(rate)

    log(f"\n=========================================================")
    log(f"  Book-side: W={wins}  L={losses}  D={draws}  (total {total})")
    log(f"  Book-side score rate: {rate:.3f} ({score}/{total})")
    log(f"  Book-side ELO estimate: {elo:+.0f}")
    log(f"=========================================================")
    log(f"")
    log(f"Interpretation:")
    log(f"  rate ≈ 0.50  →  book is neutral vs no-book (expected).")
    log(f"                  Bug must be elsewhere (NNUE+search alone")
    log(f"                  always loses to Scan, not a book issue).")
    log(f"  rate < 0.30  →  CONFIRMS book bug. Loading --book hurts")
    log(f"                  jass even against itself. Trace shows the")
    log(f"                  failure plies — debug from there.")
    log(f"  rate > 0.70  →  book is HELPFUL vs no-book. Then the Scan")
    log(f"                  regression must come from Scan-specific")
    log(f"                  interaction (e.g. timing, protocol drift).")

    if args.output:
        log_file.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
