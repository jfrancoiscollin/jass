#!/usr/bin/env python3
"""Select the frozen 512-parent Scan Gate-0 subset without reading scores."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

PREFIX = "SCAN-GATE0-2026090701:"
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


def select(meta: dict[int, tuple[str, str]]) -> list[int]:
    selected: list[int] = []
    for phase in PHASES:
        rows = [(hashlib.sha256((PREFIX + fp).encode()).hexdigest(), pid)
                for pid, (fp, p) in meta.items() if p == phase]
        rows.sort()
        if len(rows) != 500:
            raise ValueError(f"{phase} support drift")
        selected.extend(pid for _, pid in rows[:PER_PHASE])
    if len(selected) != TOTAL or len(set(selected)) != TOTAL:
        raise ValueError("Gate-0 selection cardinality drift")
    return sorted(selected)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--out-ids", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    meta = load_parent_meta(args.groups)
    ids = select(meta)
    args.out_ids.parent.mkdir(parents=True, exist_ok=True)
    args.out_ids.write_text("".join(f"{pid}\n" for pid in ids), encoding="utf-8")
    by_phase = {phase: sum(meta[pid][1] == phase for pid in ids) for phase in PHASES}
    payload = {
        "schema": "jass.scan_oracle_gate0_selection.v1",
        "benchmark_only": True,
        "selector_prefix": PREFIX,
        "source_parents": len(meta),
        "selected_parents": len(ids),
        "phase_counts": by_phase,
        "score_reads": 0,
        "outcome_reads": 0,
        "fits": 0,
        "strength_games": 0,
        "selected_ids_sha256": hashlib.sha256(args.out_ids.read_bytes()).hexdigest(),
    }
    if by_phase != {phase: PER_PHASE for phase in PHASES}:
        raise ValueError("selected phase quota drift")
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
