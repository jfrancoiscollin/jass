#!/usr/bin/env python3
"""Target-blind 2,000-parent selector for the Scan ceiling benchmark.

Consumes only zero-target outputs from ``deep_sibling_parent_filter``. Exact
and rotate180/colour-swap identities are de-duplicated, all supplied consumed
cohorts are excluded identity-only, and the preregistered phase/subset hashes
are applied without reading a score.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.calibrate_vs_scan import parse_jass_fen  # noqa: E402
from jobs.tools.tb_frontier_symmetry_dedup import (  # noqa: E402
    canonical_fingerprint,
    format_fingerprint,
    parse_fingerprint,
)

RECORD_SIZE = 38
FILTER_FIELDS = [
    "row_index", "source_row_index", "parent_fingerprint", "parent_stm",
    "pieces", "legal_moves",
]
PHASES = {
    "P0": (30, 40),
    "P1": (20, 29),
    "P2": (12, 19),
    "P3": (9, 11),
}
PHASE_ORDER = tuple(PHASES)
SELECTION_SEED = 2026091301
SUBSET_SEED = 2026091302


@dataclass(frozen=True)
class Candidate:
    canonical: str
    raw_fingerprint: str
    record: bytes
    stm: int
    pieces: int
    legal_moves: int
    phase: str
    source_shard: int
    source_row_index: int
    selection_hash: str
    subset_hash: str


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hash_key(seed: int, identity: str) -> str:
    return hashlib.sha256(f"{seed}:{identity}".encode()).hexdigest()


def phase_for(pieces: int) -> str:
    for name, (lo, hi) in PHASES.items():
        if lo <= pieces <= hi:
            return name
    raise ValueError(f"pieces outside preregistered phases: {pieces}")


def record_fingerprint(record: bytes) -> tuple[str, int]:
    if len(record) != RECORD_SIZE:
        raise ValueError("bad filtered JNNW record size")
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    stm = record[32]
    if stm not in (0, 1) or record[33:38] != b"\0" * 5:
        raise ValueError("invalid or labelled filtered JNNW record")
    fp = format_fingerprint(wm, wk, bm, bk, stm)
    # Reuse the canonical parser as the single board validity guard.
    parse_fingerprint(fp)
    return fp, (wm | wk | bm | bk).bit_count()


def bits(squares: list[int]) -> int:
    value = 0
    for square in squares:
        if not 1 <= square <= 50:
            raise ValueError("FEN square outside 1..50")
        value |= 1 << (square - 1)
    return value


def fen_identity(fen: str) -> str:
    side, wm, wk, bm, bk = parse_jass_fen(fen)
    if side not in ("W", "B"):
        raise ValueError("bad FEN side")
    return canonical_fingerprint(format_fingerprint(
        bits(wm), bits(wk), bits(bm), bits(bk), 0 if side == "W" else 1,
    ))


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", newline="") \
        if path.suffix == ".gz" else path.open("r", encoding="utf-8", newline="")


def fen_rows(path: Path) -> list[str]:
    with open_text(path) as stream:
        return [value for line in stream
                if (value := line.split("#", 1)[0].strip())]


def load_tsv_identities(path: Path) -> set[str]:
    identities: set[str] = set()
    with open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fields = set(reader.fieldnames or ())
        fp_field = next((field for field in (
            "canonical_fingerprint", "parent_fingerprint", "raw_fingerprint",
        ) if field in fields), None)
        fen_field = next((field for field in (
            "fen", "parent_fen", "position_fen",
        ) if field in fields), None)
        if fp_field is None and fen_field is None:
            raise ValueError(f"{path}: no board+STM identity field")
        for row in reader:
            if fp_field and row.get(fp_field):
                identities.add(canonical_fingerprint(row[fp_field].strip()))
            elif fen_field and row.get(fen_field):
                identities.add(fen_identity(row[fen_field].strip()))
    if not identities:
        raise ValueError(f"{path}: empty exclusion identity set")
    return identities


def load_exclusions(fen_paths: list[Path], tsv_paths: list[Path]) -> tuple[set[str], dict[str, dict[str, object]]]:
    all_ids: set[str] = set()
    receipt: dict[str, dict[str, object]] = {}
    for path in fen_paths:
        ids = {fen_identity(fen) for fen in fen_rows(path)}
        if not ids:
            raise ValueError(f"{path}: empty FEN exclusion")
        all_ids.update(ids)
        receipt[str(path)] = {"kind": "fen", "unique_identities": len(ids), "sha256": sha256(path)}
    for path in tsv_paths:
        ids = load_tsv_identities(path)
        all_ids.update(ids)
        receipt[str(path)] = {"kind": "tsv", "unique_identities": len(ids), "sha256": sha256(path)}
    if not receipt:
        raise ValueError("at least one consumed-cohort exclusion is required")
    return all_ids, receipt


def iter_filtered(jnnw: Path, meta: Path, shard: int):
    with jnnw.open("rb") as states, meta.open(newline="", encoding="utf-8") as table:
        header = states.read(8)
        if len(header) != 8 or header[:4] != b"JNNW":
            raise ValueError(f"{jnnw}: bad JNNW header")
        declared = struct.unpack_from("<I", header, 4)[0]
        reader = csv.DictReader(table, delimiter="\t")
        if reader.fieldnames != FILTER_FIELDS:
            raise ValueError(f"{meta}: parent-filter fields drift {reader.fieldnames!r}")
        rows = 0
        for raw in reader:
            record = states.read(RECORD_SIZE)
            if len(record) != RECORD_SIZE:
                raise ValueError(f"{jnnw}: truncated at row {rows}")
            if int(raw["row_index"]) != rows:
                raise ValueError(f"{meta}: row_index drift")
            if record[33:38] != b"\0" * 5:
                raise ValueError(f"{jnnw}: filtered target bytes are not zero")
            yield record, raw, shard
            rows += 1
        if rows != declared or states.read(1):
            raise ValueError(f"{jnnw}: count/trailing-byte drift")


def collect_candidates(
    jnnw_paths: list[Path],
    meta_paths: list[Path],
    excluded: set[str],
    selection_seed: int,
    subset_seed: int,
) -> tuple[dict[str, Candidate], dict[str, object]]:
    if len(jnnw_paths) != len(meta_paths):
        raise ValueError("filtered JNNW/meta path count mismatch")
    unique: dict[str, Candidate] = {}
    filtered_rows = excluded_occurrences = 0
    exact_duplicate_occurrences = symmetry_duplicate_occurrences = 0
    seen_raw: set[str] = set()
    phase_eligible = {phase: 0 for phase in PHASES}
    for shard, (jnnw, meta) in enumerate(zip(jnnw_paths, meta_paths)):
        for record, row, source_shard in iter_filtered(jnnw, meta, shard):
            filtered_rows += 1
            raw_fp = format_fingerprint(*parse_fingerprint(row["parent_fingerprint"].strip()))
            record_fp, record_pieces = record_fingerprint(record)
            if record_fp != raw_fp:
                raise ValueError("filtered metadata/JNNW fingerprint drift")
            canonical = canonical_fingerprint(raw_fp)
            if canonical in excluded:
                excluded_occurrences += 1
                continue
            stm = int(row["parent_stm"])
            pieces = int(row["pieces"])
            legal_moves = int(row["legal_moves"])
            if (stm not in (0, 1) or stm != parse_fingerprint(raw_fp)[4]
                    or pieces != record_pieces or not 2 <= legal_moves <= 16):
                raise ValueError("parent filter emitted row outside legal support")
            phase = phase_for(pieces)
            phase_eligible[phase] += 1
            candidate = Candidate(
                canonical=canonical,
                raw_fingerprint=raw_fp,
                record=record,
                stm=stm,
                pieces=pieces,
                legal_moves=legal_moves,
                phase=phase,
                source_shard=source_shard,
                source_row_index=int(row["source_row_index"]),
                selection_hash=hash_key(selection_seed, canonical),
                subset_hash=hash_key(subset_seed, canonical),
            )
            old = unique.get(canonical)
            if old is None:
                unique[canonical] = candidate
            else:
                if raw_fp in seen_raw:
                    exact_duplicate_occurrences += 1
                else:
                    symmetry_duplicate_occurrences += 1
                old_key = (old.raw_fingerprint, old.source_shard, old.source_row_index)
                new_key = (candidate.raw_fingerprint, candidate.source_shard, candidate.source_row_index)
                if new_key < old_key:
                    unique[canonical] = candidate
            seen_raw.add(raw_fp)
    return unique, {
        "filtered_rows": filtered_rows,
        "eligible_occurrences_before_canonical_dedup": sum(phase_eligible.values()),
        "eligible_occurrences_by_phase": phase_eligible,
        "excluded_occurrences": excluded_occurrences,
        "exact_duplicate_occurrences_removed": exact_duplicate_occurrences,
        "rotate180_colour_swap_duplicate_occurrences_removed": symmetry_duplicate_occurrences,
        "exact_or_symmetry_duplicate_occurrences_removed": (
            exact_duplicate_occurrences + symmetry_duplicate_occurrences
        ),
        "unique_after_exclusion": len(unique),
    }


def select(unique: dict[str, Candidate]) -> tuple[list[Candidate], set[str], set[str], dict[str, int]]:
    selected: list[Candidate] = []
    deep: set[str] = set()
    ultra: set[str] = set()
    available: dict[str, int] = {}
    for phase in PHASE_ORDER:
        rows = [candidate for candidate in unique.values() if candidate.phase == phase]
        rows.sort(key=lambda c: (c.selection_hash, c.canonical))
        available[phase] = len(rows)
        if len(rows) < 500:
            raise ValueError(f"selection support insufficient in {phase}: {len(rows)} < 500")
        chosen = rows[:500]
        selected.extend(chosen)
        nested = sorted(chosen, key=lambda c: (c.subset_hash, c.canonical))
        deep.update(c.canonical for c in nested[:128])
        ultra.update(c.canonical for c in nested[:64])
    if len(selected) != 2000 or len(deep) != 512 or len(ultra) != 256 or not ultra < deep:
        raise AssertionError("cohort/subset cardinality drift")
    return selected, deep, ultra, available


def write_jnnw(path: Path, selected: list[Candidate]) -> None:
    with path.open("wb") as out:
        out.write(b"JNNW" + struct.pack("<I", len(selected)))
        for candidate in selected:
            out.write(candidate.record)


def write_outputs(
    selected: list[Candidate],
    deep: set[str],
    ultra: set[str],
    out_jnnw: Path,
    out_tsv: Path,
    deep_tsv: Path,
    ultra_tsv: Path,
) -> None:
    for path in (out_jnnw, out_tsv, deep_tsv, ultra_tsv):
        path.parent.mkdir(parents=True, exist_ok=True)
    write_jnnw(out_jnnw, selected)
    fields = [
        "parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm",
        "pieces", "legal_moves", "phase", "source_shard", "source_row_index",
        "selection_hash", "subset_hash", "in_deep512", "in_ultra256",
    ]
    subset_fields = ["parent_id", "canonical_fingerprint", "phase", "subset_hash"]
    with out_tsv.open("w", newline="", encoding="utf-8") as full, \
            deep_tsv.open("w", newline="", encoding="utf-8") as deep_out, \
            ultra_tsv.open("w", newline="", encoding="utf-8") as ultra_out:
        writer = csv.DictWriter(full, fieldnames=fields, delimiter="\t", lineterminator="\n")
        deep_writer = csv.DictWriter(deep_out, fieldnames=subset_fields, delimiter="\t", lineterminator="\n")
        ultra_writer = csv.DictWriter(ultra_out, fieldnames=subset_fields, delimiter="\t", lineterminator="\n")
        writer.writeheader(); deep_writer.writeheader(); ultra_writer.writeheader()
        subset_rows: list[tuple[Candidate, dict[str, object]]] = []
        for parent_id, candidate in enumerate(selected):
            row = {
                "parent_id": parent_id,
                "canonical_fingerprint": candidate.canonical,
                "raw_fingerprint": candidate.raw_fingerprint,
                "parent_stm": candidate.stm,
                "pieces": candidate.pieces,
                "legal_moves": candidate.legal_moves,
                "phase": candidate.phase,
                "source_shard": candidate.source_shard,
                "source_row_index": candidate.source_row_index,
                "selection_hash": candidate.selection_hash,
                "subset_hash": candidate.subset_hash,
                "in_deep512": int(candidate.canonical in deep),
                "in_ultra256": int(candidate.canonical in ultra),
            }
            writer.writerow(row)
            subset_rows.append((candidate, row))
        # The preregistered subset lists are phase-major and then ordered by
        # the subset hash used to select them, not by the independent cohort
        # selection hash.
        subset_rows.sort(key=lambda item: (
            PHASE_ORDER.index(item[0].phase), item[0].subset_hash, item[0].canonical,
        ))
        for candidate, row in subset_rows:
            subrow = {field: row[field] for field in subset_fields}
            if candidate.canonical in deep:
                deep_writer.writerow(subrow)
            if candidate.canonical in ultra:
                ultra_writer.writerow(subrow)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filtered-jnnw", type=Path, action="append", required=True)
    parser.add_argument("--filtered-meta", type=Path, action="append", required=True)
    parser.add_argument("--exclude-fen", type=Path, action="append", default=[])
    parser.add_argument("--exclude-tsv", type=Path, action="append", default=[])
    parser.add_argument("--selection-seed", type=int, default=SELECTION_SEED)
    parser.add_argument("--subset-seed", type=int, default=SUBSET_SEED)
    parser.add_argument("--expected-shards", type=int, default=16)
    parser.add_argument("--out-jnnw", type=Path, required=True)
    parser.add_argument("--out-tsv", type=Path, required=True)
    parser.add_argument("--deep-tsv", type=Path, required=True)
    parser.add_argument("--ultra-tsv", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.selection_seed != SELECTION_SEED or args.subset_seed != SUBSET_SEED:
        raise ValueError("preregistered selection/subset seed drift")
    if len(args.filtered_jnnw) != args.expected_shards or len(args.filtered_meta) != args.expected_shards:
        raise ValueError("filtered shard cardinality drift")
    excluded, exclusions = load_exclusions(args.exclude_fen, args.exclude_tsv)
    unique, counts = collect_candidates(
        args.filtered_jnnw, args.filtered_meta, excluded,
        args.selection_seed, args.subset_seed,
    )
    selected, deep, ultra, available = select(unique)
    write_outputs(
        selected, deep, ultra, args.out_jnnw, args.out_tsv,
        args.deep_tsv, args.ultra_tsv,
    )
    selected_ids = [candidate.canonical for candidate in selected]
    payload = {
        "schema": "jass.scan_ceiling_target_blind_selection.v1",
        "passed": True,
        "benchmark_only": True,
        "target_blind": True,
        "source_labels_read": False,
        "source_scores_read": False,
        "source_wdl_read": False,
        "filtered_target_bytes_validated_zero": True,
        "selection_seed": args.selection_seed,
        "subset_seed": args.subset_seed,
        "source_shards": len(args.filtered_jnnw),
        "source_shard_receipts": [
            {
                "shard": shard,
                "filtered_jnnw_sha256": sha256(jnnw),
                "filtered_meta_sha256": sha256(meta),
            }
            for shard, (jnnw, meta) in enumerate(zip(args.filtered_jnnw, args.filtered_meta))
        ],
        "canonicalization": "exact_plus_rotate180_colour_swap",
        "excluded_unique": len(excluded),
        "exclusion_sources": exclusions,
        **counts,
        "phase_available": available,
        "selected": len(selected),
        "selected_by_phase": {phase: sum(c.phase == phase for c in selected) for phase in PHASES},
        "selected_by_side": {
            "white": sum(c.stm == 0 for c in selected),
            "black": sum(c.stm == 1 for c in selected),
        },
        "deep512": len(deep),
        "deep512_by_phase": {phase: sum(c.phase == phase and c.canonical in deep for c in selected) for phase in PHASES},
        "ultra256": len(ultra),
        "ultra256_by_phase": {phase: sum(c.phase == phase and c.canonical in ultra for c in selected) for phase in PHASES},
        "ultra_strict_subset_of_deep": ultra < deep,
        "forbidden_overlap": len(set(selected_ids) & excluded),
        "cohort_identity_sha256": hashlib.sha256(("\n".join(selected_ids) + "\n").encode()).hexdigest(),
        "parents_jnnw_sha256": sha256(args.out_jnnw),
        "parents_tsv_sha256": sha256(args.out_tsv),
        "deep512_tsv_sha256": sha256(args.deep_tsv),
        "ultra256_tsv_sha256": sha256(args.ultra_tsv),
        "fits": 0,
        "calibrations": 0,
        "strength_games": 0,
        "training_allowed": False,
        "tuning_allowed": False,
        "calibration_allowed": False,
        "model_selection_allowed": False,
        "runtime_scale_selection_allowed": False,
        "promotion_authorized": False,
    }
    if payload["forbidden_overlap"] != 0 or payload["selected_by_phase"] != {phase: 500 for phase in PHASES}:
        raise AssertionError("selection receipt contract drift")
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"selected": 2000, "deep512": 512, "ultra256": 256}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
