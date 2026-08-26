#!/usr/bin/env python3
"""Target-blind MegaCorpus parent selection for Deep Search Sibling Distillation v1.

This tool consumes the frozen census metadata plus board/STM bytes from direct R2
JNNW payloads. Historical score/WDL labels are never read by the parent filter
and are zeroed before any row enters this selector.

Global exact + rotate180/colour-swap de-dup is performed in SQLite so large
corpora stay memory bounded. Source split is assigned before parent de-dup;
when a canonical parent occurs in both source partitions, holdout wins exactly
as preregistered. Sampling is by the frozen canonical-parent hash and phase
quota only; teacher scores do not exist at this stage.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
from typing import Any, Iterator

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.tb_frontier_catalog_mine import (  # noqa: E402
    JNNW_RECORD_SIZE,
    candidate_payload_key,
    load_catalog,
    materialize_raw_jnnw,
    select_direct_candidates,
    sha256_file,
)
from jobs.tools.tb_frontier_symmetry_dedup import canonical_fingerprint  # noqa: E402

FILTER_FIELDS = [
    "row_index", "source_row_index", "parent_fingerprint", "parent_stm", "pieces", "legal_moves"
]
PHASES = {
    "P0": (30, 40, 2000),
    "P1": (20, 29, 2000),
    "P2": (12, 19, 2000),
    "P3": (9, 11, 2000),
}


def phase_for(pieces: int) -> str:
    for name, (lo, hi, _) in PHASES.items():
        if lo <= pieces <= hi:
            return name
    raise ValueError(f"pieces outside preregistered phases: {pieces}")


def source_bucket(source_identity: str, seed: int = 2026083102) -> int:
    digest = hashlib.sha256(f"{seed}:{source_identity}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little") % 5


def sample_hash(canonical_fp: str, seed: int = 2026083101) -> str:
    return hashlib.sha256(f"{seed}:{canonical_fp}".encode("utf-8")).hexdigest()


def representative_key(*, bucket: int, path: str, candidate_id: str,
                       source_row_index: int, raw_fp: str) -> str:
    # Holdout occurrence must represent a cross-partition duplicate. Within a
    # partition, census path/id/row/fingerprint gives a deterministic choice.
    partition_rank = 0 if bucket == 0 else 1
    return f"{partition_rank}:{path}\0{candidate_id}\0{source_row_index:012d}\0{raw_fp}"


def iter_filtered(parents_path: Path, tsv_path: Path) -> Iterator[tuple[bytes, dict[str, str]]]:
    with parents_path.open("rb") as raw, tsv_path.open(newline="", encoding="utf-8") as meta:
        header = raw.read(8)
        if len(header) != 8 or header[:4] != b"JNNW":
            raise ValueError("filtered parents: bad JNNW header")
        count = struct.unpack_from("<I", header, 4)[0]
        reader = csv.DictReader(meta, delimiter="\t")
        if reader.fieldnames != FILTER_FIELDS:
            raise ValueError(f"filtered metadata fields drift: {reader.fieldnames!r}")
        rows = 0
        for row in reader:
            rec = raw.read(JNNW_RECORD_SIZE)
            if len(rec) != JNNW_RECORD_SIZE:
                raise ValueError("filtered parents: truncated record stream")
            if int(row["row_index"]) != rows:
                raise ValueError("filtered metadata row_index drift")
            # Defense-in-depth: target bytes produced by the filter must be zero.
            if rec[33:38] != b"\0\0\0\0\0":
                raise ValueError("filtered parent retained nonzero historical target bytes")
            rows += 1
            yield rec, row
        if rows != count:
            raise ValueError(f"filtered count mismatch metadata={rows} header={count}")
        if raw.read(1):
            raise ValueError("filtered parents: trailing bytes")


def init_db(db: sqlite3.Connection) -> None:
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("""
        CREATE TABLE parents(
          canonical TEXT PRIMARY KEY,
          phase TEXT NOT NULL,
          hash_key TEXT NOT NULL,
          has_holdout INTEGER NOT NULL,
          occurrence_count INTEGER NOT NULL,
          cross_partition INTEGER NOT NULL,
          rep_key TEXT NOT NULL,
          record BLOB NOT NULL,
          raw_fp TEXT NOT NULL,
          stm INTEGER NOT NULL,
          pieces INTEGER NOT NULL,
          legal_moves INTEGER NOT NULL,
          source_identity TEXT NOT NULL,
          source_bucket INTEGER NOT NULL,
          candidate_id TEXT NOT NULL,
          source_path TEXT NOT NULL,
          source_row_index INTEGER NOT NULL
        )
    """)
    db.execute("CREATE INDEX parents_phase_hash ON parents(phase, hash_key, canonical)")


def merge_occurrence(db: sqlite3.Connection, *, canonical: str, phase: str, hash_key: str,
                     rec: bytes, raw_fp: str, stm: int, pieces: int, legal_moves: int,
                     source_identity: str, bucket: int, candidate_id: str,
                     source_path: str, source_row_index: int) -> tuple[bool, bool]:
    rep_key = representative_key(bucket=bucket, path=source_path, candidate_id=candidate_id,
                                 source_row_index=source_row_index, raw_fp=raw_fp)
    old = db.execute(
        "SELECT has_holdout, occurrence_count, cross_partition, rep_key, source_bucket FROM parents WHERE canonical=?",
        (canonical,),
    ).fetchone()
    if old is None:
        db.execute("""
          INSERT INTO parents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (canonical, phase, hash_key, int(bucket == 0), 1, 0, rep_key, rec, raw_fp, stm,
              pieces, legal_moves, source_identity, bucket, candidate_id, source_path, source_row_index))
        return True, False

    old_holdout, occ, cross, old_key, old_bucket = old
    if phase != db.execute("SELECT phase FROM parents WHERE canonical=?", (canonical,)).fetchone()[0]:
        raise ValueError("canonical duplicate changed material phase")
    new_holdout = bool(old_holdout) or bucket == 0
    new_cross = bool(cross) or ((old_bucket == 0) != (bucket == 0))
    replace = rep_key < old_key
    if replace:
        db.execute("""
          UPDATE parents SET has_holdout=?, occurrence_count=?, cross_partition=?, rep_key=?, record=?,
            raw_fp=?, stm=?, pieces=?, legal_moves=?, source_identity=?, source_bucket=?, candidate_id=?,
            source_path=?, source_row_index=? WHERE canonical=?
        """, (int(new_holdout), occ + 1, int(new_cross), rep_key, rec, raw_fp, stm, pieces,
              legal_moves, source_identity, bucket, candidate_id, source_path, source_row_index, canonical))
    else:
        db.execute("UPDATE parents SET has_holdout=?, occurrence_count=?, cross_partition=? WHERE canonical=?",
                   (int(new_holdout), occ + 1, int(new_cross), canonical))
    return False, new_cross and not bool(cross)


