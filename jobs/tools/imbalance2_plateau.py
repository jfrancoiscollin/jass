#!/usr/bin/env python3
"""Detect an internal L3-IMBALANCE2 plateau without Gen2 or Scan.

Input is a JSON manifest mapping four or more consecutive generations to the
candidate-only shard reports produced by ``imbalance2_scan_gate.py run`` on the
independent plateau pools. The failure cost is 2*loss + draw from the initially
material-up side. External references are forbidden in every input report.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

COST = {"win": 0.0, "draw": 1.0, "loss": 2.0}


def load_generation(paths: list[str]) -> dict[tuple[str, int], str]:
    rows: dict[tuple[str, int], str] = {}
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("engine") != "candidate":
            raise ValueError(f"{path}: plateau input must be candidate-only")
        pool = Path(str(payload.get("pool", ""))).name
        if not pool.startswith("plateau-"):
            raise ValueError(f"{path}: not an independent plateau pool")
        for row in payload["rows"]:
            if "error" in row:
                raise ValueError(f"{path}: engine error at index {row.get('index')}")
            key = (pool, int(row["index"]))
            if key in rows:
                raise ValueError(f"duplicate plateau key {key}")
            rows[key] = str(row["outcome"])
    return rows


def interval(values: list[float], alpha: float = 0.05) -> list[float]:
    values.sort()
    n = len(values)
    return [values[int((alpha / 2) * (n - 1))], values[int((1 - alpha / 2) * (n - 1))]]


def paired_delta(first: list[str], last: list[str], reps: int, seed: int) -> tuple[float, list[float]]:
    if len(first) != len(last) or not first:
        raise ValueError("paired plateau vectors are empty or misaligned")
    deltas = [COST[b] - COST[a] for a, b in zip(first, last, strict=True)]
    point = sum(deltas) / len(deltas)
    rng = random.Random(seed)
    samples = []
    for _ in range(reps):
        samples.append(sum(deltas[rng.randrange(len(deltas))] for _ in deltas) / len(deltas))
    return point, interval(samples)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--bootstrap", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=271828)
    parser.add_argument("--max-improvement", type=float, default=0.02,
                        help="maximum first-to-last cost improvement still considered flat")
    parser.add_argument("--max-last3-range", type=float, default=0.04)
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    generations = manifest.get("generations", {})
    ordered = sorted(generations, key=lambda value: int(str(value).lstrip("Gg")))
    if len(ordered) < 4:
        parser.error("plateau requires at least four consecutive generations")
    numbers = [int(str(value).lstrip("Gg")) for value in ordered]
    if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        parser.error("generations must be consecutive")
    if manifest.get("same_search_budget") is not True:
        parser.error("plateau requires the same search budget across the window")

    data = {generation: load_generation(list(generations[generation])) for generation in ordered}
    common = set.intersection(*(set(rows) for rows in data.values()))
    if not common:
        parser.error("no common plateau positions")
    pools: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key in sorted(common):
        pools[key[0]].append(key)
    if set(pools) != {"plateau-a.jnnw", "plateau-b.jnnw"}:
        parser.error("both independent plateau pools A and B are required")

    pool_reports = {}
    confirmed = True
    for pool, keys in pools.items():
        costs = {}
        for generation in ordered:
            outcomes = [data[generation][key] for key in keys]
            costs[generation] = sum(COST[outcome] for outcome in outcomes) / len(outcomes)
        first_outcomes = [data[ordered[0]][key] for key in keys]
        last_outcomes = [data[ordered[-1]][key] for key in keys]
        delta, ci = paired_delta(first_outcomes, last_outcomes, args.bootstrap, args.seed + len(pool))
        improvement = -delta
        last3 = [costs[generation] for generation in ordered[-3:]]
        passed = improvement <= args.max_improvement and ci[0] <= 0.0 <= ci[1] and (
            max(last3) - min(last3) <= args.max_last3_range
        )
        confirmed &= passed
        pool_reports[pool] = {
            "n": len(keys),
            "failure_cost_2loss_plus_draw": costs,
            "last_minus_first": delta,
            "paired_bootstrap_95": ci,
            "first_to_last_improvement": improvement,
            "last3_range": max(last3) - min(last3),
            "pass": passed,
        }

    payload = {
        "schema": 1,
        "lineage": "L3-IMBALANCE2",
        "plateau_confirmed": confirmed,
        "generations": ordered,
        "same_search_budget": True,
        "external_references_used": False,
        "metric": "material_up_failure_cost_2loss_plus_draw",
        "pool_reports": pool_reports,
        "thresholds": {
            "max_first_to_last_improvement": args.max_improvement,
            "max_last3_range": args.max_last3_range,
            "paired_ci_must_include_zero": True,
        },
        "decision": "PLATEAU_CONFIRMED" if confirmed else "STILL_IMPROVING_OR_UNSTABLE",
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
