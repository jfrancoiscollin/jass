#!/usr/bin/env python3
"""Hub node-budget scorer for the pinned official Scan 3.1 binary."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import sys
import time
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    ROOT = Path(__file__).resolve().parents[2]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

from jobs.tools.calibrate_vs_scan import (  # noqa: E402
    DONE_RE,
    EngineFailure,
    ScanEngine,
    parse_scan_move,
)
from jobs.tools.tb_frontier_symmetry_dedup import format_fingerprint  # noqa: E402

RECORD_SIZE = 38
SCAN_COMMIT = "7aae17e7b7bfc47744601afb1ee7655e18983ce5"
ALLOWED_BUDGETS = (1_000, 5_000, 50_000, 200_000, 1_000_000, 2_000_000, 5_000_000)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_info_fields(line: str) -> dict[str, str]:
    if not line.startswith("info"):
        raise ValueError("not a Scan info line")
    fields: dict[str, str] = {}
    for match in re.finditer(r"(?:^|\s)([a-z-]+)=(\"[^\"]*\"|\S+)", line):
        value = match.group(2)
        fields[match.group(1)] = value[1:-1] if value.startswith('"') else value
    return fields


def score_token_to_centi(token: str) -> int:
    value = Decimal(token) * 100
    if value != value.to_integral_value():
        raise ValueError(f"Scan score has sub-cent precision: {token}")
    return int(value)


def read_children(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError("bad children JNNW header")
    count = struct.unpack_from("<I", raw, 4)[0]
    if len(raw) != 8 + count * RECORD_SIZE:
        raise ValueError("children JNNW count/size drift")
    return [raw[8 + i * RECORD_SIZE:8 + (i + 1) * RECORD_SIZE] for i in range(count)]


def record_values(record: bytes) -> tuple[int, int, int, int, int]:
    if len(record) != RECORD_SIZE:
        raise ValueError("bad JNNW record size")
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", record, 0)
    stm = record[32]
    if stm not in (0, 1) or record[33:38] != b"\0" * 5:
        raise ValueError("invalid/labelled child record")
    all_pieces = wm | wk | bm | bk
    if all_pieces >> 50 or ((wm & wk) | (wm & bm) | (wm & bk)
                            | (wk & bm) | (wk & bk) | (bm & bk)):
        raise ValueError("invalid child bitboards")
    return wm, wk, bm, bk, stm


def record_fingerprint(record: bytes) -> str:
    return format_fingerprint(*record_values(record))


def record_to_scan_pos(record: bytes) -> str:
    wm, wk, bm, bk, stm = record_values(record)
    chars = ["e"] * 51
    chars[0] = "W" if stm == 0 else "B"
    for bitboard, marker in ((wm, "w"), (wk, "W"), (bm, "b"), (bk, "B")):
        value = bitboard
        while value:
            bit = (value & -value).bit_length() - 1
            value &= value - 1
            chars[bit + 1] = marker
    return "".join(chars)


def parse_budgets(text: str) -> list[int]:
    budgets = [int(value) for value in text.split(",") if value]
    if not budgets or len(budgets) != len(set(budgets)):
        raise ValueError("empty/duplicate Scan budget ladder")
    if any(value not in ALLOWED_BUDGETS for value in budgets):
        raise ValueError("budget outside preregistered Scan ladder")
    return budgets


def load_row_ids(path: str, count: int) -> set[int] | None:
    if path == "-":
        return None
    values = [int(line.strip()) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = set(values)
    if not rows or len(rows) != len(values) or min(rows) < 0 or max(rows) >= count:
        raise ValueError("invalid Scan row filter")
    return rows


def load_groups(path: Path, count: int) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {
            "row_index", "sibling_identity", "child_fingerprint",
            "child_rule_terminal", "child_legal_moves",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("Scan scorer group fields drift")
        rows = list(reader)
    if len(rows) != count or [int(row["row_index"]) for row in rows] != list(range(count)):
        raise ValueError("Scan scorer group/child alignment drift")
    return rows


class NodeScanEngine(ScanEngine):
    """Pinned Scan runtime with the preregistered node/analyze RPC."""

    def search_nodes(self, scan_pos: str, budget: int, timeout_s: float) -> dict[str, object]:
        if len(scan_pos) != 51 or scan_pos[0] not in "WB" or budget not in ALLOWED_BUDGETS:
            raise ValueError("invalid Scan position/budget")
        self._drain()
        self._send("new-game")
        self._send(f"pos pos={scan_pos}")
        self._send(f"level nodes={budget}")
        self._send("go analyze")
        started = time.monotonic()
        try:
            lines = self._read_until(
                lambda line: line.startswith("done") or line.startswith("error"),
                timeout_s=timeout_s,
            )
        except TimeoutError as exc:
            raise EngineFailure(f"{self.label}: node search timed out") from exc
        elapsed = time.monotonic() - started
        if lines[-1].startswith("error"):
            raise EngineFailure(f"{self.label}: {lines[-1]}")
        complete: list[tuple[str, dict[str, str]]] = []
        for line in lines:
            if not line.startswith("info"):
                continue
            fields = parse_info_fields(line)
            if "score" in fields and "nodes" in fields:
                complete.append((line, fields))
        if not complete:
            raise EngineFailure(f"{self.label}: no complete score/nodes info line")
        info_line, info = complete[-1]
        nodes = int(info["nodes"])
        if nodes <= 0 or nodes > budget:
            raise EngineFailure(f"{self.label}: invalid progressive node snapshot {nodes}/{budget}")
        child_score = score_token_to_centi(info["score"])
        done_match = DONE_RE.search(lines[-1])
        if not done_match:
            raise EngineFailure(f"{self.label}: nonterminal analyze returned no move")
        move = parse_scan_move(done_match.group(1))
        return {
            "child_score_token": info["score"],
            "child_score_centi": child_score,
            "parent_score_centi": -child_score,
            "last_info_nodes": nodes,
            "depth": int(info.get("depth", "0")),
            "mean_depth": info.get("mean-depth", ""),
            "pv": info.get("pv", ""),
            "done_move": move.scan_str(),
            "elapsed_seconds": elapsed,
            "last_info_line": info_line,
            "transcript": lines,
        }


def terminal_observation() -> dict[str, object]:
    return {
        "child_score_token": "-100.00", "child_score_centi": -10_000,
        "parent_score_centi": 10_000, "last_info_nodes": 0,
        "depth": 0, "mean_depth": "", "pv": "", "done_move": "",
        "elapsed_seconds": 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--children", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--budgets", required=True)
    parser.add_argument("--row-ids", default="-")
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--source-commit", default=SCAN_COMMIT)
    args = parser.parse_args()
    if args.source_commit != SCAN_COMMIT or args.nshards <= 0 or not 0 <= args.shard < args.nshards:
        raise ValueError("Scan provenance/shard drift")
    budgets = parse_budgets(args.budgets)
    children = read_children(args.children)
    groups = load_groups(args.groups, len(children))
    selected = load_row_ids(args.row_ids, len(children))
    for index, (record, row) in enumerate(zip(children, groups)):
        if record_fingerprint(record) != row["child_fingerprint"]:
            raise ValueError(f"child fingerprint drift at row {index}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows_written = terminal_rows = searches = 0
    node_snapshots = {str(budget): 0 for budget in budgets}
    elapsed = {str(budget): 0.0 for budget in budgets}
    engine = NodeScanEngine(str(args.scan), label=f"Scan-shard-{args.shard}")
    try:
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            fields = [
                "row_index", "sibling_identity", "budget_nodes", "parent_score_centi",
                "child_score_token", "requested_nodes", "last_info_nodes", "depth",
                "mean_depth", "pv", "done_move", "terminal_exact", "elapsed_seconds",
            ]
            writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            for index, (record, group) in enumerate(zip(children, groups)):
                if selected is not None and index not in selected:
                    continue
                if index % args.nshards != args.shard:
                    continue
                terminal = int(group["child_rule_terminal"]) == 1
                if terminal and int(group["child_legal_moves"]) != 0:
                    raise ValueError("terminal child has legal moves")
                if terminal and int(group.get("exact_parent_utility", "1")) != 1:
                    raise ValueError("terminal child does not encode a parent win")
                scan_pos = record_to_scan_pos(record)
                for budget in budgets:
                    observation = terminal_observation() if terminal else engine.search_nodes(
                        scan_pos, budget, args.timeout_seconds,
                    )
                    terminal_rows += int(terminal)
                    searches += int(not terminal)
                    node_snapshots[str(budget)] += int(observation["last_info_nodes"])
                    elapsed[str(budget)] += float(observation["elapsed_seconds"])
                    writer.writerow({
                        "row_index": index,
                        "sibling_identity": group["sibling_identity"],
                        "budget_nodes": budget,
                        "parent_score_centi": observation["parent_score_centi"],
                        "child_score_token": observation["child_score_token"],
                        "requested_nodes": budget,
                        "last_info_nodes": observation["last_info_nodes"],
                        "depth": observation["depth"],
                        "mean_depth": observation["mean_depth"],
                        "pv": observation["pv"],
                        "done_move": observation["done_move"],
                        "terminal_exact": int(terminal),
                        "elapsed_seconds": format(float(observation["elapsed_seconds"]), ".9f"),
                    })
                    rows_written += 1
    finally:
        engine.close()

    selected_rows = len(children) if selected is None else len(selected)
    shard_rows = sum(1 for row in range(len(children))
                     if (selected is None or row in selected) and row % args.nshards == args.shard)
    if rows_written != shard_rows * len(budgets):
        raise AssertionError("Scan output cardinality drift")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "jass.scan_ceiling_scan_ladder.v1",
        "benchmark_only": True,
        "source_commit": SCAN_COMMIT,
        "scan_binary_sha256": sha256(args.scan),
        "runtime_params": dict(ScanEngine.RUNTIME_PARAMS),
        "mode": "go analyze",
        "fresh_state": "new-game before every sibling/budget",
        "node_contract": "level nodes=N; stock final counter is not emitted",
        "input_children": len(children), "selected_rows": selected_rows,
        "shard": args.shard, "nshards": args.nshards, "processed_rows": shard_rows,
        "budgets_nodes": budgets, "output_rows": rows_written,
        "searches": searches, "terminal_exact_output_rows": terminal_rows,
        "last_info_nodes_sum_by_budget": node_snapshots,
        "elapsed_seconds_by_budget": elapsed,
        "children_sha256": sha256(args.children), "groups_sha256": sha256(args.groups),
        "output_sha256": sha256(args.output),
        "book_enabled": False, "threads_per_search": 1, "bb_size": 0,
        "fits": 0, "refits": 0, "calibrations": 0,
        "strength_games": 0, "promotion_authorized": False,
        "training_allowed": False, "tuning_allowed": False,
        "calibration_allowed": False, "model_selection_allowed": False,
        "runtime_scale_selection_allowed": False,
    }
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": rows_written, "searches": searches}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
