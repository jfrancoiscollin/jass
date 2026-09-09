#!/usr/bin/env python3
"""Append one hand-built TERMINAL JNNW record (no legal move for STM) to an
existing JNNW file, for the deep_relabel_source_tags_smoke CTest.

Record layout (38 bytes, matches src/main.cpp position_from_record /
run_gen_data_wdl_mode):
  32 B  uint64x4 LE bitboards  (white_men, white_kings, black_men, black_kings)
   1 B  uint8    stm           (0 = white to move, 1 = black to move)
   4 B  int32 LE score
   1 B  int8     wdl

Terminal position: a lone white man on square 8, with black men on squares
2 and 3 (FMJD numbering, bit = square - 1). White's forward diagonals from
square 8 land on squares 2 and 3 (both occupied by Black) and the landing
square beyond each (for a capture) is off-board (row -1) -> zero legal moves
for White, who is to move.
"""
import argparse
import struct
import sys

RECORD_BYTES = 38


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("in_path")
    ap.add_argument("out_path")
    args = ap.parse_args()

    with open(args.in_path, "rb") as f:
        data = f.read()
    if data[:4] != b"JNNW":
        print(f"error: {args.in_path} is not JNNW", file=sys.stderr)
        return 1
    (count,) = struct.unpack_from("<I", data, 4)
    body = data[8:]
    if len(body) != count * RECORD_BYTES:
        print("error: size/count mismatch in input JNNW", file=sys.stderr)
        return 1

    white_men = 1 << (8 - 1)
    white_kings = 0
    black_men = (1 << (2 - 1)) | (1 << (3 - 1))
    black_kings = 0
    stm = 0            # white to move
    score = 0          # placeholder; deep-relabel overwrites it
    wdl = 0            # placeholder; deep-relabel overwrites it

    terminal_rec = struct.pack(
        "<QQQQBib", white_men, white_kings, black_men, black_kings, stm, score, wdl
    )
    assert len(terminal_rec) == RECORD_BYTES, len(terminal_rec)

    new_count = count + 1
    with open(args.out_path, "wb") as f:
        f.write(b"JNNW")
        f.write(struct.pack("<I", new_count))
        f.write(body)
        f.write(terminal_rec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
