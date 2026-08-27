#!/usr/bin/env python3
"""Preregistered M3 target-blind MegaCorpus selector.

This is a thin scientific wrapper around the already-audited DSSD direct-R2
MegaCorpus selector.  It changes only the frozen M3 quantities from
L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.md:

* exactly 25,000 parents in each P0/P1/P2/P3 phase (100,000 total),
* sampling hash seed supplied by the control job as 2026090210,
* exclusion of all earlier labelled/M1/M2 parent canonical identities,
* exclusion of established force-pool exact board+STM identities.

Historical source score/WDL bytes remain unread: the base selector consumes only
the zero-target output of deep_sibling_parent_filter.  No teacher score exists
at this stage.
"""
from __future__ import annotations

import atexit
import csv
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable

from jobs.tools import deep_sibling_catalog_select as base

M3_PHASES = {
    "P0": (30, 40, 25_000),
    "P1": (20, 29, 25_000),
    "P2": (12, 19, 25_000),
    "P3": (9, 11, 25_000),
}


def _fpkey(fp: str) -> tuple[int, int, int, int, int]:
    wm, wk, bm, bk, stm = fp.strip().split(":")
    return (int(stm), int(wm, 16), int(wk, 16), int(bm, 16), int(bk, 16))


def _parse_side(spec: str) -> tuple[int, int]:
    men = kings = 0
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        king = token.startswith("K")
        square = int(token[1:] if king else token)
        if not 1 <= square <= 50:
            raise ValueError(f"force FEN square outside 1..50: {square}")
        bit = 1 << (square - 1)
        if king:
            kings |= bit
        else:
            men |= bit
    return men, kings


def _force_key(line: str) -> tuple[int, int, int, int, int]:
    clean = line.split("#", 1)[0].strip()
    parts = clean.split(":")
    if len(parts) != 3 or parts[0] not in ("W", "B"):
        raise ValueError(f"unsupported force FEN row: {line!r}")
    wm, wk = _parse_side(parts[1][1:])
    bm, bk = _parse_side(parts[2][1:])
    return (0 if parts[0] == "W" else 1, wm, wk, bm, bk)


def _iter_paths(spec: str | None) -> Iterable[Path]:
    if not spec:
        return []
    return [Path(p) for p in spec.split(os.pathsep) if p]


def load_exclusions() -> tuple[set[str], set[tuple[int, int, int, int, int]], dict]:
    canonical: set[str] = set()
    canonical_rows: dict[str, int] = {}
    for path in _iter_paths(os.environ.get("JASS_M3_EXCLUDE_CANON_TSVS")):
        rows = 0
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames is None or "canonical_fingerprint" not in reader.fieldnames:
                raise ValueError(f"{path}: missing canonical_fingerprint column")
            for row in reader:
                fp = row["canonical_fingerprint"].strip()
                if not fp:
                    raise ValueError(f"{path}: empty canonical_fingerprint")
                canonical.add(fp)
                rows += 1
        canonical_rows[str(path)] = rows

    exact: set[tuple[int, int, int, int, int]] = set()
    force_rows: dict[str, int] = {}
    force_dir_raw = os.environ.get("JASS_M3_FORCE_FEN_DIR")
    if force_dir_raw:
        force_dir = Path(force_dir_raw)
        for path in sorted(force_dir.glob("*.fen")):
            rows = 0
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.split("#", 1)[0].strip():
                    continue
                exact.add(_force_key(line))
                rows += 1
            force_rows[path.stem] = rows

    evidence = {
        "canonical_input_rows": canonical_rows,
        "canonical_unique": len(canonical),
        "force_input_rows": force_rows,
        "force_exact_unique": len(exact),
    }
    return canonical, exact, evidence


BLOCK_CANON, BLOCK_EXACT, EVIDENCE = load_exclusions()
STATS = {
    "excluded_prior_canonical_occurrences": 0,
    "excluded_force_exact_occurrences": 0,
    "accepted_occurrences_to_base_selector": 0,
}


def merge_occurrence(
    db: sqlite3.Connection,
    *,
    canonical: str,
    phase: str,
    hash_key: str,
    rec: bytes,
    raw_fp: str,
    stm: int,
    pieces: int,
    legal_moves: int,
    source_identity: str,
    bucket: int,
    candidate_id: str,
    source_path: str,
    source_row_index: int,
) -> tuple[bool, bool]:
    """Filter preregistered exclusions before the base canonical DB insert."""
    if canonical in BLOCK_CANON:
        STATS["excluded_prior_canonical_occurrences"] += 1
        return False, False
    if _fpkey(raw_fp) in BLOCK_EXACT:
        STATS["excluded_force_exact_occurrences"] += 1
        return False, False
    STATS["accepted_occurrences_to_base_selector"] += 1

    # Exact technical repair already used by deep_sibling_catalog_select_runner:
    # the frozen schema has 17 columns, not 18.
    rep_key = base.representative_key(
        bucket=bucket,
        path=source_path,
        candidate_id=candidate_id,
        source_row_index=source_row_index,
        raw_fp=raw_fp,
    )
    old = db.execute(
        "SELECT has_holdout, occurrence_count, cross_partition, rep_key, "
        "source_bucket, phase FROM parents WHERE canonical=?",
        (canonical,),
    ).fetchone()
    if old is None:
        db.execute(
            "INSERT INTO parents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                canonical,
                phase,
                hash_key,
                int(bucket == 0),
                1,
                0,
                rep_key,
                rec,
                raw_fp,
                stm,
                pieces,
                legal_moves,
                source_identity,
                bucket,
                candidate_id,
                source_path,
                source_row_index,
            ),
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
            "UPDATE parents SET has_holdout=?, occurrence_count=?, cross_partition=?, "
            "rep_key=?, record=?, raw_fp=?, stm=?, pieces=?, legal_moves=?, "
            "source_identity=?, source_bucket=?, candidate_id=?, source_path=?, "
            "source_row_index=? WHERE canonical=?",
            (
                int(new_holdout),
                occ + 1,
                int(new_cross),
                rep_key,
                rec,
                raw_fp,
                stm,
                pieces,
                legal_moves,
                source_identity,
                bucket,
                candidate_id,
                source_path,
                source_row_index,
                canonical,
            ),
        )
    else:
        db.execute(
            "UPDATE parents SET has_holdout=?, occurrence_count=?, cross_partition=? "
            "WHERE canonical=?",
            (int(new_holdout), occ + 1, int(new_cross), canonical),
        )
    return False, new_cross and not bool(cross)


def _write_exclusion_report() -> None:
    target = os.environ.get("JASS_M3_EXCLUSION_REPORT")
    if not target:
        return
    payload = {
        "schema": "jass.micro_search_m3_exclusions.v1",
        "selection_seed": 2026090210,
        "phase_quotas": {name: quota for name, (_lo, _hi, quota) in M3_PHASES.items()},
        **EVIDENCE,
        **STATS,
        "source_labels_read": False,
        "teacher_scores_read": 0,
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    Path(target).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


base.PHASES = dict(M3_PHASES)
base.merge_occurrence = merge_occurrence
atexit.register(_write_exclusion_report)

if __name__ == "__main__":
    raise SystemExit(base.main())
