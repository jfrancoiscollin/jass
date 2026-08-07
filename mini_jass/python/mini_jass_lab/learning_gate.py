"""M6 L1 consolidation pack and strict scale-up decision gate."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np
import torch
import yaml

from .experiment import (
    PendingRun,
    SUMMARY_METRICS,
    _apply_overrides,
    _digest,
    _file_sha256,
    _metric_subset,
    _node_totals,
    _oracle_tensors,
    _package_sha256,
    _sample_strata,
    _trace_diagnostics,
    build_comparison,
)
from .game_graph import GameGraph
from .loop import execute_loop
from .model import MiniJassMLP, ModelConfig, model_hash
from .oracle import OracleArrays, ensure_artefact_path, load_oracle
from .replay import ReplaySample
from .split import SPLIT_NAMES, SplitDefinition, build_split
from .train import evaluate, seed_everything


EXPERIMENT_IDS = ("E5", "E6", "E7", "E8", "E9")
M6_SUMMARY_METRICS = SUMMARY_METRICS + (
    "starts.unique",
    "training.optimizer_steps",
    "training.final_sample_pool",
    "development.selection_score_delta",
    "development.sampled.count",
    "development.sampled.value_sign_delta",
    "development.sampled.optimal_mass_delta",
    "targets.overall.value_exact_rate",
    "targets.overall.value_mae",
    "targets.overall.policy_optimal_mass",
    "targets.overall.policy_argmax_optimal_rate",
    "targets.overall.unique_states",
    "promotion.eligible_generation_count",
    "promotion.provisional_advance_count",
)


@dataclass(frozen=True)
class LearningGateConfig:
    resolved: dict[str, Any]
    m5_evidence: dict[str, Any]
    m5_path: Path


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def resolve_learning_gate_config(config_path: Path) -> LearningGateConfig:
    pack = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if pack.get("schema") != "mini_jass.learning_gate.v1":
        raise ValueError("unexpected M6 learning-gate schema")
    seeds = [int(seed) for seed in pack["paired_seeds"]]
    if len(seeds) < 5 or len(set(seeds)) != len(seeds):
        raise ValueError("M6 requires at least five distinct paired seeds")
    if tuple(pack["experiments"].keys()) != EXPERIMENT_IDS:
        raise ValueError("M6 must declare E5 through E9 in order")

    base_path = Path(pack["base_loop_config"])
    if not base_path.is_absolute():
        base_path = config_path.parent.parent / base_path
    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    if base.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M6 base must be an M4 self-play config")
    _apply_overrides(base, pack.get("base_overrides", {}))

    m5_path = Path(pack["m5_evidence"])
    if not m5_path.is_absolute():
        m5_path = config_path.parent.parent / m5_path
    m5_evidence = json.loads(m5_path.read_text(encoding="utf-8"))
    if m5_evidence.get("schema") != "mini_jass.m5_experiment_pack.v1":
        raise ValueError("M6 requires the compact M5 evidence record")
    if m5_evidence.get("result_hash") != pack["expected_m5_result_hash"]:
        raise ValueError("M5 evidence hash differs from the preregistered M6 input")
    if m5_evidence["recommendation"]["decision"] != "continue_L1":
        raise ValueError("M6 is only valid after the M5 continue-L1 decision")

    resolved = deepcopy(pack)
    resolved["paired_seeds"] = seeds
    resolved["base_loop_config"] = str(base_path.resolve())
    resolved["m5_evidence"] = str(m5_path.resolve())
    resolved["base_loop"] = base
    return LearningGateConfig(resolved, m5_evidence, m5_path)


def expand_learning_gate_configs(
    resolved: dict[str, Any],
) -> list[tuple[str, str, int, dict[str, Any]]]:
    expanded: list[tuple[str, str, int, dict[str, Any]]] = []
    for experiment_id, experiment in resolved["experiments"].items():
        for arm_name, arm in experiment["arms"].items():
            for seed in resolved["paired_seeds"]:
                config = deepcopy(resolved["base_loop"])
                _apply_overrides(config, experiment.get("overrides", {}))
                _apply_overrides(config, arm.get("overrides", {}))
                config["seed"] = seed
                config["experiment"] = {
                    "id": experiment_id,
                    "arm": arm_name,
                    "causal_factor": experiment["causal_factor"],
                }
                expanded.append((experiment_id, arm_name, seed, config))
    return expanded


def _target_subset(samples: list[ReplaySample], oracle: OracleArrays) -> dict[str, Any]:
    if not samples:
        return {
            "count": 0,
            "unique_states": 0,
            "value_exact_rate": None,
            "value_mae": None,
            "policy_optimal_mass": None,
            "policy_argmax_optimal_rate": None,
        }
    state_ids = np.asarray([sample.state_id for sample in samples], dtype=np.int64)
    value_targets = np.asarray([sample.value_target for sample in samples], dtype=np.float32)
    policies = np.stack([sample.policy_target for sample in samples])
    exact_values = oracle.values[state_ids].astype(np.float32)
    optimal_mass = (policies * oracle.optimal_mask[state_ids]).sum(axis=1)
    argmax = policies.argmax(axis=1)
    return {
        "count": len(samples),
        "unique_states": int(np.unique(state_ids).size),
        "value_exact_rate": float(np.mean(value_targets == exact_values)),
        "value_mae": float(np.mean(np.abs(value_targets - exact_values))),
        "policy_optimal_mass": float(np.mean(optimal_mass)),
        "policy_argmax_optimal_rate": float(
            np.mean(oracle.optimal_mask[state_ids, argmax])
        ),
    }


def target_diagnostics(
    samples: list[ReplaySample], oracle: OracleArrays, split: SplitDefinition
) -> dict[str, Any]:
    """Read exact labels only after the protocol and every candidate are fixed."""
    diagnostics = {"overall": _target_subset(samples, oracle), "by_cohort": {}}
    for cohort_index, cohort in enumerate(SPLIT_NAMES):
        selected = [
            sample
            for sample in samples
            if int(split.raw_assignments[sample.state_id]) == cohort_index
        ]
        diagnostics["by_cohort"][cohort] = _target_subset(selected, oracle)
    return diagnostics


def _evaluation_delta(
    initial: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    if not initial.get("count") or not candidate.get("count"):
        return {"count": 0, "value_sign_delta": None, "optimal_mass_delta": None}
    return {
        "count": int(candidate["count"]),
        "initial": initial,
        "candidate": candidate,
        "value_sign_delta": candidate["value_sign_accuracy"]
        - initial["value_sign_accuracy"],
        "optimal_mass_delta": candidate["optimal_probability_mass"]
        - initial["optimal_probability_mass"],
    }


def _mean_metric(comparison: dict[str, Any], experiment: str, arm: str, path: str) -> float:
    return float(
        comparison["experiments"][experiment]["arms"][arm]["metrics"][path]["mean"]
    )


def build_learning_recommendation(
    resolved: dict[str, Any], comparison: dict[str, Any]
) -> dict[str, Any]:
    successful = all(
        arm["run_count"] == len(resolved["paired_seeds"])
        for experiment in comparison["experiments"].values()
        for arm in experiment["arms"].values()
    )
    if not successful:
        return {
            "schema": "mini_jass.l1_learning_recommendation.v1",
            "decision": "incomplete_pack",
            "direct_10x10_transfer_authorized": False,
            "l2_transfer_authorized": False,
            "gate": {"status": "FAIL", "criteria": {"all_runs_successful": False}},
            "evidence": {},
            "rationale": "At least one preregistered M6 arm has no successful run.",
            "next_gate": "Repair and rerun the complete paired pack on L1.",
        }

    candidates: list[tuple[float, str, str]] = []
    for experiment_id, experiment in comparison["experiments"].items():
        for arm_name, arm in experiment["arms"].items():
            metric = arm["metrics"].get("development.selection_score_delta")
            if metric:
                candidates.append((float(metric["mean"]), experiment_id, arm_name))
    _, selected_experiment, selected_arm = max(candidates)
    selected = comparison["experiments"][selected_experiment]["arms"][selected_arm][
        "metrics"
    ]

    initial_coverage = _mean_metric(
        comparison, "E5", "initial_state", "coverage.unique_states"
    )
    restart_coverage = _mean_metric(
        comparison, "E5", "train_restarts", "coverage.unique_states"
    )
    coverage_multiplier = restart_coverage / initial_coverage
    value_delta = float(selected["development.value_sign_delta"]["mean"])
    mass_delta = float(selected["development.optimal_mass_delta"]["mean"])
    selection_interval = selected["development.selection_score_delta"]["confidence_95"]
    target_value = float(selected["targets.overall.value_exact_rate"]["mean"])
    target_mass = float(selected["targets.overall.policy_optimal_mass"]["mean"])
    eligible_mean = float(selected["promotion.eligible_generation_count"]["mean"])
    gate_config = resolved["learning_gate"]
    criteria = {
        "coverage_multiplier": coverage_multiplier
        >= float(gate_config["minimum_coverage_multiplier"]),
        "mean_development_value_sign_delta": value_delta
        > float(gate_config["minimum_mean_value_sign_delta"]),
        "mean_development_optimal_mass_delta": mass_delta
        > float(gate_config["minimum_mean_optimal_mass_delta"]),
        "selection_confidence_interval_above_zero": float(selection_interval[0]) > 0.0,
        "minimum_target_value_exact_rate": target_value
        >= float(gate_config["minimum_target_value_exact_rate"]),
        "minimum_target_optimal_mass": target_mass
        >= float(gate_config["minimum_target_optimal_mass"]),
        "at_least_one_eligible_candidate": eligible_mean > 0.0,
    }
    passed = all(criteria.values())
    decision = "advance_to_L2_not_10x10" if passed else "continue_L1_policy_gate"
    rationale = (
        "A paired L1 mechanism improved value-sign and optimal-move mass, its "
        "selection-score confidence interval excludes zero, and eligible candidates exist."
        if passed
        else "L1 now converts broader coverage into repeatable value progress, but the "
        "strict optimal-move-mass gate is not yet satisfied."
    )
    return {
        "schema": "mini_jass.l1_learning_recommendation.v1",
        "decision": decision,
        "direct_10x10_transfer_authorized": False,
        "l2_transfer_authorized": passed,
        "gate": {"status": "PASS" if passed else "FAIL", "criteria": criteria},
        "evidence": {
            "selected_experiment": selected_experiment,
            "selected_arm": selected_arm,
            "coverage_multiplier": coverage_multiplier,
            "mean_development_value_sign_delta": value_delta,
            "mean_development_optimal_mass_delta": mass_delta,
            "selection_score_confidence_95": selection_interval,
            "mean_target_value_exact_rate": target_value,
            "mean_target_optimal_mass": target_mass,
            "mean_eligible_generation_count": eligible_mean,
        },
        "rationale": rationale,
        "next_gate": (
            "Replicate only the selected mechanism on L2 before any Jass 10x10 work."
            if passed
            else "Repair search-policy target generalization on L1, then rerun this frozen gate."
        ),
    }


def _summary_markdown(
    result: dict[str, Any], comparison: dict[str, Any], recommendation: dict[str, Any]
) -> str:
    lines = [
        "# Mini-Jass M6 L1 learning gate",
        "",
        f"- Execution gate: **{result['gate']['status']}**",
        f"- Scientific gate: **{recommendation['gate']['status']}**",
        f"- Runs: {result['run_count']} ({result['successful_run_count']} successful)",
        f"- Decision: **{recommendation['decision']}**",
        f"- Protocol hash: `{result['protocol_hash']}`",
        "",
        "| Experiment | Arm | Nodes | Coverage | Dev value delta | Dev mass delta | Target mass |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for experiment_id, experiment in comparison["experiments"].items():
        for arm_name, arm in experiment["arms"].items():
            metrics = arm["metrics"]
            if arm["run_count"]:
                lines.append(
                    f"| {experiment_id} | {arm_name} | "
                    f"{metrics['nodes.consumed']['mean']:.1f} | "
                    f"{metrics['coverage.unique_states']['mean']:.1f} | "
                    f"{metrics['development.value_sign_delta']['mean']:.4f} | "
                    f"{metrics['development.optimal_mass_delta']['mean']:.4f} | "
                    f"{metrics['targets.overall.policy_optimal_mass']['mean']:.4f} |"
                )
    lines.extend(["", recommendation["rationale"], ""])
    return "\n".join(lines)


def _compact_record(
    result: dict[str, Any],
    recommendation: dict[str, Any],
    comparison: dict[str, Any],
    m5_evidence: dict[str, Any],
    run_dir: Path,
) -> dict[str, Any]:
    artefact_names = (
        "config.resolved.yaml",
        "arm_results.jsonl",
        "comparison.json",
        "recommendation.json",
        "result.json",
        "summary.md",
        "executable_manifest.json",
    )
    return {
        "schema": "mini_jass.m6_learning_gate.v1",
        "milestone": "M6",
        "status": result["gate"]["status"],
        "protocol_hash": result["protocol_hash"],
        "result_hash": result["result_hash"],
        "m5_result_hash": m5_evidence["result_hash"],
        "pack": {
            "experiments": list(EXPERIMENT_IDS),
            "arm_count": sum(
                len(experiment["arms"])
                for experiment in comparison["experiments"].values()
            ),
            "paired_seeds": result["paired_seeds"],
            "run_count": result["run_count"],
            "successful_run_count": result["successful_run_count"],
        },
        "gate": result["gate"],
        "scientific_gate": recommendation["gate"],
        "evidence": recommendation["evidence"],
        "recommendation": {
            "decision": recommendation["decision"],
            "l2_transfer_authorized": recommendation["l2_transfer_authorized"],
            "direct_10x10_transfer_authorized": False,
            "reason": recommendation["rationale"],
            "next_gate": recommendation["next_gate"],
        },
        "contracts": result["contracts"],
        "artifact_hashes": {
            name: _file_sha256(run_dir / name) for name in artefact_names
        },
    }


def run_learning_gate(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path | None = None,
) -> dict[str, Any]:
    loaded = resolve_learning_gate_config(config_path)
    resolved = loaded.resolved
    run_dir = ensure_artefact_path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    oracle = load_oracle(oracle_path)
    split = build_split(oracle, int(resolved["base_loop"]["split_seed"]))
    expected_hash = resolved["base_loop"]["expected_split_manifest_hash"]
    if split.manifest["manifest_hash"] != expected_hash:
        raise ValueError("M6 split differs from the frozen contract")
    development_indices = split.indices("development")
    training_start_indices = split.indices("train")
    graph = GameGraph.from_oracle(oracle)
    graph.validate()

    solver_manifest_path = ensure_artefact_path(
        Path(__file__).resolve().parents[2] / "artefacts/solver_manifest.v1.json"
    )
    solver_manifest = json.loads(solver_manifest_path.read_text(encoding="utf-8"))
    contracts = {
        "rule_schema": solver_manifest["rules"]["schema"],
        "action_schema": solver_manifest["action_schema"],
        "action_vocabulary_hash": solver_manifest["action_vocabulary_hash"],
        "raw_graph_hash": solver_manifest["raw_graph_hash"],
        "canonical_graph_hash": solver_manifest["canonical_graph_hash"],
        "solver_hash": solver_manifest["solver_hash"],
        "split_manifest_hash": split.manifest["manifest_hash"],
        "oracle_export_sha256": _file_sha256(oracle_path),
        "python_package_sha256": _package_sha256(),
        "m5_result_hash": loaded.m5_evidence["result_hash"],
        "m5_evidence_sha256": _file_sha256(loaded.m5_path),
    }
    protocol = {
        "schema": resolved["schema"],
        "paired_seeds": resolved["paired_seeds"],
        "experiments": resolved["experiments"],
        "base_loop": resolved["base_loop"],
        "report_procedure": resolved["report_procedure"],
        "learning_gate": resolved["learning_gate"],
        "frozen_test_policy": "evaluate_all_fixed_candidates_after_protocol_hash",
        "contracts": contracts,
    }
    protocol_hash = _digest(protocol)

    pending: list[PendingRun] = []
    expanded = expand_learning_gate_configs(resolved)
    for experiment, arm, seed, loop_config in expanded:
        try:
            starts = (
                training_start_indices
                if loop_config["self_play"].get("start_state_source") == "train_split"
                else None
            )
            execution = execute_loop(
                loop_config, oracle, development_indices, starts
            )
            pending.append(PendingRun(experiment, arm, seed, loop_config, execution))
        except Exception as error:
            pending.append(PendingRun(experiment, arm, seed, loop_config, None, repr(error)))

    # Only now may frozen membership and exact labels be used for diagnostics.
    frozen_indices = split.indices("frozen_test")
    tensors = _oracle_tensors(oracle, graph)
    initial_cache: dict[int, tuple[MiniJassMLP, dict[str, Any], dict[str, Any]]] = {}
    records: list[dict[str, Any]] = []
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir()
    per_run_dir = run_dir / "runs"
    per_run_dir.mkdir()
    for pending_run in pending:
        if pending_run.execution is None:
            records.append(
                {
                    "run_id": pending_run.run_id,
                    "experiment": pending_run.experiment,
                    "arm": pending_run.arm,
                    "seed": pending_run.seed,
                    "status": "FAIL",
                    "error": pending_run.error,
                }
            )
            continue
        execution = pending_run.execution
        batch_size = int(pending_run.config["development"]["batch_size"])
        if pending_run.seed not in initial_cache:
            seed_everything(pending_run.seed, int(pending_run.config["runtime"]["threads"]))
            initial = MiniJassMLP(ModelConfig(**pending_run.config["model"]))
            initial_cache[pending_run.seed] = (
                initial,
                _metric_subset(evaluate(initial, tensors, oracle, development_indices, batch_size)),
                _metric_subset(evaluate(initial, tensors, oracle, frozen_indices, batch_size)),
            )
        initial, initial_development, initial_frozen = initial_cache[pending_run.seed]
        candidate = MiniJassMLP(ModelConfig(**pending_run.config["model"]))
        candidate.load_state_dict(execution.candidate_states[-1])
        candidate_development = _metric_subset(
            evaluate(candidate, tensors, oracle, development_indices, batch_size)
        )
        candidate_frozen = _metric_subset(
            evaluate(candidate, tensors, oracle, frozen_indices, batch_size)
        )
        sampled_development_indices = development_indices[
            execution.state_sample_counts[development_indices] > 0
        ]
        if sampled_development_indices.size:
            sampled_initial = _metric_subset(
                evaluate(initial, tensors, oracle, sampled_development_indices, batch_size)
            )
            sampled_candidate = _metric_subset(
                evaluate(candidate, tensors, oracle, sampled_development_indices, batch_size)
            )
            sampled = _evaluation_delta(sampled_initial, sampled_candidate)
        else:
            sampled = {"count": 0, "value_sign_delta": None, "optimal_mass_delta": None}
        generations = execution.core["generations"]
        eligible = sum(
            record["promotion"]["eligible_after_development_and_arena"]
            for record in generations
        )
        provisional = sum(record["promotion"]["provisional_advance"] for record in generations)
        training_steps = sum(int(record["training"]["steps"]) for record in generations)
        start_unique = sum(
            int(record["self_play"]["start_states"]["unique"])
            for record in generations
        )
        development_delta = _evaluation_delta(initial_development, candidate_development)
        development_delta["selection_score_delta"] = (
            development_delta["value_sign_delta"] + development_delta["optimal_mass_delta"]
        )
        record = {
            "run_id": pending_run.run_id,
            "experiment": pending_run.experiment,
            "arm": pending_run.arm,
            "seed": pending_run.seed,
            "status": "PASS",
            "protocol_hash_before_frozen_test": protocol_hash,
            "initial_model_hash": model_hash(initial),
            "candidate_model_hash": model_hash(candidate),
            "nodes": _node_totals(execution),
            "starts": {
                "source": pending_run.config["self_play"].get("start_state_source", "initial"),
                "unique": start_unique,
                "train_cohort_only": pending_run.config["self_play"].get(
                    "start_state_source", "initial"
                )
                == "train_split",
            },
            "training": {
                "optimizer_steps": training_steps,
                "final_sample_pool": int(generations[-1]["training"]["sample_pool"]),
            },
            "coverage": {
                "unique_states": int(np.count_nonzero(execution.state_sample_counts)),
                "state_fraction": float(
                    np.count_nonzero(execution.state_sample_counts) / oracle.state_count
                ),
            },
            "development": {**development_delta, "sampled": sampled},
            "frozen_test": {
                "unsealed_after_protocol_hash": True,
                "initial": initial_frozen,
                "candidate": candidate_frozen,
                "value_error": 1.0 - candidate_frozen["value_sign_accuracy"],
                "zero_sample_count": int(
                    np.count_nonzero(execution.state_sample_counts[frozen_indices] == 0)
                ),
                "by_training_sample_count": _sample_strata(
                    candidate,
                    tensors,
                    oracle,
                    frozen_indices,
                    execution.state_sample_counts,
                    batch_size,
                ),
            },
            "targets": target_diagnostics(execution.samples, oracle, split),
            "trace": _trace_diagnostics(oracle, execution),
            "promotion": {
                "eligible_generation_count": eligible,
                "provisional_advance_count": provisional,
            },
        }
        records.append(record)
        arm_dir = per_run_dir / pending_run.run_id
        arm_dir.mkdir()
        (arm_dir / "config.resolved.yaml").write_text(
            yaml.safe_dump(pending_run.config, sort_keys=True), encoding="utf-8"
        )
        (arm_dir / "result.json").write_bytes(_json_bytes(record))
        torch.save(
            {"model": execution.candidate_states[-1], "config": pending_run.config["model"]},
            checkpoint_dir / f"{pending_run.run_id}.pt",
        )

    comparison = build_comparison(
        resolved,
        records,
        metric_paths=M6_SUMMARY_METRICS,
        schema="mini_jass.l1_learning_comparison.v1",
    )
    recommendation = build_learning_recommendation(resolved, comparison)
    successful_records = [record for record in records if record["status"] == "PASS"]
    paired_initial_weights = all(
        len(
            {
                record["initial_model_hash"]
                for record in successful_records
                if record["seed"] == seed
            }
        )
        == 1
        for seed in resolved["paired_seeds"]
    )
    maximum_node_imbalance = float(
        resolved["report_procedure"]["maximum_consumed_node_imbalance"]
    )
    node_balance = all(
        experiment["consumed_node_imbalance"] is None
        or experiment["consumed_node_imbalance"] <= maximum_node_imbalance
        for experiment in comparison["experiments"].values()
    )
    all_runs_successful = len(successful_records) == len(records)
    train_start_contract = all(
        record["starts"]["source"] == "initial"
        or record["starts"]["train_cohort_only"]
        for record in successful_records
    )
    gate = {
        "status": "PASS"
        if all_runs_successful and paired_initial_weights and node_balance and train_start_contract
        else "FAIL",
        "all_runs_reported": len(records) == len(expanded),
        "all_runs_successful": all_runs_successful,
        "paired_initial_weights": paired_initial_weights,
        "minimum_five_paired_seeds": len(resolved["paired_seeds"]) >= 5,
        "consumed_node_balance": node_balance,
        "maximum_consumed_node_imbalance": maximum_node_imbalance,
        "train_split_start_contract": train_start_contract,
        "frozen_test_unsealed_after_protocol_fixed": all(
            record["frozen_test"]["unsealed_after_protocol_hash"]
            for record in successful_records
        ),
    }
    result: dict[str, Any] = {
        "schema": "mini_jass.l1_learning_gate_result.v1",
        "protocol_hash": protocol_hash,
        "paired_seeds": resolved["paired_seeds"],
        "run_count": len(records),
        "successful_run_count": len(successful_records),
        "gate": gate,
        "scientific_gate": recommendation["gate"]["status"],
        "recommendation": recommendation["decision"],
        "contracts": contracts,
    }
    result["result_hash"] = _digest(result)

    (run_dir / "config.resolved.yaml").write_text(
        yaml.safe_dump(resolved, sort_keys=True), encoding="utf-8"
    )
    (run_dir / "seeds.json").write_bytes(
        _json_bytes({"paired_seeds": resolved["paired_seeds"]})
    )
    (run_dir / "environment.json").write_bytes(
        _json_bytes(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "torch": torch.__version__,
                "numpy": np.__version__,
            }
        )
    )
    (run_dir / "arm_results.jsonl").write_bytes(
        b"".join(
            (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
            for record in records
        )
    )
    (run_dir / "comparison.json").write_bytes(_json_bytes(comparison))
    (run_dir / "recommendation.json").write_bytes(_json_bytes(recommendation))
    (run_dir / "result.json").write_bytes(_json_bytes(result))
    (run_dir / "summary.md").write_text(
        _summary_markdown(result, comparison, recommendation), encoding="utf-8"
    )
    (run_dir / "solver_manifest.json").write_bytes(solver_manifest_path.read_bytes())
    (run_dir / "split_manifest.json").write_bytes(_json_bytes(split.manifest))
    (run_dir / "executable_manifest.json").write_bytes(_json_bytes(contracts))
    if compact_output is not None:
        compact_output = ensure_artefact_path(compact_output)
        compact_output.parent.mkdir(parents=True, exist_ok=True)
        compact_output.write_bytes(
            _json_bytes(
                _compact_record(
                    result, recommendation, comparison, loaded.m5_evidence, run_dir
                )
            )
        )
    return result
