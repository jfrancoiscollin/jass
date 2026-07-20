#!/usr/bin/env python3
"""Replay the D0 sentinels with freshly refitted control and RC4 models.

This tool performs static d14 searches only.  It preserves the D0 Scan anchor and
hypothesis label, records wall time and nodes for a matched throughput diagnostic,
and never authorizes training continuation or promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

KV_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_-]*)=([^\s]+)")


def trace_digest(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def integer_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def collect_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        for key, value in KV_RE.findall(line):
            fields[key.lower()] = value
    return fields


class TraceEngine:
    def __init__(self, cv: Any, binary: str, pattern: str, search_params: str, label: str, timeout: float):
        self.cv = cv
        self.engine = cv.JassEngine(
            binary,
            label=label,
            pattern_path=pattern,
            search_params=search_params,
        )
        self.timeout = timeout

    def analyse(self, fen: str, depth: int) -> dict[str, object]:
        self.engine.set_position_fen(fen)
        self.engine._drain()
        started = time.monotonic()
        self.engine._send(f"go depth {depth}")
        lines = self.engine._read_until(
            lambda line: line.startswith("bestmove") or line.startswith("error"),
            timeout_s=self.timeout,
        )
        elapsed = time.monotonic() - started
        last = lines[-1] if lines else ""
        if last.startswith("error") or not last.startswith("bestmove"):
            raise RuntimeError(last or "empty engine trace")
        move = self.cv.parse_jass_bestmove(last)
        fields = collect_fields(lines)
        nodes = integer_or_none(fields.get("nodes"))
        return {
            "best_move": move.jass_str(),
            "score": integer_or_none(fields.get("score")),
            "reported_depth": integer_or_none(fields.get("depth")),
            "nodes": nodes,
            "elapsed_seconds": elapsed,
            "nodes_per_second": (nodes / elapsed) if nodes is not None and elapsed > 0 else None,
            "pv": [token for token in fields.get("pv", "").split(",") if token],
            "raw_trace_sha256": trace_digest(lines),
        }

    def close(self) -> None:
        self.engine.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d0-report", required=True)
    parser.add_argument("--control-jass", required=True)
    parser.add_argument("--control-pattern", required=True)
    parser.add_argument("--rc4-jass", required=True)
    parser.add_argument("--rc4-pattern", required=True)
    parser.add_argument("--search-params", required=True)
    parser.add_argument("--depth", type=int, default=14)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.depth != 14:
        parser.error("D1 sentinel mechanism gate is preregistered at d14")
    if args.shard < 0 or args.nshards <= 0 or args.shard >= args.nshards:
        parser.error("invalid shard specification")
    if len(args.search_params.split(",")) != 63:
        parser.error("D1 requires the fully resolved 63-key search fingerprint")

    tool = Path(args.calibrate_tool).resolve()
    sys.path.insert(0, str(tool.parent))
    import calibrate_vs_scan as cv  # type: ignore

    d0 = json.loads(Path(args.d0_report).read_text(encoding="utf-8"))
    if d0.get("protocol") != "imbalance2-d0-causal-diagnostic":
        parser.error("unexpected D0 report protocol")
    cases = list(d0.get("cases", []))
    if len(cases) != 30:
        parser.error("D1 expects the 30 reviewed D0 sentinels")

    engines = {
        "control": TraceEngine(cv, args.control_jass, args.control_pattern, args.search_params, "D1-control", args.timeout),
        "rc4": TraceEngine(cv, args.rc4_jass, args.rc4_pattern, args.search_params, "D1-RC4", args.timeout),
    }
    rows: list[dict[str, object]] = []
    try:
        for ordinal, case in enumerate(cases):
            if ordinal % args.nshards != args.shard:
                continue
            for engine_name, engine in engines.items():
                row: dict[str, object] = {
                    "sentinel_id": case["sentinel_id"],
                    "stratum": case["stratum"],
                    "family": case["family"],
                    "causal_hypothesis": case["causal_hypothesis"],
                    "scan_d14_anchor_move": case["scan_d14_anchor_move"],
                    "engine": engine_name,
                    "requested_depth": args.depth,
                }
                try:
                    row["analysis"] = engine.analyse(str(case["fen"]), args.depth)
                except Exception as exc:  # noqa: BLE001 - aggregate fails closed
                    row["error"] = str(exc)
                rows.append(row)
    finally:
        for engine in engines.values():
            try:
                engine.close()
            except Exception:
                pass

    output = {
        "schema": 1,
        "protocol": "imbalance2-d1-rc4-sentinel-replay",
        "depth": args.depth,
        "shard": args.shard,
        "nshards": args.nshards,
        "rows": rows,
        "selfplay_games": 0,
        "training_records": 0,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"D1_RC4_SENTINEL_SHARD_READY shard={args.shard} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
