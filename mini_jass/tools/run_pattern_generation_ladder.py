#!/usr/bin/env python3
"""M17-P: generation ladder for PatternEval with common-search responses."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
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
    response_metrics,
    solved_tensors,
)
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402

SCHEMA = "mini_jass.pattern_generation_ladder.v1"


def build_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any], control: dict[str, Any]
) -> dict[str, Any]:
    if aggregate["mean_advancing_generations"] < float(
        control["minimum_advancing_generations"]
    ):
        return {
            "finding": "ladder_did_not_advance_enough_deployed_parents",
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


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M17-P":
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
        for generation, (candidate_state, record) in enumerate(
            zip(execution.candidate_states, execution.core["generations"]), start=1
        ):
            advanced = bool(record["promotion"]["provisional_advance"])
            advance_flags.append(advanced)
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
            }
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
    }
    recommendation = build_recommendation(
        aggregate, config["scientific_gate"], config["promotion_control"]
    )
    protocol = {
        "schema": SCHEMA,
        "milestone": "M17-P",
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "ladder_max": config["ladder_max"],
        "report_rungs": rungs,
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "response_contract": "one_ply_value_search",
        "rung_state": "deployed_parent_after_promotion_decision",
        "single_factor": "generations",
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result = {
        "schema": SCHEMA,
        "milestone": "M17-P",
        "status": "PASS",
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
