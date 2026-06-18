#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-Francois Collin
"""Mix several JNNW datasets into one pool with controlled proportions.

Rationale (2026-06-18): pure Scan-self-play is high quality but low-contrast/quiet
(0327 found it HURTS a linear fit); pure jass-self-play is diverse but weak. Mixing
them guarantees a % of strong-quality games AND keeps diversity. This tool builds a
pool of TARGET size with per-source shares.

Usage:
  jnnw_mix.py --out pool.jnnw --total 1000000 \
      --src scan.jnnw:0.5 --src jass.jnnw:0.3 --src coverage.jnnw:0.2

Shares are normalized. Each source is sampled with a uniform stride (no shuffle =
deterministic, preserves phase spread). A source smaller than its quota contributes
all it has; the shortfall is NOT redistributed (keeps proportions honest).
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

REC = 38
HDR = 8


def count(path: Path) -> int:
    with path.open("rb") as f:
        head = f.read(HDR)
    if head[:4] != b"JNNW":
        raise SystemExit(f"{path}: not a JNNW file")
    return struct.unpack("<I", head[4:8])[0]


def take_strided(path: Path, n: int) -> tuple[bytes, int]:
    """Return up to n records, strided across the file."""
    b = path.read_bytes()
    tot = struct.unpack("<I", b[4:8])[0]
    body = b[HDR:]
    n = min(n, tot)
    if n <= 0:
        return b"", 0
    stride = max(1, tot // n)
    out = bytearray()
    k = 0
    for i in range(0, tot, stride):
        out += body[i * REC:(i + 1) * REC]
        k += 1
        if k >= n:
            break
    return bytes(out), k


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--total", required=True, type=int, help="target pool size")
    ap.add_argument("--src", action="append", required=True, metavar="PATH:SHARE",
                    help="source file and its share, e.g. scan.jnnw:0.5 (repeatable)")
    args = ap.parse_args(argv)

    srcs = []
    for s in args.src:
        path, _, share = s.rpartition(":")
        if not path:
            raise SystemExit(f"bad --src {s!r} (need PATH:SHARE)")
        srcs.append((Path(path), float(share)))
    tot_share = sum(sh for _, sh in srcs)
    if tot_share <= 0:
        raise SystemExit("shares sum to 0")

    out = bytearray()
    written = 0
    print(f"mixing pool target={args.total}")
    for path, share in srcs:
        quota = int(args.total * share / tot_share)
        avail = count(path)
        data, got = take_strided(path, quota)
        out += data
        written += got
        print(f"  {path.name:32s} share={share/tot_share:.2f} quota={quota:>9d} "
              f"avail={avail:>9d} took={got:>9d}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as f:
        f.write(b"JNNW")
        f.write(struct.pack("<I", written))
        f.write(out)
    print(f"wrote {args.out} ({written} records)")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
