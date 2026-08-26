#!/usr/bin/env python3
"""Target-blind fresh-position selector for DSSD Phase-B confirmation.

This tool runs only after Phase-A PASS. It consumes a fresh CURRICULUM-play
position stream that has already passed the frozen board/STM-only parent filter.
It never consumes source score/WDL labels. Exact + historical valid
rotate180/colour-swap duplicates are removed, and any canonical parent already
present in frozen Phase-A selection is excluded before deterministic sampling.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

# Phase-B invokes this file by path from the runner work directory. In that
# direct-script mode Python puts jobs/tools (not the repository root) on
# sys.path, so package imports below must bootstrap the repository root just as
# the other standalone jobs/tools entry points do. This is packaging only; it
# does not alter any DSSD data, seeds, selection rules, targets, or scores.
if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.tb_frontier_catalog_mine import JNNW_RECORD_SIZE  # noqa: E402
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint  # noqa: E402

FILTER_FIELDS = [
    "row_index", "source_row_index", "parent_fingerprint", "parent_stm", "pieces", "legal_moves"
]
PHASES = {
    "P0": (30, 40),
    "P1": (20, 29),
    "P2": (12, 19),
    "P3": (9, 11),
}
DEFAULT_SEED = 2026083105
DEFAULT_TOTAL = 2000
DEFAULT_PHASE_QUOTA = 500


@dataclass(frozen=True)
class Candidate:
    canonical: str
    raw_fp: str
    rec: bytes
    stm: int
    pieces: int
    legal_moves: int
    phase: str
    source_row_index: int
    sample_hash: str


def phase_for(pieces: int) -> str:
    for name, (lo, hi) in PHASES.items():
        if lo <= pieces <= hi:
            return name
    raise ValueError(f"pieces outside frozen DSSD phases: {pieces}")


def sample_hash(canonical: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{canonical}".encode("utf-8")).hexdigest()


def load_excluded(path: Path) -> set[str]:
    out: set[str] = set()
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        if rd.fieldnames is None or "canonical_fingerprint" not in rd.fieldnames:
            raise ValueError("Phase-A selection TSV lacks canonical_fingerprint")
        for row in rd:
            c = row["canonical_fingerprint"].strip()
            if not c:
                raise ValueError("empty Phase-A canonical fingerprint")
            out.add(c)
    if not out:
        raise ValueError("Phase-A exclusion set is empty")
    return out


def load_filtered(jnnw: Path, tsv: Path, excluded: set[str], seed: int) -> tuple[dict[str, Candidate], dict]:
    raw = jnnw.open("rb")
    meta = tsv.open(newline="", encoding="utf-8")
    try:
        header = raw.read(8)
        if len(header) != 8 or header[:4] != b"JNNW":
            raise ValueError("fresh filtered JNNW has bad header")
        declared = struct.unpack_from("<I", header, 4)[0]
        rd = csv.DictReader(meta, delimiter="\t")
        if rd.fieldnames != FILTER_FIELDS:
            raise ValueError(f"fresh filtered metadata field drift: {rd.fieldnames!r}")
        unique: dict[str, Candidate] = {}
        excluded_overlap = 0
        symmetry_or_exact_duplicates = 0
        rows = 0
        for row in rd:
            rec = raw.read(JNNW_RECORD_SIZE)
            if len(rec) != JNNW_RECORD_SIZE:
                raise ValueError("fresh filtered JNNW truncated")
            if int(row["row_index"]) != rows:
                raise ValueError("fresh filtered row_index drift")
            if rec[33:38] != b"\0" * 5:
                raise ValueError("fresh filtered row retained historical target bytes")
            raw_fp = row["parent_fingerprint"]
            canonical = canonical_fingerprint(raw_fp)
            rows += 1
            if canonical in excluded:
                excluded_overlap += 1
                continue
            pieces = int(row["pieces"])
            stm = int(row["parent_stm"])
            legal_moves = int(row["legal_moves"])
            if stm not in (0, 1) or not (9 <= pieces <= 40) or not (2 <= legal_moves <= 16):
                raise ValueError("parent filter emitted row outside frozen DSSD eligibility")
            cand = Candidate(
                canonical=canonical,
                raw_fp=raw_fp,
                rec=rec,
                stm=stm,
                pieces=pieces,
                legal_moves=legal_moves,
                phase=phase_for(pieces),
                source_row_index=int(row["source_row_index"]),
                sample_hash=sample_hash(canonical, seed),
            )
            old = unique.get(canonical)
            if old is None:
                unique[canonical] = cand
            else:
                symmetry_or_exact_duplicates += 1
                # Deterministic representative independent of source order.
                if (cand.raw_fp, cand.source_row_index) < (old.raw_fp, old.source_row_index):
                    unique[canonical] = cand
        if rows != declared:
            raise ValueError(f"fresh filtered count mismatch metadata={rows} header={declared}")
        if raw.read(1):
            raise ValueError("fresh filtered JNNW trailing bytes")
        return unique, {
            "filtered_rows": rows,
            "excluded_phase_a_overlap_occurrences": excluded_overlap,
            "exact_or_symmetry_duplicate_occurrences_removed": symmetry_or_exact_duplicates,
            "unique_fresh_canonical_after_exclusion": len(unique),
        }
    finally:
        raw.close()
        meta.close()


def choose(unique: dict[str, Candidate], total: int, quota: int) -> tuple[list[Candidate], dict]:
    if total <= 0 or quota < 0:
        raise ValueError("invalid selection size/quota")
    by_phase = {
        ph: sorted((c for c in unique.values() if c.phase == ph), key=lambda c: (c.sample_hash, c.canonical))
        for ph in PHASES
    }
    selected: list[Candidate] = []
    selected_keys: set[str] = set()
    initial = {}
    for ph in PHASES:
        take = min(quota, len(by_phase[ph]))
        initial[ph] = take
        for c in by_phase[ph][:take]:
            selected.append(c)
            selected_keys.add(c.canonical)
    if len(selected) > total:
        raise ValueError("phase quota sum exceeds requested total")
    if len(selected) < total:
        remaining = sorted(
            (c for c in unique.values() if c.canonical not in selected_keys),
            key=lambda c: (c.sample_hash, c.canonical),
        )
        need = total - len(selected)
        selected.extend(remaining[:need])
    if len(selected) != total:
        raise ValueError(f"fresh confirmation support insufficient: selected {len(selected)} != {total}")
    selected.sort(key=lambda c: (c.sample_hash, c.canonical))
    return selected, {
        "phase_available": {ph: len(by_phase[ph]) for ph in PHASES},
        "phase_quota_target": {ph: quota for ph in PHASES},
        "phase_quota_initial_take": initial,
        "phase_selected": {ph: sum(c.phase == ph for c in selected) for ph in PHASES},
    }


def write_outputs(selected: list[Candidate], out_jnnw: Path, out_tsv: Path) -> None:
    out_jnnw.parent.mkdir(parents=True, exist_ok=True)
    out_tsv.parent.mkdir(parents=True, exist_ok=True)
    with out_jnnw.open("wb") as f:
        f.write(b"JNNW" + struct.pack("<I", len(selected)))
        for c in selected:
            f.write(c.rec)
    fields = [
        "parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm", "pieces",
        "legal_moves", "phase", "source_row_index", "sample_hash",
    ]
    with out_tsv.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        wr.writeheader()
        for pid, c in enumerate(selected):
            wr.writerow({
                "parent_id": pid,
                "canonical_fingerprint": c.canonical,
                "raw_fingerprint": c.raw_fp,
                "parent_stm": c.stm,
                "pieces": c.pieces,
                "legal_moves": c.legal_moves,
                "phase": c.phase,
                "source_row_index": c.source_row_index,
                "sample_hash": c.sample_hash,
            })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--filtered-parents", type=Path, required=True)
    ap.add_argument("--filtered-meta", type=Path, required=True)
    ap.add_argument("--exclude-selected", type=Path, required=True)
    ap.add_argument("--out-jnnw", type=Path, required=True)
    ap.add_argument("--out-tsv", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--total", type=int, default=DEFAULT_TOTAL)
    ap.add_argument("--phase-quota", type=int, default=DEFAULT_PHASE_QUOTA)
    args = ap.parse_args()

    excluded = load_excluded(args.exclude_selected)
    unique, receipt = load_filtered(args.filtered_parents, args.filtered_meta, excluded, args.seed)
    selected, sample_receipt = choose(unique, args.total, args.phase_quota)
    write_outputs(selected, args.out_jnnw, args.out_tsv)
    report = {
        "schema": "jass.deep_sibling_phase_b_fresh_selection.v1",
        "target_blind": True,
        "source_labels_read": False,
        "phase_a_canonical_overlap_selected": 0,
        "canonicalization": "exact_plus_rotate180_colour_swap",
        "seed": args.seed,
        "requested_total": args.total,
        "selected_total": len(selected),
        "requested_phase_quota": args.phase_quota,
        **receipt,
        **sample_receipt,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"selected_total": len(selected), "phase_selected": report["phase_selected"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
