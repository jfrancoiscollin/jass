#!/usr/bin/env python3
"""Select a deterministic unique opening pool disjoint from prior pools."""
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
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--expected", required=True, type=int)
    parser.add_argument("--exclude", action="append", default=[], type=Path)
    parser.add_argument("--generator-seed", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()

    if args.expected <= 0:
        raise SystemExit("--expected must be positive")

    excluded: set[str] = set()
    exclude_counts: dict[str, int] = {}
    for path in args.exclude:
        values = set(fen_rows(path))
        excluded.update(values)
        exclude_counts[str(path)] = len(values)

    candidates = fen_rows(args.candidates)
    seen: set[str] = set()
    selected: list[str] = []
    duplicate_candidates = 0
    excluded_candidates = 0
    for fen in candidates:
        if fen in seen:
            duplicate_candidates += 1
            continue
        seen.add(fen)
        if fen in excluded:
            excluded_candidates += 1
            continue
        selected.append(fen)
        if len(selected) == args.expected:
            break

    if len(selected) != args.expected:
        raise SystemExit(
            "not enough independent openings: "
            f"wanted {args.expected}, selected {len(selected)} from "
            f"{len(candidates)} candidates"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(selected) + "\n", encoding="utf-8")
    payload = {
        "schema": 1,
        "mode": "deterministic-ordered-filter",
        "candidate_pool": str(args.candidates),
        "candidate_records": len(candidates),
        "candidate_sha256": hashlib.sha256(
            args.candidates.read_bytes()
        ).hexdigest(),
        "records": len(selected),
        "unique_records": len(set(selected)),
        "generator_seed": args.generator_seed,
        "sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
        "excluded_sources": exclude_counts,
        "excluded_candidates_before_cutoff": excluded_candidates,
        "duplicate_candidates_before_cutoff": duplicate_candidates,
        "overlap_records": len(set(selected) & excluded),
    }
    if payload["unique_records"] != args.expected or payload["overlap_records"]:
        raise SystemExit("internal independent-opening selection failure")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
