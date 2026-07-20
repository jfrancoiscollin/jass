#!/usr/bin/env python3
"""Replay D0 sentinel positions with G4, G8 and Scan at fixed depths.

This is a static-search diagnostic, not self-play and not training.  Every search
publishes the selected move, score/depth/nodes/PV fields when the engine exposes
them, plus the raw HUB trace and its digest.  Scan fields that are not emitted by
its HUB build remain null rather than being inferred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

DONE_RE = re.compile(r"^done\s+move=(\S+)")
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


def jass_result(cv: Any, lines: list[str]) -> dict[str, object]:
    last = lines[-1] if lines else ""
    if last.startswith("error"):
        raise RuntimeError(last)
    if not last.startswith("bestmove"):
        raise RuntimeError(f"unexpected Jass terminal line: {last!r}")
    move = cv.parse_jass_bestmove(last)
    fields = collect_fields(lines)
    pv = [token for token in fields.get("pv", "").split(",") if token]
    return {
        "best_move": move.jass_str(),
        "scan_move": move.scan_str(),
        "captures": list(move.captures),
        "score": integer_or_none(fields.get("score")),
        "reported_depth": integer_or_none(fields.get("depth")),
        "nodes": integer_or_none(fields.get("nodes")),
        "pv": pv,
        "raw_trace": lines,
        "raw_trace_sha256": trace_digest(lines),
    }


def scan_result(cv: Any, lines: list[str]) -> dict[str, object]:
    last = lines[-1] if lines else ""
    if last.startswith("error"):
        raise RuntimeError(last)
    match = DONE_RE.search(last)
    if not match:
        raise RuntimeError(f"unexpected Scan terminal line: {last!r}")
    move = cv.parse_scan_move(match.group(1))
    fields = collect_fields(lines)
    pv_raw = fields.get("pv", "")
    pv = [token for token in re.split(r"[,;]", pv_raw) if token]
    return {
        "best_move": move.jass_str(),
        "scan_move": move.scan_str(),
        "captures": list(move.captures),
        "score": integer_or_none(fields.get("score")),
        "reported_depth": integer_or_none(fields.get("depth")),
        "nodes": integer_or_none(fields.get("nodes")),
        "pv": pv,
        "raw_trace": lines,
        "raw_trace_sha256": trace_digest(lines),
    }


class JassTraceEngine:
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
        self.engine._send(f"go depth {depth}")
        lines = self.engine._read_until(
            lambda line: line.startswith("bestmove") or line.startswith("error"),
            timeout_s=self.timeout,
        )
        return jass_result(self.cv, lines)

    def close(self) -> None:
        self.engine.close()


class ScanTraceEngine:
    def __init__(self, cv: Any, binary: str, bb_size: int, timeout: float):
        self.cv = cv
        self.engine = cv.ScanEngine(binary, label="D0-Scan", no_book=True, bb_size=bb_size)
        self.timeout = timeout

    def analyse(self, fen: str, depth: int) -> dict[str, object]:
        self.engine.new_game()
        self.engine._drain()
        self.engine._send(f"pos pos={self.cv.jass_fen_to_scan_pos(fen)}")
        self.engine._send(f"level depth={depth}")
        self.engine._send("go think")
        lines = self.engine._read_until(
            lambda line: line.startswith("done") or line.startswith("error"),
            timeout_s=self.timeout,
        )
        return scan_result(self.cv, lines)

    def close(self) -> None:
        self.engine.close()


def parse_depths(value: str) -> list[int]:
    depths = [int(token) for token in value.split(",") if token]
    if sorted(set(depths)) != [8, 10, 12, 14]:
        raise ValueError("D0 depth ladder must be exactly 8,10,12,14")
    return depths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinels", required=True)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--g4-pattern", required=True)
    parser.add_argument("--g8-pattern", required=True)
    parser.add_argument("--scan", required=True)
    parser.add_argument("--search-params", required=True)
    parser.add_argument("--depths", default="8,10,12,14")
    parser.add_argument("--scan-bb-size", type=int, default=0)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--jass-timeout", type=float, default=600.0)
    parser.add_argument("--scan-timeout", type=float, default=600.0)
    parser.add_argument("--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.shard < 0 or args.nshards <= 0 or args.shard >= args.nshards:
        parser.error("invalid shard specification")
    if args.scan_bb_size != 0:
        parser.error("D0 requires Scan bb-size=0 for the same empirical reference contract")
    if len(args.search_params.split(",")) != 63:
        parser.error("D0 requires the fully resolved 63-key search fingerprint")
    depths = parse_depths(args.depths)

    tool = Path(args.calibrate_tool).resolve()
    sys.path.insert(0, str(tool.parent))
    import calibrate_vs_scan as cv  # type: ignore

    payload = json.loads(Path(args.sentinels).read_text(encoding="utf-8"))
    sentinels = payload.get("sentinels", [])
    if not 20 <= len(sentinels) <= 40:
        parser.error("sentinel input must contain 20..40 positions")

    engines = {
        "g4": JassTraceEngine(cv, args.jass, args.g4_pattern, args.search_params, "D0-G4", args.jass_timeout),
        "g8": JassTraceEngine(cv, args.jass, args.g8_pattern, args.search_params, "D0-G8", args.jass_timeout),
        "scan": ScanTraceEngine(cv, args.scan, args.scan_bb_size, args.scan_timeout),
    }
    rows: list[dict[str, object]] = []
    try:
        for ordinal, sentinel in enumerate(sentinels):
            if ordinal % args.nshards != args.shard:
                continue
            fen = str(sentinel["fen"])
            for depth in depths:
                for engine_name, engine in engines.items():
                    row = {
                        "sentinel_id": sentinel["sentinel_id"],
                        "pool": sentinel["pool"],
                        "index": sentinel["index"],
                        "stratum": sentinel["stratum"],
                        "family": sentinel["family"],
                        "reference_source": sentinel["reference_source"],
                        "reference_outcome": sentinel["reference_outcome"],
                        "engine": engine_name,
                        "requested_depth": depth,
                    }
                    try:
                        row["analysis"] = engine.analyse(fen, depth)
                    except Exception as exc:  # noqa: BLE001 - report fail-closed at aggregate boundary
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
        "protocol": "imbalance2-d0-static-multidepth-replay",
        "diagnostic_only": True,
        "selfplay_games": 0,
        "training_records": 0,
        "depths": depths,
        "scan_bb_size": args.scan_bb_size,
        "shard": args.shard,
        "nshards": args.nshards,
        "rows": rows,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"D0_REPLAY_SHARD_READY shard={args.shard} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
