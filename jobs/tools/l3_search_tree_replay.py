#!/usr/bin/env python3
"""Replay 0958 sentinels through Scan and the Jass search ladder."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any


DONE_RE = re.compile(r"^done\s+move=(\S+)")
KV_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_-]*)=([^\s]+)")
DEPTHS = (8, 10, 12)


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


def parse_jass(cv: Any, lines: list[str], elapsed: float) -> dict[str, object]:
    last = lines[-1] if lines else ""
    if last.startswith("error") or not last.startswith("bestmove"):
        raise RuntimeError(last or "empty Jass trace")
    move = cv.parse_jass_bestmove(last)
    fields = collect_fields(lines)
    nodes = integer_or_none(fields.get("nodes"))
    return {
        "best_move": move.jass_str(),
        "scan_move": move.scan_str(),
        "score": integer_or_none(fields.get("score")),
        "reported_depth": integer_or_none(fields.get("depth")),
        "nodes": nodes,
        "cutoffs": integer_or_none(fields.get("cutoffs")),
        "first_move_cutoffs": integer_or_none(fields.get("cut1")),
        "pvs_researches": integer_or_none(fields.get("research")),
        "moves_searched": integer_or_none(fields.get("movessearched")),
        "scan_verify_probes": integer_or_none(fields.get("scanverify")),
        "scan_verify_cutoffs": integer_or_none(fields.get("scanverifycuts")),
        "scan_threat_reentries": integer_or_none(fields.get("scanthreat")),
        "elapsed_seconds": elapsed,
        "nodes_per_second": nodes / elapsed if nodes is not None and elapsed > 0 else None,
        "pv": [token for token in fields.get("pv", "").split(",") if token],
        "raw_trace": lines,
        "raw_trace_sha256": trace_digest(lines),
    }


def parse_scan(cv: Any, lines: list[str], elapsed: float) -> dict[str, object]:
    last = lines[-1] if lines else ""
    if last.startswith("error"):
        raise RuntimeError(last)
    match = DONE_RE.search(last)
    if not match:
        raise RuntimeError(f"unexpected Scan terminal line: {last!r}")
    move = cv.parse_scan_move(match.group(1))
    fields = collect_fields(lines)
    nodes = integer_or_none(fields.get("nodes"))
    pv_raw = fields.get("pv", "")
    return {
        "best_move": move.jass_str(),
        "scan_move": move.scan_str(),
        "score": integer_or_none(fields.get("score")),
        "reported_depth": integer_or_none(fields.get("depth")),
        "nodes": nodes,
        "elapsed_seconds": elapsed,
        "nodes_per_second": nodes / elapsed if nodes is not None and elapsed > 0 else None,
        "pv": [token for token in re.split(r"[,;]", pv_raw) if token],
        "raw_trace": lines,
        "raw_trace_sha256": trace_digest(lines),
    }


class JassTraceEngine:
    def __init__(
        self,
        cv: Any,
        binary: str,
        pattern: str,
        search_params: str,
        label: str,
        timeout: float,
    ):
        self.cv = cv
        self.engine = cv.JassEngine(
            binary,
            label=label,
            pattern_path=pattern,
            search_params=search_params,
        )
        self.timeout = timeout

    def analyse(self, fen: str, depth: int) -> dict[str, object]:
        # Every row is an independent root: clear TT, history and game state so
        # shard/order cannot alter the comparison.
        self.engine.new_game()
        self.engine.set_position_fen(fen)
        self.engine._drain()
        started = time.monotonic()
        self.engine._send(f"go depth {depth}")
        lines = self.engine._read_until(
            lambda line: line.startswith("bestmove") or line.startswith("error"),
            timeout_s=self.timeout,
        )
        return parse_jass(self.cv, lines, time.monotonic() - started)

    def close(self) -> None:
        self.engine.close()


class ScanTraceEngine:
    def __init__(self, cv: Any, binary: str, timeout: float):
        self.cv = cv
        self.engine = cv.ScanEngine(
            binary, label="0958-Scan", no_book=True, bb_size=0
        )
        self.timeout = timeout

    def analyse(self, fen: str, depth: int) -> dict[str, object]:
        self.engine.new_game()
        self.engine._drain()
        self.engine._send(f"pos pos={self.cv.jass_fen_to_scan_pos(fen)}")
        self.engine._send(f"level depth={depth}")
        started = time.monotonic()
        self.engine._send("go think")
        lines = self.engine._read_until(
            lambda line: line.startswith("done") or line.startswith("error"),
            timeout_s=self.timeout,
        )
        return parse_scan(self.cv, lines, time.monotonic() - started)

    def close(self) -> None:
        self.engine.close()


def load_contracts(
    sentinels_path: Path, variants_path: Path
) -> tuple[list[dict[str, object]], dict[str, str]]:
    sentinels = json.loads(sentinels_path.read_text(encoding="utf-8"))
    if sentinels.get("protocol") != "l3-pure-m1-search-tree-audit-sentinels-v1":
        raise ValueError("unexpected sentinel protocol")
    rows = list(sentinels.get("sentinels", []))
    if len(rows) != 48:
        raise ValueError(f"0958 requires exactly 48 sentinels, found {len(rows)}")

    variants = json.loads(variants_path.read_text(encoding="utf-8"))
    if (
        variants.get("protocol")
        != "l3-pure-m1-search-tree-audit-search-ladder-v1"
    ):
        raise ValueError("unexpected search-variant protocol")
    names = ["Q00", *variants["variant_order"]]
    specs = {"Q00": str(variants["base"]["search_params"])}
    specs.update(
        {
            name: str(variants["arms"][name]["search_params"])
            for name in variants["variant_order"]
        }
    )
    if list(specs) != names or any(len(spec.split(",")) != 63 for spec in specs.values()):
        raise ValueError("search ladder is incomplete or not fully resolved")
    return rows, specs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinels", type=Path, required=True)
    parser.add_argument("--variants", type=Path, required=True)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--scan", required=True)
    parser.add_argument("--depths", default="8,10,12")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--jass-timeout", type=float, default=900.0)
    parser.add_argument("--scan-timeout", type=float, default=900.0)
    parser.add_argument(
        "--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    depths = tuple(int(token) for token in args.depths.split(",") if token)
    if depths != DEPTHS:
        parser.error("0958 depth ladder must be exactly 8,10,12")
    if args.shard < 0 or args.nshards <= 0 or args.shard >= args.nshards:
        parser.error("invalid shard specification")

    tool = Path(args.calibrate_tool).resolve()
    sys.path.insert(0, str(tool.parent))
    import calibrate_vs_scan as cv  # type: ignore

    sentinels, specs = load_contracts(args.sentinels, args.variants)
    engines: dict[str, Any] = {
        name: JassTraceEngine(
            cv, args.jass, args.pattern, spec, f"0958-{name}", args.jass_timeout
        )
        for name, spec in specs.items()
    }
    engines["SCAN_NATIVE"] = ScanTraceEngine(cv, args.scan, args.scan_timeout)

    rows: list[dict[str, object]] = []
    try:
        for ordinal, sentinel in enumerate(sentinels):
            if ordinal % args.nshards != args.shard:
                continue
            fen = str(sentinel["fen"])
            for depth in depths:
                for engine_name, engine in engines.items():
                    row: dict[str, object] = {
                        "sentinel_id": sentinel["sentinel_id"],
                        "stratum": sentinel["stratum"],
                        "source_index": sentinel["source_index"],
                        "advantaged_side": sentinel["advantaged_side"],
                        "family": sentinel["family"],
                        "engine": engine_name,
                        "requested_depth": depth,
                    }
                    try:
                        row["analysis"] = engine.analyse(fen, depth)
                    except Exception as exc:  # aggregate fails closed
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
        "protocol": "l3-pure-m1-search-tree-audit-replay-v1",
        "diagnostic_only": True,
        "depths": list(depths),
        "engines": list(engines),
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
    print(f"SEARCH_TREE_REPLAY_SHARD_READY shard={args.shard} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
