#!/usr/bin/env python3
"""Read-only paired inference and power audit for a completed M17-P2 result."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist, stdev
from typing import Any, Iterable

import yaml


SCHEMA = "mini_jass.pattern_generation_ladder_readout.v1"


def digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def paired_interval(values: Iterable[float], critical: float) -> dict[str, Any]:
    data = [float(value) for value in values]
    if len(data) < 2:
        raise ValueError("paired interval requires at least two seeds")
    center = sum(data) / len(data)
    standard_deviation = stdev(data)
    standard_error = standard_deviation / math.sqrt(len(data))
    return {
        "count": len(data),
        "mean": center,
        "standard_deviation": standard_deviation,
        "standard_error": standard_error,
        "confidence_critical_95": float(critical),
        "lower": center - float(critical) * standard_error,
        "upper": center + float(critical) * standard_error,
    }


def normal_approximation_sample_size(
    standard_deviation: float,
    effect: float,
    target_power: float,
) -> int:
    if standard_deviation < 0.0 or effect <= 0.0:
        raise ValueError("sample-size inputs must be positive")
    if not 0.5 < target_power < 1.0:
        raise ValueError("target power must be between 0.5 and 1")
    if standard_deviation == 0.0:
        return 2
    z_alpha = NormalDist().inv_cdf(0.975)
    z_power = NormalDist().inv_cdf(target_power)
    return max(2, math.ceil(((z_alpha + z_power) * standard_deviation / effect) ** 2))


def _load_config(path: Path) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M17-P2-READOUT":
        raise ValueError("unexpected M17-P2 readout schema")
    if config["primary_endpoint"] != "paired_zero_regret_delta_g8_minus_g1":
        raise ValueError("unexpected M17-P2 primary endpoint")
    if config["boundaries"] != {
        "cohorts_read": ["development"],
        "cohorts_sealed": ["frozen_test"],
        "promotable": False,
        "production_jass_changes_authorized": False,
        "direct_10x10_transfer_authorized": False,
    }:
        raise ValueError("M17-P2 readout crossed a scientific boundary")
    return config


def analyze(result: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    source = config["source_result"]
    if result.get("schema") != source["schema"]:
        raise ValueError("source result schema mismatch")
    if result.get("milestone") != source["milestone"]:
        raise ValueError("source result milestone mismatch")
    if result.get("result_hash") != source["result_hash"]:
        raise ValueError("source result hash mismatch")
    if result.get("protocol_hash") != source["protocol_hash"]:
        raise ValueError("source protocol hash mismatch")

    expected_seeds = int(config["expected_seed_count"])
    rows = result.get("seed_results", [])
    seeds = [int(row["seed"]) for row in rows]
    if len(rows) != expected_seeds or len(set(seeds)) != expected_seeds:
        raise ValueError("source result does not contain the expected unique seeds")
    rungs = [int(rung) for rung in config["report_rungs"]]
    if rungs != [1, 2, 4, 8]:
        raise ValueError("M17-P2 readout requires rungs 1/2/4/8")

    zero_regret_by_rung = {
        rung: [float(row["by_rung"][str(rung)]["zero_regret_delta"]) for row in rows]
        for rung in rungs
    }
    value_sign_by_rung = {
        rung: [float(row["by_rung"][str(rung)]["value_sign_delta"]) for row in rows]
        for rung in rungs
    }
    critical = float(config["paired_confidence_critical_95"])
    primary_values = [
        final - first
        for final, first in zip(zero_regret_by_rung[8], zero_regret_by_rung[1])
    ]
    primary = paired_interval(primary_values, critical)
    primary.update(
        {
            "name": config["primary_endpoint"],
            "seeds_positive": sum(value > 0.0 for value in primary_values),
            "seeds_zero": sum(value == 0.0 for value in primary_values),
            "seeds_negative": sum(value < 0.0 for value in primary_values),
            "by_seed": [
                {
                    "seed": seed,
                    "g1_zero_regret_delta": first,
                    "g8_zero_regret_delta": final,
                    "g8_minus_g1": contrast,
                }
                for seed, first, final, contrast in zip(
                    seeds,
                    zero_regret_by_rung[1],
                    zero_regret_by_rung[8],
                    primary_values,
                )
            ],
        }
    )

    adjacent: dict[str, Any] = {}
    for lower_rung, upper_rung in zip(rungs, rungs[1:]):
        adjacent[f"g{upper_rung}_minus_g{lower_rung}"] = paired_interval(
            (
                upper - lower
                for upper, lower in zip(
                    zero_regret_by_rung[upper_rung],
                    zero_regret_by_rung[lower_rung],
                )
            ),
            critical,
        )

    diagnostics = [
        diagnostic
        for row in rows
        for diagnostic in row.get("promotion_diagnostics", [])
    ]
    expected_generations = expected_seeds * int(config["ladder_max"])
    if len(diagnostics) != expected_generations:
        raise ValueError("source result has incomplete promotion diagnostics")
    arena_rows = [diagnostic["arena"] for diagnostic in diagnostics]
    start_contract_pass = all(
        arena["start_state_source"] == "provided"
        and int(arena["unique_start_state_count"]) == int(arena["pairs"])
        and len(arena["start_state_ids"]) == int(arena["pairs"])
        and len(set(int(state) for state in arena["start_state_ids"]))
        == int(arena["pairs"])
        for arena in arena_rows
    )
    confidence_contract_pass = all(
        arena["confidence_unit"] == "pairs"
        and int(arena["effective_observations"]) == int(arena["pairs"])
        for arena in arena_rows
    )
    histogram_contract_pass = all(
        sum(int(count) for count in arena["pair_score_histogram"].values())
        == int(arena["pairs"])
        for arena in arena_rows
    )
    arena_scores = [float(arena["score"]) for arena in arena_rows]
    distinct_arena_scores = sorted(set(arena_scores))
    endpoint_varies = len(distinct_arena_scores) > 1
    arena_audit_pass = (
        start_contract_pass
        and confidence_contract_pass
        and histogram_contract_pass
        and endpoint_varies
    )

    practical_effect = float(config["minimum_practical_compounding_gain"])
    target_power = float(config["replication_target_power"])
    sample_size_practical = normal_approximation_sample_size(
        float(primary["standard_deviation"]), practical_effect, target_power
    )
    observed_effect = abs(float(primary["mean"]))
    sample_size_observed = (
        normal_approximation_sample_size(
            float(primary["standard_deviation"]), observed_effect, target_power
        )
        if observed_effect > 0.0
        else None
    )
    recommended_seed_count = max(expected_seeds, sample_size_practical)
    primary_confirmed = float(primary["lower"]) > 0.0
    status = "PASS" if arena_audit_pass and primary_confirmed else "INCONCLUSIVE"
    if not arena_audit_pass:
        status = "FAIL"

    readout: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M17-P2-READOUT",
        "status": status,
        "source": {
            "job_id": source["job_id"],
            "attempt_id": source["attempt_id"],
            "result_hash": source["result_hash"],
            "protocol_hash": result["protocol_hash"],
            "seed_count": expected_seeds,
        },
        "primary": primary,
        "zero_regret_delta_by_rung": {
            str(rung): paired_interval(zero_regret_by_rung[rung], critical)
            for rung in rungs
        },
        "value_sign_delta_by_rung": {
            str(rung): paired_interval(value_sign_by_rung[rung], critical)
            for rung in rungs
        },
        "adjacent_zero_regret_contrasts": adjacent,
        "process": {
            "advancing_generations": paired_interval(
                (float(row["advancing_generations"]) for row in rows), critical
            ),
            "seeds_with_zero_advance": sum(
                int(row["advancing_generations"]) == 0 for row in rows
            ),
            "seeds_monotone_all_rungs": sum(
                all(
                    zero_regret_by_rung[rungs[index]][row_index]
                    >= zero_regret_by_rung[rungs[index - 1]][row_index]
                    for index in range(1, len(rungs))
                )
                for row_index in range(expected_seeds)
            ),
        },
        "arena_audit": {
            "generation_count": len(arena_rows),
            "pairs_per_generation": sorted(
                set(int(arena["pairs"]) for arena in arena_rows)
            ),
            "start_contract_pass": start_contract_pass,
            "confidence_contract_pass": confidence_contract_pass,
            "histogram_contract_pass": histogram_contract_pass,
            "distinct_score_count": len(distinct_arena_scores),
            "minimum_score": min(arena_scores),
            "maximum_score": max(arena_scores),
            "score_equal_half_count": sum(score == 0.5 for score in arena_scores),
            "endpoint_varies": endpoint_varies,
            "pass": arena_audit_pass,
        },
        "replication_sizing": {
            "method": "paired_normal_approximation_two_sided_alpha_0.05",
            "target_power": target_power,
            "minimum_practical_compounding_gain": practical_effect,
            "source_standard_deviation": primary["standard_deviation"],
            "sample_size_for_minimum_practical_gain": sample_size_practical,
            "sample_size_for_observed_gain": sample_size_observed,
            "minimum_fresh_seed_count": expected_seeds,
            "recommended_fresh_seed_count": recommended_seed_count,
        },
        "recommendation": {
            "primary_ci_above_zero": primary_confirmed,
            "arena_audit_pass": arena_audit_pass,
            "decision": (
                "replicate_ladder_on_sized_fresh_seed_cohort"
                if status == "PASS"
                else "do_not_replicate_until_readout_is_resolved"
            ),
            "promotable": False,
        },
        "sealed_cohort_contract": {
            "cohorts_read": ["development"],
            "cohorts_not_read": ["frozen_test"],
        },
    }
    readout["readout_hash"] = digest(readout)
    return readout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = _load_config(args.config)
    result = json.loads(args.input.read_text(encoding="utf-8"))
    readout = analyze(result, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(readout, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"status": readout["status"], "readout_hash": readout["readout_hash"]}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
