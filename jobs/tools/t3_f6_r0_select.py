#!/usr/bin/env python3
"""Target-blind, phase-balanced R0 corpus selection with consumed-cohort exclusion."""
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools.calibrate_vs_scan import parse_jass_fen
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint, format_fingerprint

PHASES = {"P0": (30, 40), "P1": (20, 29), "P2": (12, 19), "P3": (9, 11)}


def fen_rows(path: Path) -> list[str]:
    return [value for line in path.read_text(encoding="utf-8").splitlines()
            if (value := line.split("#", 1)[0].strip())]


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
    raise ValueError(f"candidate pieces outside R0 phases: {pieces}")


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", newline="") if path.suffix == ".gz" \
        else path.open("r", encoding="utf-8", newline="")


def load_tsv_identities(path: Path) -> set[str]:
    out: set[str] = set()
    with open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fields = set(reader.fieldnames or ())
        fp_field = next((field for field in
                         ("canonical_fingerprint", "parent_fingerprint", "raw_fingerprint")
                         if field in fields), None)
        fen_field = next((field for field in ("fen", "parent_fen", "position_fen")
                          if field in fields), None)
        if fp_field is None and fen_field is None:
            raise ValueError(f"{path}: no board+STM identity field")
        for row in reader:
            if fp_field and row.get(fp_field):
                out.add(canonical_fingerprint(row[fp_field].strip()))
            elif fen_field and row.get(fen_field):
                out.add(fen_fingerprint(row[fen_field].strip())[0])
    return out


def write_jnnw(path: Path, selected: list[tuple[str, tuple[int, int, int, int, int], str]]) -> None:
    with path.open("wb") as out:
        out.write(b"JNNW" + struct.pack("<I", len(selected)))
        for _, values, _ in selected:
            wm, wk, bm, bk, stm = values
            out.write(struct.pack("<QQQQBib", wm, wk, bm, bk, stm, 0, 0))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--exclude-fen", type=Path, action="append", default=[])
    parser.add_argument("--exclude-tsv", type=Path, action="append", default=[])
    parser.add_argument("--selection-seed", type=int, default=2026090902)
    parser.add_argument("--permutation-seed", type=int, default=2026090903)
    parser.add_argument("--benchmark-seed", type=int, default=2026090904)
    parser.add_argument("--out-fen", type=Path, required=True)
    parser.add_argument("--out-jnnw", type=Path, required=True)
    parser.add_argument("--out-benchmark-fen", type=Path, required=True)
    parser.add_argument("--out-benchmark-jnnw", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    candidates = fen_rows(args.candidates)
    if len(candidates) != 40000:
        raise ValueError(f"candidate cardinality {len(candidates)} != 40000")
    excluded: set[str] = set()
    source_counts: dict[str, int] = {}
    for path in args.exclude_fen:
        identities = {fen_fingerprint(fen)[0] for fen in fen_rows(path)}
        excluded.update(identities); source_counts[str(path)] = len(identities)
    for path in args.exclude_tsv:
        identities = load_tsv_identities(path)
        excluded.update(identities); source_counts[str(path)] = len(identities)

    unique: dict[str, tuple[str, tuple[int, int, int, int, int], str]] = {}
    excluded_occurrences = 0
    duplicate_occurrences = 0
    for fen in candidates:
        canonical, values = fen_fingerprint(fen)
        if canonical in excluded:
            excluded_occurrences += 1
            continue
        key = hashlib.sha256(f"{args.selection_seed}:{canonical}".encode()).hexdigest()
        candidate = (fen, values, key)
        old = unique.get(canonical)
        if old is None:
            unique[canonical] = candidate
        else:
            duplicate_occurrences += 1
            if (fen, key) < (old[0], old[2]):
                unique[canonical] = candidate
    by_phase = {phase: sorted((row for row in unique.values()
                               if phase_for(row[1]) == phase), key=lambda row: (row[2], row[0]))
                for phase in PHASES}
    selected: list[tuple[str, tuple[int, int, int, int, int], str]] = []
    for phase in PHASES:
        if len(by_phase[phase]) < 1024:
            raise ValueError(f"R0 support insufficient in {phase}: {len(by_phase[phase])}")
        selected.extend(by_phase[phase][:1024])
    if {fen_fingerprint(row[0])[0] for row in selected} & excluded:
        raise ValueError("R0 selected/excluded overlap")
    random.Random(args.permutation_seed).shuffle(selected)
    args.out_fen.write_text("\n".join(row[0] for row in selected) + "\n", encoding="utf-8")
    write_jnnw(args.out_jnnw, selected)
    benchmark = sorted(selected, key=lambda row: (
        hashlib.sha256(f"{args.benchmark_seed}:{row[0]}".encode()).digest(), row[0]))
    args.out_benchmark_fen.write_text(
        "\n".join(row[0] for row in benchmark) + "\n", encoding="utf-8"
    )
    write_jnnw(args.out_benchmark_jnnw, benchmark)
    phase_counts = Counter(phase_for(row[1]) for row in selected)
    side_counts = Counter("white" if row[1][4] == 0 else "black" for row in selected)
    report = {
        "schema": "jass.t3_f6_r0_target_blind_selection.v1",
        "passed": True,
        "candidate_records": len(candidates),
        "candidate_sha256": hashlib.sha256(args.candidates.read_bytes()).hexdigest(),
        "selected": len(selected),
        "selected_by_phase": dict(sorted(phase_counts.items())),
        "selected_by_side": dict(sorted(side_counts.items())),
        "selection_seed": args.selection_seed,
        "permutation_seed": args.permutation_seed,
        "benchmark_seed": args.benchmark_seed,
        "canonicalization": "exact_plus_rotate180_colour_swap",
        "unique_after_exclusion": len(unique),
        "excluded_unique": len(excluded),
        "excluded_occurrences": excluded_occurrences,
        "duplicate_occurrences": duplicate_occurrences,
        "excluded_sources": source_counts,
        "forbidden_overlap": 0,
        "fen_sha256": hashlib.sha256(args.out_fen.read_bytes()).hexdigest(),
        "jnnw_sha256": hashlib.sha256(args.out_jnnw.read_bytes()).hexdigest(),
        "benchmark_fen_sha256": hashlib.sha256(args.out_benchmark_fen.read_bytes()).hexdigest(),
        "benchmark_jnnw_sha256": hashlib.sha256(args.out_benchmark_jnnw.read_bytes()).hexdigest(),
        "score_reads": 0,
        "wdl_reads": 0,
        "deep_label_reads": 0,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
