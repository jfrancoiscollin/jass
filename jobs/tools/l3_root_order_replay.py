#!/usr/bin/env python3
"""Replay 0960 sentinels with Jass forced to native Scan root ordering."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

try:
    from l3_internal_root_trace import parse_root_events
    from l3_root_order_oracle import make_root_order_engine_class
except ModuleNotFoundError:  # pragma: no cover
    from jobs.tools.l3_internal_root_trace import parse_root_events
    from jobs.tools.l3_root_order_oracle import make_root_order_engine_class


KV_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_-]*)=([^\s]+)")


def load_sentinels(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("protocol") != "l3-pure-m1-search-tree-audit-sentinels-v1":
        raise ValueError("unexpected sentinel protocol")
    rows = list(payload.get("sentinels", []))
    if len(rows) != 48:
        raise ValueError(f"expected 48 sentinels, found {len(rows)}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinels", type=Path, required=True)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--search-params-file", type=Path, required=True)
    parser.add_argument("--scan", required=True)
    parser.add_argument("--depth", type=int, default=12)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument(
        "--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.depth != 12:
        parser.error("0961 sentinel replay depth must be 12")
    if args.shard < 0 or args.nshards <= 0 or args.shard >= args.nshards:
        parser.error("invalid shard specification")

    os.environ["SCAN_TRACE_ROOT"] = "1"
    os.environ["JASS_TRACE_ROOT"] = "1"
    tool = Path(args.calibrate_tool).resolve()
    sys.path.insert(0, str(tool.parent))
    import calibrate_vs_scan as cv  # type: ignore

    params = args.search_params_file.read_text(encoding="utf-8").strip()
    if len(params.split(",")) != 65:
        raise ValueError("0961 requires the 65-key 0959 fingerprint")
    Engine = make_root_order_engine_class(cv)
    engine = Engine(
        args.jass,
        scan_path=args.scan,
        label="0961-root-order-replay",
        pattern_path=args.pattern,
        search_params=params,
        timeout=args.timeout,
    )
    rows: list[dict[str, object]] = []
    try:
        for ordinal, sentinel in enumerate(load_sentinels(args.sentinels)):
            if ordinal % args.nshards != args.shard:
                continue
            row = {
                key: sentinel[key]
                for key in (
                    "sentinel_id",
                    "stratum",
                    "source_index",
                    "advantaged_side",
                    "family",
                )
            }
            started = time.monotonic()
            try:
                engine.new_game()
                engine.set_position_fen(str(sentinel["fen"]))
                move = engine.go(depth=args.depth)
                lines = engine.last_jass_lines
                fields = dict(KV_RE.findall(lines[-1]))
                trace_lines = [
                    line for line in lines if line.startswith("info roottrace ")
                ]
                row["analysis"] = {
                    "best_move": move.jass_str() if move else None,
                    "elapsed_seconds": time.monotonic() - started,
                    "events": parse_root_events(lines),
                    "root_order_applications": int(fields["rootorder"]),
                    "root_order_failures": int(fields["rootorderfail"]),
                    "trace_sha256": hashlib.sha256(
                        ("\n".join(trace_lines) + "\n").encode()
                    ).hexdigest(),
                    "terminal_line": lines[-1],
                }
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
    finally:
        engine.close()

    output = {
        "schema": 1,
        "protocol": "l3-pure-m1-root-order-causal-replay-v1",
        "diagnostic_only": True,
        "depth": args.depth,
        "shard": args.shard,
        "nshards": args.nshards,
        "rows": rows,
        "oracle_totals": {
            "schedule_queries": engine.schedule_queries,
            "terminal_queries": engine.schedule_terminal_queries,
            "applications": engine.schedule_applications,
            "failures": engine.schedule_failures,
        },
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"ROOT_ORDER_REPLAY_SHARD_READY shard={args.shard} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
