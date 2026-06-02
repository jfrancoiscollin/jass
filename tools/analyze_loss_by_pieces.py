#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Post-hoc analysis of jass games vs Scan : where does jass win/lose by
piece count phase ?

Reads per-game JSONs produced by `calibrate_vs_scan.py --dump-games-dir`.
For each game, replays positions via the dumped FENs, tracks piece count
and (optionally) jass eval at each ply, then buckets games by piece
count at the "decision point" (drift to losing for losses, jump to
winning for wins).

Phases (matches Scan's typical piece-count breakdown) :
   opening   : 30 - 40 pieces
   midgame   : 22 - 29 pieces
   late-mid  : 15 - 21 pieces
   endgame   :  8 - 14 pieces
   deep-eg   :  2 -  7 pieces

Usage:
   python3 tools/analyze_loss_by_pieces.py \\
       --games-dir path/to/games/dir \\
       --nnue v11.bin \\
       --jass ./build/jass \\
       [--eval-threshold 200] [--max-games 0]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# Reuse jass FEN parsing from calibrate_vs_scan
sys.path.insert(0, str(Path(__file__).parent))
from calibrate_vs_scan import parse_jass_fen, JassEngine  # noqa: E402


def piece_count(fen: str) -> int:
    """Return total piece count from a jass FEN (W:W31-50:B1-20)."""
    _side, wm, wk, bm, bk = parse_jass_fen(fen)
    return len(wm) + len(wk) + len(bm) + len(bk)


def phase_bucket(n: int) -> str:
    if n >= 30: return "opening (30-40)"
    if n >= 22: return "midgame (22-29)"
    if n >= 15: return "late-mid (15-21)"
    if n >= 8:  return "endgame (8-14)"
    return "deep-eg (2-7)"


# Order phases for display
PHASE_ORDER = [
    "opening (30-40)",
    "midgame (22-29)",
    "late-mid (15-21)",
    "endgame (8-14)",
    "deep-eg (2-7)",
]


def analyze_game(g: dict, jass: Optional[JassEngine] = None,
                 eval_threshold: int = 200) -> dict:
    """Return per-game analysis :
       - terminal piece count (last FEN)
       - decision-point piece count (drift for losses, jump for wins)
       - jass POV outcome ("W"/"D"/"L")
    """
    fens = g.get("fens", [])
    if not fens:
        return {}

    jass_is_white = g["jass_is_white"]
    outcome_white = g["outcome"]  # W/D/L from white POV
    if outcome_white == "D":
        jass_outcome = "D"
    elif (outcome_white == "W" and jass_is_white) or \
         (outcome_white == "L" and not jass_is_white):
        jass_outcome = "W"
    else:
        jass_outcome = "L"

    terminal_pc = piece_count(fens[-1])

    # Decision point : without per-ply eval (which requires re-running
    # jass eval on each FEN — expensive), we use a proxy = the ply at
    # which the piece-count phase first matches the terminal phase. This
    # is the moment the game entered its final phase, which correlates
    # with the decisive material exchanges.
    terminal_bucket = phase_bucket(terminal_pc)
    decision_ply = None
    decision_pc = None
    for i, fen in enumerate(fens):
        pc = piece_count(fen)
        if phase_bucket(pc) == terminal_bucket:
            decision_ply = i
            decision_pc = pc
            break
    if decision_ply is None:
        decision_ply = 0
        decision_pc = piece_count(fens[0])

    # If a JassEngine instance is provided, run a richer drift analysis :
    # find the ply at which jass eval first crosses the threshold
    # (negative for losses, positive for wins).
    drift_ply = None
    drift_pc = None
    if jass is not None and jass_outcome != "D":
        # Replay FEN by FEN, query jass eval
        target_sign = -1 if jass_outcome == "L" else +1
        for i, fen in enumerate(fens):
            jass.set_position_fen(fen)
            # Quick d4 eval (cheap)
            jass._send("go depth 4")
            try:
                lines = jass._read_until(
                    lambda l: l.startswith("bestmove") or l.startswith("error"),
                    timeout_s=10.0)
            except (TimeoutError, RuntimeError):
                continue
            # parse score from "info" lines (jass HUB emits "info depth=X score=Y")
            score = None
            for ln in lines:
                m = re.search(r"\bscore=([-+]?\d+)\b", ln)
                if m:
                    score = int(m.group(1))
            if score is None:
                continue
            # STM-POV. Convert to jass-POV : if jass is white and STM is
            # white in fen, jass_score = +score. If STM is black and jass
            # is black, jass_score = +score. Otherwise flip.
            stm_is_white = fen.startswith("W")
            jass_score = score if (stm_is_white == jass_is_white) else -score
            if target_sign * jass_score >= eval_threshold:
                drift_ply = i
                drift_pc = piece_count(fen)
                break

    return {
        "jass_outcome":  jass_outcome,
        "outcome_white": outcome_white,
        "plies":         g["plies"],
        "terminal_pc":   terminal_pc,
        "decision_ply":  decision_ply,
        "decision_pc":   decision_pc,
        "drift_ply":     drift_ply,
        "drift_pc":      drift_pc,
        "reason":        g["reason"],
    }


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--games-dir", required=True, type=Path,
                   help="directory of per-game JSONs (from "
                        "calibrate_vs_scan --dump-games-dir)")
    p.add_argument("--jass", default=None,
                   help="optional path to jass binary for per-ply eval "
                        "drift analysis (slow ; without it, decision "
                        "point is the start of terminal piece-count "
                        "phase, which is a fair proxy for free)")
    p.add_argument("--nnue", default=None,
                   help="weights file for jass (when --jass is given)")
    p.add_argument("--eval-threshold", type=int, default=200,
                   help="centipawn threshold for drift detection")
    p.add_argument("--max-games", type=int, default=0,
                   help="cap games processed (0 = all)")
    args = p.parse_args(argv)

    game_files = sorted(args.games_dir.glob("game-*.json"))
    if args.max_games:
        game_files = game_files[:args.max_games]
    if not game_files:
        print(f"no games found in {args.games_dir}", file=sys.stderr)
        return 1

    jass = None
    if args.jass:
        jass = JassEngine(args.jass, label="Analyzer",
                          no_nnue=False, nnue_path=args.nnue, no_book=True)

    by_outcome_terminal = defaultdict(Counter)  # {jass_outcome: {bucket: count}}
    by_outcome_decision = defaultdict(Counter)
    by_outcome_drift    = defaultdict(Counter)
    outcomes = Counter()

    try:
        for gf in game_files:
            g = json.loads(gf.read_text())
            r = analyze_game(g, jass=jass, eval_threshold=args.eval_threshold)
            if not r:
                continue
            outcome = r["jass_outcome"]
            outcomes[outcome] += 1
            by_outcome_terminal[outcome][phase_bucket(r["terminal_pc"])] += 1
            by_outcome_decision[outcome][phase_bucket(r["decision_pc"])] += 1
            if r["drift_pc"] is not None:
                by_outcome_drift[outcome][phase_bucket(r["drift_pc"])] += 1
    finally:
        if jass is not None:
            jass.close()

    total = sum(outcomes.values())
    print(f"\nAnalyzed {total} games : "
          f"jass W={outcomes['W']}  D={outcomes['D']}  L={outcomes['L']}")
    print(f"score rate : {(outcomes['W'] + 0.5 * outcomes['D']) / total:.3f}")

    def print_table(title: str, table: dict):
        print(f"\n=== {title} ===")
        # Header
        outcomes_keys = ["L", "D", "W"]
        cols = "  ".join(f"{o:>8}" for o in outcomes_keys)
        print(f"  {'phase':<20}  {cols}")
        for phase in PHASE_ORDER:
            row = []
            for o in outcomes_keys:
                n = table[o].get(phase, 0)
                denom = outcomes[o] if outcomes[o] > 0 else 1
                pct = 100.0 * n / denom
                row.append(f"{n:3d} ({pct:4.1f}%)")
            print(f"  {phase:<20}  " + "  ".join(f"{c:>8}" for c in row))

    print_table("Terminal piece count (where the game ENDED)",
                by_outcome_terminal)
    print_table("Decision phase (when game entered its final phase)",
                by_outcome_decision)
    if jass is not None:
        print_table(f"Drift phase (eval crossed ±{args.eval_threshold} cp)",
                    by_outcome_drift)

    # Also : average plies per outcome
    print("\nAverage plies by outcome :")
    plies_by_outcome = defaultdict(list)
    for gf in game_files:
        g = json.loads(gf.read_text())
        jass_is_white = g["jass_is_white"]
        ow = g["outcome"]
        if ow == "D":
            o = "D"
        elif (ow == "W" and jass_is_white) or (ow == "L" and not jass_is_white):
            o = "W"
        else:
            o = "L"
        plies_by_outcome[o].append(g["plies"])
    for o in ("L", "D", "W"):
        ps = plies_by_outcome[o]
        if ps:
            print(f"  {o}: n={len(ps):3d}  avg={sum(ps)/len(ps):6.1f}  "
                  f"min={min(ps):3d}  max={max(ps):3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
