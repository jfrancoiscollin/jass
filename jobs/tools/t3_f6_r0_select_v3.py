#!/usr/bin/env python3
"""Preregistered target-blind R0-v3 selection with mechanical leaf witnesses."""
from __future__ import annotations

import argparse
import csv
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

from jobs.tools.t3_f6_r0_select import (
    PHASES,
    fen_fingerprint,
    fen_rows,
    load_tsv_identities,
    phase_for,
)


@dataclass(frozen=True)
class Candidate:
    fen: str
    values: tuple[int, int, int, int, int]
    canonical: str
    general_key: str
    isolated_key: str
    trace_key: str
    isolated: bool


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_json_fens(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    found: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)
        elif isinstance(value, str) and ":" in value:
            try:
                found.add(fen_fingerprint(value)[0])
            except (ValueError, IndexError, KeyError):
                pass

    visit(payload)
    if not found:
        raise ValueError(f"{path}: no FEN identity found")
    return found


def load_mechanics(path: Path) -> tuple[dict[str, bool], int]:
    result: dict[str, bool] = {}
    rows = 0
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"fen", "phase", "isolated"}
        if not required <= set(reader.fieldnames or ()):
            raise ValueError("mechanical classification schema drift")
        for row in reader:
            rows += 1
            fen = row["fen"]
            isolated = row["isolated"] == "1"
            values = fen_fingerprint(fen)[1]
            if row["phase"] != phase_for(values):
                raise ValueError("mechanical classification phase drift")
            old = result.get(fen)
            if old is not None and old != isolated:
                raise ValueError("duplicate FEN has inconsistent isolation")
            result[fen] = isolated
    return result, rows


def write_fens(path: Path, rows: list[Candidate]) -> None:
    path.write_text("\n".join(row.fen for row in rows) + "\n", encoding="utf-8")


def write_jnnw(path: Path, rows: list[Candidate]) -> None:
    with path.open("wb") as out:
        out.write(b"JNNW" + struct.pack("<I", len(rows)))
        for row in rows:
            wm, wk, bm, bk, stm = row.values
            out.write(struct.pack("<QQQQBib", wm, wk, bm, bk, stm, 0, 0))


