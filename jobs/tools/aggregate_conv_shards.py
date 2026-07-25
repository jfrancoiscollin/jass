#!/usr/bin/env python3
"""Strictly aggregate ``conv_fixed_wdl`` shard JSON files.

The aggregator refuses missing, duplicate, malformed or mis-numbered shards and
checks accounting against the expected pool size. Schema-2 inputs additionally
retain a complete, unique source-index trace for paired downstream statistics.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


OUTCOMES = {"win", "draw", "loss", "skipped_draw_label", "error"}
METADATA_KEYS = (
    "depth",
    "movetime",
    "jass",
    "defender_jass",
    "pattern",
    "defender_pattern",
    "search_params",
    "defender_search_params",
    "root_order_scan",
    "pool_jnnw",
    "pool_sha256",
)


def _validate_position_results(payload: dict, source: Path, shard: int) -> list[dict]:
    details = payload.get("position_results")
    if not isinstance(details, list):
        raise ValueError(f"{source}: position_results must be a list")

    seen: set[int] = set()
    counts: Counter[str] = Counter()
    normalized: list[dict] = []
    nshards = int(payload["nshards"])
    for row in details:
        if not isinstance(row, dict):
            raise ValueError(f"{source}: malformed position result")
        index = row.get("index")
        outcome = row.get("result")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError(f"{source}: invalid source index {index!r}")
        if index % nshards != shard:
            raise ValueError(f"{source}: index {index} does not belong to shard {shard}")
        if index in seen:
            raise ValueError(f"{source}: duplicate source index {index}")
        if outcome not in OUTCOMES:
            raise ValueError(f"{source}: invalid position outcome {outcome!r}")
        seen.add(index)
        counts[outcome] += 1
        normalized.append({"index": index, "result": outcome})

    expected = {
        "win": int(payload.get("n_win", 0)),
        "draw": int(payload.get("n_draw", 0)),
        "loss": int(payload.get("n_loss", 0)),
        "skipped_draw_label": int(payload.get("n_skipped_draw_label", 0)),
        "error": int(payload.get("n_errors", 0)),
    }
    if dict(counts) != {key: value for key, value in expected.items() if value}:
        raise ValueError(
            f"{source}: position outcomes {dict(counts)} do not match counters {expected}"
        )
    return normalized


def aggregate(
    paths: list[str | Path],
    expected_shards: int,
    expected_records: int | None = None,
    max_error_rate: float = 0.08,
    stratum: str = "global",
    require_position_results: bool = False,
) -> dict:
    if expected_shards <= 0:
        raise ValueError("expected_shards must be positive")
    if len(paths) != expected_shards:
        raise ValueError(f"got {len(paths)} shard files, expected {expected_shards}")

    shards: dict[int, tuple[dict, Path]] = {}
    for path in paths:
        source = Path(path)
        if not source.is_file() or source.stat().st_size == 0:
            raise ValueError(f"missing/empty shard file: {source}")
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {source}: {exc}") from exc
        shard = int(payload.get("shard", -1))
        nshards = int(payload.get("nshards", -1))
        if nshards != expected_shards:
            raise ValueError(f"{source}: nshards={nshards}, expected {expected_shards}")
        if not 0 <= shard < expected_shards:
            raise ValueError(f"{source}: invalid shard index {shard}")
        if shard in shards:
            raise ValueError(f"duplicate shard {shard}")
        shards[shard] = (payload, source)

    missing = sorted(set(range(expected_shards)) - set(shards))
    if missing:
        raise ValueError(f"missing shard indices: {missing}")

    totals = {
        "n_pos": 0,
        "n_win": 0,
        "n_draw": 0,
        "n_loss": 0,
        "n_skipped_draw_label": 0,
        "n_errors": 0,
        "n_restarts": 0,
        "root_order_schedule_queries": 0,
        "root_order_schedule_terminal_queries": 0,
        "root_order_applications": 0,
        "root_order_failures": 0,
    }
    errors: list[str] = []
    first_payload = shards[0][0]
    metadata = {key: first_payload.get(key) for key in METADATA_KEYS}
    detail_presence = ["position_results" in shards[i][0] for i in range(expected_shards)]
    if require_position_results and not all(detail_presence):
        raise ValueError("position_results required for every shard")
    if any(detail_presence) and not all(detail_presence):
        raise ValueError("mixed shard schemas: partial position_results")

    position_results: list[dict] = []
    seen_indices: set[int] = set()
    for shard in range(expected_shards):
        payload, source = shards[shard]
        for key in totals:
            totals[key] += int(payload.get(key, 0))
        errors.extend(str(item) for item in payload.get("errors", []))
        for key, expected in metadata.items():
            if payload.get(key) != expected:
                raise ValueError(f"{source}: inconsistent {key} across shards")
        if all(detail_presence):
            details = _validate_position_results(payload, source, shard)
            duplicate = seen_indices.intersection(row["index"] for row in details)
            if duplicate:
                raise ValueError(f"duplicate source indices across shards: {sorted(duplicate)}")
            seen_indices.update(row["index"] for row in details)
            position_results.extend(details)

    accounted = totals["n_pos"] + totals["n_skipped_draw_label"] + totals["n_errors"]
    if expected_records is not None and accounted != expected_records:
        raise ValueError(
            f"accounting mismatch: played+skipped+errors={accounted}, expected={expected_records}"
        )
    if totals["n_pos"] != totals["n_win"] + totals["n_draw"] + totals["n_loss"]:
        raise ValueError("W/D/L does not sum to n_pos")

    if all(detail_presence):
        position_results.sort(key=lambda row: row["index"])
        if len(position_results) != accounted:
            raise ValueError("position detail count does not match accounting")
        if expected_records is not None and seen_indices != set(range(expected_records)):
            missing_indices = sorted(set(range(expected_records)) - seen_indices)
            extra_indices = sorted(seen_indices - set(range(expected_records)))
            raise ValueError(
                f"source index coverage mismatch: missing={missing_indices[:10]} "
                f"extra={extra_indices[:10]}"
            )

    denominator = expected_records if expected_records is not None else max(accounted, 1)
    error_rate = totals["n_errors"] / denominator
    if error_rate > max_error_rate:
        raise ValueError(
            f"error rate {error_rate:.3%} exceeds threshold {max_error_rate:.3%}"
        )

    result = {
        "schema": 2 if all(detail_presence) else 1,
        "stratum": stratum,
        "expected_shards": expected_shards,
        "expected_records": expected_records,
        **totals,
        **metadata,
        "accounted_records": accounted,
        "error_rate": round(error_rate, 6),
        "conversion": None
        if totals["n_pos"] == 0
        else round(totals["n_win"] / totals["n_pos"], 6),
        "errors": errors[:50],
        "complete": True,
    }
    if all(detail_presence):
        result["position_results"] = position_results
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--expected-shards", type=int, required=True)
    parser.add_argument("--expected-records", type=int)
    parser.add_argument("--max-error-rate", type=float, default=0.08)
    parser.add_argument("--stratum", default="global")
    parser.add_argument("--require-position-results", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        result = aggregate(
            args.inputs,
            args.expected_shards,
            args.expected_records,
            args.max_error_rate,
            args.stratum,
            args.require_position_results,
        )
        Path(args.out).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
