#!/usr/bin/env python3
"""Build a material-stratified difficulty reference for L3-IMBALANCE2.

The two low-material start strata (1v3 and 2v4, respectively 4 and 6 total
pieces) are labelled by the exact EGDB outside this tool.  Higher-material
strata (3v5 through 18v20) use Scan self-play on the same fixed pools as an
empirical reference.  Scan is never described as exact and this report is not
an input to training.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct

MAGIC = b"JNNW"
REC_SIZE = 38
CATS = ("win", "draw", "loss")
COST = {"win": 0.0, "draw": 1.0, "loss": 2.0}


def read_jnnw(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: invalid JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != count * REC_SIZE:
        raise ValueError(f"{path}: size/count mismatch")
    return [body[i * REC_SIZE:(i + 1) * REC_SIZE] for i in range(count)]


def write_jnnw(path: Path, records: list[bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(MAGIC + struct.pack("<I", len(records)) + b"".join(records))


def total_pieces(item: dict[str, object]) -> int:
    return int(item["white_men"]) + int(item["black_men"])


def extract(args: argparse.Namespace) -> int:
    records = read_jnnw(Path(args.pool))
    metadata = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    if len(records) != len(metadata):
        raise ValueError("pool and metadata length mismatch")

    selected_records: list[bytes] = []
    selected_meta: list[dict[str, object]] = []
    source_pool = Path(args.pool).name
    for index, (record, raw_item) in enumerate(zip(records, metadata, strict=True)):
        item = dict(raw_item)
        pieces = total_pieces(item)
        keep = pieces <= args.exact_max_pieces if args.mode == "exact" else pieces > args.exact_max_pieces
        if not keep:
            continue
        item["source_index"] = index
        item["source_pool"] = source_pool
        item["total_pieces"] = pieces
        selected_records.append(record)
        selected_meta.append(item)

    if not selected_records:
        raise ValueError(f"{args.mode}: empty extracted pool")
    if args.mode == "exact" and any(total_pieces(item) > args.exact_max_pieces for item in selected_meta):
        raise ValueError("exact extraction contains an out-of-domain position")
    if args.mode == "high" and any(total_pieces(item) <= args.exact_max_pieces for item in selected_meta):
        raise ValueError("high extraction contains an exact-TB position")

    write_jnnw(Path(args.out_data), selected_records)
    Path(args.out_meta).write_text(json.dumps(selected_meta, indent=2) + "\n", encoding="utf-8")
    report = {
        "schema": 1,
        "mode": args.mode,
        "source_pool": source_pool,
        "records": len(selected_records),
        "exact_max_total_pieces": args.exact_max_pieces,
        "strata": sorted({str(item["stratum"]) for item in selected_meta}, key=lambda value: int(value.split("v", 1)[0])),
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


def up_outcome_from_tb(record: bytes, item: dict[str, object]) -> str:
    stm = record[32]
    wdl = struct.unpack_from("<b", record, 37)[0]
    if stm not in (0, 1) or wdl not in (-1, 0, 1):
        raise ValueError("invalid exact-TB STM/WDL record")
    up = str(item["advantaged_side"])
    if up not in ("W", "B"):
        raise ValueError("invalid advantaged side")
    up_is_stm = (up == "W" and stm == 0) or (up == "B" and stm == 1)
    value = wdl if up_is_stm else -wdl
    return {1: "win", 0: "draw", -1: "loss"}[value]


def rates(outcomes: list[str]) -> dict[str, float]:
    if not outcomes:
        raise ValueError("empty outcome vector")
    return {cat: outcomes.count(cat) / len(outcomes) for cat in CATS}


def summarize(outcomes: list[str], source: str, total: int) -> dict[str, object]:
    r = rates(outcomes)
    return {
        "n": len(outcomes),
        "total_pieces": total,
        "source": source,
        "rates": r,
        "failure_cost_2loss_plus_draw": 2.0 * r["loss"] + r["draw"],
    }


def aggregate(args: argparse.Namespace) -> int:
    if len(args.tb_data) != len(args.tb_meta):
        raise ValueError("--tb-data and --tb-meta counts differ")

    by_stratum: dict[str, list[str]] = defaultdict(list)
    pool_stratum: dict[tuple[str, str], list[str]] = defaultdict(list)
    totals: dict[str, int] = {}
    sources: dict[str, str] = {}

    for data_path, meta_path in zip(args.tb_data, args.tb_meta, strict=True):
        records = read_jnnw(Path(data_path))
        metadata = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        if len(records) != len(metadata):
            raise ValueError(f"{data_path}: exact data/meta mismatch")
        for record, item in zip(records, metadata, strict=True):
            pieces = total_pieces(item)
            if pieces > args.exact_max_pieces:
                raise ValueError(f"{data_path}: exact report contains {pieces} pieces")
            stratum = str(item["stratum"])
            pool = str(item["source_pool"])
            outcome = up_outcome_from_tb(record, item)
            by_stratum[stratum].append(outcome)
            pool_stratum[(pool, stratum)].append(outcome)
            totals[stratum] = pieces
            sources[stratum] = "exact_egdb_wdl"

    for path in args.scan_inputs:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("engine") != "scan":
            raise ValueError(f"{path}: expected Scan report")
        pool = Path(str(payload.get("pool", ""))).name
        for row in payload.get("rows", []):
            if "error" in row:
                raise ValueError(f"{path}: Scan error at index {row.get('index')}")
            stratum = str(row["stratum"])
            low, high = (int(value) for value in stratum.split("v", 1))
            pieces = low + high
            if pieces <= args.exact_max_pieces:
                raise ValueError(f"{path}: Scan reference contains exact-TB stratum {stratum}")
            outcome = str(row["outcome"])
            if outcome not in COST:
                raise ValueError(f"{path}: invalid Scan outcome {outcome!r}")
            by_stratum[stratum].append(outcome)
            pool_stratum[(pool, stratum)].append(outcome)
            totals[stratum] = pieces
            sources[stratum] = args.scan_source_label

    expected = {f"{n}v{n+2}" for n in range(1, 19)}
    if set(by_stratum) != expected:
        missing = sorted(expected - set(by_stratum))
        extra = sorted(set(by_stratum) - expected)
        raise ValueError(f"reference strata mismatch; missing={missing} extra={extra}")

    strata: dict[str, object] = {}
    for stratum in sorted(by_stratum, key=lambda value: int(value.split("v", 1)[0])):
        strata[stratum] = summarize(by_stratum[stratum], sources[stratum], totals[stratum])
        strata[stratum]["pools"] = {
            pool: summarize(values, sources[stratum], totals[stratum])
            for (pool, name), values in sorted(pool_stratum.items())
            if name == stratum
        }

    exact = [payload for payload in strata.values() if payload["source"] == "exact_egdb_wdl"]
    scan = [payload for payload in strata.values() if payload["source"] == args.scan_source_label]
    payload = {
        "schema": 1,
        "protocol": "material-stratified-conversion-difficulty-reference",
        "lineage": "L3-IMBALANCE2",
        "perspective": "initial_material_up_side",
        "exact_tb_max_total_pieces": args.exact_max_pieces,
        "exact_tb_strata": ["1v3", "2v4"],
        "scan_reference_strata": [f"{n}v{n+2}" for n in range(3, 19)],
        "scan_reference_is_exact": False,
        "reference_used_for_training": False,
        "reference_used_for_weighting": False,
        "strata": strata,
        "macro_equal_stratum_failure_cost": sum(float(item["failure_cost_2loss_plus_draw"]) for item in strata.values()) / len(strata),
        "exact_tb_macro_failure_cost": sum(float(item["failure_cost_2loss_plus_draw"]) for item in exact) / len(exact),
        "scan_macro_failure_cost": sum(float(item["failure_cost_2loss_plus_draw"]) for item in scan) / len(scan),
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("DIFFICULTY_REFERENCE_READY")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    extract_p = sub.add_parser("extract")
    extract_p.add_argument("--pool", required=True)
    extract_p.add_argument("--meta", required=True)
    extract_p.add_argument("--mode", choices=("exact", "high"), required=True)
    extract_p.add_argument("--exact-max-pieces", type=int, default=6)
    extract_p.add_argument("--out-data", required=True)
    extract_p.add_argument("--out-meta", required=True)
    extract_p.add_argument("--report")
    extract_p.set_defaults(func=extract)

    aggregate_p = sub.add_parser("aggregate")
    aggregate_p.add_argument("--tb-data", action="append", required=True)
    aggregate_p.add_argument("--tb-meta", action="append", required=True)
    aggregate_p.add_argument("--scan-inputs", nargs="+", required=True)
    aggregate_p.add_argument("--scan-source-label", default="scan_d10_selfplay_reference")
    aggregate_p.add_argument("--exact-max-pieces", type=int, default=6)
    aggregate_p.add_argument("--out", required=True)
    aggregate_p.set_defaults(func=aggregate)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
