#!/usr/bin/env python3
"""Technical launcher for the frozen DSSD selector.

The underlying selector was added in the same implementation PR. This wrapper
repairs only its SQLite INSERT arity (17 schema columns); it does not alter any
scientific selection, split, source, quota, seed, symmetry, or filtering rule.
"""
from __future__ import annotations

import sqlite3
from jobs.tools import deep_sibling_catalog_select as base


def merge_occurrence(db: sqlite3.Connection, *, canonical: str, phase: str, hash_key: str,
                     rec: bytes, raw_fp: str, stm: int, pieces: int, legal_moves: int,
                     source_identity: str, bucket: int, candidate_id: str,
                     source_path: str, source_row_index: int) -> tuple[bool, bool]:
    rep_key = base.representative_key(
        bucket=bucket, path=source_path, candidate_id=candidate_id,
        source_row_index=source_row_index, raw_fp=raw_fp,
    )
    old = db.execute(
        "SELECT has_holdout, occurrence_count, cross_partition, rep_key, source_bucket, phase "
        "FROM parents WHERE canonical=?", (canonical,)
    ).fetchone()
    if old is None:
        db.execute(
            "INSERT INTO parents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (canonical, phase, hash_key, int(bucket == 0), 1, 0, rep_key, rec, raw_fp, stm,
             pieces, legal_moves, source_identity, bucket, candidate_id, source_path, source_row_index),
        )
        return True, False

    old_holdout, occ, cross, old_key, old_bucket, old_phase = old
    if phase != old_phase:
        raise ValueError("canonical duplicate changed material phase")
    new_holdout = bool(old_holdout) or bucket == 0
    new_cross = bool(cross) or ((old_bucket == 0) != (bucket == 0))
    replace = rep_key < old_key
    if replace:
        db.execute(
            "UPDATE parents SET has_holdout=?, occurrence_count=?, cross_partition=?, rep_key=?, record=?, "
            "raw_fp=?, stm=?, pieces=?, legal_moves=?, source_identity=?, source_bucket=?, candidate_id=?, "
            "source_path=?, source_row_index=? WHERE canonical=?",
            (int(new_holdout), occ + 1, int(new_cross), rep_key, rec, raw_fp, stm, pieces,
             legal_moves, source_identity, bucket, candidate_id, source_path, source_row_index, canonical),
        )
    else:
        db.execute(
            "UPDATE parents SET has_holdout=?, occurrence_count=?, cross_partition=? WHERE canonical=?",
            (int(new_holdout), occ + 1, int(new_cross), canonical),
        )
    return False, new_cross and not bool(cross)


base.merge_occurrence = merge_occurrence

if __name__ == "__main__":
    raise SystemExit(base.main())
