#!/usr/bin/env python3
"""Diagnostic-only root profiler for pinned Scan 3.1 in CLS-D."""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

if __package__ in (None, ""):
    import sys
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.calibrate_vs_scan import parse_scan_move  # noqa: E402
from jobs.tools.scan_ceiling_scan_score import (  # noqa: E402
    ALLOWED_BUDGETS,
    NodeScanEngine,
    read_children,
    record_fingerprint,
    record_to_scan_pos,
    sha256,
)

SCHEMA = "jass.cls_depth_growth_scan.v1"
SCAN_COMMIT = "7aae17e7b7bfc47744601afb1ee7655e18983ce5"
FROZEN_BUDGETS = (5_000, 50_000, 200_000)


def canonical_move(text: str) -> str:
    move = parse_scan_move(text)
    base = f"{move.frm}{'x' if move.captures else '-'}{move.to}"
    if not move.captures:
        return base
    return base + "|caps=" + ",".join(str(value) for value in sorted(move.captures))


def read_metadata(path: Path, count: int) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"parent_id", "canonical_fingerprint", "raw_fingerprint", "parent_stm",
                    "pieces", "legal_moves", "phase"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("parents.tsv fields drift")
        rows = list(reader)
    if len(rows) != count or [int(row["parent_id"]) for row in rows] != list(range(count)):
        raise ValueError("parents.tsv/JNNW cardinality drift")
    return rows


def read_ids(path: Path, count: int) -> list[int]:
    values = [int(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not values or len(values) != len(set(values)) or min(values) < 0 or max(values) >= count:
        raise ValueError("invalid root id file")
    return values


def parse_budgets(text: str) -> list[int]:
    values = [int(value) for value in text.split(",") if value]
    if not values or len(values) != len(set(values)) or any(value not in FROZEN_BUDGETS for value in values):
        raise ValueError("budget outside frozen CLS-D ladder")
    if any(value not in ALLOWED_BUDGETS for value in values):
        raise ValueError("budget unsupported by pinned Scan scorer")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--parents", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--root-ids", type=Path, required=True)
    parser.add_argument("--budgets", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-commit", default=SCAN_COMMIT)
    args = parser.parse_args()
    if args.source_commit != SCAN_COMMIT:
        raise ValueError("Scan source commit drift")

    records = read_children(args.parents)
    metadata = read_metadata(args.metadata, len(records))
    root_ids = read_ids(args.root_ids, len(records))
    budgets = parse_budgets(args.budgets)
    for idx, (record, meta) in enumerate(zip(records, metadata)):
        if record_fingerprint(record) != meta["raw_fingerprint"]:
            raise ValueError(f"root fingerprint drift at {idx}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    searches = 0
    nodes_sum = 0
    elapsed_sum = 0.0
    engine = NodeScanEngine(str(args.scan), label="CLS-D-Scan")
    try:
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            fields = [
                "root_id", "phase", "stm", "pieces", "branching", "forced_capture_at_root",
                "max_capture_len", "budget_kind", "budget", "nodes_requested", "nodes_observed",
                "node_semantics", "engine", "completed_nominal_depth", "seldepth", "wall_ms", "nps",
                "bestmove_canonical", "score_cp", "terminal_flag", "qnodes", "eval_calls", "tt_hit_rate",
                "cutoffs", "first_move_cutoffs", "pvs_researches", "moves_searched",
            ]
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            for root_id in root_ids:
                record = records[root_id]
                meta = metadata[root_id]
                scan_pos = record_to_scan_pos(record)
                for budget in budgets:
                    obs = engine.search_nodes(scan_pos, budget, args.timeout_seconds)
                    nodes = int(obs["last_info_nodes"])
                    elapsed = float(obs["elapsed_seconds"])
                    searches += 1
                    nodes_sum += nodes
                    elapsed_sum += elapsed
                    writer.writerow({
                        "root_id": root_id,
                        "phase": meta["phase"],
                        "stm": meta["parent_stm"],
                        "pieces": meta["pieces"],
                        "branching": meta["legal_moves"],
                        # The frozen selector does not store capture morphology; these are populated
                        # by the Jass PARITY row in the merged preregistered per_root.tsv.
                        "forced_capture_at_root": "NA",
                        "max_capture_len": "NA",
                        "budget_kind": "nodes",
                        "budget": budget,
                        "nodes_requested": budget,
                        "nodes_observed": nodes,
                        "node_semantics": "exact requested N; last complete info is a progressive snapshot bounded by the next 16-node poll, not total consumed",
                        "engine": "SCAN",
                        "completed_nominal_depth": int(obs["depth"]),
                        "seldepth": "NA",
                        "wall_ms": format(elapsed * 1000.0, ".6f"),
                        "nps": format(nodes / elapsed if elapsed > 0 else 0.0, ".6f"),
                        "bestmove_canonical": canonical_move(str(obs["done_move"])),
                        "score_cp": int(obs["child_score_centi"]),
                        "terminal_flag": 0,
                        "qnodes": "NA", "eval_calls": "NA", "tt_hit_rate": "NA",
                        "cutoffs": "NA", "first_move_cutoffs": "NA",
                        "pvs_researches": "NA", "moves_searched": "NA",
                    })
    finally:
        engine.close()

    if searches != len(root_ids) * len(budgets):
        raise AssertionError("Scan CLS-D search cardinality drift")
    payload = {
        "schema": SCHEMA,
        "diagnostic_only": True,
        "source_commit": SCAN_COMMIT,
        "scan_binary_sha256": sha256(args.scan),
        "roots": len(root_ids),
        "searches": searches,
        "budgets_nodes": budgets,
        "nodes_observed_sum": nodes_sum,
        "elapsed_seconds": elapsed_sum,
        "threads": 1,
        "book_enabled": False,
        "bb_size": 0,
        "tt_size": 24,
        "fresh_state": "new-game before every root/budget",
        "cross_engine_depth_curve_available": False,
        "parents_sha256": sha256(args.parents),
        "root_ids_sha256": hashlib.sha256(args.root_ids.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "fits": 0,
        "strength_games": 0,
        "promotion_authorized": False,
    }
    args.report.write_text(__import__("json").dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
