#!/usr/bin/env python3
"""Evaluate L3-IMBALANCE2 progress from a parent generation through one phase.

The cleaned input manifest maps five consecutive candidate-only report sets,
normally G4..G8, to the same A64/B64 positions and search budget. The primary
metric is the equal-weight macro average across the eighteen material strata.
Raw global and per-pool metrics remain secondary diagnostics.

An optional material-difficulty reference (exact EGDB for 1v3/2v4, empirical
Scan for 3v5..18v20) is joined for interpretation only. It never enters the
causal improvement rule, training, weighting, or automatic continuation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import random
from pathlib import Path

CATS = ("win", "draw", "loss")
COST = {"win": 0.0, "draw": 1.0, "loss": 2.0}
EXPECTED_POOLS = {"plateau-a.jnnw", "plateau-b.jnnw"}
EXPECTED_STRATA = {f"{n}v{n + 2}" for n in range(1, 19)}


def generation_number(value: str) -> int:
    return int(str(value).lstrip("Gg"))


def stratum_number(value: str) -> int:
    return int(value.split("v", 1)[0])


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("empty vector")
    return sum(values) / len(values)


def interval(values: list[float], alpha: float = 0.05) -> list[float]:
    if not values:
        raise ValueError("empty bootstrap vector")
    values.sort()
    n = len(values)
    return [
        values[int((alpha / 2) * (n - 1))],
        values[int((1 - alpha / 2) * (n - 1))],
    ]


def bootstrap(values: list[float], reps: int, seed: int) -> list[float]:
    if not values:
        raise ValueError("empty comparison vector")
    rng = random.Random(seed)
    n = len(values)
    return interval(
        [mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(reps)]
    )


def stratified_bootstrap(
    values_by_stratum: dict[str, list[float]], reps: int, seed: int
) -> list[float]:
    if set(values_by_stratum) != EXPECTED_STRATA:
        raise ValueError("stratified bootstrap requires all 18 strata")
    if any(not values for values in values_by_stratum.values()):
        raise ValueError("empty stratum vector")
    rng = random.Random(seed)
    ordered = [values_by_stratum[s] for s in sorted(values_by_stratum, key=stratum_number)]
    samples = []
    for _ in range(reps):
        stratum_means = []
        for values in ordered:
            n = len(values)
            stratum_means.append(mean([values[rng.randrange(n)] for _ in range(n)]))
        samples.append(mean(stratum_means))
    return interval(samples)


def rates(outcomes: list[str]) -> dict[str, float]:
    if not outcomes:
        raise ValueError("empty outcome vector")
    return {cat: outcomes.count(cat) / len(outcomes) for cat in CATS}


def cost(outcomes: list[str]) -> float:
    return mean([COST[outcome] for outcome in outcomes])


def load_set(paths: list[str]) -> dict[tuple[str, int], dict[str, str]]:
    rows: dict[tuple[str, int], dict[str, str]] = {}
    for raw_path in paths:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("engine") != "candidate":
            raise ValueError(f"{path}: phase progress accepts candidate-only reports")
        pool = Path(str(payload.get("pool", ""))).name
        if pool not in EXPECTED_POOLS:
            raise ValueError(f"{path}: unexpected pool {pool!r}")
        for row in payload.get("rows", []):
            if "error" in row:
                raise ValueError(f"{path}: uncleaned engine error at index {row.get('index')}")
            key = (pool, int(row["index"]))
            if key in rows:
                raise ValueError(f"{path}: duplicate paired key {key}")
            outcome = str(row.get("outcome"))
            stratum = str(row.get("stratum"))
            if outcome not in COST:
                raise ValueError(f"{path}: invalid outcome {outcome!r}")
            if stratum not in EXPECTED_STRATA:
                raise ValueError(f"{path}: invalid stratum {stratum!r}")
            rows[key] = {"outcome": outcome, "stratum": stratum}
    return rows


def load_reference(path: str | None) -> dict[str, dict[str, object]] | None:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("protocol") != "material-stratified-conversion-difficulty-reference":
        raise ValueError("unexpected difficulty-reference protocol")
    if payload.get("reference_used_for_training") is not False:
        raise ValueError("difficulty reference must not be a training input")
    if payload.get("scan_reference_is_exact") is not False:
        raise ValueError("Scan reference must remain explicitly non-exact")
    strata = payload.get("strata", {})
    if set(strata) != EXPECTED_STRATA:
        raise ValueError("difficulty reference must cover all 18 strata")
    return strata


def summarize_generation(
    data: dict[tuple[str, int], dict[str, str]],
    keys: list[tuple[str, int]],
    pools: dict[str, list[tuple[str, int]]],
    strata_keys: dict[str, list[tuple[str, int]]],
    reference: dict[str, dict[str, object]] | None,
) -> dict[str, object]:
    all_outcomes = [data[key]["outcome"] for key in keys]
    result: dict[str, object] = {
        "n": len(keys),
        "rates": rates(all_outcomes),
        "failure_cost_2loss_plus_draw": cost(all_outcomes),
        "pools": {},
        "strata": {},
    }
    for pool, pool_keys in sorted(pools.items()):
        outcomes = [data[key]["outcome"] for key in pool_keys]
        result["pools"][pool] = {
            "n": len(pool_keys),
            "rates": rates(outcomes),
            "failure_cost_2loss_plus_draw": cost(outcomes),
        }
    stratum_costs = []
    reference_deltas = []
    for stratum in sorted(strata_keys, key=stratum_number):
        s_keys = strata_keys[stratum]
        outcomes = [data[key]["outcome"] for key in s_keys]
        item: dict[str, object] = {
            "n": len(s_keys),
            "rates": rates(outcomes),
            "failure_cost_2loss_plus_draw": cost(outcomes),
        }
        stratum_costs.append(float(item["failure_cost_2loss_plus_draw"]))
        if reference is not None:
            ref = reference[stratum]
            ref_cost = float(ref["failure_cost_2loss_plus_draw"])
            item["difficulty_reference"] = {
                "source": ref["source"],
                "n": ref["n"],
                "total_pieces": ref["total_pieces"],
                "rates": ref["rates"],
                "failure_cost_2loss_plus_draw": ref_cost,
                "reference_is_exact": ref["source"] == "exact_egdb_wdl",
            }
            item["minus_reference_failure_cost"] = (
                float(item["failure_cost_2loss_plus_draw"]) - ref_cost
            )
            reference_deltas.append(float(item["minus_reference_failure_cost"]))
        result["strata"][stratum] = item
    result["macro_equal_stratum"] = {
        "n_strata": len(stratum_costs),
        "failure_cost_2loss_plus_draw": mean(stratum_costs),
    }
    if reference_deltas:
        result["macro_equal_stratum"]["minus_reference_failure_cost"] = mean(
            reference_deltas
        )
    return result


def paired_view(
    first: dict[tuple[str, int], dict[str, str]],
    last: dict[tuple[str, int], dict[str, str]],
    keys: list[tuple[str, int]],
    pools: dict[str, list[tuple[str, int]]],
    strata_keys: dict[str, list[tuple[str, int]]],
    reps: int,
    seed: int,
) -> dict[str, object]:
    first_outcomes = [first[key]["outcome"] for key in keys]
    last_outcomes = [last[key]["outcome"] for key in keys]
    deltas = [
        COST[b] - COST[a] for a, b in zip(first_outcomes, last_outcomes, strict=True)
    ]
    result: dict[str, object] = {
        "n": len(keys),
        "first_failure_cost_2loss_plus_draw": cost(first_outcomes),
        "last_failure_cost_2loss_plus_draw": cost(last_outcomes),
        "last_minus_first_failure_cost": mean(deltas),
        "paired_bootstrap_95": bootstrap(deltas, reps, seed),
        "pools": {},
        "strata": {},
    }
    for pool_index, (pool, pool_keys) in enumerate(sorted(pools.items())):
        a = [first[key]["outcome"] for key in pool_keys]
        b = [last[key]["outcome"] for key in pool_keys]
        pool_deltas = [COST[y] - COST[x] for x, y in zip(a, b, strict=True)]
        result["pools"][pool] = {
            "n": len(pool_keys),
            "first_failure_cost_2loss_plus_draw": cost(a),
            "last_failure_cost_2loss_plus_draw": cost(b),
            "last_minus_first_failure_cost": mean(pool_deltas),
            "paired_bootstrap_95": bootstrap(
                pool_deltas, reps, seed + pool_index + 1
            ),
        }
    macro_deltas: dict[str, list[float]] = {}
    point_deltas = []
    for stratum_index, stratum in enumerate(sorted(strata_keys, key=stratum_number)):
        s_keys = strata_keys[stratum]
        a = [first[key]["outcome"] for key in s_keys]
        b = [last[key]["outcome"] for key in s_keys]
        s_deltas = [COST[y] - COST[x] for x, y in zip(a, b, strict=True)]
        point = mean(s_deltas)
        point_deltas.append(point)
        macro_deltas[stratum] = s_deltas
        result["strata"][stratum] = {
            "n": len(s_keys),
            "first_failure_cost_2loss_plus_draw": cost(a),
            "last_failure_cost_2loss_plus_draw": cost(b),
            "last_minus_first_failure_cost": point,
            "paired_bootstrap_95": bootstrap(
                s_deltas, reps, seed + 100 + stratum_index
            ),
            "first_rates": rates(a),
            "last_rates": rates(b),
        }
    result["macro_equal_stratum"] = {
        "n_strata": len(point_deltas),
        "last_minus_first_failure_cost": mean(point_deltas),
        "stratified_bootstrap_95": stratified_bootstrap(
            macro_deltas, reps, seed + 999
        ),
        "nonworse_strata": sum(delta <= 0.0 for delta in point_deltas),
        "improved_strata": sum(delta < 0.0 for delta in point_deltas),
        "worst_stratum_regression": max(point_deltas),
        "best_stratum_improvement": min(point_deltas),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--reference")
    parser.add_argument("--exclusions")
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=161806)
    parser.add_argument("--baseline-generation", default="G4")
    parser.add_argument("--phase-start-generation", default="G5")
    parser.add_argument("--phase-end-generation", default="G8")
    parser.add_argument("--min-effect", type=float, default=0.02)
    parser.add_argument("--min-nonworse-strata", type=int, default=12)
    parser.add_argument("--max-stratum-regression", type=float, default=0.10)
    parser.add_argument("--max-plateau-last3-range", type=float, default=0.04)
    args = parser.parse_args()
    if args.bootstrap < 1000:
        parser.error("bootstrap must use at least 1000 replicates")
    if not 0 <= args.min_nonworse_strata <= 18:
        parser.error("min nonworse strata must be between zero and eighteen")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if manifest.get("same_pools") is not True or manifest.get("same_search_budget") is not True:
        parser.error("phase progress requires identical pools and search budget")
    report_sets = manifest.get("report_sets", {})
    ordered = sorted(report_sets, key=generation_number)
    expected = [
        args.baseline_generation,
        args.phase_start_generation,
        *[
            f"G{n}"
            for n in range(
                generation_number(args.phase_start_generation) + 1,
                generation_number(args.phase_end_generation),
            )
        ],
        args.phase_end_generation,
    ]
    if ordered != expected:
        parser.error(f"expected consecutive report sets {expected}, got {ordered}")

    data = {name: load_set(list(report_sets[name])) for name in ordered}
    keys = set(data[ordered[0]])
    if not keys:
        parser.error("no paired positions")
    for name in ordered[1:]:
        if set(data[name]) != keys:
            parser.error(f"{name}: cleaned report keys are not perfectly paired")
        for key in keys:
            if data[name][key]["stratum"] != data[ordered[0]][key]["stratum"]:
                parser.error(f"{name}: stratum mismatch at {key}")

    pools: dict[str, list[tuple[str, int]]] = defaultdict(list)
    strata_keys: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key in sorted(keys):
        pools[key[0]].append(key)
        strata_keys[data[ordered[0]][key]["stratum"]].append(key)
    if set(pools) != EXPECTED_POOLS:
        parser.error("both A64/B64 pools are required")
    if set(strata_keys) != EXPECTED_STRATA:
        parser.error("all 18 material strata are required")

    reference = load_reference(args.reference)
    generation_reports = {
        name: summarize_generation(
            data[name], sorted(keys), pools, strata_keys, reference
        )
        for name in ordered
    }

    baseline = args.baseline_generation
    phase_start = args.phase_start_generation
    phase_end = args.phase_end_generation
    comparisons = {}
    for offset, name in enumerate(ordered[1:], 1):
        comparisons[f"{baseline}_to_{name}"] = paired_view(
            data[baseline],
            data[name],
            sorted(keys),
            pools,
            strata_keys,
            args.bootstrap,
            args.seed + offset * 10000,
        )
    comparisons[f"{phase_start}_to_{phase_end}"] = paired_view(
        data[phase_start],
        data[phase_end],
        sorted(keys),
        pools,
        strata_keys,
        args.bootstrap,
        args.seed + 90000,
    )

    final_comparison = comparisons[f"{baseline}_to_{phase_end}"]
    final_macro = final_comparison["macro_equal_stratum"]
    final_pool_deltas = [
        float(item["last_minus_first_failure_cost"])
        for item in final_comparison["pools"].values()
    ]
    clear_broad_improvement = (
        float(final_macro["last_minus_first_failure_cost"]) <= -args.min_effect
        and float(final_macro["stratified_bootstrap_95"][1]) <= 0.0
        and all(delta <= 0.0 for delta in final_pool_deltas)
        and int(final_macro["nonworse_strata"]) >= args.min_nonworse_strata
        and float(final_macro["worst_stratum_regression"]) <= args.max_stratum_regression
    )

    phase_view = comparisons[f"{phase_start}_to_{phase_end}"]
    pool_plateau = {}
    plateau_confirmed = True
    phase_generations = ordered[1:]
    for pool in sorted(pools):
        costs = {
            generation: float(generation_reports[generation]["pools"][pool]["failure_cost_2loss_plus_draw"])
            for generation in phase_generations
        }
        pair = phase_view["pools"][pool]
        delta = float(pair["last_minus_first_failure_cost"])
        ci = list(pair["paired_bootstrap_95"])
        improvement = -delta
        last3 = [costs[generation] for generation in phase_generations[-3:]]
        passed = (
            improvement <= args.min_effect
            and ci[0] <= 0.0 <= ci[1]
            and max(last3) - min(last3) <= args.max_plateau_last3_range
        )
        plateau_confirmed &= passed
        pool_plateau[pool] = {
            "n": len(pools[pool]),
            "failure_cost_2loss_plus_draw": costs,
            "last_minus_first": delta,
            "first_to_last_improvement": improvement,
            "paired_bootstrap_95": ci,
            "last3_range": max(last3) - min(last3),
            "pass": passed,
        }

    if clear_broad_improvement:
        decision = "P2_CLEAR_BROAD_IMPROVEMENT"
        recommendation = "REVIEW_P3_ONLY_AFTER_GENERALIST_AND_EXTERNAL_GATES"
    elif plateau_confirmed:
        decision = "P2_PLATEAU_NO_CLEAR_IMPROVEMENT"
        recommendation = "STOP_BEFORE_P3_REDESIGN"
    else:
        decision = "P2_NO_CLEAR_IMPROVEMENT_OR_UNSTABLE"
        recommendation = "STOP_BEFORE_P3_REDESIGN"

    exclusions = None
    if args.exclusions:
        exclusions = json.loads(Path(args.exclusions).read_text(encoding="utf-8"))

    payload = {
        "schema": 1,
        "protocol": "role-v2-g4-to-g8-common-a64-b64-stratified-progress",
        "lineage": "L3-IMBALANCE2-ROLE-V2",
        "generations": ordered,
        "baseline_generation": baseline,
        "phase_generations": phase_generations,
        "same_pools": True,
        "same_search_budget": True,
        "metric": "stratum_equal_weight_material_up_failure_cost_2loss_plus_draw",
        "raw_global_metric_retained_as_secondary": True,
        "difficulty_reference_used_for_reporting": reference is not None,
        "difficulty_reference_used_for_training": False,
        "difficulty_reference_used_in_decision_rule": False,
        "scan_reference_is_exact": False if reference is not None else None,
        "symmetric_exclusion": exclusions,
        "generation_reports": generation_reports,
        "comparisons": comparisons,
        "p2_plateau": {
            "confirmed": plateau_confirmed,
            "pool_reports": pool_plateau,
            "thresholds": {
                "max_first_to_last_improvement": args.min_effect,
                "paired_ci_must_include_zero": True,
                "max_last3_range": args.max_plateau_last3_range,
            },
        },
        "clear_broad_improvement": clear_broad_improvement,
        "decision_rule": {
            "minimum_macro_cost_improvement": args.min_effect,
            "stratified_ci_upper_must_be_at_most_zero": True,
            "both_pool_point_deltas_must_be_nonpositive": True,
            "minimum_nonworse_strata": args.min_nonworse_strata,
            "maximum_single_stratum_regression": args.max_stratum_regression,
            "difficulty_reference_not_used": True,
        },
        "decision": decision,
        "recommendation_for_review": recommendation,
        "promotion_authorized": False,
        "p3_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
