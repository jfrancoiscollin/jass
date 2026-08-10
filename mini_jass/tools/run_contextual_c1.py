#!/usr/bin/env python3
"""Run contextual pool C1 with paired replay, batches, arenas and exports."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import yaml  # noqa: E402

import mini_jass_lab.loop as loop_module  # noqa: E402
from mini_jass_lab.arena import ArenaConfig, run_arena  # noqa: E402
from mini_jass_lab.context_replay import (  # noqa: E402
    allocate_disjoint_state_manifests,
    assigned_states,
    freeze_replay_manifest,
)
from mini_jass_lab.context_scaffold import (  # noqa: E402
    ContextualPatternScaffold,
    prove_scalar_export,
)
from mini_jass_lab.context_training import (  # noqa: E402
    DEPLOYABLE_ARMS,
    batch_schedule,
    contextual_replay_targets,
    tensor_state_hash,
    train_contextual_from_replay,
)
from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.pattern_eval import PatternEval  # noqa: E402
from mini_jass_lab.pattern_reconstruction import (  # noqa: E402
    digest,
    mean,
    paired_interval,
    response_metrics,
    solved_tensors,
)
from mini_jass_lab.patterns import PatternSet  # noqa: E402
from mini_jass_lab.selfplay import generate_self_play  # noqa: E402
from mini_jass_lab.selfplay_train import train_from_replay  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402

SCHEMA = "mini_jass.contextual_c1.v1"
CONFIG_SCHEMA = "mini_jass.contextual_outcome_supervision.v3"
FROZEN_C0_HASH = "ca0c9cb3d9f99ed9984947fe046e85b7f060ad49d10948e892d608bc99ad19f4"
PRIMARY_HIGH = "WDL_PLUS_FULL_CONTEXT"
PRIMARY_LOW = "WDL_ONLY"


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != CONFIG_SCHEMA:
        raise ValueError("C1 requires the frozen contextual v3 contract")
    if config.get("status") not in (
        "C0_PASS_C1_implementation_ready_for_verification",
        "C1_FROZEN_C2_implementation_ready_for_verification",
    ):
        raise ValueError("C1 requires a frozen C0 PASS or frozen C1 evidence")
    c0 = config["c0_gate"]["frozen_report_v1"]
    if (
        c0.get("report_hash") != FROZEN_C0_HASH
        or c0.get("status") != "PASS"
        or c0.get("c1_training_authorized") is not True
        or c0.get("sealed_test_read") is not False
    ):
        raise ValueError("C1 authorization differs from the frozen C0 evidence")
    if config["replay_source_decision_v1"].get("selected_source") != "G1_WIDE_OUTCOME":
        raise ValueError("C1 replay source differs from the M21-P decision")
    if (
        tuple(arm for arm in config["c1_arms"] if arm != "ORACLE_VALUE_DIAGNOSTIC")
        != DEPLOYABLE_ARMS
    ):
        raise ValueError("C1 deployable arm order changed")

    c1_seeds = tuple(int(seed) for seed in config["c1_decision"]["paired_seeds"])
    c2_seeds = tuple(
        int(seed) for seed in config["c2_disjoint_replication"]["paired_seeds"]
    )
    if (
        len(c1_seeds) != 20
        or len(c2_seeds) != 20
        or len(set(c1_seeds)) != 20
        or len(set(c2_seeds)) != 20
        or not set(c1_seeds).isdisjoint(c2_seeds)
    ):
        raise ValueError("C1/C2 require 20 fresh globally disjoint seeds each")

    execution = config["c1_execution_v1"]
    replay = execution["replay"]
    training = execution["training"]
    arena = execution["arena"]
    if (
        replay.get("source") != "G1_WIDE_OUTCOME"
        or replay.get("generator_model") != "initial_shared_scaffold_scalar_export"
        or replay.get("row_selection") != "all_generated_train_rows"
        or replay.get("recorded_selected_action_required") is not True
        or replay.get("state_cohort") != "train"
        or replay.get("start_state_source") != "train_split"
        or int(replay.get("games_per_seed", 0)) != 1024
    ):
        raise ValueError("C1 replay realization changed")
    if (
        int(training["steps"]) != 1024
        or int(training["batch_size"]) != 128
        or float(training["value_weight"]) != 1.0
        or float(training["policy_weight"]) != 0.0
        or training.get("explicit_identical_batch_schedule_all_arms") is not True
    ):
        raise ValueError("C1 training schedule changed")
    expected_weights = {
        "WDL_ONLY": (0.0, 0.0, 0.0),
        "WDL_PLUS_CONTEXT": (0.25, 0.0, 0.0),
        "WDL_PLUS_DELTA_CONTEXT": (0.0, 0.25, 0.0),
        "WDL_PLUS_RESIDUAL": (0.0, 0.0, 0.25),
        "WDL_PLUS_FULL_CONTEXT": (1.0 / 12.0,) * 3,
    }
    realized_weights = {
        arm: (
            float(config["c1_arms"][arm]["beta_context"]),
            float(config["c1_arms"][arm]["gamma_delta_context"]),
            float(config["c1_arms"][arm]["eta_residual"]),
        )
        for arm in DEPLOYABLE_ARMS
    }
    if realized_weights != expected_weights:
        raise ValueError("C1 auxiliary weights changed")
    if (
        arena.get("start_state_source") != "development_provided_unique"
        or int(arena["pairs_per_seed"])
        != int(config["power_sizing_v1"]["selected_pairs_per_seed"])
        or arena.get("C1_C2_start_state_disjointness_required") is not True
    ):
        raise ValueError("C1 arena realization changed")
    if execution["export_proof"].get("every_deployable_checkpoint") is not True:
        raise ValueError("C1 cannot omit per-checkpoint export proofs")
    if (
        float(execution["export_proof"]["maximum_absolute_value_error"]) != 1.0e-6
        or float(execution["export_proof"]["required_common_search_action_match_rate"])
        != 1.0
    ):
        raise ValueError("C1 export proof thresholds changed")

    root = path.resolve().parent.parent
    base_loop = yaml.safe_load(
        (root / config["data_contract"]["base_loop_config"]).read_text(encoding="utf-8")
    )
    if (
        base_loop.get("schema") != "mini_jass.selfplay.v1"
        or base_loop["model"].get("architecture") != "folded_pattern_value"
        or float(base_loop["training"]["policy_weight"]) != 0.0
    ):
        raise ValueError("C1 requires the value-only folded PatternEval loop")
    return deepcopy(config), base_loop


def _scaffold(config: dict[str, Any], seed: int) -> ContextualPatternScaffold:
    scaffold = config["training_scaffold_v1"]
    initialization = scaffold["initialization"]
    return ContextualPatternScaffold(
        PatternSet.from_window(int(scaffold["pattern_window"])),
        seed=int(seed),
        rank=int(scaffold["shared_rank"]),
        include_reversible_plies=bool(scaffold["include_reversible_plies"]),
        bucket_standard_deviation=float(
            initialization["bucket_embedding_standard_deviation"]
        ),
        reversible_standard_deviation=float(
            initialization["reversible_embedding_standard_deviation"]
        ),
        auxiliary_standard_deviation=float(
            initialization["auxiliary_head_standard_deviation"]
        ),
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_progress(path: Path | None, completed: int, total: int, seed: int) -> None:
    if path is None:
        return
    _write_json(
        path,
        {
            "schema": "mini_jass.contextual_c1_progress.v1",
            "completed_seeds": int(completed),
            "total_seeds": int(total),
            "last_completed_seed": int(seed),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _compact_generation_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    compact = {key: value for key, value in metrics.items() if key != "search_trace"}
    trace = metrics.get("search_trace", [])
    compact["search_trace_row_count"] = len(trace)
    compact["search_trace_hash"] = digest(trace)
    return compact


def _save_pattern_eval(path: Path, model: PatternEval) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        bucket_weight=model.bucket_weight.detach().cpu().numpy(),
        extra_weight=model.extra_weight.detach().cpu().numpy(),
        bias=model.bias.detach().cpu().numpy(),
        bucket_class=model.bucket_class.detach().cpu().numpy(),
    )


def _direct_table_fit(
    initial: PatternEval,
    graph: GameGraph,
    samples: list[Any],
    schedule: np.ndarray,
    training: dict[str, Any],
    seed: int,
) -> tuple[PatternEval, dict[str, Any]]:
    model = PatternEval(initial.pattern_set, initial.include_reversible_plies)
    model.load_state_dict(initial.state_dict())
    initial_hash = tensor_state_hash(model)
    metrics = train_from_replay(
        model,
        graph,
        samples,
        steps=int(schedule.shape[0]),
        batch_size=int(schedule.shape[1]),
        learning_rate=float(training["learning_rate"]),
        weight_decay=float(training["weight_decay"]),
        value_weight=float(training["value_weight"]),
        policy_weight=float(training["policy_weight"]),
        seed=int(seed),
        batch_indices=schedule,
    )
    metrics["initial_export_hash"] = initial_hash
    metrics["final_export_hash"] = tensor_state_hash(model)
    return model, metrics


def _aggregate(
    rows: list[dict[str, Any]], critical: float
) -> tuple[dict[str, Any], str]:
    deltas = [
        float(row["arms"][PRIMARY_HIGH]["arena_score"])
        - float(row["arms"][PRIMARY_LOW]["arena_score"])
        for row in rows
    ]
    interval = paired_interval(deltas, critical)
    interval["positive_seed_count"] = sum(delta > 0.0 for delta in deltas)
    interval["zero_seed_count"] = sum(delta == 0.0 for delta in deltas)
    value_mae_deltas = [
        float(row["arms"][PRIMARY_HIGH]["development"]["value_mae"])
        - float(row["arms"][PRIMARY_LOW]["development"]["value_mae"])
        for row in rows
    ]
    mechanism_interval = paired_interval(value_mae_deltas, critical)
    direct_arena_deltas = [
        float(row["arms"][PRIMARY_LOW]["arena_score"])
        - float(row["direct_table_descriptive_control"]["arena_score"])
        for row in rows
    ]
    direct_value_deltas = [
        float(row["arms"][PRIMARY_LOW]["development"]["value_mae"])
        - float(row["direct_table_descriptive_control"]["development"]["value_mae"])
        for row in rows
    ]
    label = (
        "PROVISIONAL_POSITIVE_REQUIRES_C2"
        if float(interval["lower"]) > 0.0
        else "PROVISIONAL_NO_SIGNAL_REQUIRES_C2"
    )
    aggregate = {
        "paired_seed_count": len(rows),
        "primary_contrast": f"{PRIMARY_HIGH}_minus_{PRIMARY_LOW}",
        "primary_common_search_arena_score": interval,
        "registered_mechanism_value_mae": {
            "contrast": f"{PRIMARY_HIGH}_minus_{PRIMARY_LOW}",
            "improvement_direction": "negative",
            "paired_interval": mechanism_interval,
            "C1_only_no_final_claim": True,
        },
        "scaffold_cost_descriptive_control": {
            "contrast": "WDL_ONLY_scaffold_minus_WDL_DIRECT_TABLE",
            "arena_score": paired_interval(direct_arena_deltas, critical),
            "value_mae": paired_interval(direct_value_deltas, critical),
            "excluded_from_C1_decision": True,
        },
        "arms": {
            arm: {
                "mean_arena_score": mean(
                    row["arms"][arm]["arena_score"] for row in rows
                ),
                "mean_value_mae": mean(
                    row["arms"][arm]["development"]["value_mae"] for row in rows
                ),
                "mean_zero_regret_rate": mean(
                    row["arms"][arm]["development"]["zero_regret_rate"] for row in rows
                ),
            }
            for arm in DEPLOYABLE_ARMS
        },
        "all_replays_paired": True,
        "all_batch_schedules_paired": True,
        "all_initial_scalar_states_paired": True,
        "all_arena_starts_paired": True,
        "all_export_proofs_passed": True,
        "mean_replay_sample_count": mean(
            row["replay_manifest"]["sample_count"] for row in rows
        ),
        "frozen_test_read": False,
    }
    return aggregate, label


def run_c1(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    *,
    implementation_sha: str,
    execution_host: str | None = None,
    progress_output: Path | None = None,
) -> dict[str, Any]:
    config, base_loop = _resolve(config_path)
    if len(implementation_sha) != 40 or any(
        character not in "0123456789abcdef" for character in implementation_sha
    ):
        raise ValueError("C1 implementation SHA must be a full lowercase Git SHA")
    host = execution_host or platform.node()
    if host != "cpx62":
        raise ValueError(f"contextual C1 requires cpx62, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    expected_split = config["data_contract"]["split_manifest_hash"]
    if split.manifest["manifest_hash"] != expected_split:
        raise ValueError("C1 split differs from the frozen L1 contract")
    train = split.indices("train")
    development = split.indices("development")
    train_mask = np.zeros(graph.state_count, dtype=np.bool_)
    train_mask[train] = True
    train_nonterminal = [
        int(state) for state in train if graph.terminal_value(int(state)) is None
    ]
    development_nonterminal = [
        int(state) for state in development if graph.terminal_value(int(state)) is None
    ]
    c1_seeds = tuple(int(seed) for seed in config["c1_decision"]["paired_seeds"])
    c2_seeds = tuple(
        int(seed) for seed in config["c2_disjoint_replication"]["paired_seeds"]
    )
    pools = {"C1": c1_seeds, "C2": c2_seeds}
    execution = config["c1_execution_v1"]
    replay_config = execution["replay"]
    training = execution["training"]
    arena_config = execution["arena"]
    replay_starts = allocate_disjoint_state_manifests(
        train_nonterminal,
        pools,
        states_per_seed=int(replay_config["reserved_start_states_per_seed"]),
        namespace=(f"{replay_config['start_manifest_namespace']}|{expected_split}"),
    )
    arena_starts = allocate_disjoint_state_manifests(
        development_nonterminal,
        pools,
        states_per_seed=int(arena_config["pairs_per_seed"]),
        namespace=f"{arena_config['start_manifest_namespace']}|{expected_split}",
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / "replay-start-manifest.json", replay_starts)
    _write_json(run_dir / "arena-start-manifest.json", arena_starts)

    graph_tensors = solved_tensors(oracle, graph)
    development_batch = int(base_loop["development"]["batch_size"])
    arena = ArenaConfig(
        pairs=int(arena_config["pairs_per_seed"]),
        max_plies=int(arena_config["max_plies"]),
        search_depth=int(arena_config["search_depth"]),
        node_budget=int(arena_config["node_budget"]),
        epsilon=float(arena_config["epsilon"]),
        confidence_z=float(arena_config["confidence_z"]),
        confidence_unit=str(arena_config["confidence_unit"]),
        start_state_source="provided",
    )
    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    for raw_seed in c1_seeds:
        seed = int(raw_seed)
        seed_everything(seed, int(base_loop["runtime"]["threads"]))
        initial_scaffold = _scaffold(config, seed)
        initial_export = initial_scaffold.export_pattern_eval()
        initial_hash = tensor_state_hash(initial_export)
        before = response_metrics(
            initial_export,
            graph,
            graph_tensors,
            oracle,
            development,
            development_batch,
        )

        raw_selfplay = deepcopy(base_loop["self_play"])
        raw_selfplay["games"] = int(replay_config["games_per_seed"])
        raw_selfplay["game_schedule"] = None
        raw_selfplay["start_state_source"] = "train_split"
        replay_start_row = assigned_states(replay_starts, "C1", seed)
        generation = generate_self_play(
            graph,
            initial_export,
            loop_module._parse_self_play(raw_selfplay),
            int(replay_config["generation"]),
            seed + int(replay_config["seed_offset"]),
            replay_start_row,
        )
        samples = [
            sample
            for sample in generation.samples
            if bool(train_mask[int(sample.state_id)])
        ]
        replay_manifest = freeze_replay_manifest(
            samples,
            pool="C1",
            seed=seed,
            source="G1_WIDE_OUTCOME",
            start_state_ids=replay_start_row,
        )
        targets = contextual_replay_targets(
            oracle,
            graph,
            samples,
            allowed_state_mask=train_mask,
            baseline_weights=config["baseline_v1"]["weights"],
            tau=float(config["baseline_v1"]["tau"]),
            residual_clip=float(config["baseline_v1"]["residual_clip"]),
        )
        schedule = batch_schedule(
            len(samples),
            int(training["steps"]),
            int(training["batch_size"]),
            seed + int(training["schedule_seed_offset"]),
        )
        starts = assigned_states(arena_starts, "C1", seed)
        arena_seed = seed + int(arena_config["seed_offset"])
        arm_rows: dict[str, Any] = {}
        exported_models: dict[str, PatternEval] = {}
        arena_start_hash: str | None = None
        schedule_hash: str | None = None
        for arm in DEPLOYABLE_ARMS:
            seed_everything(seed, int(base_loop["runtime"]["threads"]))
            scaffold = _scaffold(config, seed)
            if tensor_state_hash(scaffold.export_pattern_eval()) != initial_hash:
                raise RuntimeError("C1 arm scalar initial states diverged")
            metrics = train_contextual_from_replay(
                scaffold,
                graph,
                targets,
                arm=arm,
                config=config,
                indices=schedule,
                learning_rate=float(training["learning_rate"]),
                weight_decay=float(training["weight_decay"]),
            )
            if schedule_hash is None:
                schedule_hash = str(metrics["batch_schedule_hash"])
            elif metrics["batch_schedule_hash"] != schedule_hash:
                raise RuntimeError("C1 arm batch schedules diverged")
            exported = scaffold.export_pattern_eval()
            proof = prove_scalar_export(scaffold, oracle)
            if not proof["value_error_pass"] or not proof["action_match_pass"]:
                raise RuntimeError(
                    "C1 scalar export proof failed: "
                    f"seed={seed} arm={arm} proof={json.dumps(proof, sort_keys=True)}"
                )
            development_metrics = response_metrics(
                exported,
                graph,
                graph_tensors,
                oracle,
                development,
                development_batch,
            )
            arena_result = run_arena(
                graph,
                exported,
                initial_export,
                arena,
                arena_seed,
                starts,
            )
            if int(arena_result["unique_start_state_count"]) != int(arena.pairs):
                raise RuntimeError("C1 arena did not use one unique start per pair")
            current_start_hash = digest(arena_result["start_state_ids"])
            if arena_start_hash is None:
                arena_start_hash = current_start_hash
            elif current_start_hash != arena_start_hash:
                raise RuntimeError("C1 arm arena starts diverged")
            exported_models[arm] = exported
            _save_pattern_eval(
                run_dir / "checkpoints" / str(seed) / f"{arm}.npz", exported
            )
            arm_rows[arm] = {
                "training": metrics,
                "development": development_metrics,
                "arena": arena_result,
                "arena_score": float(arena_result["score"]),
                "export_proof": proof,
                "oracle_training_signal": False,
            }

        full_weight = exported_models[PRIMARY_HIGH].bucket_weight.detach()
        wdl_weight = exported_models[PRIMARY_LOW].bucket_weight.detach()
        auxiliary_changed = int(torch.count_nonzero(full_weight != wdl_weight).item())
        if auxiliary_changed < 1:
            raise RuntimeError("contextual auxiliary loss changed no exported bucket")

        direct, direct_training = _direct_table_fit(
            initial_export,
            graph,
            samples,
            schedule,
            training,
            seed,
        )
        if direct_training["initial_export_hash"] != initial_hash:
            raise RuntimeError(
                "direct-table control did not share scalar initialization"
            )
        direct_development = response_metrics(
            direct,
            graph,
            graph_tensors,
            oracle,
            development,
            development_batch,
        )
        direct_arena = run_arena(
            graph,
            direct,
            initial_export,
            arena,
            arena_seed,
            starts,
        )
        if digest(direct_arena["start_state_ids"]) != arena_start_hash:
            raise RuntimeError("direct-table descriptive control changed arena starts")
        _save_pattern_eval(
            run_dir / "checkpoints" / str(seed) / "WDL_DIRECT_TABLE.npz", direct
        )

        row = {
            "seed": seed,
            "initial_scalar_hash": initial_hash,
            "initial_development": before,
            "replay_manifest": replay_manifest,
            "replay_generation": _compact_generation_metrics(generation.metrics),
            "batch_schedule_hash": schedule_hash,
            "arena_start_hash": arena_start_hash,
            "arms": arm_rows,
            "auxiliary_export_difference": {
                "comparison": f"{PRIMARY_HIGH}_minus_{PRIMARY_LOW}",
                "changed_bucket_count": auxiliary_changed,
            },
            "direct_table_descriptive_control": {
                "training": direct_training,
                "development": direct_development,
                "arena": direct_arena,
                "arena_score": float(direct_arena["score"]),
                "excluded_from_C1_decision": True,
            },
        }
        rows.append(row)
        _write_json(run_dir / f"seed-{seed}.json", row)
        _write_progress(progress_output, len(rows), len(c1_seeds), seed)

    critical = float(
        config["c1_decision"]["provisional_readout"]["paired_confidence_critical_95"]
    )
    aggregate, status = _aggregate(rows, critical)
    protocol = {
        "schema": SCHEMA,
        "config_schema": config["schema"],
        "c0_report_hash": config["c0_gate"]["frozen_report_v1"]["report_hash"],
        "M21P_result_hash": config["data_contract"]["prerequisites"][
            "M21_P_strength_source"
        ]["result_hash"],
        "power_report_hash": config["power_sizing_v1"]["frozen_report_v1"][
            "report_hash"
        ],
        "selected_replay_source": config["replay_source_decision_v1"][
            "selected_source"
        ],
        "paired_seeds": list(c1_seeds),
        "deployable_arms": list(DEPLOYABLE_ARMS),
        "execution": execution,
        "replay_start_manifest_hash": replay_starts["manifest_hash"],
        "arena_start_manifest_hash": arena_starts["manifest_hash"],
        "execution_host": host,
        "implementation_sha": implementation_sha,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
        "elapsed_seconds": float(time.monotonic() - started),
        "c2_required": True,
        "c1_terminal_PASS_or_FAIL_forbidden": True,
        "sealed_cohort_contract": {
            "cohorts_read": ["train", "development"],
            "cohorts_not_read": ["frozen_test"],
            "oracle_training_signal_deployable_arms": False,
        },
        "promotable": False,
        "implementation_sha": implementation_sha,
    }
    result["result_hash"] = digest(
        {key: value for key, value in result.items() if key != "elapsed_seconds"}
    )
    _write_json(run_dir / "result.full.json", result)
    compact = {
        "schema": SCHEMA,
        "status": status,
        "implementation_sha": implementation_sha,
        "protocol_hash": result["protocol_hash"],
        "result_hash": result["result_hash"],
        "aggregate": aggregate,
        "c2_required": True,
        "sealed_test_read": False,
    }
    _write_json(compact_output, compact)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--execution-host")
    parser.add_argument("--implementation-sha", required=True)
    parser.add_argument("--progress-output", type=Path)
    args = parser.parse_args()
    result = run_c1(
        args.config,
        args.oracle,
        args.run_dir,
        args.compact_output,
        implementation_sha=args.implementation_sha,
        execution_host=args.execution_host,
        progress_output=args.progress_output,
    )
    print(
        json.dumps({"status": result["status"], "result_hash": result["result_hash"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
