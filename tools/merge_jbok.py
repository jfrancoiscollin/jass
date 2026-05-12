#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
"""
Merge several JBOK opening-book files into one, deduplicating by
zobrist hash (keeping the entry with the deepest search).

JBOK format (little-endian, from src/book.hpp):
    [0..4)   magic = "JBOK"
    [4..8)   uint32 version (currently 1)
    [8..12)  uint32 entry_count
    [12..)   entry_count × 16-byte entries:
               uint64       zobrist_hash
               PackedMove   best_move      (4 bytes)
               int16        score          (centipawn, STM POV)
               uint16       depth_searched (0 if unknown)

Usage
-----
    python3 tools/merge_jbok.py --out merged.bok partial-1.bok \\
        partial-2.bok partial-3.bok partial-4.bok

This exists because `--build-book` (src/main.cpp) is single-threaded
and the runner's CCX23 has 4 vCPU. Sharding the FEN list across N
processes gives a ~Nx speedup; this script glues the partial .bok
files back together.
"""

import argparse
import struct
import sys
from pathlib import Path

JBOK_MAGIC   = b"JBOK"
JBOK_VERSION = 1
HEADER_SIZE  = 12
ENTRY_SIZE   = 16  # uint64 hash + 4B move + int16 score + uint16 depth


def read_entries(path: Path):
    raw = path.read_bytes()
    if len(raw) < HEADER_SIZE:
        raise ValueError(f"{path}: shorter than header")
    if raw[:4] != JBOK_MAGIC:
        raise ValueError(f"{path}: bad magic {raw[:4]!r}, expected JBOK")
    version = struct.unpack_from("<I", raw, 4)[0]
    if version != JBOK_VERSION:
        raise ValueError(f"{path}: unsupported version {version}")
    count = struct.unpack_from("<I", raw, 8)[0]
    if len(raw) != HEADER_SIZE + count * ENTRY_SIZE:
        raise ValueError(
            f"{path}: size mismatch (header says {count} entries → "
            f"{HEADER_SIZE + count * ENTRY_SIZE} bytes, file is {len(raw)})")
    entries = []
    off = HEADER_SIZE
    for _ in range(count):
        h     = struct.unpack_from("<Q", raw, off)[0]
        mv    = raw[off + 8:off + 12]                            # 4-byte PackedMove
        score = struct.unpack_from("<h", raw, off + 12)[0]
        depth = struct.unpack_from("<H", raw, off + 14)[0]
        entries.append((h, mv, score, depth))
        off += ENTRY_SIZE
    return entries


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--out", type=Path, required=True,
                   help="output merged JBOK path")
    p.add_argument("inputs", nargs="+", type=Path,
                   help="partial JBOK files to merge")
    args = p.parse_args(argv)

    by_hash: dict[int, tuple[bytes, int, int]] = {}  # h → (mv, score, depth)
    total_in = 0
    for path in args.inputs:
        entries = read_entries(path)
        total_in += len(entries)
        for h, mv, score, depth in entries:
            cur = by_hash.get(h)
            # Keep the entry with the deepest search; tie-break on first seen.
            if cur is None or depth > cur[2]:
                by_hash[h] = (mv, score, depth)

    with args.out.open("wb") as f:
        f.write(JBOK_MAGIC)
        f.write(struct.pack("<II", JBOK_VERSION, len(by_hash)))
        for h in sorted(by_hash):
            mv, score, depth = by_hash[h]
            f.write(struct.pack("<Q", h))
            f.write(mv)
            f.write(struct.pack("<hH", score, depth))

    print(f"merged {total_in} input entries from {len(args.inputs)} files "
          f"→ {len(by_hash)} unique → {args.out} "
          f"({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
