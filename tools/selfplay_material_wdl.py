#!/usr/bin/env python3
"""Self-play one engine against itself from fixed-material start positions and
tally W/D/L from the material-up side's point of view.

For each start FEN the SAME engine (Scan-vs-Scan or gen2-vs-gen2) plays both
sides to a terminal / 25-move / ply-cap result at a fixed budget (depth). The
outcome is reported from the side that holds the material lead (e.g. 20 men vs
18), so the tally answers: how decisively does this engine's play convert a
2-man edge? Engines and referee are reused across positions.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate_vs_scan import (  # noqa: E402
    JassEngine, ScanEngine, Referee, play_game, parse_jass_fen,
)


def read_positions(path: str) -> list[str]:
    fens = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        fen = raw.split("#", 1)[0].strip()
        if fen:
            fens.append(fen)
    return fens


def up_side(fen: str, big: int) -> str:
    """Return 'W' or 'B' — the side holding `big` total pieces."""
    _stm, wm, wk, bm, bk = parse_jass_fen(fen)
    w, b = len(wm) + len(wk), len(bm) + len(bk)
    if w == big:
        return "W"
    if b == big:
        return "B"
    raise ValueError(f"neither side has {big} pieces: {fen}")


def make_engines(kind: str, jass: str, scan: str, pattern: str | None):
    if kind == "jass":
        if not pattern:
            raise SystemExit("--jass-pattern required for engine=jass")
        white = JassEngine(jass, label="gen2-W", pattern_path=pattern)
        black = JassEngine(jass, label="gen2-B", pattern_path=pattern)
    elif kind == "scan":
        white = ScanEngine(scan, label="scan-W")
        black = ScanEngine(scan, label="scan-B")
    else:
        raise SystemExit(f"unknown engine {kind}")
    return white, black


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", choices=("jass", "scan"), required=True)
    ap.add_argument("--jass", required=True, help="jass binary (engine and/or referee)")
    ap.add_argument("--scan", default="", help="scan binary (engine=scan)")
    ap.add_argument("--jass-pattern", default="", help="gen2 pattern (engine=jass)")
    ap.add_argument("--positions", required=True)
    ap.add_argument("--big", type=int, default=20)
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--max-plies", type=int, default=400)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    fens = read_positions(args.positions)
    mine = [(i, f) for i, f in enumerate(fens) if i % args.nshards == args.shard]

    white, black = make_engines(args.engine, args.jass, args.scan, args.jass_pattern or None)
    referee = Referee(args.jass)
    tally = {"W": 0, "D": 0, "L": 0}
    per_pos = []
    try:
        for idx, fen in mine:
            up = up_side(fen, args.big)
            gr = play_game(white, black, referee, fen, depth=args.depth, max_plies=args.max_plies)
            # gr.outcome is from White's POV; fold to the material-up side.
            if up == "W":
                up_outcome = gr.outcome
            else:
                up_outcome = {"W": "L", "L": "W", "D": "D"}[gr.outcome]
            tally[up_outcome] += 1
            per_pos.append({"index": idx, "up_side": up, "up_outcome": up_outcome,
                            "white_outcome": gr.outcome, "plies": gr.plies, "reason": gr.reason})
    finally:
        for e in (white, black):
            try:
                e.close()
            except Exception:
                pass
        try:
            referee.close()
        except Exception:
            pass

    n = sum(tally.values())
    report = {
        "schema": 1, "stage": "selfplay_material_wdl", "engine": args.engine,
        "big": args.big, "depth": args.depth, "max_plies": args.max_plies,
        "shard": args.shard, "nshards": args.nshards, "n": n,
        "tally_up_side": tally,
        "pct_up_side": {k: round(100.0 * v / n, 2) for k, v in tally.items()} if n else {},
        "per_position": per_pos,
    }
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"engine": args.engine, "n": n, "tally": tally,
                      "pct": report["pct_up_side"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
