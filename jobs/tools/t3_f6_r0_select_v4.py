#!/usr/bin/env python3
"""Preregistered target-blind R0-v4 selector and 512-root search subset."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import random
import struct
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.calibrate_vs_scan import parse_jass_fen
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint, format_fingerprint

PHASES = {"P0": (30, 40), "P1": (20, 29), "P2": (12, 19), "P3": (9, 11)}


@dataclass(frozen=True)
class Candidate:
    fen: str
    values: tuple[int, int, int, int, int]
    canonical: str
    selection_key: str
    search_key: str
    benchmark_key: str


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", newline="") \
        if path.suffix == ".gz" else path.open("r", encoding="utf-8", newline="")


def fen_rows(path: Path) -> list[str]:
    with open_text(path) as stream:
        return [value for line in stream if (value := line.split("#", 1)[0].strip())]


def bits(squares: list[int]) -> int:
    out = 0
    for square in squares:
        if not 1 <= square <= 50:
            raise ValueError("FEN square outside board")
        out |= 1 << (square - 1)
    return out


def fen_fingerprint(fen: str) -> tuple[str, tuple[int, int, int, int, int]]:
    side, wm, wk, bm, bk = parse_jass_fen(fen)
    values = (bits(wm), bits(wk), bits(bm), bits(bk), 0 if side == "W" else 1)
    return canonical_fingerprint(format_fingerprint(*values)), values


def phase_for(values: tuple[int, int, int, int, int]) -> str:
    pieces = sum(value.bit_count() for value in values[:4])
    for name, (lo, hi) in PHASES.items():
        if lo <= pieces <= hi:
            return name
    raise ValueError(f"candidate pieces outside R0-v4 phases: {pieces}")


def identity_text(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("empty identity")
    if ":" in raw and raw.split(":", 1)[0] in ("W", "B"):
        return fen_fingerprint(raw)[0]
    return canonical_fingerprint(raw)


def load_tsv_identities(path: Path) -> set[str]:
    out: set[str] = set()
    identity_fields = (
        "canonical_fingerprint", "raw_fingerprint", "parent_canonical",
        "parent_fingerprint", "child_canonical", "child_fingerprint",
    )
    fen_fields = ("fen", "parent_fen", "position_fen", "child_fen")
    with open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fields = set(reader.fieldnames or ())
        available = [field for field in identity_fields + fen_fields if field in fields]
        if not available:
            raise ValueError(f"{path}: no board+STM identity field")
        for row in reader:
            for field in available:
                if row.get(field):
                    out.add(identity_text(row[field]))
    if not out:
        raise ValueError(f"{path}: empty identity exclusion")
    return out


def extract_json_fens(path: Path) -> set[str]:
    found: set[str] = set()
    def visit(value: object) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and ":" in value:
            try:
                found.add(fen_fingerprint(value)[0])
            except (ValueError, IndexError, KeyError):
                pass
    visit(json.loads(path.read_text(encoding="utf-8")))
    if not found:
        raise ValueError(f"{path}: no FEN identity found")
    return found


def write_fens(path: Path, rows: list[Candidate]) -> None:
    path.write_text("\n".join(row.fen for row in rows) + "\n", encoding="utf-8")


def write_jnnw(path: Path, rows: list[Candidate]) -> None:
    with path.open("wb") as out:
        out.write(b"JNNW" + struct.pack("<I", len(rows)))
        for row in rows:
            wm, wk, bm, bk, stm = row.values
            out.write(struct.pack("<QQQQBib", wm, wk, bm, bk, stm, 0, 0))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--exclude-fen", type=Path, action="append", default=[])
    parser.add_argument("--exclude-tsv", type=Path, action="append", default=[])
    parser.add_argument("--exclude-json-fens", type=Path, action="append", default=[])
    parser.add_argument("--selection-seed", type=int, required=True)
    parser.add_argument("--permutation-seed", type=int, required=True)
    parser.add_argument("--search-seed", type=int, required=True)
    parser.add_argument("--benchmark-seed", type=int, required=True)
    parser.add_argument("--out-fen", type=Path, required=True)
    parser.add_argument("--out-jnnw", type=Path, required=True)
    parser.add_argument("--out-benchmark-fen", type=Path, required=True)
    parser.add_argument("--out-benchmark-jnnw", type=Path, required=True)
    parser.add_argument("--out-search-fen", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    actual = (args.selection_seed, args.permutation_seed,
              args.search_seed, args.benchmark_seed)
    if actual != (2026092502, 2026092503, 2026092504, 2026092505):
        raise ValueError(f"R0-v4 seed drift: {actual}")

    candidates = fen_rows(args.candidates)
    if len(candidates) != 40000:
        raise ValueError(f"candidate cardinality {len(candidates)} != 40000")
    excluded: set[str] = set()
    sources: dict[str, int] = {}
    for path in args.exclude_fen:
        identities = {fen_fingerprint(fen)[0] for fen in fen_rows(path)}
        if not identities:
            raise ValueError(f"{path}: empty FEN exclusion")
        excluded.update(identities); sources[str(path)] = len(identities)
    for path in args.exclude_tsv:
        identities = load_tsv_identities(path)
        excluded.update(identities); sources[str(path)] = len(identities)
    for path in args.exclude_json_fens:
        identities = extract_json_fens(path)
        excluded.update(identities); sources[str(path)] = len(identities)

    unique: dict[str, Candidate] = {}
    excluded_occurrences = duplicate_occurrences = 0
    for fen in candidates:
        canonical, values = fen_fingerprint(fen)
        if canonical in excluded:
            excluded_occurrences += 1
            continue
        row = Candidate(
            fen, values, canonical,
            hashlib.sha256(f"{args.selection_seed}:{canonical}".encode()).hexdigest(),
            hashlib.sha256(f"{args.search_seed}:{canonical}".encode()).hexdigest(),
            hashlib.sha256(f"{args.benchmark_seed}:{canonical}".encode()).hexdigest(),
        )
        old = unique.get(canonical)
        if old is None or row.fen < old.fen:
            unique[canonical] = row
        if old is not None:
            duplicate_occurrences += 1

    selected: list[Candidate] = []
    search_rows: list[Candidate] = []
    support: dict[str, int] = {}
    for phase in PHASES:
        rows = [row for row in unique.values() if phase_for(row.values) == phase]
        support[phase] = len(rows)
        if len(rows) < 1024:
            raise ValueError(f"R0-v4 support insufficient in {phase}: {len(rows)}")
        chosen = sorted(rows, key=lambda row: (row.selection_key, row.canonical))[:1024]
        selected.extend(chosen)
        search_rows.extend(sorted(chosen, key=lambda row: (row.search_key, row.canonical))[:128])

    if len(selected) != 4096 or len(search_rows) != 512:
        raise AssertionError("R0-v4 selected/subset cardinality drift")
    if {row.canonical for row in selected} & excluded:
        raise ValueError("R0-v4 selected/excluded overlap")
    selected_output = list(selected)
    random.Random(args.permutation_seed).shuffle(selected_output)
    benchmark = sorted(selected, key=lambda row: (row.benchmark_key, row.canonical))
    search_output = sorted(search_rows, key=lambda row: (row.search_key, row.canonical))
    write_fens(args.out_fen, selected_output)
    write_jnnw(args.out_jnnw, selected_output)
    write_fens(args.out_benchmark_fen, benchmark)
    write_jnnw(args.out_benchmark_jnnw, benchmark)
    write_fens(args.out_search_fen, search_output)

    report = {
        "schema": "jass.t3_f6_r0_target_blind_selection.v4",
        "passed": True,
        "verdict": "R0_V4_TARGET_BLIND_CORPUS_READY",
        "candidate_records": len(candidates),
        "candidate_sha256": sha(args.candidates),
        "selected": len(selected),
        "selected_by_phase": dict(sorted(Counter(phase_for(r.values) for r in selected).items())),
        "search_subset": len(search_rows),
        "search_subset_by_phase": dict(sorted(Counter(phase_for(r.values) for r in search_rows).items())),
        "selection_seed": args.selection_seed,
        "permutation_seed": args.permutation_seed,
        "search_seed": args.search_seed,
        "benchmark_seed": args.benchmark_seed,
        "canonicalization": "exact_plus_rotate180_colour_swap",
        "unique_after_exclusion": len(unique),
        "support_by_phase": support,
        "excluded_unique": len(excluded),
        "excluded_occurrences": excluded_occurrences,
        "duplicate_occurrences": duplicate_occurrences,
        "excluded_sources": sources,
        "forbidden_overlap": 0,
        "fen_sha256": sha(args.out_fen),
        "jnnw_sha256": sha(args.out_jnnw),
        "benchmark_fen_sha256": sha(args.out_benchmark_fen),
        "benchmark_jnnw_sha256": sha(args.out_benchmark_jnnw),
        "search_fen_sha256": sha(args.out_search_fen),
        "score_reads": 0,
        "wdl_reads": 0,
        "deep_label_reads": 0,
        "runtime_metric_reads": 0,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
