#!/usr/bin/env python3
"""Sample real men-only positions at a fixed material imbalance and emit FENs.

Reads a JNNW corpus (38-byte records: wm,wk,bm,bk,stm,score,wdl), keeps
positions with NO kings and exactly {big} men on one side / {small} on the
other (either colour), de-duplicates by position, and writes a deterministic
spread of N Hub FENs — one per line, with a comment naming the material-up
side. Used to seed the 18v20 self-play conversion experiment.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

MAGIC = b"JNNW"
HEADER = 8
RECORD = 38
_FMT = struct.Struct("<QQQQBib")


def _squares(bb: int) -> list[int]:
    out = []
    while bb:
        low = bb & -bb
        out.append(low.bit_length())   # bit i (0-based) -> square i+1
        bb ^= low
    return out


def record_to_fen(wm: int, wk: int, bm: int, bk: int, stm: int) -> str:
    def side(prefix, men, kings):
        toks = [str(s) for s in _squares(men)] + [f"K{s}" for s in _squares(kings)]
        toks.sort(key=lambda t: int(t[1:]) if t.startswith("K") else int(t))
        return prefix + ",".join(toks)
    stm_ch = "W" if stm == 0 else "B"
    return f"{stm_ch}:{side('W', wm, wk)}:{side('B', bm, bk)}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", nargs="+", required=True, help="JNNW corpus file(s)")
    ap.add_argument("--big", type=int, default=20)
    ap.add_argument("--small", type=int, default=18)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    seen: set[bytes] = set()
    eligible: list[tuple[str, str]] = []  # (fen, up_side)
    scanned = 0
    for path in args.input:
        raw = Path(path).read_bytes()
        if raw[:4] != MAGIC:
            raise SystemExit(f"{path}: not a JNNW file")
        n = struct.unpack_from("<I", raw, 4)[0]
        off = HEADER
        for _ in range(n):
            wm, wk, bm, bk, stm, _score, _wdl = _FMT.unpack_from(raw, off)
            off += RECORD
            scanned += 1
            if wk or bk:
                continue
            cw, cb = wm.bit_count(), bm.bit_count()
            if {cw, cb} != {args.big, args.small}:
                continue
            key = raw[off - RECORD: off - RECORD + 33]  # 4 bitboards + stm
            if key in seen:
                continue
            seen.add(key)
            up = "W" if cw == args.big else "B"
            eligible.append((record_to_fen(wm, wk, bm, bk, stm), up))

    if len(eligible) < args.count:
        raise SystemExit(f"only {len(eligible)} unique {args.big}v{args.small} "
                         f"men-only positions found (need {args.count})")
    # deterministic even spread across the eligible pool
    idx = [i * len(eligible) // args.count for i in range(args.count)]
    selected = [eligible[i] for i in idx]

    with Path(args.out).open("w", encoding="utf-8") as fh:
        fh.write(f"# {args.count} men-only {args.big}v{args.small} positions "
                 f"(no kings); up_side after '#'\n")
        for fen, up in selected:
            fh.write(f"{fen}  # up={up}\n")
    print(json.dumps({"scanned": scanned, "eligible_unique": len(eligible),
                      "selected": len(selected), "big": args.big, "small": args.small}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
