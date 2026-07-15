#!/usr/bin/env python3
"""Strictly aggregate ``conv_fixed_wdl`` shard JSON files.

The aggregator refuses missing, duplicate, malformed or mis-numbered shards and
checks accounting against the expected pool size. This prevents a partial set of
successful shards from being silently interpreted as a valid conversion score.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def aggregate(
    paths: list[str | Path],
    expected_shards: int,
    expected_records: int | None = None,
    max_error_rate: float = 0.08,
    stratum: str = "global",
) -> dict:
    if expected_shards <= 0:
        raise ValueError("expected_shards must be positive")
    if len(paths) != expected_shards:
        raise ValueError(f"got {len(paths)} shard files, expected {expected_shards}")

    shards: dict[int, dict] = {}
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
        shards[shard] = payload

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
    }
    errors: list[str] = []
    for shard in range(expected_shards):
        payload = shards[shard]
        for key in totals:
            totals[key] += int(payload.get(key, 0))
        errors.extend(str(item) for item in payload.get("errors", []))

    accounted = totals["n_pos"] + totals["n_skipped_draw_label"] + totals["n_errors"]
    if expected_records is not None and accounted != expected_records:
        raise ValueError(
            f"accounting mismatch: played+skipped+errors={accounted}, expected={expected_records}"
        )
    if totals["n_pos"] != totals["n_win"] + totals["n_draw"] + totals["n_loss"]:
        raise ValueError("W/D/L does not sum to n_pos")

    denominator = expected_records if expected_records is not None else max(accounted, 1)
    error_rate = totals["n_errors"] / denominator
    if error_rate > max_error_rate:
        raise ValueError(
            f"error rate {error_rate:.3%} exceeds threshold {max_error_rate:.3%}"
        )

    result = {
        "stratum": stratum,
        "expected_shards": expected_shards,
        "expected_records": expected_records,
        **totals,
        "accounted_records": accounted,
        "error_rate": round(error_rate, 6),
        "conversion": None
        if totals["n_pos"] == 0
        else round(totals["n_win"] / totals["n_pos"], 6),
        "errors": errors[:50],
        "complete": True,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--expected-shards", type=int, required=True)
    parser.add_argument("--expected-records", type=int)
    parser.add_argument("--max-error-rate", type=float, default=0.08)
    parser.add_argument("--stratum", default="global")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    try:
        result = aggregate(
            args.inputs,
            args.expected_shards,
            args.expected_records,
            args.max_error_rate,
            args.stratum,
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
