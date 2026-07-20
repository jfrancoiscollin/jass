#!/usr/bin/env python3
"""Aggregate the D1-RC4 screen and apply its preregistered no-go gate.

Primary evidence is paired C64/D64 self-play, macro-averaged equally over the 18
material strata.  D0 sentinel correction, throughput and a paired generalist
match are secondary vetoes.  A pass only recommends human review of D1-B; it
never authorizes continuation or promotion automatically.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import random
from pathlib import Path

CATS = ("win", "draw", "loss")
COST = {"win": 0.0, "draw": 1.0, "loss": 2.0}
EXPECTED_POOLS = {"plateau-c.jnnw", "plateau-d.jnnw"}
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
            raise ValueError(f"{path}: unexpected D1 pool {pool!r}")
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


def paired_view(
    control: dict[tuple[str, int], dict[str, object]],
    rc4: dict[tuple[str, int], dict[str, object]],
    keys: list[tuple[str, int]],
    reps: int,
    seed: int,
) -> dict[str, object]:
    pools: dict[str, list[tuple[str, int]]] = defaultdict(list)
    strata: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for key in keys:
        pools[key[0]].append(key)
        strata[str(control[key]["stratum"])].append(key)

    deltas = [COST[str(rc4[key]["outcome"])] - COST[str(control[key]["outcome"])] for key in keys]
    result: dict[str, object] = {
        "n": len(keys),
        "rc4_minus_control_failure_cost": mean(deltas),
        "paired_bootstrap_95": bootstrap(deltas, reps, seed),
        "pools": {},
        "strata": {},
    }
    for ordinal, (pool, pkeys) in enumerate(sorted(pools.items())):
        vector = [COST[str(rc4[key]["outcome"])] - COST[str(control[key]["outcome"])] for key in pkeys]
        result["pools"][pool] = {
            "n": len(vector),
            "rc4_minus_control_failure_cost": mean(vector),
            "paired_bootstrap_95": bootstrap(vector, reps, seed + ordinal + 1),
        }

    by_stratum_delta: dict[str, list[float]] = {}
    points = []
    for ordinal, stratum in enumerate(sorted(strata, key=stratum_number)):
        skeys = strata[stratum]
        control_out = [str(control[key]["outcome"]) for key in skeys]
        rc4_out = [str(rc4[key]["outcome"]) for key in skeys]
        vector = [COST[b] - COST[a] for a, b in zip(control_out, rc4_out, strict=True)]
        point = mean(vector)
        points.append(point)
        by_stratum_delta[stratum] = vector
        result["strata"][stratum] = {
            "n": len(vector),
            "control_rates": rates(control_out),
            "rc4_rates": rates(rc4_out),
            "control_failure_cost": cost(control_out),
            "rc4_failure_cost": cost(rc4_out),
            "rc4_minus_control_failure_cost": point,
            "paired_bootstrap_95": bootstrap(vector, reps, seed + 100 + ordinal),
        }
    result["macro_equal_stratum"] = {
        "n_strata": 18,
        "rc4_minus_control_failure_cost": mean(points),
        "stratified_bootstrap_95": stratified_bootstrap(by_stratum_delta, reps, seed + 999),
        "nonworse_strata": sum(value <= 0.0 for value in points),
        "improved_strata": sum(value < 0.0 for value in points),
        "worst_stratum_regression": max(points),
        "best_stratum_improvement": min(points),
    }
    return result


def sentinel_gate(d0_path: str, replay_paths: list[str]) -> dict[str, object]:
    d0 = json.loads(Path(d0_path).read_text(encoding="utf-8"))
    cases = {str(item["sentinel_id"]): item for item in d0.get("cases", [])}
    if len(cases) != 30:
        raise ValueError("D1 requires all 30 D0 cases")
    rows: dict[tuple[str, str], dict[str, object]] = {}
    for raw_path in replay_paths:
        payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
        if payload.get("protocol") != "imbalance2-d1-rc4-sentinel-replay":
            raise ValueError(f"{raw_path}: unexpected sentinel protocol")
        for row in payload.get("rows", []):
            if "error" in row:
                raise ValueError(f"{raw_path}: sentinel engine error: {row['error']}")
            key = (str(row["sentinel_id"]), str(row["engine"]))
            if key in rows:
                raise ValueError(f"duplicate sentinel replay {key}")
            rows[key] = row
    expected = {(sentinel, engine) for sentinel in cases for engine in ("control", "rc4")}
    if set(rows) != expected:
        raise ValueError("sentinel replay matrix is incomplete")

    target_ids = [key for key, item in cases.items() if item["causal_hypothesis"] == "REPRESENTATION_OR_OBJECTIVE_CANDIDATE"]
    if len(target_ids) != 7:
        raise ValueError(f"expected seven representation/objective sentinels, found {len(target_ids)}")
    corrected = []
    target_details = []
    new_divergences = []
    all_details = []
    totals = {"control": {"nodes": 0, "seconds": 0.0}, "rc4": {"nodes": 0, "seconds": 0.0}}
    for sentinel_id, case in cases.items():
        anchor = str(case["scan_d14_anchor_move"])
        control_analysis = dict(rows[(sentinel_id, "control")]["analysis"])
        rc4_analysis = dict(rows[(sentinel_id, "rc4")]["analysis"])
        control_move = str(control_analysis["best_move"])
        rc4_move = str(rc4_analysis["best_move"])
        for engine, analysis in (("control", control_analysis), ("rc4", rc4_analysis)):
            nodes = analysis.get("nodes")
            elapsed = analysis.get("elapsed_seconds")
            if nodes is None or elapsed is None or float(elapsed) <= 0:
                raise ValueError(f"missing throughput fields for {sentinel_id}/{engine}")
            totals[engine]["nodes"] += int(nodes)
            totals[engine]["seconds"] += float(elapsed)
        detail = {
            "sentinel_id": sentinel_id,
            "hypothesis": case["causal_hypothesis"],
            "scan_anchor": anchor,
            "control_move": control_move,
            "rc4_move": rc4_move,
            "control_matches": control_move == anchor,
            "rc4_matches": rc4_move == anchor,
        }
        all_details.append(detail)
        if sentinel_id in target_ids:
            target_details.append(detail)
            if control_move != anchor and rc4_move == anchor:
                corrected.append(sentinel_id)
        elif control_move == anchor and rc4_move != anchor:
            new_divergences.append(sentinel_id)

    nps_control = totals["control"]["nodes"] / totals["control"]["seconds"]
    nps_rc4 = totals["rc4"]["nodes"] / totals["rc4"]["seconds"]
    ratio = nps_rc4 / nps_control
    return {
        "target_representation_cases": len(target_ids),
        "corrected_representation_cases": len(corrected),
        "corrected_ids": corrected,
        "new_divergences_non_target": len(new_divergences),
        "new_divergence_ids": new_divergences,
        "target_details": target_details,
        "all_details": all_details,
        "throughput": {
            "control_nodes_per_second": nps_control,
            "rc4_nodes_per_second": nps_rc4,
            "rc4_over_control": ratio,
            "minimum_ratio": 0.95,
            "pass": ratio >= 0.95,
        },
        "mechanism_pass": len(corrected) >= 4 and len(new_divergences) <= 2,
        "guards": {"min_corrected_representation_cases": 4, "max_new_divergences": 2},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--d0-report", required=True)
    parser.add_argument("--sentinel-inputs", nargs="+", required=True)
    parser.add_argument("--generalist", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=314159)
    parser.add_argument("--min-effect", type=float, default=0.02)
    parser.add_argument("--min-nonworse-strata", type=int, default=12)
    parser.add_argument("--max-stratum-regression", type=float, default=0.10)
    parser.add_argument("--max-excluded", type=int, default=2)
    parser.add_argument("--max-excluded-fraction", type=float, default=0.001)
    args = parser.parse_args()
    if args.bootstrap < 10000:
        parser.error("D1 requires at least 10000 bootstrap replicates")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if manifest.get("same_pools") is not True or manifest.get("same_search_budget") is not True:
        parser.error("D1 requires identical pools and search budget")
    sets = manifest.get("report_sets", {})
    if set(sets) != {"control", "rc4"}:
        parser.error("D1 manifest requires control and rc4 report sets")
    control_raw = load_report_set(list(sets["control"]))
    rc4_raw = load_report_set(list(sets["rc4"]))
    if set(control_raw) != set(rc4_raw):
        parser.error("control and RC4 keys differ before cleaning")
    all_keys = sorted(control_raw)
    if len(all_keys) != 2 * 18 * 64:
        parser.error(f"expected 2304 preregistered C64/D64 positions, got {len(all_keys)}")
    errors = []
    excluded = set()
    for key in all_keys:
        for arm, row in (("control", control_raw[key]), ("rc4", rc4_raw[key])):
            if "error" in row:
                error = str(row["error"])
                if "no match" not in error.lower() and "timeout" not in error.lower():
                    parser.error(f"non-timeout engine error at {key}/{arm}: {error}")
                excluded.add(key)
                errors.append({"arm": arm, "pool": key[0], "index": key[1], "error": error})
    if len(excluded) > args.max_excluded:
        parser.error("too many excluded positions")
    if len(excluded) / len(all_keys) > args.max_excluded_fraction:
        parser.error("excluded fraction exceeds preregistration")
    keys = [key for key in all_keys if key not in excluded]
    if {str(control_raw[key]["stratum"]) for key in keys} != EXPECTED_STRATA:
        parser.error("cleaned data do not cover all 18 strata")

    arms = {"control": summarize_arm(control_raw, keys), "rc4": summarize_arm(rc4_raw, keys)}
    paired = paired_view(control_raw, rc4_raw, keys, args.bootstrap, args.seed)
    macro = paired["macro_equal_stratum"]
    pool_deltas = [float(item["rc4_minus_control_failure_cost"]) for item in paired["pools"].values()]
    primary_pass = (
        float(macro["rc4_minus_control_failure_cost"]) <= -args.min_effect
        and float(macro["stratified_bootstrap_95"][1]) <= 0.0
        and all(value <= 0.0 for value in pool_deltas)
        and int(macro["nonworse_strata"]) >= args.min_nonworse_strata
        and float(macro["worst_stratum_regression"]) <= args.max_stratum_regression
    )

    sentinel = sentinel_gate(args.d0_report, args.sentinel_inputs)
    generalist = json.loads(Path(args.generalist).read_text(encoding="utf-8"))
    if generalist.get("protocol") != "d1-rc4-paired-generalist-guard":
        parser.error("unexpected generalist guard protocol")
    overall_pass = primary_pass and bool(sentinel["mechanism_pass"]) and bool(sentinel["throughput"]["pass"]) and bool(generalist.get("pass"))
    decision = "D1_RC4_SCREEN_PASS_REVIEW_D1B" if overall_pass else "D1_RC4_NO_GO"
    payload = {
        "schema": 1,
        "protocol": "l3-imbalance2-d1-rc4-screen",
        "decision": decision,
        "recommendation_for_human_review": "REVIEW_SHORT_D1B_ONLY" if overall_pass else "REJECT_RC4_AND_DESIGN_SEPARATE_SEARCH_PILOT",
        "source_corpus": "immutable_0852_g4_source_same_bytes_both_arms",
        "selfplay_training_games": 0,
        "scan_used_for_training": False,
        "new_eval_pools": {"names": ["C64", "D64"], "seed": args.seed, "per_stratum": 64},
        "excluded_positions": [{"pool": key[0], "index": key[1]} for key in sorted(excluded)],
        "error_details": errors,
        "arms": arms,
        "paired": paired,
        "sentinel_gate": sentinel,
        "generalist_gate": generalist,
        "gates": {
            "primary_pass": primary_pass,
            "mechanism_pass": sentinel["mechanism_pass"],
            "throughput_pass": sentinel["throughput"]["pass"],
            "generalist_pass": generalist.get("pass"),
            "overall_pass": overall_pass,
            "min_effect": args.min_effect,
            "min_nonworse_strata": args.min_nonworse_strata,
            "max_stratum_regression": args.max_stratum_regression,
        },
        "d1b_authorized": False,
        "training_continuation_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
