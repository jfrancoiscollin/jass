#!/usr/bin/env python3
"""Validate a fixed FEN opening pool and publish its provenance manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def fen_rows(path: Path) -> list[str]:
    return [
        fen
        for line in path.read_text(encoding="utf-8").splitlines()
        if (fen := line.split("#", 1)[0].strip())
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", required=True, type=Path)
    parser.add_argument("--expected", required=True, type=int)
    parser.add_argument("--exclude", action="append", default=[], type=Path)
    parser.add_argument("--generator-seed", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    rows = fen_rows(args.pool)
    unique = set(rows)
    if len(rows) != args.expected:
        raise SystemExit(f"expected {args.expected} openings, got {len(rows)}")
    if len(unique) != len(rows):
        raise SystemExit(f"opening pool contains {len(rows) - len(unique)} duplicates")

    excluded: set[str] = set()
    exclude_counts: dict[str, int] = {}
    for path in args.exclude:
        values = set(fen_rows(path))
        excluded.update(values)
        exclude_counts[str(path)] = len(values)
    overlap = sorted(unique & excluded)
    if overlap:
        raise SystemExit(f"opening pool overlaps exclusions: {len(overlap)} positions")

    payload = {
        "schema": 1,
        "mode": "deterministic-random-legal-quiet-trajectories",
        "pool": str(args.pool),
        "records": len(rows),
        "unique_records": len(unique),
        "generator_seed": args.generator_seed,
        "sha256": hashlib.sha256(args.pool.read_bytes()).hexdigest(),
        "excluded_sources": exclude_counts,
        "overlap_records": 0,
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
