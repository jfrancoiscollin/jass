#!/usr/bin/env python3
"""Compare two L3-IMBALANCE2 P1 lineages on identical plateau pools.

The input manifest maps each lineage and generation to candidate-only shard
reports produced by ``imbalance2_scan_gate.py run``. Outcomes are paired by
pool and index. A negative V2-minus-V1 failure-cost delta favours the
role-aware V2 lineage.

The primary report is stratified by material stratum. An optional difficulty
reference adds exact EGDB WDL distributions for 1v3/2v4 and Scan self-play
references for 3v5..18v20. The reference is descriptive only: it is not used
for training, weighting, or the V1-vs-V2 lead rule.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import random
from pathlib import Path

CATS = ("win", "draw", "loss")
COST = {"win": 0.0, "draw": 1.0, "loss": 2.0}


def ordered_generations(mapping: dict[str, object]) -> list[str]:
    ordered = sorted(mapping, key=lambda value: int(str(value).lstrip("Gg")))
    numbers = [int(value.lstrip("Gg")) for value in ordered]
    if len(ordered) < 4 or numbers != list(range(numbers[0], numbers[0] + len(numbers))):
        raise ValueError("each lineage requires at least four consecutive generations")
    return ordered


def stratum_order(value: str) -> int:
    return int(value.split("v", 1)[0])


def load_generation(paths: list[str]) -> dict[tuple[str, int], dict[str, str]]:
    rows: dict[tuple[str, int], dict[str, str]] = {}
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("engine") != "candidate":
            raise ValueError(f"{path}: comparison accepts candidate-only reports")
        pool = Path(str(payload.get("pool", ""))).name
        if pool not in {"plateau-a.jnnw", "plateau-b.jnnw"}:
            raise ValueError(f"{path}: unexpected plateau pool {pool!r}")
        for row in payload.get("rows", []):
            if "error" in row:
                raise ValueError(f"{path}: engine error at index {row.get('index')}")
            key = (pool, int(row["index"]))
            if key in rows:
                raise ValueError(f"{path}: duplicate paired key {key}")
            outcome = str(row["outcome"])
            if outcome not in COST:
                raise ValueError(f"{path}: invalid outcome {outcome!r}")
            rows[key] = {"outcome": outcome, "stratum": str(row["stratum"])}
    return rows


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("empty comparison vector")
    return sum(values) / len(values)


def interval(values: list[float], alpha: float = 0.05) -> list[float]:
    values.sort()
    n = len(values)
    return [values[int((alpha / 2) * (n - 1))], values[int((1 - alpha / 2) * (n - 1))]]


def bootstrap(values: list[float], reps: int, seed: int) -> list[float]:
    if not values:
        raise ValueError("empty comparison vector")
    rng = random.Random(seed)
    n = len(values)
    samples = [mean([values[rng.randrange(n)] for _ in range(n)]) for _ in range(reps)]
    return interval(samples)


def stratified_bootstrap(groups: dict[str, list[float]], reps: int, seed: int) -> list[float]:
    if not groups or any(not values for values in groups.values()):
        raise ValueError("empty stratified comparison vector")
    rng = random.Random(seed)
    samples: list[float] = []
    ordered = [groups[name] for name in sorted(groups, key=stratum_order)]
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


def rate_delta(observed: dict[str, float], reference: dict[str, float]) -> dict[str, float]:
    return {cat: observed[cat] - reference[cat] for cat in CATS}


def comparison(
    v1: dict[tuple[str, int], dict[str, str]],
    v2: dict[tuple[str, int], dict[str, str]],
    keys: list[tuple[str, int]],
    reps: int,
    seed: int,
    reference: dict[str, object] | None = None,
) -> dict[str, object]:
    v1_outcomes = [v1[key]["outcome"] for key in keys]
    v2_outcomes = [v2[key]["outcome"] for key in keys]
    deltas = [COST[b] - COST[a] for a, b in zip(v1_outcomes, v2_outcomes, strict=True)]
    v1_rates = rates(v1_outcomes)
    v2_rates = rates(v2_outcomes)
    report: dict[str, object] = {
        "n": len(keys),
        "v1_failure_cost_2loss_plus_draw": mean([COST[value] for value in v1_outcomes]),
        "v2_failure_cost_2loss_plus_draw": mean([COST[value] for value in v2_outcomes]),
        "v2_minus_v1_failure_cost": mean(deltas),
        "paired_bootstrap_95": bootstrap(deltas, reps, seed),
        "v1_rates": v1_rates,
        "v2_rates": v2_rates,
    }
    if reference is not None:
        reference_rates = {cat: float(reference["rates"][cat]) for cat in CATS}
        reference_cost = float(reference["failure_cost_2loss_plus_draw"])
        report["difficulty_reference"] = {
            "source": reference["source"],
            "n": reference["n"],
            "total_pieces": reference["total_pieces"],
            "rates": reference_rates,
            "failure_cost_2loss_plus_draw": reference_cost,
            "reference_is_exact": reference["source"] == "exact_egdb_wdl",
        }
        report["v1_minus_reference_failure_cost"] = (
            float(report["v1_failure_cost_2loss_plus_draw"]) - reference_cost
        )
        report["v2_minus_reference_failure_cost"] = (
            float(report["v2_failure_cost_2loss_plus_draw"]) - reference_cost
        )
        report["v1_minus_reference_rates"] = rate_delta(v1_rates, reference_rates)
        report["v2_minus_reference_rates"] = rate_delta(v2_rates, reference_rates)
    return report


def macro_from_strata(strata: dict[str, dict[str, object]], reps: int, seed: int) -> dict[str, object]:
    deltas_by_stratum: dict[str, list[float]] = {}
    for name, report in strata.items():
        deltas_by_stratum[name] = list(report.pop("_paired_deltas"))
    macro: dict[str, object] = {
        "n_strata": len(strata),
        "v1_failure_cost_2loss_plus_draw": mean(
            [float(report["v1_failure_cost_2loss_plus_draw"]) for report in strata.values()]
        ),
        "v2_failure_cost_2loss_plus_draw": mean(
            [float(report["v2_failure_cost_2loss_plus_draw"]) for report in strata.values()]
        ),
        "v2_minus_v1_failure_cost": mean(
            [float(report["v2_minus_v1_failure_cost"]) for report in strata.values()]
        ),
        "stratified_bootstrap_95": stratified_bootstrap(deltas_by_stratum, reps, seed),
    }
    if all("v1_minus_reference_failure_cost" in report for report in strata.values()):
        macro["v1_minus_reference_failure_cost"] = mean(
            [float(report["v1_minus_reference_failure_cost"]) for report in strata.values()]
        )
        macro["v2_minus_reference_failure_cost"] = mean(
            [float(report["v2_minus_reference_failure_cost"]) for report in strata.values()]
        )
    return macro


def load_reference(path: str | None) -> dict[str, dict[str, object]] | None:
    if path is None:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("protocol") != "material-stratified-conversion-difficulty-reference":
        raise ValueError("unexpected difficulty-reference protocol")
    if payload.get("reference_used_for_training") is not False:
        raise ValueError("difficulty reference must not be a training input")
    if payload.get("scan_reference_is_exact") is not False:
        raise ValueError("Scan reference must be marked non-exact")
    strata = payload.get("strata", {})
    expected = {f"{n}v{n+2}" for n in range(1, 19)}
    if set(strata) != expected:
        raise ValueError("difficulty reference must cover all 18 strata")
    return strata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=161803)
    parser.add_argument("--min-effect", type=float, default=0.02)
    parser.add_argument("--reference")
    args = parser.parse_args()
    if args.bootstrap < 1000:
        parser.error("bootstrap must use at least 1000 replicates")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if manifest.get("same_pools") is not True or manifest.get("same_search_budget") is not True:
        parser.error("comparison requires identical pools and search budgets")
    lineages = manifest.get("lineages", {})
    if set(lineages) != {"v1", "v2"}:
        parser.error("manifest must contain exactly v1 and v2 lineages")

    generations = ordered_generations(lineages["v1"])
    if ordered_generations(lineages["v2"]) != generations:
        parser.error("v1 and v2 generation windows differ")

    loaded: dict[str, dict[str, dict[tuple[str, int], dict[str, str]]]] = {
        lineage: {
            generation: load_generation(list(lineages[lineage][generation]))
            for generation in generations
        }
        for lineage in ("v1", "v2")
    }

    expected_keys = set(loaded["v1"][generations[0]])
    if not expected_keys:
        parser.error("no plateau rows")
    for lineage in ("v1", "v2"):
        for generation in generations:
            if set(loaded[lineage][generation]) != expected_keys:
                parser.error(f"{lineage} {generation}: plateau rows are not perfectly paired")

    pools: dict[str, list[tuple[str, int]]] = defaultdict(list)
    strata_keys: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key in sorted(expected_keys):
        pools[key[0]].append(key)
        stratum = loaded["v1"][generations[0]][key]["stratum"]
        if loaded["v2"][generations[0]][key]["stratum"] != stratum:
            parser.error(f"stratum mismatch at {key}")
        strata_keys[stratum].append(key)
    if set(pools) != {"plateau-a.jnnw", "plateau-b.jnnw"}:
        parser.error("both plateau pools A and B are required")
    expected_strata = {f"{n}v{n+2}" for n in range(1, 19)}
    if set(strata_keys) != expected_strata:
        parser.error("comparison must cover all 18 material strata")

    reference = load_reference(args.reference)
    generation_reports: dict[str, object] = {}
    for generation_index, generation in enumerate(generations):
        report = comparison(
            loaded["v1"][generation],
            loaded["v2"][generation],
            sorted(expected_keys),
            args.bootstrap,
            args.seed + generation_index * 100,
        )
        report["pools"] = {
            pool: comparison(
                loaded["v1"][generation],
                loaded["v2"][generation],
                keys,
                args.bootstrap,
                args.seed + generation_index * 100 + pool_index + 1,
            )
            for pool_index, (pool, keys) in enumerate(sorted(pools.items()))
        }
        stratum_reports: dict[str, dict[str, object]] = {}
        for stratum_index, stratum in enumerate(sorted(strata_keys, key=stratum_order)):
            keys = strata_keys[stratum]
            item = comparison(
                loaded["v1"][generation],
                loaded["v2"][generation],
                keys,
                args.bootstrap,
                args.seed + generation_index * 1000 + stratum_index + 100,
                reference[stratum] if reference is not None else None,
            )
            item["_paired_deltas"] = [
                COST[loaded["v2"][generation][key]["outcome"]]
                - COST[loaded["v1"][generation][key]["outcome"]]
                for key in keys
            ]
            stratum_reports[stratum] = item
        report["strata"] = stratum_reports
        report["macro_equal_stratum"] = macro_from_strata(
            stratum_reports,
            args.bootstrap,
            args.seed + generation_index * 1000 + 999,
        )
        generation_reports[generation] = report

    final_generation = generations[-1]
    final = generation_reports[final_generation]
    final_macro = final["macro_equal_stratum"]
    final_delta = float(final_macro["v2_minus_v1_failure_cost"])
    final_ci = list(final_macro["stratified_bootstrap_95"])
    pool_deltas = [
        float(payload["v2_minus_v1_failure_cost"])
        for payload in final["pools"].values()
    ]
    clear_lead = (
        final_delta <= -args.min_effect
        and final_ci[1] <= 0.0
        and all(delta <= 0.0 for delta in pool_deltas)
    )

    payload = {
        "schema": 2,
        "protocol": "paired-p1-v1-vs-role-v2-on-common-a64-b64",
        "lineage_v1": "L3-IMBALANCE2",
        "lineage_v2": "L3-IMBALANCE2-ROLE-V2",
        "generations": generations,
        "same_pools": True,
        "same_search_budget": True,
        "difficulty_reference_used_for_reporting": reference is not None,
        "difficulty_reference_used_for_training": False,
        "difficulty_reference_used_in_lead_rule": False,
        "external_references_used": reference is not None,
        "metric": "stratum_equal_weight_material_up_failure_cost_2loss_plus_draw",
        "raw_global_metric_retained_as_secondary": True,
        "negative_delta_favours": "v2",
        "generation_reports": generation_reports,
        "final_generation": final_generation,
        "lead_rule": {
            "minimum_macro_cost_improvement": args.min_effect,
            "stratified_ci_upper_must_be_at_most_zero": True,
            "both_pool_point_deltas_must_be_nonpositive": True,
            "difficulty_reference_not_used": True,
        },
        "v2_clear_lead": clear_lead,
        "decision": "V2_CLEAR_LEAD_AT_P1" if clear_lead else "V2_NO_CLEAR_LEAD_AT_P1",
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
