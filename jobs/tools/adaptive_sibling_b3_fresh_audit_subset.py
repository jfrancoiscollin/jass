#!/usr/bin/env python3
"""Seal the preregistered target-blind 1,000-parent B3 reference-audit subset.

The subset is selected only from the sealed B3 fresh source cohort identities.
No adaptive-teacher or full-ladder score/label artifact is an input.  The frozen
rule is SHA256("2026110817:<canonical_fingerprint>"), lowest 125 per phase/STM
cell, with deterministic identity tie-breaks.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
import struct
import sys
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
else:
    ROOT = Path(__file__).resolve().parents[2]

from jobs.tools import adaptive_sibling_b2_select as selector  # noqa: E402
from jobs.tools import adaptive_sibling_b3_parity_stage as parity_stage  # noqa: E402
from jobs.tools import adaptive_sibling_b3_fresh_teacher_stage as fresh_teacher  # noqa: E402

SCHEMA = "jass.adaptive_sibling_b3_fresh_audit_subset.v1"
VERDICT = "B3_FRESH_AUDIT_SUBSET_SEALED_V1"
AUDIT_SEED = 2_026_110_817
AUDIT_PER_CELL = 125
AUDIT_PARENTS = 1_000
SOURCE_PARENTS = 4_000
RECORD_SIZE = 38
TSV_FIELDS = [
    "audit_parent_id", "source_parent_id", "canonical_fingerprint",
    "raw_fingerprint", "parent_stm", "pieces", "legal_moves", "phase",
    "source_shard", "source_row_index", "source_selection_hash",
    "audit_selection_hash", "cell",
]


class StageError(RuntimeError):
    pass


def canonical(value: object) -> bytes:
    return parity_stage.canonical(value)


def write_new(path: Path, raw: bytes) -> None:
    parity_stage.write_new(path, raw)


def descriptor(path: Path, **extra: object) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise StageError(f"not a regular file: {path}")
    return {"local_name": path.name, "sha256": parity_stage.sha_file(path),
            "size_bytes": path.stat().st_size, **extra}


def audit_hash(canonical_fingerprint: str) -> str:
    return hashlib.sha256(
        f"{AUDIT_SEED}:{canonical_fingerprint}".encode("ascii")
    ).hexdigest()


@dataclass(frozen=True)
class Parent:
    source_parent_id: int
    canonical_fingerprint: str
    raw_fingerprint: str
    parent_stm: int
    pieces: int
    legal_moves: int
    phase: str
    source_shard: int
    source_row_index: int
    source_selection_hash: str
    audit_selection_hash: str
    record: bytes

    @property
    def cell(self) -> str:
        return f"{self.phase}_stm{self.parent_stm}"

    @property
    def audit_order(self) -> tuple[bytes, str, int]:
        return (bytes.fromhex(self.audit_selection_hash),
                self.canonical_fingerprint, self.source_parent_id)


def _strict_uint(text: str, label: str, lo: int, hi: int) -> int:
    if not text.isascii() or not text.isdigit() or (len(text) > 1 and text.startswith("0")):
        raise StageError(f"{label} is not a canonical unsigned integer")
    value = int(text)
    if not lo <= value <= hi:
        raise StageError(f"{label} outside {lo}..{hi}")
    return value


def load_source(root: Path) -> tuple[list[Parent], bytes]:
    parents_tsv = root / "parents.tsv"
    parents_jnnw = root / "parents.jnnw"
    identities_path = root / "ordered-identities.txt"
    try:
        tsv_raw = parents_tsv.read_bytes()
        jnnw_raw = parents_jnnw.read_bytes()
        identities_raw = identities_path.read_bytes()
    except OSError as exc:
        raise StageError(f"cannot read source cohort: {exc}") from exc
    if b"\r" in tsv_raw or not tsv_raw.endswith(b"\n"):
        raise StageError("source parents TSV is not LF-canonical")
    try:
        reader = csv.DictReader(io.StringIO(tsv_raw.decode("utf-8"), newline=""), delimiter="\t")
    except UnicodeError as exc:
        raise StageError("source parents TSV is not UTF-8") from exc
    if reader.fieldnames != selector.OUTPUT_FIELDS:
        raise StageError("source parents TSV fields drift")
    rows = list(reader)
    if len(rows) != SOURCE_PARENTS:
        raise StageError("source parents TSV must contain exactly 4000 rows")
    if len(jnnw_raw) != 8 + SOURCE_PARENTS * RECORD_SIZE \
            or jnnw_raw[:4] != b"JNNW" \
            or struct.unpack_from("<I", jnnw_raw, 4)[0] != SOURCE_PARENTS:
        raise StageError("source parents JNNW header/count/size mismatch")
    if not identities_raw.endswith(b"\n") or b"\r" in identities_raw:
        raise StageError("source ordered identities is not canonical LF text")
    try:
        identities = identities_raw.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise StageError("source identities are not ASCII") from exc
    if len(identities) != SOURCE_PARENTS:
        raise StageError("source ordered identities cardinality mismatch")

    parents: list[Parent] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if set(row) != set(selector.OUTPUT_FIELDS):
            raise StageError("source TSV row fields drift")
        parent_id = _strict_uint(row["parent_id"], "parent_id", 0, SOURCE_PARENTS - 1)
        if parent_id != index:
            raise StageError("source parent ids are not zero-based TSV order")
        canonical_fp = row["canonical_fingerprint"]
        if canonical_fp != identities[index] or canonical_fp in seen:
            raise StageError("source canonical identity mismatch/duplicate")
        seen.add(canonical_fp)
        stm = _strict_uint(row["parent_stm"], "parent_stm", 0, 1)
        pieces = _strict_uint(row["pieces"], "pieces", 9, 40)
        legal_moves = _strict_uint(row["legal_moves"], "legal_moves", 2, 16)
        phase = row["phase"]
        if phase not in selector.PHASES or selector.phase_for(pieces) != phase:
            raise StageError("source phase/piece mismatch")
        source_shard = _strict_uint(row["source_shard"], "source_shard", 0, 15)
        source_row_index = _strict_uint(row["source_row_index"], "source_row_index", 0, 9_999)
        source_hash = row["selection_hash"]
        if len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
            raise StageError("source selection hash malformed")
        record = jnnw_raw[8 + index * RECORD_SIZE:8 + (index + 1) * RECORD_SIZE]
        if record[33:] != b"\0" * 5:
            raise StageError("source parent target bytes are nonzero")
        parents.append(Parent(
            source_parent_id=parent_id,
            canonical_fingerprint=canonical_fp,
            raw_fingerprint=row["raw_fingerprint"],
            parent_stm=stm,
            pieces=pieces,
            legal_moves=legal_moves,
            phase=phase,
            source_shard=source_shard,
            source_row_index=source_row_index,
            source_selection_hash=source_hash,
            audit_selection_hash=audit_hash(canonical_fp),
            record=record,
        ))
    return parents, identities_raw


def select_subset(parents: Sequence[Parent]) -> list[Parent]:
    if len(parents) != SOURCE_PARENTS:
        raise StageError("audit selection requires exactly 4000 source parents")
    by_cell: dict[str, list[Parent]] = {cell: [] for cell in selector.CELL_ORDER}
    for parent in parents:
        if parent.cell not in by_cell:
            raise StageError(f"unknown source cell {parent.cell}")
        by_cell[parent.cell].append(parent)
    if any(len(by_cell[cell]) != selector.CELL_QUOTA for cell in selector.CELL_ORDER):
        raise StageError("source cohort is not exactly 500 parents per frozen cell")
    selected: list[Parent] = []
    for cell in selector.CELL_ORDER:
        selected.extend(sorted(by_cell[cell], key=lambda item: item.audit_order)[:AUDIT_PER_CELL])
    if len(selected) != AUDIT_PARENTS \
            or len({p.canonical_fingerprint for p in selected}) != AUDIT_PARENTS:
        raise StageError("audit subset cardinality/uniqueness mismatch")
    return selected


def publish_subset(selected: Sequence[Parent], artifacts: Path) -> dict[str, object]:
    if len(selected) != AUDIT_PARENTS:
        raise StageError("cannot publish non-1000 audit subset")
    jnnw_path = artifacts / "b3-fresh-audit-parents.jnnw"
    tsv_path = artifacts / "b3-fresh-audit-parents.tsv"
    identities_path = artifacts / "b3-fresh-audit-identities.txt"
    source_ids_path = artifacts / "b3-fresh-audit-source-parent-ids.txt"
    write_new(jnnw_path, b"JNNW" + struct.pack("<I", AUDIT_PARENTS)
              + b"".join(parent.record for parent in selected))
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=TSV_FIELDS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for audit_id, parent in enumerate(selected):
        writer.writerow({
            "audit_parent_id": audit_id,
            "source_parent_id": parent.source_parent_id,
            "canonical_fingerprint": parent.canonical_fingerprint,
            "raw_fingerprint": parent.raw_fingerprint,
            "parent_stm": parent.parent_stm,
            "pieces": parent.pieces,
            "legal_moves": parent.legal_moves,
            "phase": parent.phase,
            "source_shard": parent.source_shard,
            "source_row_index": parent.source_row_index,
            "source_selection_hash": parent.source_selection_hash,
            "audit_selection_hash": parent.audit_selection_hash,
            "cell": parent.cell,
        })
    write_new(tsv_path, out.getvalue().encode("utf-8"))
    write_new(identities_path, "".join(
        f"{parent.canonical_fingerprint}\n" for parent in selected).encode("ascii"))
    write_new(source_ids_path, "".join(
        f"{parent.source_parent_id}\n" for parent in selected).encode("ascii"))
    counts = {cell: sum(parent.cell == cell for parent in selected)
              for cell in selector.CELL_ORDER}
    if counts != {cell: AUDIT_PER_CELL for cell in selector.CELL_ORDER}:
        raise StageError("published audit cell counts drift")
    return {
        "parents_jnnw": descriptor(jnnw_path, records=AUDIT_PARENTS,
                                   record_size_bytes=RECORD_SIZE),
        "parents_tsv": descriptor(tsv_path, rows=AUDIT_PARENTS),
        "ordered_identities": descriptor(
            identities_path, rows=AUDIT_PARENTS,
            serialization="canonical_fingerprint_ascii, one per line, LF terminated"),
        "source_parent_ids": descriptor(
            source_ids_path, rows=AUDIT_PARENTS,
            serialization="source_parent_id_decimal, one per line, LF terminated"),
        "cells": counts,
    }


def fetch_source(args: argparse.Namespace, work: Path) -> tuple[Path, dict[str, Any], str]:
    target = work / "source"
    mappings = [
        ("artefacts/source-selection-publication.json", "source-selection-publication.json"),
        ("artefacts/parents.jnnw", "parents.jnnw"),
        ("artefacts/parents.tsv", "parents.tsv"),
        ("artefacts/ordered-identities.txt", "ordered-identities.txt"),
    ]
    parity_stage.fetch_completed(
        args.source_prefix, job=args.source_job, attempt=args.source_attempt,
        expected_code=args.source_code_sha, mappings=mappings,
        out_dir=target, report=work / "source-fetch.json",
    )
    publication_path = target / "source-selection-publication.json"
    try:
        publication = json.loads(publication_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageError("invalid source publication JSON") from exc
    fresh_teacher.verify_source_publication(publication, target)
    return target, publication, parity_stage.sha_file(publication_path)


def run_stage(args: argparse.Namespace) -> dict[str, object]:
    if args.work_dir.exists() or args.work_dir.is_symlink():
        raise StageError("work-dir must be absent")
    args.work_dir.mkdir(parents=True)
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    source_root, publication, publication_sha = fetch_source(args, args.work_dir)
    parents, source_identity_bytes = load_source(source_root)
    selected = select_subset(parents)
    outputs = publish_subset(selected, args.artifact_dir)
    source = {
        "job_id": args.source_job,
        "attempt_id": args.source_attempt,
        "code_sha": args.source_code_sha,
        "prefix": args.source_prefix,
        "publication_sha256": publication_sha,
        "parents_jnnw": publication["selection"]["parents_jnnw"],
        "ordered_identities": publication["selection"]["ordered_identities"],
        "ordered_identities_bytes_sha256": hashlib.sha256(source_identity_bytes).hexdigest(),
    }
    seal = {
        "schema": SCHEMA,
        "state": "completed",
        "verdict": VERDICT,
        "source": source,
        "audit": {
            "seed": AUDIT_SEED,
            "parents": AUDIT_PARENTS,
            "per_cell": AUDIT_PER_CELL,
            "selection": "sha256(seed_decimal:canonical_fingerprint), lowest per cell",
            "tie_break": ["canonical_fingerprint_ascii", "source_parent_id_uint"],
            "target_blind": True,
        },
        "outputs": outputs,
        "teacher_score_reads": 0,
        "teacher_label_reads": 0,
        "reference_audit_reads": 0,
        "fits": 0,
        "strength_games": 0,
        "promotions": 0,
        "bakes": 0,
        "next_stage": "B3_FRESH_FULL_LADDER_AUDIT",
    }
    write_new(args.artifact_dir / "b3-fresh-audit-subset-seal.json", canonical(seal))
    write_new(args.artifact_dir / "scientific-summary.json", canonical(seal))
    return seal


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--source-job", required=True)
    parser.add_argument("--source-attempt", required=True)
    parser.add_argument("--source-code-sha", required=True)
    parser.add_argument("--source-prefix", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        result = run_stage(parse_args(argv))
    except Exception as exc:
        print(f"adaptive_sibling_b3_fresh_audit_subset: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"state": result["state"], "verdict": result["verdict"],
                      "next_stage": result["next_stage"]},
                     sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
