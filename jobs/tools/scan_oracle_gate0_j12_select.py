#!/usr/bin/env python3
"""Select a fresh phase-balanced J12 Gate0 cohort disjoint from the original Gate0."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

PREFIX = "SCAN-J12-FRESH-2026090801:"
PHASES = ("P0", "P1", "P2", "P3")
PER_PHASE = 128
TOTAL = 512


def load_parent_meta(path: Path) -> dict[int, tuple[str, str]]:
    out: dict[int, tuple[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"parent_id", "parent_fingerprint", "parent_phase"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("sibling metadata fields drift")
        for row in reader:
            pid = int(row["parent_id"])
            value = (row["parent_fingerprint"], row["parent_phase"])
            old = out.get(pid)
            if old is not None and old != value:
                raise ValueError(f"parent metadata drift for {pid}")
            out[pid] = value
    if sorted(out) != list(range(2000)):
        raise ValueError("frozen Scan cohort parent ids are not exactly 0..1999")
    counts = {phase: sum(v[1] == phase for v in out.values()) for phase in PHASES}
    if counts != {phase: 500 for phase in PHASES}:
        raise ValueError(f"frozen phase quota drift: {counts}")
    return out


def load_excluded(path: Path, meta: dict[int, tuple[str, str]]) -> set[int]:
    ids = [int(x) for x in path.read_text(encoding="utf-8").split()]
    if len(ids) != 512 or len(set(ids)) != 512:
        raise ValueError("prior Gate0 exclusion cardinality drift")
    excluded = set(ids)
    if any(pid not in meta for pid in excluded):
        raise ValueError("prior Gate0 exclusion outside source cohort")
    phase_counts = {phase: sum(meta[pid][1] == phase for pid in excluded) for phase in PHASES}
    if phase_counts != {phase: 128 for phase in PHASES}:
        raise ValueError(f"prior Gate0 exclusion phase drift: {phase_counts}")
    return excluded


def select(meta: dict[int, tuple[str, str]], excluded: set[int]) -> list[int]:
    chosen: list[int] = []
    for phase in PHASES:
        rows = [
            (hashlib.sha256((PREFIX + fp).encode("utf-8")).digest(), pid)
            for pid, (fp, p) in meta.items()
            if p == phase and pid not in excluded
        ]
        rows.sort()
        if len(rows) != 372:
            raise ValueError(f"residual {phase} support drift: {len(rows)}")
        chosen.extend(pid for _, pid in rows[:PER_PHASE])
    if len(chosen) != TOTAL or len(set(chosen)) != TOTAL:
        raise ValueError("J12 fresh cohort cardinality drift")
    if set(chosen) & excluded:
        raise ValueError("J12 fresh cohort overlaps prior Gate0")
    return sorted(chosen)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--exclude-ids", type=Path, required=True)
    ap.add_argument("--out-ids", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    meta = load_parent_meta(args.groups)
    excluded = load_excluded(args.exclude_ids, meta)
    ids = select(meta, excluded)
    args.out_ids.parent.mkdir(parents=True, exist_ok=True)
    args.out_ids.write_text("".join(f"{pid}\n" for pid in ids), encoding="utf-8")
    phase_counts = {phase: sum(meta[pid][1] == phase for pid in ids) for phase in PHASES}
    if phase_counts != {phase: PER_PHASE for phase in PHASES}:
        raise ValueError("J12 selected phase quota drift")
    payload = {
        "schema": "jass.scan_oracle_gate0_j12_selection.v1",
        "benchmark_only": True,
        "selector_prefix": PREFIX,
        "source_parents": len(meta),
        "excluded_parents": len(excluded),
        "selected_parents": len(ids),
        "phase_counts": phase_counts,
        "overlap_with_prior_gate0": len(set(ids) & excluded),
        "score_reads": 0,
        "outcome_reads": 0,
        "fits": 0,
        "strength_games": 0,
        "excluded_ids_sha256": hashlib.sha256(args.exclude_ids.read_bytes()).hexdigest(),
        "selected_ids_sha256": hashlib.sha256(args.out_ids.read_bytes()).hexdigest(),
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
