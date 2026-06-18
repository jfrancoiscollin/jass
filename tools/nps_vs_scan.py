#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-Francois Collin
"""Measure jass' search-speed handicap vs Scan at EQUAL DEPTH.

For a sample of positions, time jass-to-depth-D and Scan-to-depth-D. The ratio
(jass_time / scan_time) is how many times slower jass is — i.e. exactly the
movetime-compensation factor for the permanent fair benchmark (give jass that
factor more time than Scan). Reuses the proven calibrate_vs_scan engine adapters.

Usage:
  nps_vs_scan.py --jass build/jass --scan scan_linux --positions corpus.jnnw \
      --jass-pattern eval.pjtw --n 40 --depths 9,12,15 --min-pieces 12
"""
from __future__ import annotations

import argparse
import random
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import calibrate_vs_scan as cv  # noqa: E402

REC = 38


def _sqs(bb: int) -> list[int]:
    return [b + 1 for b in range(50) if (bb >> b) & 1]


def load_fens(path: Path, n: int, min_pieces: int, rng: random.Random) -> list[str]:
    b = path.read_bytes()
    total = struct.unpack("<I", b[4:8])[0]
    body = b[8:]
    idx = list(range(total)); rng.shuffle(idx)
    out: list[str] = []
    for i in idx:
        rec = body[i * REC:(i + 1) * REC]
        if len(rec) < REC:
            continue
        wm, wk, bm, bk = struct.unpack("<4Q", rec[0:32])
        pc = sum(bin(x).count("1") for x in (wm, wk, bm, bk))
        if pc < min_pieces:
            continue
        side = "W" if rec[32] == 0 else "B"
        w = [f"K{s}" for s in _sqs(wk)] + [str(s) for s in _sqs(wm)]
        bl = [f"K{s}" for s in _sqs(bk)] + [str(s) for s in _sqs(bm)]
        out.append(f"{side}:W{','.join(w)}:B{','.join(bl)}")
        if len(out) >= n:
            break
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--jass", required=True)
    ap.add_argument("--scan", required=True)
    ap.add_argument("--jass-pattern", default=None)
    ap.add_argument("--positions", required=True, type=Path)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--depths", default="9,12,15")
    ap.add_argument("--min-pieces", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)

    depths = [int(d) for d in args.depths.split(",") if d.strip()]
    rng = random.Random(args.seed)
    fens = load_fens(args.positions, args.n, args.min_pieces, rng)
    if not fens:
        print("error: no positions", file=sys.stderr); return 1
    print(f"nps: {len(fens)} positions (>= {args.min_pieces}p), depths {depths}")

    jass = cv.JassEngine(args.jass, pattern_path=args.jass_pattern)
    scan = cv.ScanEngine(args.scan, bb_size=0)
    try:
        print(f"{'depth':>5} {'jass_s/pos':>11} {'scan_s/pos':>11} {'jass/scan':>10}")
        for D in depths:
            jt = st = 0.0; nj = ns = 0
            for fen in fens:
                spos = cv.jass_fen_to_scan_pos(fen)
                try:
                    jass.new_game(); jass.set_position_fen(fen)
                    t = time.perf_counter(); jass.go(depth=D); jt += time.perf_counter() - t; nj += 1
                except Exception:
                    pass
                try:
                    scan.new_game()
                    t = time.perf_counter(); scan.go_from(spos, [], depth=D); st += time.perf_counter() - t; ns += 1
                except Exception:
                    pass
            ja = jt / nj if nj else float("nan")
            sa = st / ns if ns else float("nan")
            ratio = ja / sa if sa else float("nan")
            print(f"{D:>5} {ja:>11.4f} {sa:>11.4f} {ratio:>10.2f}", flush=True)
    finally:
        try: jass.close()
        except Exception: pass
        try: scan.close()
        except Exception: pass
    print("\njass/scan ratio = movetime-compensation factor (give jass that x more time = fair).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
