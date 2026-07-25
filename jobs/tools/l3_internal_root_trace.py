#!/usr/bin/env python3
"""Capture comparable iterative-deepening root traces from Jass and Scan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any


TRACE_PREFIX = "info roottrace "
KV_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_-]*)=([^\s]+)")
DONE_RE = re.compile(r"^done\s+move=(\S+)")
MAX_DEPTH = 12
ENGINES = ("JASS_EXACT", "SCAN_NATIVE_INSTRUMENTED")


def digest(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def parse_int(fields: dict[str, str], key: str) -> int:
    try:
        return int(fields[key])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid/missing integer {key}: {fields!r}") from exc


def parse_root_events(lines: list[str]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for raw in lines:
        if not raw.startswith(TRACE_PREFIX):
            continue
        fields = dict(KV_RE.findall(raw[len(TRACE_PREFIX) :]))
        event = fields.pop("event", "")
        if event not in {"begin", "move", "end"}:
            raise ValueError(f"invalid root trace event: {raw!r}")
        parsed: dict[str, object] = {
            "event": event,
            "depth": parse_int(fields, "depth"),
            "attempt": parse_int(fields, "attempt"),
        }
        integer_fields = {
            "alpha",
            "beta",
            "moves",
            "index",
            "alpha_before",
            "score",
            "best",
            "cutoff",
            "searched",
            "complete",
        }
        for key, value in fields.items():
            parsed[key] = int(value) if key in integer_fields else value
        events.append(parsed)
    if not events:
        raise ValueError("engine emitted no roottrace events")
    validate_events(events)
    return events


def validate_events(events: list[dict[str, object]]) -> None:
    attempts: dict[tuple[int, int], list[dict[str, object]]] = {}
    for event in events:
        key = (int(event["depth"]), int(event["attempt"]))
        attempts.setdefault(key, []).append(event)
    expected_depths = set(range(1, MAX_DEPTH + 1))
    if {depth for depth, _ in attempts} != expected_depths:
        raise ValueError("root trace does not cover every depth 1..12")
    for key, rows in attempts.items():
        if rows[0]["event"] != "begin" or rows[-1]["event"] != "end":
            raise ValueError(f"incomplete root attempt {key}")
        moves = [row for row in rows if row["event"] == "move"]
        if [row.get("index") for row in moves] != list(range(1, len(moves) + 1)):
            raise ValueError(f"non-contiguous move indices in {key}")
        if int(rows[-1].get("searched", -1)) != len(moves):
            raise ValueError(f"searched count mismatch in {key}")


def analyse_jass(cv: Any, engine: Any, fen: str, timeout: float) -> dict[str, object]:
    engine.new_game()
    engine.set_position_fen(fen)
    engine._drain()
    started = time.monotonic()
    engine._send(f"go depth {MAX_DEPTH}")
    lines = engine._read_until(
        lambda line: line.startswith("bestmove") or line.startswith("error"),
        timeout_s=timeout,
    )
    if not lines[-1].startswith("bestmove"):
        raise RuntimeError(lines[-1])
    move = cv.parse_jass_bestmove(lines[-1])
    events = parse_root_events(lines)
    return {
        "best_move": move.jass_str(),
        "elapsed_seconds": time.monotonic() - started,
        "events": events,
        "trace_sha256": digest(
            [line for line in lines if line.startswith(TRACE_PREFIX)]
        ),
        "terminal_line": lines[-1],
    }


def analyse_scan(cv: Any, engine: Any, fen: str, timeout: float) -> dict[str, object]:
    engine.new_game()
    engine._drain()
    engine._send(f"pos pos={cv.jass_fen_to_scan_pos(fen)}")
    engine._send(f"level depth={MAX_DEPTH}")
    started = time.monotonic()
    engine._send("go think")
    lines = engine._read_until(
        lambda line: line.startswith("done") or line.startswith("error"),
        timeout_s=timeout,
    )
    match = DONE_RE.search(lines[-1])
    if not match:
        raise RuntimeError(lines[-1])
    move = cv.parse_scan_move(match.group(1))
    events = parse_root_events(lines)
    return {
        "best_move": move.jass_str(),
        "elapsed_seconds": time.monotonic() - started,
        "events": events,
        "trace_sha256": digest(
            [line for line in lines if line.startswith(TRACE_PREFIX)]
        ),
        "terminal_line": lines[-1],
    }


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
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument(
        "--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.shard < 0 or args.nshards <= 0 or args.shard >= args.nshards:
        parser.error("invalid shard specification")

    os.environ["JASS_TRACE_ROOT"] = "1"
    os.environ["SCAN_TRACE_ROOT"] = "1"
    tool = Path(args.calibrate_tool).resolve()
    sys.path.insert(0, str(tool.parent))
    import calibrate_vs_scan as cv  # type: ignore

    search_params = args.search_params_file.read_text(encoding="utf-8").strip()
    if len(search_params.split(",")) != 65:
        raise ValueError("0959 exact-semantics fingerprint must contain 65 keys")
    sentinels = load_sentinels(args.sentinels)
    jass = cv.JassEngine(
        args.jass,
        label="0960-Jass-exact",
        pattern_path=args.pattern,
        search_params=search_params,
    )
    scan = cv.ScanEngine(
        args.scan,
        label="0960-Scan-instrumented",
        no_book=True,
        bb_size=0,
    )
    rows: list[dict[str, object]] = []
    try:
        for ordinal, sentinel in enumerate(sentinels):
            if ordinal % args.nshards != args.shard:
                continue
            common = {
                key: sentinel[key]
                for key in (
                    "sentinel_id",
                    "stratum",
                    "source_index",
                    "advantaged_side",
                    "family",
                )
            }
            fen = str(sentinel["fen"])
            for engine_name, analyse, engine in (
                ("JASS_EXACT", analyse_jass, jass),
                ("SCAN_NATIVE_INSTRUMENTED", analyse_scan, scan),
            ):
                row = {**common, "engine": engine_name}
                try:
                    row["analysis"] = analyse(cv, engine, fen, args.timeout)
                except Exception as exc:
                    row["error"] = f"{type(exc).__name__}: {exc}"
                rows.append(row)
    finally:
        jass.close()
        scan.close()

    output = {
        "schema": 1,
        "protocol": "l3-pure-m1-root-internal-trace-replay-v1",
        "diagnostic_only": True,
        "max_depth": MAX_DEPTH,
        "engines": list(ENGINES),
        "shard": args.shard,
        "nshards": args.nshards,
        "rows": rows,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"ROOT_INTERNAL_TRACE_SHARD_READY shard={args.shard} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
