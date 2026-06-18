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


def load_seeds(path: Path, min_pieces: int, rng: random.Random, n: int,
               shard: int = 0, nshards: int = 1) -> list[str]:
    """Sample up to `n` early-game (>= min_pieces) seed FENs.

    For parallel generation, pass nshards>1 with a SHARED rng seed across all
    shards: every shard shuffles the index list identically, then takes the
    disjoint stripe `idx[shard::nshards]`. This guarantees no two shards ever
    seed from the same opening — critical because Scan at a fixed depth is
    deterministic, so a shared opening would yield byte-identical games.
    """
    b = path.read_bytes()
    total = struct.unpack("<I", b[4:8])[0]
    body = b[8:]
    idx = list(range(total))
    rng.shuffle(idx)
    if nshards > 1:
        idx = idx[shard::nshards]
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
    # DIVERSITY (piste 3) — force decisive, varied self-play instead of quiet/drawish
    # Scan-vs-equal-Scan games (the 0327 low-contrast problem). Two knobs:
    #   --weak-depth D2 : the two sides play at DIFFERENT depths (strong --depth vs
    #     weak D2), the strong side randomized per game → decisive games, gradient.
    #   --depth-jitter J: per game, the (strong) depth is drawn from [depth-J, depth].
    ap.add_argument("--weak-depth", type=int, default=None,
                    help="weaker side's Scan depth (strong=--depth); asymmetric self-play")
    ap.add_argument("--depth-jitter", type=int, default=0,
                    help="per-game random depth reduction in [0, J] on the strong side")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--nshards", type=int, default=1,
                    help="total parallel shards (all must share the SAME --seed)")
    ap.add_argument("--shard", type=int, default=0, help="this shard's index in [0,nshards)")
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    seeds = load_seeds(args.seeds, args.min_pieces, rng, args.games,
                       shard=args.shard, nshards=args.nshards)
    if not seeds:
        print("error: no seed positions found", file=sys.stderr)
        return 1
    print(f"scan-selfplay: {len(seeds)} seeds (>= {args.min_pieces}p), Scan depth {args.depth}")

    scan = cv.ScanEngine(args.scan, bb_size=0)
    # Asymmetric-strength self-play (diversity): a SECOND Scan at --weak-depth.
    scan_weak = cv.ScanEngine(args.scan, bb_size=0) if args.weak_depth else None
    if scan_weak is not None:
        print(f"  diversity: strong depth {args.depth} vs weak depth {args.weak_depth} "
              f"(strong side randomized per game)")
    referee = cv.Referee(args.jass)
    records = bytearray()
    n_pos = 0
    wmap = {"W": 1, "D": 0, "L": -1}
    try:
        for g, opening in enumerate(seeds):
            # per-game depth jitter on the strong side
            sd = args.depth - (rng.randint(0, args.depth_jitter) if args.depth_jitter else 0)
            sd = max(2, sd)
            try:
                if scan_weak is not None:
                    # assign strong/weak to the two sides, randomized per game
                    scan.default_depth = sd
                    scan_weak.default_depth = args.weak_depth
                    if rng.random() < 0.5:
                        white, black = scan, scan_weak
                    else:
                        white, black = scan_weak, scan
                    r = cv.play_game(white, black, referee, opening,
                                     max_plies=args.max_plies)
                else:
                    r = cv.play_game(scan, scan, referee, opening,
                                     depth=sd, max_plies=args.max_plies)
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
        if scan_weak is not None:
            try: scan_weak.close()
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
