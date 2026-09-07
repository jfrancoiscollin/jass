#!/usr/bin/env python3
"""Frozen target-blind pool selection for D3 runtime equal-node."""
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
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint

CANDIDATES = 30000
PRIMARY = 750
HARNESS = 100
GENERATION_SEED = 2026111301
SELECTION_PREFIX = "2026111302:"


def rank_key(canonical: str) -> tuple[bytes, str]:
    return hashlib.sha256((SELECTION_PREFIX + canonical).encode()).digest(), canonical


def load_canonical_file(path: Path) -> set[str]:
    return {
        canonical_fingerprint(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def load_c_parent_jsonl(path: Path) -> set[str]:
    out: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        value = row.get("canonical_parent_identity")
        if not isinstance(value, str) or not value:
            raise ValueError(f"{path}:{lineno}: missing canonical_parent_identity")
        out.add(canonical_fingerprint(value))
    return out


def select_unique(unique: dict[str, str], excluded: set[str]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    ranked = sorted(
        ((canonical, fen) for canonical, fen in unique.items() if canonical not in excluded),
        key=lambda item: rank_key(item[0]),
    )
    if len(ranked) < PRIMARY + HARNESS:
        raise ValueError("D3 equal-node fresh support below 850 openings")
    return ranked[:PRIMARY], ranked[PRIMARY:PRIMARY + HARNESS]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", type=Path, required=True)
    p.add_argument("--exclude-fen", type=Path, action="append", default=[])
    p.add_argument("--exclude-tsv", type=Path, action="append", default=[])
    p.add_argument("--exclude-canonical-file", type=Path, action="append", default=[])
    p.add_argument("--exclude-c-parent-jsonl", type=Path, action="append", default=[])
    p.add_argument("--out-primary", type=Path, required=True)
    p.add_argument("--out-harness", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()

    candidates = fen_rows(a.candidates)
    if len(candidates) != CANDIDATES:
        raise ValueError(f"candidate cardinality {len(candidates)} != {CANDIDATES}")

    excluded: set[str] = set()
    sources: dict[str, int] = {}
    for path in a.exclude_fen:
        ids = {fen_fingerprint(fen)[0] for fen in fen_rows(path)}
        excluded.update(ids); sources[str(path)] = len(ids)
    for path in a.exclude_tsv:
        ids = load_tsv_identities(path)
        excluded.update(ids); sources[str(path)] = len(ids)
    for path in a.exclude_canonical_file:
        ids = load_canonical_file(path)
        excluded.update(ids); sources[str(path)] = len(ids)
    for path in a.exclude_c_parent_jsonl:
        ids = load_c_parent_jsonl(path)
        excluded.update(ids); sources[str(path)] = len(ids)

    unique: dict[str, str] = {}
    duplicate_occurrences = 0
    excluded_occurrences = 0
    for fen in candidates:
        canonical, _ = fen_fingerprint(fen)
        if canonical in excluded:
            excluded_occurrences += 1
            continue
        old = unique.get(canonical)
        if old is None:
            unique[canonical] = fen
        else:
            duplicate_occurrences += 1
            if fen < old:
                unique[canonical] = fen

    primary, harness = select_unique(unique, excluded)
    pids = {c for c, _ in primary}; hids = {c for c, _ in harness}
    if pids & hids or (pids | hids) & excluded:
        raise ValueError("D3 equal-node overlap invariant failed")

    a.out_primary.write_text("\n".join(f for _, f in primary) + "\n", encoding="utf-8")
    a.out_harness.write_text("\n".join(f for _, f in harness) + "\n", encoding="utf-8")
    manifest = []
    for cell, rows in (("EQUAL_NODE_PRIMARY", primary), ("EQUAL_NODE_HARNESS", harness)):
        for index, (canonical, fen) in enumerate(rows):
            manifest.append({
                "cell": cell,
                "index": index,
                "canonical_identity": canonical,
                "fen": fen,
                "selection_digest": hashlib.sha256((SELECTION_PREFIX + canonical).encode()).hexdigest(),
            })
    a.manifest.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in manifest),
        encoding="utf-8",
    )
    report = {
        "schema": "jass.d3.runtime_equal_node_pool.v1",
        "verdict": "D3_RUNTIME_EQUAL_NODE_POOL_READY_V1",
        "candidate_records": len(candidates),
        "candidate_sha256": hashlib.sha256(a.candidates.read_bytes()).hexdigest(),
        "generation_seed": GENERATION_SEED,
        "selection_prefix": SELECTION_PREFIX,
        "canonicalization": "board+STM rotate180+colour-swap",
        "primary_openings": PRIMARY,
        "harness_openings": HARNESS,
        "primary_games": 2 * PRIMARY,
        "harness_games": 2 * HARNESS,
        "unique_after_exclusion": len(unique),
        "excluded_unique": len(excluded),
        "excluded_occurrences": excluded_occurrences,
        "duplicate_occurrences": duplicate_occurrences,
        "excluded_sources": sources,
        "forbidden_overlap": 0,
        "inter_cell_overlap": 0,
        "primary_sha256": hashlib.sha256(a.out_primary.read_bytes()).hexdigest(),
        "harness_sha256": hashlib.sha256(a.out_harness.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(a.manifest.read_bytes()).hexdigest(),
        "target_reads": 0,
        "qscore_reads": 0,
        "search_decision_trace_reads": 0,
        "full_ladder_1843_reads": 0,
        "teacher_reads": 0,
    }
    a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
