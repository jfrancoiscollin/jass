#!/usr/bin/env python3
"""Convert score-free Jass FEN rows to counted zero-target JNNW."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.calibrate_vs_scan import parse_jass_fen  # noqa: E402


def bits(squares: list[int]) -> int:
    value = 0
    for square in squares:
        if not 1 <= square <= 50:
            raise ValueError("FEN square outside 1..50")
        mask = 1 << (square - 1)
        if value & mask:
            raise ValueError("duplicate FEN square")
        value |= mask
    return value


def fen_record(fen: str) -> bytes:
    side, wm, wk, bm, bk = parse_jass_fen(fen)
    if side not in ("W", "B"):
        raise ValueError("invalid FEN side")
    values = bits(wm), bits(wk), bits(bm), bits(bk)
    if (values[0] & values[1]) | (values[0] & values[2]) | (values[0] & values[3]) \
            | (values[1] & values[2]) | (values[1] & values[3]) | (values[2] & values[3]):
        raise ValueError("overlapping FEN pieces")
    return struct.pack("<QQQQBib", *values, 0 if side == "W" else 1, 0, 0)


def load_fens(path: Path) -> list[str]:
    return [value for line in path.read_text(encoding="utf-8").splitlines()
            if (value := line.split("#", 1)[0].strip())]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    fens = load_fens(args.input)
    if args.expected_count is not None and len(fens) != args.expected_count:
        raise ValueError(f"FEN count {len(fens)} != {args.expected_count}")
    if not fens:
        raise ValueError("empty FEN corpus")
    records = [fen_record(fen) for fen in fens]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as stream:
        stream.write(b"JNNW" + struct.pack("<I", len(records)))
        for record in records:
            stream.write(record)
    payload = {
        "schema": "jass.scan_ceiling_fen_to_jnnw.v1",
        "rows": len(records),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "target_bytes_zero": True,
        "scores_read": 0, "wdl_read": 0, "fits": 0, "strength_games": 0,
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(records)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
