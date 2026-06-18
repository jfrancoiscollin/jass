#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-Francois Collin
"""Generate STRONG-distribution training positions by having Scan play itself.

Distillation only teaches the teacher's eval on the positions you show it; if those
positions come from weak self-play (covariate shift), you learn Scan's eval where it
does not matter. This tool produces positions from Scan's OWN play: it seeds games
from a pool of opening positions (sampled from a JNNW, high piece-count = early game),
has Scan play BOTH sides (reusing tools/calibrate_vs_scan's jass-referee + Scan player),
and dumps every position visited, labelled with the game outcome (WDL, stm-POV).

Output JNNW (score=0, wdl=game outcome). Distill with `--target wdl`, or relabel with
tools/relabel_with_scan.py to add Scan's eval score and `--target score`.
"""

from __future__ import annotations

import argparse
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import calibrate_vs_scan as cv  # noqa: E402

REC = 38


def _sqs(bb: int) -> list[int]:
    return [b + 1 for b in range(50) if (bb >> b) & 1]


def _popcount(*bbs: int) -> int:
    return sum(bin(b).count("1") for b in bbs)


def record_to_fen(rec: bytes) -> tuple[str, int]:
    """JNNW 38-byte record -> (jass FEN, piece count)."""
    wm, wk, bm, bk = struct.unpack("<4Q", rec[0:32])
    stm = rec[32]
    side = "W" if stm == 0 else "B"
    w = [f"K{s}" for s in _sqs(wk)] + [str(s) for s in _sqs(wm)]
    b = [f"K{s}" for s in _sqs(bk)] + [str(s) for s in _sqs(bm)]
    return f"{side}:W{','.join(w)}:B{','.join(b)}", _popcount(wm, wk, bm, bk)


def fen_to_record(fen: str, wdl_stm: int) -> bytes:
    side, wm, wk, bm, bk = cv.parse_jass_fen(fen)
    def bb(squares):
        v = 0
        for s in squares:
            v |= 1 << (s - 1)
        return v
    return (struct.pack("<4Q", bb(wm), bb(wk), bb(bm), bb(bk))
            + struct.pack("<B", 0 if side == "W" else 1)
            + struct.pack("<i", 0)
            + struct.pack("<b", wdl_stm))


def load_seeds(path: Path, min_pieces: int, rng: random.Random, n: int) -> list[str]:
    b = path.read_bytes()
    total = struct.unpack("<I", b[4:8])[0]
    body = b[8:]
    idx = list(range(total))
    rng.shuffle(idx)
    seeds: list[str] = []
    for i in idx:
        rec = body[i * REC:(i + 1) * REC]
        if len(rec) < REC:
            continue
        fen, pc = record_to_fen(rec)
        if pc >= min_pieces:
            seeds.append(fen)
            if len(seeds) >= n:
                break
    return seeds


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scan", required=True, help="Scan binary")
    ap.add_argument("--jass", required=True, help="jass binary (neutral referee)")
    ap.add_argument("--seeds", required=True, type=Path, help="JNNW to sample opening seeds from")
    ap.add_argument("--out", required=True, type=Path, help="output JNNW")
    ap.add_argument("--games", type=int, default=2000)
    ap.add_argument("--depth", type=int, default=8, help="Scan search depth per move")
    ap.add_argument("--max-plies", type=int, default=200)
    ap.add_argument("--min-pieces", type=int, default=40, help="seed piece-count floor (early game)")
    ap.add_argument("--sample-every", type=int, default=1, help="keep 1 position in N")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    seeds = load_seeds(args.seeds, args.min_pieces, rng, args.games)
    if not seeds:
        print("error: no seed positions found", file=sys.stderr)
        return 1
    print(f"scan-selfplay: {len(seeds)} seeds (>= {args.min_pieces}p), Scan depth {args.depth}")

    scan = cv.ScanEngine(args.scan, bb_size=0)
    referee = cv.Referee(args.jass)
    records = bytearray()
    n_pos = 0
    wmap = {"W": 1, "D": 0, "L": -1}
    try:
        for g, opening in enumerate(seeds):
            try:
                r = cv.play_game(scan, scan, referee, opening,
                                 depth=args.depth, max_plies=args.max_plies)
            except Exception as exc:  # noqa: BLE001 — keep going on a flaky game
                print(f"  game {g}: {exc}", file=sys.stderr)
                continue
            ow = wmap.get(r.outcome, 0)
            for k, fen in enumerate(r.fens):
                if k % args.sample_every:
                    continue
                try:
                    side = fen.split(":", 1)[0].strip()
                except Exception:
                    continue
                wdl = ow if side == "W" else -ow
                records += fen_to_record(fen, wdl)
                n_pos += 1
            if (g + 1) % 50 == 0:
                print(f"  {g+1}/{len(seeds)} games, {n_pos} positions", flush=True)
    finally:
        try: scan.close()
        except Exception: pass
        try: referee.close()
        except Exception: pass

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as f:
        f.write(b"JNNW")
        f.write(struct.pack("<I", n_pos))
        f.write(records)
    print(f"wrote {args.out} ({n_pos} positions from {len(seeds)} Scan self-play games)")
    return 0 if n_pos else 1


if __name__ == "__main__":
    raise SystemExit(main())