def write_support_failure(args: argparse.Namespace, reason: str,
                          candidate_count: int, mechanical_rows: int,
                          unique_count: int, excluded_count: int,
                          excluded_occurrences: int, duplicate_occurrences: int,
                          source_counts: dict[str, int],
                          support_by_phase: dict[str, dict[str, int]]) -> int:
    report = {
        "schema": "jass.t3_f6_r0_target_blind_selection.v3",
        "passed": False,
        "verdict": "R0_V3_RUNTIME_SUPPORT_INCONCLUSIVE",
        "reason": reason,
        "candidate_records": candidate_count,
        "candidate_sha256": sha(args.candidates),
        "mechanical_rows": mechanical_rows,
        "mechanics_sha256": sha(args.mechanics),
        "unique_after_exclusion": unique_count,
        "excluded_unique": excluded_count,
        "excluded_occurrences": excluded_occurrences,
        "duplicate_occurrences": duplicate_occurrences,
        "excluded_sources": source_counts,
        "support_by_phase": support_by_phase,
        "selection_seed": args.selection_seed,
        "permutation_seed": args.permutation_seed,
        "benchmark_seed": args.benchmark_seed,
        "isolated_seed": args.isolated_seed,
        "trace_seed": args.trace_seed,
        "canonicalization": "exact_plus_rotate180_colour_swap",
        "forbidden_overlap": 0,
        "score_reads": 0,
        "wdl_reads": 0,
        "deep_label_reads": 0,
        "runtime_metric_reads": 0,
    }
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--mechanics", type=Path, required=True)
    parser.add_argument("--exclude-fen", type=Path, action="append", default=[])
    parser.add_argument("--exclude-tsv", type=Path, action="append", default=[])
    parser.add_argument("--exclude-json-fens", type=Path, action="append", default=[])
    parser.add_argument("--selection-seed", type=int, required=True)
    parser.add_argument("--permutation-seed", type=int, required=True)
    parser.add_argument("--benchmark-seed", type=int, required=True)
    parser.add_argument("--isolated-seed", type=int, required=True)
    parser.add_argument("--trace-seed", type=int, required=True)
    parser.add_argument("--out-fen", type=Path, required=True)
    parser.add_argument("--out-jnnw", type=Path, required=True)
    parser.add_argument("--out-benchmark-fen", type=Path, required=True)
    parser.add_argument("--out-benchmark-jnnw", type=Path, required=True)
    parser.add_argument("--out-isolated-fen", type=Path, required=True)
    parser.add_argument("--out-real-trace-fen", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    expected_seeds = (2026092102, 2026092103, 2026092104, 2026092105, 2026092106)
    actual_seeds = (args.selection_seed, args.permutation_seed, args.benchmark_seed,
                    args.isolated_seed, args.trace_seed)
    if actual_seeds != expected_seeds:
        raise ValueError(f"R0-v3 seed drift: {actual_seeds}")

    raw_candidates = fen_rows(args.candidates)
    if len(raw_candidates) != 120000:
        raise ValueError(f"candidate cardinality {len(raw_candidates)} != 120000")
    mechanics, mechanical_rows = load_mechanics(args.mechanics)
    if mechanical_rows != 120000 or any(fen not in mechanics for fen in raw_candidates):
        raise ValueError("mechanical classification cardinality/coverage drift")

    excluded: set[str] = set()
    source_counts: dict[str, int] = {}
    for path in args.exclude_fen:
        identities = {fen_fingerprint(fen)[0] for fen in fen_rows(path)}
        excluded.update(identities)
        source_counts[str(path)] = len(identities)
    for path in args.exclude_tsv:
        identities = load_tsv_identities(path)
        excluded.update(identities)
        source_counts[str(path)] = len(identities)
    for path in args.exclude_json_fens:
        identities = extract_json_fens(path)
        excluded.update(identities)
        source_counts[str(path)] = len(identities)

    unique: dict[str, Candidate] = {}
    excluded_occurrences = 0
    duplicate_occurrences = 0
    canonical_isolation: dict[str, bool] = {}
    for fen in raw_candidates:
        canonical, values = fen_fingerprint(fen)
        isolated = mechanics[fen]
        previous_isolation = canonical_isolation.setdefault(canonical, isolated)
        if previous_isolation != isolated:
            raise ValueError("colour-canonical identity has inconsistent isolation")
        if canonical in excluded:
            excluded_occurrences += 1
            continue
        row = Candidate(
            fen=fen,
            values=values,
            canonical=canonical,
            general_key=hashlib.sha256(
                f"{args.selection_seed}:{canonical}".encode()).hexdigest(),
            isolated_key=hashlib.sha256(
                f"{args.isolated_seed}:{canonical}".encode()).hexdigest(),
            trace_key=hashlib.sha256(
                f"{args.trace_seed}:{canonical}".encode()).hexdigest(),
            isolated=isolated,
        )
        old = unique.get(canonical)
        if old is None or (row.fen, row.general_key) < (old.fen, old.general_key):
            unique[canonical] = row
        if old is not None:
            duplicate_occurrences += 1

    selected_by_phase: dict[str, list[Candidate]] = {}
    isolated_by_phase: dict[str, list[Candidate]] = {}
    real_by_phase: dict[str, list[Candidate]] = {}
    support_by_phase: dict[str, dict[str, int]] = {}
    for phase in PHASES:
        support = [row for row in unique.values() if phase_for(row.values) == phase]
        isolated_support = sorted(
            (row for row in support if row.isolated),
            key=lambda row: (row.isolated_key, row.fen),
        )
        if len(isolated_support) < 32:
            support_by_phase[phase] = {
                "unique": len(support), "isolated": len(isolated_support)}
            return write_support_failure(
                args, f"{phase} isolated support {len(isolated_support)} < 32",
                len(raw_candidates), mechanical_rows, len(unique), len(excluded),
                excluded_occurrences, duplicate_occurrences, source_counts,
                support_by_phase)
        isolated = isolated_support[:32]
        reserved = {row.canonical for row in isolated}
        general = sorted(
            (row for row in support if row.canonical not in reserved),
            key=lambda row: (row.general_key, row.fen),
        )
        if len(general) < 992:
            support_by_phase[phase] = {
                "unique": len(support), "isolated": len(isolated_support),
                "general": len(general)}
            return write_support_failure(
                args, f"{phase} general support {len(general)} < 992",
                len(raw_candidates), mechanical_rows, len(unique), len(excluded),
                excluded_occurrences, duplicate_occurrences, source_counts,
                support_by_phase)
        selected = isolated + general[:992]
        nonisolated = sorted(
            (row for row in selected if not row.isolated),
            key=lambda row: (row.trace_key, row.fen),
        )
        if len(nonisolated) < 32:
            support_by_phase[phase] = {
                "unique": len(support), "isolated": len(isolated_support),
                "general": len(general), "selected_nonisolated": len(nonisolated)}
            return write_support_failure(
                args, f"{phase} nonisolated support {len(nonisolated)} < 32",
                len(raw_candidates), mechanical_rows, len(unique), len(excluded),
                excluded_occurrences, duplicate_occurrences, source_counts,
                support_by_phase)
        selected_by_phase[phase] = selected
        isolated_by_phase[phase] = isolated
        real_by_phase[phase] = isolated + nonisolated[:32]
        support_by_phase[phase] = {
            "unique": len(support),
            "isolated": len(isolated_support),
            "selected": len(selected),
            "selected_isolated": len(isolated),
            "selected_nonisolated": sum(not row.isolated for row in selected),
        }

    selected = [row for phase in PHASES for row in selected_by_phase[phase]]
    isolated = [row for phase in PHASES for row in isolated_by_phase[phase]]
    real = [row for phase in PHASES for row in real_by_phase[phase]]
    if len(selected) != 4096 or len(isolated) != 128 or len(real) != 256:
        raise ValueError("R0-v3 selected/witness cardinality drift")
    if {row.canonical for row in selected} & excluded:
        raise ValueError("R0-v3 selected/excluded overlap")

    random.Random(args.permutation_seed).shuffle(selected)
    benchmark = sorted(selected, key=lambda row: (
        hashlib.sha256(f"{args.benchmark_seed}:{row.canonical}".encode()).digest(),
        row.fen,
    ))
    write_fens(args.out_fen, selected)
    write_jnnw(args.out_jnnw, selected)
    write_fens(args.out_benchmark_fen, benchmark)
    write_jnnw(args.out_benchmark_jnnw, benchmark)
    write_fens(args.out_isolated_fen, isolated)
    write_fens(args.out_real_trace_fen, real)

    report = {
        "schema": "jass.t3_f6_r0_target_blind_selection.v3",
        "passed": True,
        "candidate_records": len(raw_candidates),
        "candidate_sha256": sha(args.candidates),
        "mechanical_rows": mechanical_rows,
        "mechanics_sha256": sha(args.mechanics),
        "selected": len(selected),
        "selected_by_phase": dict(Counter(phase_for(row.values) for row in selected)),
        "selected_by_side": dict(Counter(
            "white" if row.values[4] == 0 else "black" for row in selected)),
        "isolated_roots": len(isolated),
        "isolated_by_phase": dict(Counter(phase_for(row.values) for row in isolated)),
        "real_trace_roots": len(real),
        "real_trace_by_phase": dict(Counter(phase_for(row.values) for row in real)),
        "support_by_phase": support_by_phase,
        "selection_seed": args.selection_seed,
        "permutation_seed": args.permutation_seed,
        "benchmark_seed": args.benchmark_seed,
        "isolated_seed": args.isolated_seed,
        "trace_seed": args.trace_seed,
        "canonicalization": "exact_plus_rotate180_colour_swap",
        "unique_after_exclusion": len(unique),
        "excluded_unique": len(excluded),
        "excluded_occurrences": excluded_occurrences,
        "duplicate_occurrences": duplicate_occurrences,
        "excluded_sources": source_counts,
        "forbidden_overlap": 0,
        "fen_sha256": sha(args.out_fen),
        "jnnw_sha256": sha(args.out_jnnw),
        "benchmark_fen_sha256": sha(args.out_benchmark_fen),
        "benchmark_jnnw_sha256": sha(args.out_benchmark_jnnw),
        "isolated_fen_sha256": sha(args.out_isolated_fen),
        "real_trace_fen_sha256": sha(args.out_real_trace_fen),
        "score_reads": 0,
        "wdl_reads": 0,
        "deep_label_reads": 0,
        "runtime_metric_reads": 0,
    }
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
