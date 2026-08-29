#!/usr/bin/env python3
"""Build a transparent per-shard timeout plan from the HOME preflight rate.

This is operational metadata only.  It never reads or changes a score, a
selection decision, or a scientific budget.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def _load_row_ids(path: str) -> set[int] | None:
    if path == "-":
        return None
    values = {
        int(line.strip())
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    if not values:
        raise ValueError("row-id filter is empty")
    return values


def build_timeout_plan(
    preflight: dict[str, Any],
    groups_path: Path,
    row_ids_path: str,
    engine: str,
    budgets: tuple[int, ...],
    nshards: int,
    *,
    safety_factor: float = 1.3,
    grace_seconds: float = 120.0,
    minimum_timeout_seconds: int = 300,
) -> dict[str, Any]:
    if engine not in {"Jass", "Scan"}:
        raise ValueError(f"unsupported engine {engine!r}")
    if nshards <= 0 or not budgets or any(value <= 0 for value in budgets):
        raise ValueError("invalid shard count or node ladder")
    if safety_factor < 1.0 or grace_seconds < 0 or minimum_timeout_seconds <= 0:
        raise ValueError("invalid timeout policy")

    planning = preflight["throughput_and_eta"]
    if planning.get("planning_only_not_scientific_metric") is not True:
        raise ValueError("preflight planning guard drift")
    if int(planning.get("worker_cap", 0)) != 15:
        raise ValueError("preflight worker cap drift")
    nps = float(planning["observed_1k_smoke"][engine]["requested_nodes_per_second"])
    if not math.isfinite(nps) or nps <= 0:
        raise ValueError("preflight NPS is not positive and finite")

    with groups_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    required = {"row_index", "child_rule_terminal", "child_tb_exact"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("sibling group fields drift")
    if [int(row["row_index"]) for row in rows] != list(range(len(rows))):
        raise ValueError("sibling row indices are not contiguous")
    selected = _load_row_ids(row_ids_path)
    if selected is not None and (min(selected) < 0 or max(selected) >= len(rows)):
        raise ValueError("row-id filter is out of range")

    budget_sum = sum(budgets)
    shards: list[dict[str, Any]] = []
    for shard in range(nshards):
        chosen = [
            row for row in rows
            if (selected is None or int(row["row_index"]) in selected)
            and int(row["row_index"]) % nshards == shard
        ]
        searched = 0
        for row in chosen:
            terminal = int(row["child_rule_terminal"]) == 1
            tb_exact = int(row["child_tb_exact"]) == 1
            if not terminal and not (engine == "Jass" and tb_exact):
                searched += 1
        requested_nodes = searched * budget_sum
        healthy_seconds = requested_nodes / nps
        timeout_seconds = max(
            minimum_timeout_seconds,
            math.ceil(healthy_seconds * safety_factor + grace_seconds),
        )
        shards.append({
            "shard": shard,
            "selected_rows": len(chosen),
            "searched_rows": searched,
            "requested_nodes": requested_nodes,
            "healthy_seconds_at_smoke_nps": healthy_seconds,
            "timeout_seconds": timeout_seconds,
        })

    chosen_total = sum(item["selected_rows"] for item in shards)
    expected_total = len(rows) if selected is None else len(selected)
    if chosen_total != expected_total or chosen_total <= 0:
        raise ValueError("selected row coverage drift")
    workers = min(15, nshards)
    wave_starts = range(0, nshards, workers)
    healthy_stage = sum(
        max(item["healthy_seconds_at_smoke_nps"] for item in shards[start:start + workers])
        for start in wave_starts
    )
    timeout_stage = sum(
        max(item["timeout_seconds"] for item in shards[start:start + workers])
        for start in wave_starts
    )
    per_search_timeout = max(
        minimum_timeout_seconds,
        math.ceil(max(budgets) / nps * safety_factor + grace_seconds),
    )
    return {
        "schema": "jass.scan_ceiling_shard_timeout_plan.v1",
        "planning_only_not_scientific_metric": True,
        "engine": engine,
        "groups_sha256": hashlib.sha256(groups_path.read_bytes()).hexdigest(),
        "row_ids_sha256": (
            None if row_ids_path == "-"
            else hashlib.sha256(Path(row_ids_path).read_bytes()).hexdigest()
        ),
        "budgets_nodes": list(budgets),
        "nshards": nshards,
        "worker_cap": workers,
        "smoke_requested_nodes_per_second": nps,
        "safety_factor": safety_factor,
        "grace_seconds": grace_seconds,
        "minimum_timeout_seconds": minimum_timeout_seconds,
        "per_search_timeout_seconds": per_search_timeout,
        "stage_healthy_eta_seconds": healthy_stage,
        "stage_timeout_ceiling_seconds": timeout_stage,
        "selected_rows": chosen_total,
        "searched_rows": sum(item["searched_rows"] for item in shards),
        "requested_nodes": sum(item["requested_nodes"] for item in shards),
        "scientific_budgets_changed": False,
        "shards": shards,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--row-ids", default="-")
    parser.add_argument("--engine", choices=("Jass", "Scan"), required=True)
    parser.add_argument("--budgets", required=True)
    parser.add_argument("--nshards", type=int, default=16)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-tsv", type=Path, required=True)
    args = parser.parse_args()
    budgets = tuple(int(value) for value in args.budgets.split(","))
    plan = build_timeout_plan(
        json.loads(args.preflight.read_text(encoding="utf-8")),
        args.groups,
        args.row_ids,
        args.engine,
        budgets,
        args.nshards,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with args.output_tsv.open("w", newline="", encoding="utf-8") as stream:
        fields = (
            "shard", "selected_rows", "searched_rows", "requested_nodes",
            "healthy_seconds_at_smoke_nps", "timeout_seconds",
        )
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows({name: item[name] for name in fields} for item in plan["shards"])


if __name__ == "__main__":
    main()