def json_dump(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    catalog_rows = load_catalog(args.catalog)
    candidates, selection_counts = select_direct_candidates(catalog_rows)
    if not candidates:
        raise ValueError("frozen catalog has no selected direct R2 JNNW payloads")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.output_jnnw.parent.mkdir(parents=True, exist_ok=True)
    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    args.source_report.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        args.db.unlink()
    db = sqlite3.connect(args.db)
    init_db(db)

    valid_sources = 0
    unsupported_sources = 0
    source_rows = 0
    filter_selected_occurrences = 0
    unique_insertions = 0
    cross_partition_parents = 0

    with args.source_report.open("w", encoding="utf-8") as sr:
        for ordinal, candidate in enumerate(candidates, 1):
            data = candidate.get("data") or {}
            uri = str(data.get("r2_uri") or "")
            path = str(data.get("path") or "")
            cid = str(candidate.get("candidate_id") or f"candidate-{ordinal}")
            identity = candidate_payload_key(candidate)
            bucket = source_bucket(identity, args.split_seed)
            stem = f"src-{ordinal:04d}"
            download = args.work_dir / (stem + (".jnnw.gz" if path.lower().endswith(".gz") else ".jnnw"))
            raw = args.work_dir / f"{stem}.raw.jnnw"
            parents = args.work_dir / f"{stem}.parents.jnnw"
            meta = args.work_dir / f"{stem}.parents.tsv"
            freport = args.work_dir / f"{stem}.filter.json"
            item: dict[str, Any] = {
                "ordinal": ordinal, "candidate_id": cid, "r2_uri": uri, "path": path,
                "source_identity": identity, "source_bucket": bucket,
                "partition": "holdout" if bucket == 0 else "train",
            }
            try:
                cp = subprocess.run([args.rclone_binary, "copyto", uri, str(download)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                    timeout=args.copy_timeout_seconds)
                if cp.returncode != 0:
                    raise RuntimeError(f"R2 retrieval failed for frozen census object {uri}: {cp.stderr[-1000:]}")
                declared = data.get("declared_sha256")
                if args.verify_declared_sha and isinstance(declared, str) and len(declared) == 64:
                    item["download_sha256"] = sha256_file(download)
                    item["declared_sha_matches_download"] = item["download_sha256"] == declared
                try:
                    nrecords, raw_bytes = materialize_raw_jnnw(download, raw, path)
                except (OSError, ValueError, gzip.BadGzipFile) as exc:
                    unsupported_sources += 1
                    item.update(status="unsupported_payload", error=str(exc))
                    sr.write(json.dumps(item, sort_keys=True) + "\n"); sr.flush()
                    continue
                source_rows += nrecords
                item["records"] = nrecords; item["raw_bytes"] = raw_bytes
                proc = subprocess.run([
                    str(args.parent_filter), str(raw), str(parents), str(meta), str(freport),
                    "9", "40", "2", "16",
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if proc.returncode != 0:
                    raise RuntimeError(f"parent filter failed rc={proc.returncode}: {proc.stderr[-1000:]}")
                fsum = json.loads(freport.read_text(encoding="utf-8"))
                if fsum.get("labels_used_from_sources") is not False or fsum.get("source_score_bytes_read") is not False or fsum.get("source_wdl_bytes_read") is not False:
                    raise ValueError("parent filter label-blind receipt failed")
                item["filter"] = fsum
                added_here = 0
                occurrences_here = 0
                for rec, row in iter_filtered(parents, meta):
                    raw_fp = row["parent_fingerprint"]
                    canonical = canonical_fingerprint(raw_fp)
                    pieces = int(row["pieces"]); stm = int(row["parent_stm"])
                    legal_moves = int(row["legal_moves"]); src_row = int(row["source_row_index"])
                    phase = phase_for(pieces)
                    inserted, new_cross = merge_occurrence(
                        db, canonical=canonical, phase=phase, hash_key=sample_hash(canonical, args.sample_seed),
                        rec=rec, raw_fp=raw_fp, stm=stm, pieces=pieces, legal_moves=legal_moves,
                        source_identity=identity, bucket=bucket, candidate_id=cid, source_path=path,
                        source_row_index=src_row,
                    )
                    added_here += int(inserted); cross_partition_parents += int(new_cross)
                    occurrences_here += 1
                db.commit()
                valid_sources += 1
                filter_selected_occurrences += occurrences_here
                unique_insertions += added_here
                item.update(status="ok", eligible_occurrences=occurrences_here, unique_canonical_added=added_here)
            finally:
                for p in (download, raw, parents, meta, freport):
                    try: p.unlink()
                    except FileNotFoundError: pass
            sr.write(json.dumps(item, sort_keys=True) + "\n"); sr.flush()
            if args.progress:
                total_unique = db.execute("SELECT COUNT(*) FROM parents").fetchone()[0]
                json_dump(args.progress, {
                    "processed_sources": ordinal, "selected_sources": len(candidates),
                    "valid_sources": valid_sources, "unsupported_sources": unsupported_sources,
                    "source_rows_scanned": source_rows, "eligible_occurrences": filter_selected_occurrences,
                    "unique_canonical_parents": total_unique,
                })

    phase_available = {p: db.execute("SELECT COUNT(*) FROM parents WHERE phase=?", (p,)).fetchone()[0] for p in PHASES}
    selected_rows: list[sqlite3.Row] = []
    db.row_factory = sqlite3.Row
    for phase, (_, _, quota) in PHASES.items():
        selected_rows.extend(db.execute(
            "SELECT * FROM parents WHERE phase=? ORDER BY hash_key, canonical LIMIT ?", (phase, quota)
        ).fetchall())
    exact_8000 = len(selected_rows) == sum(v[2] for v in PHASES.values()) and all(
        phase_available[p] >= PHASES[p][2] for p in PHASES
    )

    with args.output_jnnw.open("wb+") as out, args.output_tsv.open("w", newline="", encoding="utf-8") as meta:
        out.write(b"JNNW" + struct.pack("<I", 0))
        fields = ["parent_id","canonical_fingerprint","raw_fingerprint","parent_stm","pieces","legal_moves",
                  "phase","partition","source_identity","source_bucket","candidate_id","source_path",
                  "source_row_index","sample_hash"]
        writer = csv.DictWriter(meta, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for pid, row in enumerate(selected_rows):
            out.write(row["record"])
            writer.writerow({
                "parent_id": pid, "canonical_fingerprint": row["canonical"], "raw_fingerprint": row["raw_fp"],
                "parent_stm": row["stm"], "pieces": row["pieces"], "legal_moves": row["legal_moves"],
                "phase": row["phase"], "partition": "holdout" if row["has_holdout"] else "train",
                "source_identity": row["source_identity"], "source_bucket": row["source_bucket"],
                "candidate_id": row["candidate_id"], "source_path": row["source_path"],
                "source_row_index": row["source_row_index"], "sample_hash": row["hash_key"],
            })
        out.seek(4); out.write(struct.pack("<I", len(selected_rows)))

    phase_selected = {p: sum(r["phase"] == p for r in selected_rows) for p in PHASES}
    holdout = [r for r in selected_rows if r["has_holdout"]]
    train = [r for r in selected_rows if not r["has_holdout"]]
    holdout_phase = {p: sum(r["phase"] == p for r in holdout) for p in PHASES}
    holdout_color = {"white": sum(r["stm"] == 0 for r in holdout), "black": sum(r["stm"] == 1 for r in holdout)}
    train_color = {"white": sum(r["stm"] == 0 for r in train), "black": sum(r["stm"] == 1 for r in train)}
    gross_support = (
        exact_8000 and len(selected_rows) >= 6000 and len(holdout) >= 1000
        and all(holdout_phase[p] >= 200 for p in PHASES)
        and holdout_color["white"] >= 300 and holdout_color["black"] >= 300
    )
    total_unique = db.execute("SELECT COUNT(*) FROM parents").fetchone()[0]
    symmetry_or_exact_duplicates = filter_selected_occurrences - total_unique
    report = {
        "schema": "jass.deep_sibling.catalog_selection.v1",
        "catalog_sha256": sha256_file(args.catalog),
        "catalog_selection": selection_counts,
        "direct_candidates_effective": len(candidates),
        "valid_sources": valid_sources,
        "unsupported_sources": unsupported_sources,
        "source_rows_scanned": source_rows,
        "eligible_occurrences": filter_selected_occurrences,
        "unique_canonical_parents": total_unique,
        "exact_or_symmetry_duplicates_removed": symmetry_or_exact_duplicates,
        "cross_partition_duplicate_parents": cross_partition_parents,
        "source_split": {"seed": args.split_seed, "rule": "u64le(sha256(seed:source_payload_identity)[0:8])%5", "holdout_bucket": 0},
        "source_payload_identity": "sha256:<declared_sha256> else uri:<r2_uri>",
        "sampling": {"seed": args.sample_seed, "rule": "sha256(seed:canonical_parent_fingerprint)",
                     "phase_available": phase_available, "phase_selected": phase_selected,
                     "selected_parents": len(selected_rows), "exact_8000": exact_8000},
        "selected_partition": {"train": len(train), "holdout": len(holdout),
                               "holdout_by_phase": holdout_phase, "holdout_by_color": holdout_color,
                               "train_by_color": train_color},
        "gross_support_before_teacher": gross_support,
        "gross_support_note": "stable-pair-per-parent support is evaluated only after frozen 50k/200k teacher labels",
        "labels_used_from_sources": False,
        "teacher_scores_read": False,
        "pattern_eval_fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    json_dump(args.report, report)
    db.close()
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--parent-filter", type=Path, required=True)
    ap.add_argument("--work-dir", type=Path, required=True)
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output-jnnw", type=Path, required=True)
    ap.add_argument("--output-tsv", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--source-report", type=Path, required=True)
    ap.add_argument("--progress", type=Path)
    ap.add_argument("--sample-seed", type=int, default=2026083101)
    ap.add_argument("--split-seed", type=int, default=2026083102)
    ap.add_argument("--rclone-binary", default=os.environ.get("RCLONE_BINARY", "rclone"))
    ap.add_argument("--copy-timeout-seconds", type=int, default=3600)
    ap.add_argument("--verify-declared-sha", action="store_true")
    args = ap.parse_args()
    try:
        result = run(args)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"deep_sibling_catalog_select: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
