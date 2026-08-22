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
import argparse, hashlib, json, sys, time
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
    p.add_argument("--movetime", type=float, default=None,
                   help="seconds/move for BOTH sides (overrides --depth). Use for "
                        "equal-time A/B where one side has a costlier search (e.g. ext_forcing).")
    p.add_argument("--pairs", type=int, default=8, help="colour-swap pairs per opening")
    p.add_argument("--max-plies", type=int, default=160)
    p.add_argument("--game-timeout", type=float, default=None,
                   help="per-game wall-clock cap in seconds; a game exceeding it is scored a DRAW. "
                        "Bounds the movetime-endgame overshoot bug (moves stay under the per-move "
                        "timeout but accumulate) so the gate completes instead of running for hours.")
    p.add_argument("--shard", type=int, default=0, help="this shard index [0..nshards)")
    p.add_argument("--nshards", type=int, default=1, help="total shards (game-level parallelism)")
    p.add_argument("--quiet", action="store_true", help="only print the RESULT line")
    p.add_argument("--search-params-a", default=None,
                   help="HUB --search-params override for side A (e.g. no_reduce_forcing=1)")
    p.add_argument("--search-params-b", default=None,
                   help="HUB --search-params override for side B")
    p.add_argument("--progress-file", default=None,
                   help="write the running 'RESULT a d b' tally to this path after EVERY "
                        "game (overwrite+flush). Survives the runner's non-flush on jobs whose "
                        "result is only known at the end (point it under the committed artefacts dir).")
    p.add_argument("--results-jsonl", default=None,
                   help="optional per-game JSONL for paired opening-level inference; each shard "
                        "must write a distinct path")
    p.add_argument("--dump-games-dir", default=None,
                   help="optional directory for immutable complete per-game JSON dumps "
                        "(opening, moves and FEN trajectory); global game indices make "
                        "concurrent shard filenames disjoint")
    p.add_argument("--openings-file", default=None,
                   help="play from custom opening FENs (one per line, '#' comments). With deterministic "
                        "search each (opening, colour) is ONE unique game, so the built-in 9-opening pool "
                        "caps N at ~18 — pass e.g. data/dilf_combinations.fen for hundreds of openings.")
    args = p.parse_args(argv)

    a = JassEngine(args.jass_a, label="A", pattern_path=args.pattern_a,
                   search_params=args.search_params_a)
    b = JassEngine(args.jass_b, label="B", pattern_path=args.pattern_b,
                   search_params=args.search_params_b)
    referee = Referee(args.jass_a)   # play_game needs a Referee (apply_move/legality), NOT a JassEngine
    if args.openings_file:
        openings = [o for o in (ln.split("#", 1)[0].strip() for ln in open(args.openings_file)) if o]  # filtre les vides (lignes # / vides) -> sinon set_position_fen("") hang
        openings = [o for o in openings if o]
    else:
        openings = opening_pool_via_jass(args.jass_a)

    # Full deterministic game list, then take this shard's disjoint slice.
    specs = [
        (game_index, opening_index, pair_index, opening, a_is_white)
        for game_index, (opening_index, pair_index, opening, a_is_white) in enumerate(
            (opening_index, pair_index, opening, a_is_white)
            for opening_index, opening in enumerate(openings)
            for pair_index in range(args.pairs)
            for a_is_white in (True, False)
        )
    ]
    specs = specs[args.shard::args.nshards]

    a_wins = b_wins = draws = 0
    t0 = time.time()
    results_handle = open(args.results_jsonl, "w", encoding="utf-8") if args.results_jsonl else None
    dump_dir = Path(args.dump_games_dir) if args.dump_games_dir else None
    if dump_dir is not None:
        dump_dir.mkdir(parents=True, exist_ok=True)
    for game_index, opening_index, pair_index, opening, a_is_white in specs:
        white, black = (a, b) if a_is_white else (b, a)
        error = None
        try:
            r = play_game(white, black, referee, opening,
                          depth=(None if args.movetime else args.depth),
                          movetime=args.movetime, max_plies=args.max_plies,
                          game_timeout_s=args.game_timeout)
        except Exception as exc:  # noqa: BLE001
            # ROBUSTESSE : un coup qui timeout (overshoot movetime-endgame) ou un moteur qui
            # deraille NE DOIT PAS crasher le shard (= perte de toutes les games restantes).
            # Compter nulle + continuer. (Sinon un seul mauvais game fait chuter n / peut hang.)
            print(f"  game skipped ({exc})", file=sys.stderr, flush=True)
            draws += 1
            outcome = "D"
            score_a = 0.5
            error = str(exc)
        else:
            outcome = r.outcome
            if outcome == "D":
                draws += 1
                score_a = 0.5
            elif (outcome == "W" and a_is_white) or (outcome == "L" and not a_is_white):
                a_wins += 1
                score_a = 1.0
            else:
                b_wins += 1
                score_a = 0.0
            if dump_dir is not None:
                dump_path = dump_dir / f"game-{game_index:08d}.json"
                payload = {
                    "schema": "jass.complete_game_dump.v1",
                    "game_id": game_index,
                    "opening_id": hashlib.sha256(opening.encode("utf-8")).hexdigest()[:16],
                    "opening_index": opening_index,
                    "opening": opening,
                    "pair_index": pair_index,
                    "jass_is_white": a_is_white,
                    "jass_score": score_a,
                    "outcome": outcome,
                    "reason": r.reason,
                    "plies": r.plies,
                    "moves": list(r.moves),
                    "fens": list(r.fens),
                }
                if len(payload["fens"]) != len(payload["moves"]) + 1:
                    raise RuntimeError("complete game trajectory contract drift")
                with dump_path.open("x", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2, sort_keys=True)
                    handle.write("\n")
        if results_handle:
            results_handle.write(json.dumps({
                "game_index": game_index,
                "opening_index": opening_index,
                "opening_sha256": hashlib.sha256(opening.encode("utf-8")).hexdigest(),
                "pair_index": pair_index,
                "a_is_white": a_is_white,
                "outcome_white": outcome,
                "score_a": score_a,
                "error": error,
            }, sort_keys=True) + "\n")
            results_handle.flush()
        # Incremental tally so the running result survives the runner's non-flush
        # (the final RESULT only lands at job end otherwise → lost if not committed).
        if args.progress_file:
            with open(args.progress_file, "w") as pf:
                pf.write(f"RESULT {a_wins} {draws} {b_wins}\n")
                pf.flush()
    # Machine-readable line for aggregation across shards.
    print(f"RESULT {a_wins} {draws} {b_wins}")
    if not args.quiet:
        g = a_wins + b_wins + draws
        rate = (a_wins + 0.5 * draws) / g if g else 0.0
        print(f"  shard {args.shard}/{args.nshards}  games={g}  A={a_wins} B={b_wins} D={draws}  ({time.time()-t0:.0f}s)")
        print(f"  A score rate: {rate:.3f}   elo(A-B) ~ {estimate_elo(rate):+.0f}")
    for eng in (a, b, referee):
        try: eng.close()
        except Exception: pass
    if results_handle:
        results_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
