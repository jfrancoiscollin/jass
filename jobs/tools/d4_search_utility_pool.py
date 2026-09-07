#!/usr/bin/env python3
"""Frozen target-blind D4 root-pool selection."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.t3_f6_r0_select import fen_fingerprint, fen_rows, load_tsv_identities
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint

CANDIDATES = 30_000
SELECTED = 4_000
GENERATION_SEED = 2026111501
SELECTION_PREFIX = "2026111502:"
SPLITS = ((0, 3200, "train"), (3200, 3600, "valid"), (3600, 4000, "test"))


def split_for_index(index: int) -> str:
    for lo, hi, name in SPLITS:
        if lo <= index < hi:
            return name
    raise ValueError("root index outside D4 split")


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
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        value = row.get("canonical_parent_identity")
        if not isinstance(value, str) or not value:
            raise ValueError(f"{path}:{number}: missing canonical_parent_identity")
        out.add(canonical_fingerprint(value))
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", type=Path, required=True)
    p.add_argument("--exclude-fen", type=Path, action="append", default=[])
    p.add_argument("--exclude-tsv", type=Path, action="append", default=[])
    p.add_argument("--exclude-canonical-file", type=Path, action="append", default=[])
    p.add_argument("--exclude-c-parent-jsonl", type=Path, action="append", default=[])
    p.add_argument("--out-roots", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()

    candidates = fen_rows(a.candidates)
    if len(candidates) != CANDIDATES:
        raise ValueError(f"candidate cardinality {len(candidates)} != {CANDIDATES}")

    excluded: set[str] = set()
    sources: dict[str, int] = {}
    for path in a.exclude_fen:
        ids = {fen_fingerprint(fen)[0] for fen in fen_rows(path)}
        excluded.update(ids)
        sources[str(path)] = len(ids)
    for path in a.exclude_tsv:
        ids = load_tsv_identities(path)
        excluded.update(ids)
        sources[str(path)] = len(ids)
    for path in a.exclude_canonical_file:
        ids = load_canonical_file(path)
        excluded.update(ids)
        sources[str(path)] = len(ids)
    for path in a.exclude_c_parent_jsonl:
        ids = load_c_parent_jsonl(path)
        excluded.update(ids)
        sources[str(path)] = len(ids)

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

    ranked = sorted(unique.items(), key=lambda item: rank_key(item[0]))
    if len(ranked) < SELECTED:
        raise ValueError(f"D4 root support {len(ranked)} < {SELECTED}")
    selected = ranked[:SELECTED]
    if {canonical for canonical, _ in selected} & excluded:
        raise ValueError("D4 selected/excluded overlap")

    a.out_roots.parent.mkdir(parents=True, exist_ok=True)
    with a.out_roots.open("w", encoding="utf-8", newline="") as out:
        out.write("root_index\tsplit\tcanonical_identity\tfen\tselection_digest\n")
        for index, (canonical, fen) in enumerate(selected):
            digest = hashlib.sha256((SELECTION_PREFIX + canonical).encode()).hexdigest()
            out.write(f"{index}\t{split_for_index(index)}\t{canonical}\t{fen}\t{digest}\n")

    split_counts = {name: hi - lo for lo, hi, name in SPLITS}
    report = {
        "schema": "jass.d4.search_utility_root_pool.v1",
        "verdict": "D4_SEARCH_UTILITY_ROOT_POOL_READY_V1",
        "candidate_records": len(candidates),
        "candidate_sha256": hashlib.sha256(a.candidates.read_bytes()).hexdigest(),
        "generation_seed": GENERATION_SEED,
        "selection_prefix": SELECTION_PREFIX,
        "canonicalization": "board+STM rotate180+colour-swap",
        "selected_roots": len(selected),
        "split_counts": split_counts,
        "unique_after_exclusion": len(unique),
        "excluded_unique": len(excluded),
        "excluded_occurrences": excluded_occurrences,
        "duplicate_occurrences": duplicate_occurrences,
        "excluded_sources": dict(sorted(sources.items())),
        "forbidden_overlap": 0,
        "roots_sha256": hashlib.sha256(a.out_roots.read_bytes()).hexdigest(),
        "target_reads": 0,
        "game_outcome_reads": 0,
        "qscore_reads": 0,
        "search_decision_trace_reads": 0,
        "full_ladder_1843_reads": 0,
        "d3_score_reads": 0,
        "teacher_reads": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
    }
    a.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
