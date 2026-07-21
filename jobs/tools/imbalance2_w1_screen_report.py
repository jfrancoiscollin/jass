#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregate the L3-IMBALANCE2 W1 adaptive-weight screen.

Primary evidence is paired E64/F64 candidate-only conversion, macro-averaged equally
across 18 material strata.  A small paired generalist match is a veto.  A screen
pass never authorizes promotion or training continuation; it only justifies a
fresh, larger cross-fit oracle calibration and confirmation experiment.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import random
from pathlib import Path

CATS = ("win", "draw", "loss")
COST = {"win": 0.0, "draw": 1.0, "loss": 2.0}
EXPECTED_POOLS = {"plateau-e.jnnw", "plateau-f.jnnw"}
EXPECTED_STRATA = {f"{n}v{n + 2}" for n in range(1, 19)}


def stratum_number(value: str) -> int:
    return int(value.split("v", 1)[0])


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("empty vector")
    return sum(values) / len(values)


def interval(values: list[float]) -> list[float]:
    values.sort()
    n = len(values)
    return [values[int(0.025 * (n - 1))], values[int(0.975 * (n - 1))]]


def bootstrap(values: list[float], reps: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    n = len(values)
    return interval([mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(reps)])


def stratified_bootstrap(values: dict[str, list[float]], reps: int, seed: int) -> list[float]:
    if set(values) != EXPECTED_STRATA or any(not vector for vector in values.values()):
        raise ValueError("stratified bootstrap requires all 18 non-empty strata")
    ordered = [values[name] for name in sorted(values, key=stratum_number)]
    rng = random.Random(seed)
    samples = []
    for _ in range(reps):
        stratum_means = []
        for vector in ordered:
            n = len(vector)
            stratum_means.append(mean([vector[rng.randrange(n)] for _ in range(n)]))
        samples.append(mean(stratum_means))
    return interval(samples)


def rates(outcomes: list[str]) -> dict[str, float]:
    return {cat: outcomes.count(cat) / len(outcomes) for cat in CATS}


def cost(outcomes: list[str]) -> float:
    return mean([COST[value] for value in outcomes])


def load_report_set(paths: list[str]) -> dict[tuple[str, int], dict[str, object]]:
    rows: dict[tuple[str, int], dict[str, object]] = {}
    for raw_path in paths:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("engine") != "candidate":
            raise ValueError(f"{path}: expected candidate self-play report")
        pool = Path(str(payload.get("pool", ""))).name
        if pool not in EXPECTED_POOLS:
            raise ValueError(f"{path}: unexpected W1 pool {pool!r}")
        for raw in payload.get("rows", []):
            row = dict(raw)
            key = (pool, int(row["index"]))
            if key in rows:
                raise ValueError(f"{path}: duplicate key {key}")
            stratum = str(row.get("stratum"))
            if stratum not in EXPECTED_STRATA:
                raise ValueError(f"{path}: invalid stratum {stratum!r}")
            if "error" not in row and str(row.get("outcome")) not in COST:
                raise ValueError(f"{path}: invalid outcome at {key}")
            rows[key] = row
    return rows


def summarize_arm(data: dict[tuple[str, int], dict[str, object]], keys: list[tuple[str, int]]) -> dict[str, object]:
    pools: dict[str, list[tuple[str, int]]] = defaultdict(list)
    strata: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key in keys:
        pools[key[0]].append(key)
        strata[str(data[key]["stratum"])].append(key)
    outcomes = [str(data[key]["outcome"]) for key in keys]
    result: dict[str, object] = {
        "n": len(keys),
        "rates": rates(outcomes),
        "failure_cost_2loss_plus_draw": cost(outcomes),
        "pools": {},
        "strata": {},
    }
    stratum_costs = []
    for pool, pkeys in sorted(pools.items()):
        values = [str(data[key]["outcome"]) for key in pkeys]
        result["pools"][pool] = {"n": len(pkeys), "rates": rates(values), "failure_cost_2loss_plus_draw": cost(values)}
    for stratum in sorted(strata, key=stratum_number):
        values = [str(data[key]["outcome"]) for key in strata[stratum]]
        item = {"n": len(values), "rates": rates(values), "failure_cost_2loss_plus_draw": cost(values)}
        stratum_costs.append(float(item["failure_cost_2loss_plus_draw"]))
        result["strata"][stratum] = item
    result["macro_equal_stratum_failure_cost"] = mean(stratum_costs)
    return result


def paired_view(control: dict[tuple[str, int], dict[str, object]], adaptive: dict[tuple[str, int], dict[str, object]], keys: list[tuple[str, int]], reps: int, seed: int) -> dict[str, object]:
    pools: dict[str, list[tuple[str, int]]] = defaultdict(list)
    strata: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key in keys:
        pools[key[0]].append(key)
        strata[str(control[key]["stratum"])].append(key)
    deltas = [COST[str(adaptive[key]["outcome"])] - COST[str(control[key]["outcome"])] for key in keys]
    result: dict[str, object] = {
        "n": len(keys),
        "adaptive_minus_control_failure_cost": mean(deltas),
        "paired_bootstrap_95": bootstrap(deltas, reps, seed),
        "pools": {},
        "strata": {},
    }
    for ordinal, (pool, pkeys) in enumerate(sorted(pools.items())):
        vector = [COST[str(adaptive[key]["outcome"])] - COST[str(control[key]["outcome"])] for key in pkeys]
        result["pools"][pool] = {
            "n": len(vector),
            "adaptive_minus_control_failure_cost": mean(vector),
            "paired_bootstrap_95": bootstrap(vector, reps, seed + ordinal + 1),
        }
    by_stratum: dict[str, list[float]] = {}
    points = []
    for ordinal, stratum in enumerate(sorted(strata, key=stratum_number)):
        skeys = strata[stratum]
        control_out = [str(control[key]["outcome"]) for key in skeys]
        adaptive_out = [str(adaptive[key]["outcome"]) for key in skeys]
        vector = [COST[b] - COST[a] for a, b in zip(control_out, adaptive_out, strict=True)]
        point = mean(vector)
        points.append(point)
        by_stratum[stratum] = vector
        result["strata"][stratum] = {
            "n": len(vector),
            "control_rates": rates(control_out),
            "adaptive_rates": rates(adaptive_out),
            "control_failure_cost": cost(control_out),
            "adaptive_failure_cost": cost(adaptive_out),
            "adaptive_minus_control_failure_cost": point,
            "paired_bootstrap_95": bootstrap(vector, reps, seed + 100 + ordinal),
        }
    result["macro_equal_stratum"] = {
        "n_strata": 18,
        "adaptive_minus_control_failure_cost": mean(points),
        "stratified_bootstrap_95": stratified_bootstrap(by_stratum, reps, seed + 999),
        "nonworse_strata": sum(value <= 0.0 for value in points),
        "improved_strata": sum(value < 0.0 for value in points),
        "worst_stratum_regression": max(points),
        "best_stratum_improvement": min(points),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--generalist", required=True)
    parser.add_argument("--policy-report", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary-out", required=True)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=141421)
    parser.add_argument("--min-effect", type=float, default=0.02)
    parser.add_argument("--min-nonworse-strata", type=int, default=12)
    parser.add_argument("--max-stratum-regression", type=float, default=0.10)
    parser.add_argument("--max-excluded", type=int, default=2)
    parser.add_argument("--max-excluded-fraction", type=float, default=0.001)
    args = parser.parse_args()
    if args.bootstrap < 10000:
        parser.error("W1 requires at least 10000 bootstrap replicates")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if manifest.get("same_pools") is not True or manifest.get("same_search_budget") is not True:
        parser.error("W1 requires identical pools and search budget")
    sets = manifest.get("report_sets", {})
    if set(sets) != {"control", "adaptive"}:
        parser.error("W1 manifest requires control and adaptive report sets")
    try:
        control_raw = load_report_set(list(sets["control"]))
        adaptive_raw = load_report_set(list(sets["adaptive"]))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    if set(control_raw) != set(adaptive_raw):
        parser.error("control and adaptive keys differ before cleaning")
    all_keys = sorted(control_raw)
    if len(all_keys) != 2 * 18 * 64:
        parser.error(f"expected 2304 preregistered E64/F64 positions, got {len(all_keys)}")
    errors = []
    excluded = set()
    for key in all_keys:
        for arm, row in (("control", control_raw[key]), ("adaptive", adaptive_raw[key])):
            if "error" in row:
                error = str(row["error"])
                if "no match" not in error.lower() and "timeout" not in error.lower():
                    parser.error(f"non-timeout engine error at {key}/{arm}: {error}")
                excluded.add(key)
                errors.append({"arm": arm, "pool": key[0], "index": key[1], "error": error})
    if len(excluded) > args.max_excluded or len(excluded) / len(all_keys) > args.max_excluded_fraction:
        parser.error("exclusions exceed preregistered limit")
    keys = [key for key in all_keys if key not in excluded]
    if {str(control_raw[key]["stratum"]) for key in keys} != EXPECTED_STRATA:
        parser.error("cleaned data do not cover all 18 strata")

    arms = {"control": summarize_arm(control_raw, keys), "adaptive": summarize_arm(adaptive_raw, keys)}
    paired = paired_view(control_raw, adaptive_raw, keys, args.bootstrap, args.seed)
    macro = paired["macro_equal_stratum"]
    pool_deltas = [float(item["adaptive_minus_control_failure_cost"]) for item in paired["pools"].values()]
    primary_pass = (
        float(macro["adaptive_minus_control_failure_cost"]) <= -args.min_effect
        and float(macro["stratified_bootstrap_95"][1]) <= 0.0
        and all(value <= 0.0 for value in pool_deltas)
        and int(macro["nonworse_strata"]) >= args.min_nonworse_strata
        and float(macro["worst_stratum_regression"]) <= args.max_stratum_regression
    )
    generalist = json.loads(Path(args.generalist).read_text(encoding="utf-8"))
    if generalist.get("protocol") != "l3-imbalance2-w1-paired-generalist-guard":
        parser.error("unexpected generalist guard protocol")
    policy = json.loads(Path(args.policy_report).read_text(encoding="utf-8"))
    if policy.get("protocol") != "l3-imbalance2-w1-stratum-adaptive-resample":
        parser.error("unexpected adaptive policy report")
    overall_pass = primary_pass and bool(generalist.get("pass"))
    decision = "W1_ADAPTIVE_SCREEN_PASS_REVIEW_CONFIRMATION" if overall_pass else "W1_ADAPTIVE_NO_GO"
    payload = {
        "schema": 1,
        "protocol": "l3-imbalance2-w1-stratum-adaptive-screen",
        "decision": decision,
        "recommendation_for_human_review": "DESIGN_FRESH_C512_CROSSFIT_CONFIRMATION" if overall_pass else "REJECT_CURRENT_STRATUM_WEIGHT_POLICY",
        "source_corpus": "immutable_0852_g4_source_same_bytes_both_arms",
        "selfplay_training_games": 0,
        "scan_used_for_training_labels": False,
        "oracle_used_for_sampling_weights": True,
        "teacher_calibrated_specialist_only": True,
        "new_eval_pools": {"names": ["E64", "F64"], "seed": args.seed, "per_stratum": 64},
        "excluded_positions": [{"pool": key[0], "index": key[1]} for key in sorted(excluded)],
        "error_details": errors,
        "arms": arms,
        "paired": paired,
        "generalist_gate": generalist,
        "adaptive_policy": policy,
        "gates": {
            "primary_pass": primary_pass,
            "generalist_pass": generalist.get("pass"),
            "overall_pass": overall_pass,
            "min_effect": args.min_effect,
            "min_nonworse_strata": args.min_nonworse_strata,
            "max_stratum_regression": args.max_stratum_regression,
        },
        "confirmation_requires_fresh_c512_crossfit": True,
        "training_continuation_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "verdict": decision,
        "macro_delta_adaptive_minus_control": macro["adaptive_minus_control_failure_cost"],
        "macro_ci95": macro["stratified_bootstrap_95"],
        "nonworse_strata": macro["nonworse_strata"],
        "pool_deltas": {k: v["adaptive_minus_control_failure_cost"] for k, v in paired["pools"].items()},
        "generalist_adaptive_score": generalist.get("adaptive_score_rate"),
        "generalist_pass": generalist.get("pass"),
        "confirmation_requires_fresh_c512_crossfit": True,
        "training_continuation_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
        "result_file": "w1-adaptive-screen-decision.json",
    }
    Path(args.summary_out).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
