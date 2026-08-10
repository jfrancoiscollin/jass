#!/usr/bin/env python3
"""Run disjoint contextual pool C2 and the frozen chained C1+C2 decision."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import numpy as np  # noqa: E402
import torch  # noqa: E402

import mini_jass_lab.loop as loop_module  # noqa: E402
from mini_jass_lab.arena import ArenaConfig, run_arena  # noqa: E402
from mini_jass_lab.context_decision import (  # noqa: E402
    contextual_mechanism_decision,
    sequential_flat_prior_paired_score,
)
from mini_jass_lab.context_replay import (  # noqa: E402
    allocate_disjoint_state_manifests,
    assert_replay_pool_disjointness,
    assigned_states,
    freeze_replay_manifest,
)
from mini_jass_lab.context_scaffold import prove_scalar_export  # noqa: E402
from mini_jass_lab.context_training import (  # noqa: E402
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
from mini_jass_lab.selfplay import generate_self_play  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402
from run_contextual_c1 import (  # noqa: E402
    _compact_generation_metrics,
    _resolve as _resolve_c1_contract,
    _save_pattern_eval,
    _scaffold,
    _write_json,
)

SCHEMA = "mini_jass.contextual_c2.v1"
PRIMARY_HIGH = "WDL_PLUS_FULL_CONTEXT"
PRIMARY_LOW = "WDL_ONLY"
C2_ARMS = (PRIMARY_LOW, PRIMARY_HIGH)
FROZEN_C1_RESULT_HASH = (
    "5d3bbf6490e9d1eb6bf3a73b82bb2ab4a53099ec9799db08cd6815cc0fb28f28"
)
FROZEN_C1_FREEZE_HASH = (
    "1d0c02385103d6bdd31e9d070e468c450ecbf0e4a763d7ea19fff9d0c5dc192c"
)


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config, base_loop = _resolve_c1_contract(path)
    if config.get("status") not in (
        "C1_FROZEN_C2_implementation_ready_for_verification",
        "C2_FROZEN_SEALED_READ_implementation_ready_for_verification",
        "C3_COMPLETE_DIAGNOSTIC_ONLY",
    ):
        raise ValueError("C2 requires the independently frozen C1 evidence")
    frozen = config["c1_decision"]["frozen_report_v1"]
    if (
        frozen.get("source_result_hash") != FROZEN_C1_RESULT_HASH
        or frozen.get("freeze_report_hash") != FROZEN_C1_FREEZE_HASH
        or frozen.get("freeze_status") != "PASS_C1_FREEZE_C2_AUTHORIZED"
        or frozen.get("c2_authorized") is not True
        or frozen.get("sealed_test_read") is not False
    ):
        raise ValueError("C2 authorization differs from the frozen C1 evidence")
    replication = config["c2_disjoint_replication"]
    if tuple(replication["arms"]) != C2_ARMS:
        raise ValueError("C2 confirmatory arms changed")
    if (
        replication.get("required_even_if_C1_is_flat_or_negative") is not True
        or replication.get("training_replay_disjoint_from_C1") is not True
        or replication.get("arena_starts_disjoint_from_C1") is not True
        or replication.get("same_frozen_recipe_as_C1") is not True
    ):
        raise ValueError("C2 disjoint replication contract changed")
    decision = config["final_chained_decision"]
    definition = decision["estimator_definition"]
    if (
        tuple(decision["evidence_pools"]) != ("C1", "C2")
        or decision.get("pool_disjointness_required") is not True
        or decision.get("estimator")
        != "sequential_flat_prior_paired_score_v1"
        or decision.get("C1_posterior_becomes_C2_prior") is not True
        or definition.get("initial_prior") != "improper_flat_on_score_delta"
        or definition.get("sequential_update")
        != "inverse_variance_normal_C1_then_C2"
        or float(decision["heterogeneity_guard"]["maximum_z"]) != 1.96
        or float(
            decision["signal_established"][
                "posterior_probability_score_delta_gt_zero_strictly_greater_than"
            ]
        )
        != 0.95
        or decision.get("automatic_promotion_forbidden") is not True
    ):
        raise ValueError("C2 final decision contract changed")
    return config, base_loop


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _verify_embedded_hash(value: Mapping[str, Any], field: str) -> None:
    expected = str(value[field])
    actual = digest({key: item for key, item in value.items() if key != field})
    if actual != expected:
        raise ValueError(f"{field} mismatch: {actual} != {expected}")


def _verify_c1(
    config: Mapping[str, Any],
    result_path: Path,
    freeze_report_path: Path,
    replay_starts_path: Path,
    arena_starts_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    frozen = config["c1_decision"]["frozen_report_v1"]
    freeze_report = _load_json(freeze_report_path)
    _verify_embedded_hash(freeze_report, "report_hash")
    if (
        freeze_report.get("schema") != "mini_jass.contextual_c1_freeze.v1"
        or freeze_report.get("report_hash") != frozen["freeze_report_hash"]
        or freeze_report.get("status") != frozen["freeze_status"]
        or freeze_report.get("source_result_hash") != frozen["source_result_hash"]
        or freeze_report.get("source_protocol_hash")
        != frozen["source_protocol_hash"]
        or freeze_report.get("source_implementation_sha")
        != frozen["source_implementation_sha"]
        or freeze_report.get("replay_start_manifest_hash")
        != frozen["replay_start_manifest_hash"]
        or freeze_report.get("arena_start_manifest_hash")
        != frozen["arena_start_manifest_hash"]
        or freeze_report.get("c2_authorized") is not True
        or freeze_report.get("sealed_test_read") is not False
    ):
        raise ValueError("C1 freeze report differs from the control pin")
    result = _load_json(result_path)
    if (
        result.get("schema") != "mini_jass.contextual_c1.v1"
        or result.get("status") != frozen["source_status"]
        or result.get("result_hash") != frozen["source_result_hash"]
        or result.get("protocol_hash") != frozen["source_protocol_hash"]
        or result.get("implementation_sha") != frozen["source_implementation_sha"]
        or result.get("c2_required") is not True
        or result["sealed_cohort_contract"].get("cohorts_not_read")
        != ["frozen_test"]
    ):
        raise ValueError("C1 full result differs from the frozen evidence")
    calculated_result_hash = digest(
        {
            key: value
            for key, value in result.items()
            if key not in ("elapsed_seconds", "result_hash")
        }
    )
    if calculated_result_hash != result["result_hash"]:
        raise ValueError("C1 full result content hash mismatch")
    if digest(result["protocol"]) != result["protocol_hash"]:
        raise ValueError("C1 protocol content hash mismatch")
    replay_starts = _load_json(replay_starts_path)
    arena_starts = _load_json(arena_starts_path)
    _verify_embedded_hash(replay_starts, "manifest_hash")
    _verify_embedded_hash(arena_starts, "manifest_hash")
    if (
        replay_starts["manifest_hash"] != frozen["replay_start_manifest_hash"]
        or arena_starts["manifest_hash"] != frozen["arena_start_manifest_hash"]
        or result["protocol"]["replay_start_manifest_hash"]
        != replay_starts["manifest_hash"]
        or result["protocol"]["arena_start_manifest_hash"]
        != arena_starts["manifest_hash"]
    ):
        raise ValueError("C1 start manifests differ from the frozen evidence")
    manifests = [row["replay_manifest"] for row in result["seed_results"]]
    hashes = [manifest["manifest_hash"] for manifest in manifests]
    if hashes != list(frozen["replay_manifest_hashes"]):
        raise ValueError("C1 replay manifests differ from the frozen evidence")
    if hashes != list(freeze_report["c1_replay_manifest_hashes"]):
        raise ValueError("C1 replay manifests differ from the freeze report")
    for manifest in manifests:
        _verify_embedded_hash(manifest, "manifest_hash")
    return result, replay_starts, arena_starts


def _write_progress(path: Path | None, completed: int, total: int, seed: int) -> None:
    if path is None:
        return
    _write_json(
        path,
        {
            "schema": "mini_jass.contextual_c2_progress.v1",
            "completed_seeds": int(completed),
            "total_seeds": int(total),
            "last_completed_seed": int(seed),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _pool_deltas(rows: list[dict[str, Any]], metric: str) -> list[float]:
    if metric == "arena_score":
        return [
            float(row["arms"][PRIMARY_HIGH]["arena_score"])
            - float(row["arms"][PRIMARY_LOW]["arena_score"])
            for row in rows
        ]
    if metric == "value_mae":
        return [
            float(row["arms"][PRIMARY_HIGH]["development"]["value_mae"])
            - float(row["arms"][PRIMARY_LOW]["development"]["value_mae"])
            for row in rows
        ]
    raise ValueError(f"unsupported contextual metric: {metric}")


def _aggregate(rows: list[dict[str, Any]], critical: float) -> dict[str, Any]:
    primary = paired_interval(_pool_deltas(rows, "arena_score"), critical)
    primary["positive_seed_count"] = sum(
        delta > 0.0 for delta in _pool_deltas(rows, "arena_score")
    )
    primary["zero_seed_count"] = sum(
        delta == 0.0 for delta in _pool_deltas(rows, "arena_score")
    )
    return {
        "paired_seed_count": len(rows),
        "primary_contrast": f"{PRIMARY_HIGH}_minus_{PRIMARY_LOW}",
        "primary_common_search_arena_score": primary,
        "registered_mechanism_value_mae": {
            "contrast": f"{PRIMARY_HIGH}_minus_{PRIMARY_LOW}",
            "improvement_direction": "negative",
            "paired_interval": paired_interval(
                _pool_deltas(rows, "value_mae"), critical
            ),
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
                    row["arms"][arm]["development"]["zero_regret_rate"]
                    for row in rows
                ),
            }
            for arm in C2_ARMS
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


def run_c2(
    config_path: Path,
    oracle_path: Path,
    c1_result_path: Path,
    c1_freeze_report_path: Path,
    c1_replay_starts_path: Path,
    c1_arena_starts_path: Path,
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
        raise ValueError("C2 implementation SHA must be a full lowercase Git SHA")
    host = execution_host or platform.node()
    if host != "cpx62":
        raise ValueError(f"contextual C2 requires cpx62, got {host}")
    c1_result, frozen_replay_starts, frozen_arena_starts = _verify_c1(
        config,
        c1_result_path,
        c1_freeze_report_path,
        c1_replay_starts_path,
        c1_arena_starts_path,
    )
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    expected_split = config["data_contract"]["split_manifest_hash"]
    if split.manifest["manifest_hash"] != expected_split:
        raise ValueError("C2 split differs from the frozen L1 contract")
    train = split.indices("train")
    development = split.indices("development")
    train_mask = np.zeros(graph.state_count, dtype=np.bool_)
    train_mask[train] = True
    train_nonterminal = [
        int(state) for state in train if graph.terminal_value(int(state)) is None
    ]
    development_nonterminal = [
        int(state)
        for state in development
        if graph.terminal_value(int(state)) is None
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
        namespace=f"{replay_config['start_manifest_namespace']}|{expected_split}",
    )
    arena_starts = allocate_disjoint_state_manifests(
        development_nonterminal,
        pools,
        states_per_seed=int(arena_config["pairs_per_seed"]),
        namespace=f"{arena_config['start_manifest_namespace']}|{expected_split}",
    )
    if replay_starts != frozen_replay_starts or arena_starts != frozen_arena_starts:
        raise ValueError("C2 could not reproduce the globally disjoint start manifests")
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
    for raw_seed in c2_seeds:
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
        replay_start_row = assigned_states(replay_starts, "C2", seed)
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
            pool="C2",
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
        starts = assigned_states(arena_starts, "C2", seed)
        arena_seed = seed + int(arena_config["seed_offset"])
        arm_rows: dict[str, Any] = {}
        exported_models: dict[str, PatternEval] = {}
        arena_start_hash: str | None = None
        schedule_hash: str | None = None
        for arm in C2_ARMS:
            seed_everything(seed, int(base_loop["runtime"]["threads"]))
            scaffold = _scaffold(config, seed)
            if tensor_state_hash(scaffold.export_pattern_eval()) != initial_hash:
                raise RuntimeError("C2 arm scalar initial states diverged")
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
                raise RuntimeError("C2 arm batch schedules diverged")
            exported = scaffold.export_pattern_eval()
            proof = prove_scalar_export(scaffold, oracle)
            if not proof["value_error_pass"] or not proof["action_match_pass"]:
                raise RuntimeError(
                    "C2 scalar export proof failed: "
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
                graph, exported, initial_export, arena, arena_seed, starts
            )
            if int(arena_result["unique_start_state_count"]) != int(arena.pairs):
                raise RuntimeError("C2 arena did not use one unique start per pair")
            current_start_hash = digest(arena_result["start_state_ids"])
            if arena_start_hash is None:
                arena_start_hash = current_start_hash
            elif current_start_hash != arena_start_hash:
                raise RuntimeError("C2 arm arena starts diverged")
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
        changed = int(
            torch.count_nonzero(
                exported_models[PRIMARY_HIGH].bucket_weight.detach()
                != exported_models[PRIMARY_LOW].bucket_weight.detach()
            ).item()
        )
        if changed < 1:
            raise RuntimeError("C2 contextual auxiliary loss changed no exported bucket")
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
                "changed_bucket_count": changed,
            },
        }
        rows.append(row)
        _write_json(run_dir / f"seed-{seed}.json", row)
        _write_progress(progress_output, len(rows), len(c2_seeds), seed)

    c1_manifests = [row["replay_manifest"] for row in c1_result["seed_results"]]
    c2_manifests = [row["replay_manifest"] for row in rows]
    disjointness = assert_replay_pool_disjointness(c1_manifests + c2_manifests)
    _write_json(run_dir / "replay-disjointness.json", disjointness)
    critical = float(
        config["c1_decision"]["provisional_readout"][
            "paired_confidence_critical_95"
        ]
    )
    aggregate = _aggregate(rows, critical)
    c1_rows = c1_result["seed_results"]
    decision_config = config["final_chained_decision"]
    final_decision = sequential_flat_prior_paired_score(
        _pool_deltas(c1_rows, "arena_score"),
        _pool_deltas(rows, "arena_score"),
        thresholds=tuple(
            float(value)
            for value in decision_config[
                "publish_posterior_probability_above_score_delta"
            ]
        ),
        heterogeneity_maximum_z=float(
            decision_config["heterogeneity_guard"]["maximum_z"]
        ),
        signal_probability=float(
            decision_config["signal_established"][
                "posterior_probability_score_delta_gt_zero_strictly_greater_than"
            ]
        ),
    )
    mechanism = contextual_mechanism_decision(
        _pool_deltas(c1_rows, "value_mae"),
        _pool_deltas(rows, "value_mae"),
        heterogeneity_maximum_z=float(
            decision_config["heterogeneity_guard"]["maximum_z"]
        ),
        signal_probability=0.95,
    )
    force_signal = final_decision["decision"] == "SIGNAL_ESTABLISHED"
    mechanism_signal = bool(mechanism["signal"])
    interpretation = (
        "force_and_calibration"
        if force_signal and mechanism_signal
        else "calibration_without_force"
        if mechanism_signal
        else "force_without_calibration"
        if force_signal
        else "neither"
    )
    protocol = {
        "schema": SCHEMA,
        "config_schema": config["schema"],
        "c1_result_hash": c1_result["result_hash"],
        "c1_freeze_report_hash": config["c1_decision"]["frozen_report_v1"][
            "freeze_report_hash"
        ],
        "paired_seeds": list(c2_seeds),
        "deployable_arms": list(C2_ARMS),
        "execution": execution,
        "replay_start_manifest_hash": replay_starts["manifest_hash"],
        "arena_start_manifest_hash": arena_starts["manifest_hash"],
        "replay_disjointness_report_hash": disjointness["report_hash"],
        "final_chained_decision": decision_config,
        "execution_host": host,
        "implementation_sha": implementation_sha,
    }
    status = f"C2_COMPLETE_{final_decision['decision']}"
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "status": status,
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "c1_frozen_summary": {
            "result_hash": c1_result["result_hash"],
            "status": c1_result["status"],
            "aggregate": c1_result["aggregate"],
        },
        "c2_aggregate": aggregate,
        "c2_seed_results": rows,
        "replay_disjointness": disjointness,
        "final_chained_decision": final_decision,
        "registered_mechanism_decision": mechanism,
        "mechanism_force_interpretation": interpretation,
        "elapsed_seconds": float(time.monotonic() - started),
        "sealed_cohort_contract": {
            "cohorts_read": ["train", "development"],
            "cohorts_not_read": ["frozen_test"],
            "sealed_test_read_authorized_only_after_independent_C2_freeze": True,
        },
        "promotable": False,
        "automatic_promotion": False,
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
        "c1_status": c1_result["status"],
        "c2_aggregate": aggregate,
        "replay_disjointness": disjointness,
        "final_chained_decision": final_decision,
        "registered_mechanism_decision": mechanism,
        "mechanism_force_interpretation": interpretation,
        "sealed_test_read": False,
        "promotable": False,
    }
    _write_json(compact_output, compact)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--c1-result", type=Path, required=True)
    parser.add_argument("--c1-freeze-report", type=Path, required=True)
    parser.add_argument("--c1-replay-start-manifest", type=Path, required=True)
    parser.add_argument("--c1-arena-start-manifest", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--execution-host")
    parser.add_argument("--implementation-sha", required=True)
    parser.add_argument("--progress-output", type=Path)
    args = parser.parse_args()
    result = run_c2(
        args.config,
        args.oracle,
        args.c1_result,
        args.c1_freeze_report,
        args.c1_replay_start_manifest,
        args.c1_arena_start_manifest,
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
