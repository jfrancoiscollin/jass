#!/usr/bin/env python3
"""Canonical fresh 3000-opening selector for T3/F6 Pool1 or Pool2."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.t3_f6_r0_select import fen_fingerprint, fen_rows, load_tsv_identities


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--exclude-fen", type=Path, action="append", default=[])
    parser.add_argument("--exclude-tsv", type=Path, action="append", default=[])
    parser.add_argument("--selection-seed", type=int, required=True)
    parser.add_argument("--generator-seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    candidates = fen_rows(args.candidates)
    if len(candidates) != 30000:
        raise ValueError(f"force candidate cardinality {len(candidates)} != 30000")
    excluded: set[str] = set()
    sources: dict[str, int] = {}
    for path in args.exclude_fen:
        identities = {fen_fingerprint(fen)[0] for fen in fen_rows(path)}
        excluded.update(identities); sources[str(path)] = len(identities)
    for path in args.exclude_tsv:
        identities = load_tsv_identities(path)
        excluded.update(identities); sources[str(path)] = len(identities)
    unique: dict[str, str] = {}
    duplicates = overlap_occurrences = 0
    for fen in candidates:
        canonical = fen_fingerprint(fen)[0]
        if canonical in excluded:
            overlap_occurrences += 1
            continue
        old = unique.get(canonical)
        if old is not None:
            duplicates += 1
            unique[canonical] = min(old, fen)
        else:
            unique[canonical] = fen
    ranked = sorted(unique.items(), key=lambda item: (
        hashlib.sha256(f"{args.selection_seed}:{item[0]}".encode()).digest(), item[0]))
    selected = ranked[:3000]
    if len(selected) != 3000:
        raise ValueError("fresh force support below 3000")
    if {canonical for canonical, _ in selected} & excluded:
        raise ValueError("selected force pool overlap")
    args.out.write_text("\n".join(fen for _, fen in selected) + "\n", encoding="utf-8")
    payload = {
        "schema": "jass.t3_f6_fresh_force_pool.v1",
        "verdict": "T3_F6_FRESH_FORCE_POOL_READY",
        "passed": True,
        "candidate_records": len(candidates),
        "candidate_sha256": hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
        "generator_seed": args.generator_seed,
        "selection_seed": args.selection_seed,
        "openings": len(selected),
        "canonicalization": "exact_plus_rotate180_colour_swap",
        "unique_after_exclusion": len(unique),
        "duplicates_removed": duplicates,
        "excluded_occurrences": overlap_occurrences,
        "excluded_unique": len(excluded),
        "excluded_sources": sources,
        "forbidden_overlap": 0,
        "pool_sha256": hashlib.sha256(args.out.read_bytes()).hexdigest(),
        "score_reads": 0,
        "wdl_reads": 0,
        "deep_label_reads": 0,
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
