#!/usr/bin/env python3
"""M17-P: generation ladder for PatternEval with common-search responses."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.loop import execute_loop  # noqa: E402
from mini_jass_lab.model_factory import build_model, model_descriptor  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.pattern_reconstruction import (  # noqa: E402
    assert_pattern_value_model,
    digest,
    mean,
    paired_interval,
    response_metrics,
    solved_tensors,
)
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything, selection_score  # noqa: E402

SCHEMA = "mini_jass.pattern_generation_ladder.v1"
SCHEMA_V2 = "mini_jass.pattern_generation_ladder.v2"
SCHEMA_REPLICATION = "mini_jass.pattern_generation_ladder_replication.v1"


def arena_score_lower_bound(
    score: float,
    pairs: int,
    confidence_z: float,
    confidence_unit: str = "games",
) -> float:
    """Return the same normal-approximation bound used by the live arena."""
    pairs = int(pairs)
    if pairs < 1:
        raise ValueError("arena lower bound requires at least one pair")
    if confidence_unit not in {"games", "pairs"}:
        raise ValueError("arena confidence_unit must be games or pairs")
    effective_observations = 2 * pairs if confidence_unit == "games" else pairs
    standard_error = math.sqrt(
        max(score * (1.0 - score), 0.0) / effective_observations
    )
    return max(0.0, float(score) - float(confidence_z) * standard_error)


def build_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any], control: dict[str, Any]
) -> dict[str, Any]:
    if aggregate["mean_advancing_generations"] < float(
        control["minimum_advancing_generations"]
    ):
        development_passes = aggregate.get("development_pass_count")
        arena_passes = aggregate.get("arena_pass_count")
        if development_passes == 0 and arena_passes == 0:
            blocked_component = "development_and_arena"
        elif development_passes == 0:
            blocked_component = "development"
        elif arena_passes == 0:
            blocked_component = "arena"
        else:
            blocked_component = "combined_or_stochastic"
        return {
            "status": "INCONCLUSIVE",
            "finding": (
                "ladder_did_not_advance_enough_deployed_parents"
                if development_passes is None or arena_passes is None
                else f"ladder_did_not_advance_{blocked_component}_gate_blocked"
            ),
            "blocked_component": blocked_component,
            "iteration_compounds": None,
            "decision": "INCONCLUSIVE_promotion_gate_blocked_iteration",
            "promotable": False,
        }
    rungs = aggregate["rungs"]
    deltas = aggregate["mean_zero_regret_delta_by_rung"]
    monotone = 1 + sum(
        deltas[str(rungs[index])] >= deltas[str(rungs[index - 1])]
        for index in range(1, len(rungs))
    )
    final = float(deltas[str(rungs[-1])])
    compounds = (
        monotone >= int(gate["minimum_monotone_rungs"])
        and final > float(gate["minimum_final_zero_regret_delta"])
        and final > float(deltas[str(rungs[0])])
    )
    return {
        "status": "PASS",
        "finding": (
            "pattern_iteration_compounds_across_generations"
            if compounds
            else "pattern_iteration_does_not_compound_in_this_loop"
        ),
        "iteration_compounds": compounds,
        "monotone_rungs": monotone,
        "decision": (
            "replicate_ladder_on_fresh_seeds"
            if compounds
            else "generation_count_is_not_the_primary_limit"
        ),
        "promotable": False,
    }


def build_replication_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any], control: dict[str, Any]
) -> dict[str, Any]:
    """Apply the preregistered M17-P2R confirmatory decision rule."""
    if aggregate["mean_advancing_generations"] < float(
        control["minimum_advancing_generations"]
    ):
        return {
            "status": "INCONCLUSIVE",
            "finding": "replication_ladder_did_not_advance_enough_deployed_parents",
            "replication_confirms": None,
            "iteration_compounds": None,
            "decision": "INCONCLUSIVE_promotion_gate_blocked_replication",
            "promotable": False,
        }

    primary = aggregate["paired_zero_regret_g8_minus_g1"]
    confidence_pass = (
        not bool(gate["require_primary_ci_above_zero"])
        or float(primary["lower"]) > 0.0
    )
    practical_pass = float(primary["mean"]) >= float(
        gate["minimum_practical_compounding_gain"]
    )
    confirms = confidence_pass and practical_pass
    if confirms:
        finding = "pattern_iteration_compounding_replicates"
        decision = "proceed_to_state_distribution_decomposition"
    elif confidence_pass:
        finding = "compounding_detected_below_practical_threshold"
        decision = "do_not_advance_iteration_claim"
    else:
        finding = "pattern_iteration_compounding_does_not_replicate"
        decision = "do_not_advance_iteration_claim"
    return {
        "status": "PASS",
        "finding": finding,
        "replication_confirms": confirms,
        "iteration_compounds": confirms,
        "primary_confidence_pass": confidence_pass,
        "primary_practical_pass": practical_pass,
        "minimum_practical_compounding_gain": float(
            gate["minimum_practical_compounding_gain"]
        ),
        "decision": decision,
        "promotable": False,
    }


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    identity = (config.get("schema"), config.get("milestone"))
    if identity not in {
        (SCHEMA, "M17-P"),
        (SCHEMA_V2, "M17-P2"),
        (SCHEMA_REPLICATION, "M17-P2R"),
    }:
        raise ValueError("unexpected M17-P schema")
    rungs = [int(value) for value in config["report_rungs"]]
    if not rungs or rungs != sorted(rungs) or max(rungs) != int(config["ladder_max"]):
        raise ValueError("M17-P rungs must be sorted and reach ladder_max")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("cohorts_read") != ["development"]
        or boundaries.get("cohorts_sealed") != ["frozen_test"]
        or boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M17-P crossed a scientific boundary")
    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1" or int(loop["generations"]) != 1:
        raise ValueError("M17-P base loop must be the one-generation Pattern recipe")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M17-P base loop must use PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M17-P cannot train a policy head")
    if config["schema"] in {SCHEMA_V2, SCHEMA_REPLICATION}:
        control = config["promotion_control"]
        pairs = int(control["arena_pairs"])
        loop["arena"]["pairs"] = pairs
        epsilon = float(control["arena_epsilon"])
        loop["arena"]["epsilon"] = epsilon
        start_state_source = str(control["arena_start_state_source"])
        if start_state_source != "development":
            raise ValueError("M17-P2 requires varied development start states")
        loop["arena"]["start_state_source"] = "provided"
        confidence_unit = str(control["arena_confidence_unit"])
        loop["arena"]["confidence_unit"] = confidence_unit
        neutral_score = float(control["neutral_arena_score"])
        lower_bound = arena_score_lower_bound(
            neutral_score,
            pairs,
            float(loop["arena"]["confidence_z"]),
            confidence_unit,
        )
        declared_lower_bound = float(control["neutral_score_lower_bound"])
        if not math.isclose(lower_bound, declared_lower_bound, abs_tol=1e-12):
            raise ValueError("M17-P2 declared neutral arena bound is incorrect")
        required_lower_bound = float(loop["promotion"]["minimum_arena_lower_bound"])
        if lower_bound < required_lower_bound:
            raise ValueError("M17-P2 arena is underpowered at the neutral score")
    if config["schema"] == SCHEMA_REPLICATION:
        if len(config["paired_seeds"]) != 20 or len(set(config["paired_seeds"])) != 20:
            raise ValueError("M17-P2R requires 20 unique paired seeds")
        gate = config["scientific_gate"]
        if gate.get("primary_endpoint") != "paired_zero_regret_delta_g8_minus_g1":
            raise ValueError("M17-P2R primary endpoint is not preregistered")
        if float(gate["minimum_practical_compounding_gain"]) <= 0.0:
            raise ValueError("M17-P2R practical compounding gain must be positive")
    return deepcopy(config), loop


def run_m17p(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
) -> dict[str, Any]:
    config, base_loop = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M17-P requires cpx62, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M17-P split differs from the frozen L1 contract")
    train = split.indices("train")
    development = split.indices("development")
    train_mask = np.zeros(graph.state_count, dtype=np.bool_)
    train_mask[train] = True
    tensors = solved_tensors(oracle, graph)
    batch = int(base_loop["development"]["batch_size"])
    rungs = [int(value) for value in config["report_rungs"]]

    rows: list[dict[str, Any]] = []
    for raw_seed in config["paired_seeds"]:
        seed = int(raw_seed)
        loop = deepcopy(base_loop)
        loop["seed"] = seed
        loop["generations"] = int(config["ladder_max"])
        execution = execute_loop(loop, oracle, development, train, train_mask)
        seed_everything(seed, int(loop["runtime"]["threads"]))
        initial = build_model(loop["model"])
        assert_pattern_value_model(initial)
        before = response_metrics(initial, graph, tensors, oracle, development, batch)
        deployed_state = deepcopy(initial.state_dict())
        by_rung: dict[str, Any] = {}
        advance_flags: list[bool] = []
        promotion_diagnostics: list[dict[str, Any]] = []
        for generation, (candidate_state, record) in enumerate(
            zip(execution.candidate_states, execution.core["generations"]), start=1
        ):
            advanced = bool(record["promotion"]["provisional_advance"])
            advance_flags.append(advanced)
            parent_development = record["development"]["parent"]
            candidate_development = record["development"]["candidate"]
            arena = record["arena"]
            promotion = record["promotion"]
            promotion_diagnostics.append(
                {
                    "generation": generation,
                    "development": {
                        "parent_selection_score": selection_score(parent_development),
                        "candidate_selection_score": selection_score(
                            candidate_development
                        ),
                        "selection_score_improvement": float(
                            record["development"]["selection_score_improvement"]
                        ),
                        "parent_zero_regret_rate": float(
                            parent_development["zero_regret_rate"]
                        ),
                        "candidate_zero_regret_rate": float(
                            candidate_development["zero_regret_rate"]
                        ),
                        "parent_value_sign_accuracy": float(
                            parent_development["value_sign_accuracy"]
                        ),
                        "candidate_value_sign_accuracy": float(
                            candidate_development["value_sign_accuracy"]
                        ),
                        "pass": bool(promotion["development_pass"]),
                    },
                    "arena": {
                        "pairs": int(arena["pairs"]),
                        "games": int(arena["games"]),
                        "wins": int(arena["wins"]),
                        "draws": int(arena["draws"]),
                        "losses": int(arena["losses"]),
                        "score": float(arena["score"]),
                        "score_lower_confidence_bound": float(
                            arena["score_lower_confidence_bound"]
                        ),
                        "confidence_z": float(arena["confidence_z"]),
                        "confidence_unit": str(arena["confidence_unit"]),
                        "effective_observations": int(
                            arena["effective_observations"]
                        ),
                        "start_state_source": str(arena["start_state_source"]),
                        "unique_start_state_count": int(
                            arena["unique_start_state_count"]
                        ),
                        "start_state_ids": [
                            int(state_id) for state_id in arena["start_state_ids"]
                        ],
                        "pair_score_histogram": dict(
                            arena["pair_score_histogram"]
                        ),
                        "pass": bool(promotion["arena_pass"]),
                    },
                    "eligible_after_development_and_arena": bool(
                        promotion["eligible_after_development_and_arena"]
                    ),
                    "provisional_advance": advanced,
                }
            )
            if advanced:
                deployed_state = deepcopy(candidate_state)
            if generation in rungs:
                deployed = build_model(loop["model"])
                assert_pattern_value_model(deployed)
                deployed.load_state_dict(deployed_state)
                after = response_metrics(
                    deployed, graph, tensors, oracle, development, batch
                )
                by_rung[str(generation)] = {
                    "zero_regret_delta": float(after["zero_regret_rate"])
                    - float(before["zero_regret_rate"]),
                    "value_sign_delta": float(after["value_sign_accuracy"])
                    - float(before["value_sign_accuracy"]),
                    "deployed_parent": True,
                    "metrics": after,
                }
        rows.append(
            {
                "seed": seed,
                "initial": before,
                "by_rung": by_rung,
                "advancing_generations": int(sum(advance_flags)),
                "advance_flags": advance_flags,
                "promotion_diagnostics": promotion_diagnostics,
            }
        )

    diagnostics = [
        diagnostic
        for row in rows
        for diagnostic in row["promotion_diagnostics"]
    ]
    development_pass_count = sum(
        diagnostic["development"]["pass"] for diagnostic in diagnostics
    )
    arena_pass_count = sum(diagnostic["arena"]["pass"] for diagnostic in diagnostics)
    eligible_count = sum(
        diagnostic["eligible_after_development_and_arena"]
        for diagnostic in diagnostics
    )
    aggregate = {
        "rungs": rungs,
        "paired_seed_count": len(rows),
        "mean_zero_regret_delta_by_rung": {
            str(rung): mean(
                row["by_rung"][str(rung)]["zero_regret_delta"] for row in rows
            )
            for rung in rungs
        },
        "mean_value_sign_delta_by_rung": {
            str(rung): mean(
                row["by_rung"][str(rung)]["value_sign_delta"] for row in rows
            )
            for rung in rungs
        },
        "mean_advancing_generations": mean(
            row["advancing_generations"] for row in rows
        ),
        "seeds_with_zero_advance": sum(
            row["advancing_generations"] == 0 for row in rows
        ),
        "total_generation_count": len(diagnostics),
        "development_pass_count": development_pass_count,
        "arena_pass_count": arena_pass_count,
        "eligible_count": eligible_count,
        "promotion_failure_matrix": {
            "fail_development_only": sum(
                not diagnostic["development"]["pass"]
                and diagnostic["arena"]["pass"]
                for diagnostic in diagnostics
            ),
            "fail_arena_only": sum(
                diagnostic["development"]["pass"]
                and not diagnostic["arena"]["pass"]
                for diagnostic in diagnostics
            ),
            "fail_both": sum(
                not diagnostic["development"]["pass"]
                and not diagnostic["arena"]["pass"]
                for diagnostic in diagnostics
            ),
        },
        "mean_development_selection_score_improvement": mean(
            diagnostic["development"]["selection_score_improvement"]
            for diagnostic in diagnostics
        ),
        "mean_arena_score": mean(
            diagnostic["arena"]["score"] for diagnostic in diagnostics
        ),
        "mean_arena_score_lower_confidence_bound": mean(
            diagnostic["arena"]["score_lower_confidence_bound"]
            for diagnostic in diagnostics
        ),
    }
    if config["schema"] == SCHEMA_REPLICATION:
        primary_values = [
            float(row["by_rung"]["8"]["zero_regret_delta"])
            - float(row["by_rung"]["1"]["zero_regret_delta"])
            for row in rows
        ]
        primary = paired_interval(
            primary_values,
            float(config["scientific_gate"]["paired_confidence_critical_95"]),
        )
        primary["standard_deviation"] = float(
            primary["standard_error"] * math.sqrt(primary["count"])
        )
        primary["positive_seed_count"] = sum(value > 0.0 for value in primary_values)
        primary["zero_seed_count"] = sum(value == 0.0 for value in primary_values)
        primary["negative_seed_count"] = sum(value < 0.0 for value in primary_values)
        primary["by_seed"] = [
            {"seed": int(row["seed"]), "delta": float(value)}
            for row, value in zip(rows, primary_values)
        ]
        aggregate["paired_zero_regret_g8_minus_g1"] = primary
        recommendation = build_replication_recommendation(
            aggregate, config["scientific_gate"], config["promotion_control"]
        )
    else:
        recommendation = build_recommendation(
            aggregate, config["scientific_gate"], config["promotion_control"]
        )
    neutral_score = float(
        config["promotion_control"].get("neutral_arena_score", 0.5)
    )
    protocol = {
        "schema": config["schema"],
        "milestone": config["milestone"],
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "ladder_max": config["ladder_max"],
        "report_rungs": rungs,
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "response_contract": "one_ply_value_search",
        "rung_state": "deployed_parent_after_promotion_decision",
        "single_factor": "generations",
        "analysis_role": (
            "fresh_seed_confirmatory_replication"
            if config["schema"] == SCHEMA_REPLICATION
            else "discovery"
        ),
        "resolved_promotion_gate": {
            "arena_pairs": int(base_loop["arena"]["pairs"]),
            "arena_games": 2 * int(base_loop["arena"]["pairs"]),
            "confidence_unit": str(
                base_loop["arena"].get("confidence_unit", "games")
            ),
            "effective_observations": (
                2 * int(base_loop["arena"]["pairs"])
                if base_loop["arena"].get("confidence_unit", "games") == "games"
                else int(base_loop["arena"]["pairs"])
            ),
            "confidence_z": float(base_loop["arena"]["confidence_z"]),
            "epsilon": float(base_loop["arena"]["epsilon"]),
            "start_state_source": str(
                base_loop["arena"].get("start_state_source", "initial")
            ),
            "start_state_cohort": (
                "development"
                if base_loop["arena"].get("start_state_source") == "provided"
                else None
            ),
            "minimum_arena_lower_bound": float(
                base_loop["promotion"]["minimum_arena_lower_bound"]
            ),
            "neutral_arena_score": neutral_score,
            "neutral_score_lower_bound": arena_score_lower_bound(
                neutral_score,
                int(base_loop["arena"]["pairs"]),
                float(base_loop["arena"]["confidence_z"]),
                str(base_loop["arena"].get("confidence_unit", "games")),
            ),
        },
        "source_iteration": config.get("source_iteration"),
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result = {
        "schema": config["schema"],
        "milestone": config["milestone"],
        "status": recommendation.get("status", "PASS"),
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
        "recommendation": recommendation,
        "sealed_cohort_contract": {
            "cohorts_read": ["development"],
            "cohorts_not_read": ["frozen_test"],
        },
    }
    result["result_hash"] = digest(result)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--execution-host")
    args = parser.parse_args()
    result = run_m17p(
        args.config, args.oracle, args.run_dir, args.compact_output, args.execution_host
    )
    print(json.dumps({"status": result["status"], "result_hash": result["result_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
