"""M7 balanced-root policy-target experiment and scientific gate."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
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
    build_comparison,
)
from .game_graph import GameGraph
from .learning_gate import _evaluation_delta, target_diagnostics
from .loop import execute_loop
from .model import MiniJassMLP, ModelConfig, model_hash
from .oracle import ensure_artefact_path, load_oracle
from .split import build_split
from .train import evaluate, seed_everything


EXPERIMENT_IDS = ("E10",)
ARM_IDS = ("visit_distribution", "best_action", "score_softmax")
M7_SUMMARY_METRICS = SUMMARY_METRICS + (
    "development.selection_score_delta",
    "targets.overall.value_exact_rate",
    "targets.overall.policy_optimal_mass",
    "targets.overall.policy_argmax_optimal_rate",
    "root.action_coverage",
    "root.maximum_budget_imbalance",
    "promotion.eligible_generation_count",
)


@dataclass(frozen=True)
class PolicyGateConfig:
    resolved: dict[str, Any]
    m6_evidence: dict[str, Any]
    m6_path: Path


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def resolve_policy_gate_config(config_path: Path) -> PolicyGateConfig:
    pack = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if pack.get("schema") != "mini_jass.policy_target_gate.v1":
        raise ValueError("unexpected M7 policy-target gate schema")
    seeds = [int(seed) for seed in pack["paired_seeds"]]
    if len(seeds) < 5 or len(set(seeds)) != len(seeds):
        raise ValueError("M7 requires at least five distinct paired seeds")
    if tuple(pack["experiments"].keys()) != EXPERIMENT_IDS:
        raise ValueError("M7 must declare E10 only")
    experiment = pack["experiments"]["E10"]
    if tuple(experiment["arms"].keys()) != ARM_IDS:
        raise ValueError("E10 must compare visits, best action, and score softmax")

    base_path = Path(pack["base_loop_config"])
    if not base_path.is_absolute():
        base_path = config_path.parent.parent / base_path
    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    if base.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M7 base must be an M4 self-play config")
    _apply_overrides(base, pack.get("base_overrides", {}))

    m6_path = Path(pack["m6_evidence"])
    if not m6_path.is_absolute():
        m6_path = config_path.parent.parent / m6_path
    m6_evidence = json.loads(m6_path.read_text(encoding="utf-8"))
    if m6_evidence.get("schema") != "mini_jass.m6_learning_gate.v1":
        raise ValueError("M7 requires the compact M6 evidence record")
    if m6_evidence.get("result_hash") != pack["expected_m6_result_hash"]:
        raise ValueError("M6 evidence hash differs from the preregistered M7 input")
    if m6_evidence["recommendation"]["decision"] != "continue_L1_policy_gate":
        raise ValueError("M7 is only valid after the M6 policy-gate decision")

    resolved = deepcopy(pack)
    resolved["paired_seeds"] = seeds
    resolved["base_loop_config"] = str(base_path.resolve())
    resolved["m6_evidence"] = str(m6_path.resolve())
    resolved["base_loop"] = base
    expanded = expand_policy_gate_configs(resolved)
    causal_signatures: set[str] = set()
    for _, _, _, config in expanded:
        if config["self_play"]["root_allocation"] != "balanced":
            raise ValueError("M7 requires balanced root allocation")
        if config["self_play"]["behavior_policy"] != "search_scores":
            raise ValueError("M7 requires target-independent search-score behavior")
        causal = deepcopy(config)
        causal["seed"] = 0
        causal["self_play"]["policy_target"] = "<causal-factor>"
        causal["experiment"]["arm"] = "<causal-factor>"
        causal_signatures.add(_digest(causal))
    if len(causal_signatures) != 1:
        raise ValueError("M7 arms may differ only by policy-target encoding")
    return PolicyGateConfig(resolved, m6_evidence, m6_path)


def expand_policy_gate_configs(
    resolved: dict[str, Any],
) -> list[tuple[str, str, int, dict[str, Any]]]:
    expanded: list[tuple[str, str, int, dict[str, Any]]] = []
    experiment = resolved["experiments"]["E10"]
    for arm_name, arm in experiment["arms"].items():
        for seed in resolved["paired_seeds"]:
            config = deepcopy(resolved["base_loop"])
            _apply_overrides(config, experiment.get("overrides", {}))
            _apply_overrides(config, arm.get("overrides", {}))
            config["seed"] = seed
            config["experiment"] = {
                "id": "E10",
                "arm": arm_name,
                "causal_factor": experiment["causal_factor"],
            }
            expanded.append(("E10", arm_name, seed, config))
    return expanded


def _root_diagnostics(execution: Any) -> dict[str, Any]:
    legal = 0
    searched = 0
    failures = 0
    maximum_imbalance = 0
    decisions = 0
    for generation in execution.core["generations"]:
        search = generation["self_play"]["search"]
        decisions += int(search["decisions"])
        legal += int(search["root_legal_actions"])
        searched += int(search["root_searched_actions"])
        failures += int(search["root_coverage_failures"])
        maximum_imbalance = max(
            maximum_imbalance, int(search["root_maximum_budget_imbalance"])
        )
    return {
        "decisions": decisions,
        "legal_actions": legal,
        "searched_actions": searched,
        "action_coverage": searched / legal if legal else 0.0,
        "coverage_failures": failures,
        "maximum_budget_imbalance": maximum_imbalance,
    }


def build_policy_recommendation(
    resolved: dict[str, Any], comparison: dict[str, Any]
) -> dict[str, Any]:
    experiment = comparison["experiments"]["E10"]
    successful = all(
        arm["run_count"] == len(resolved["paired_seeds"])
        for arm in experiment["arms"].values()
    )
    if not successful:
        return {
            "schema": "mini_jass.policy_target_recommendation.v1",
            "decision": "incomplete_pack",
            "l2_transfer_authorized": False,
            "direct_10x10_transfer_authorized": False,
            "gate": {"status": "FAIL", "criteria": {"all_runs_successful": False}},
            "evidence": {},
            "reason": "At least one preregistered M7 arm has no successful run.",
            "next_gate": "Repair and rerun the complete paired M7 pack on L1.",
        }

    selected_arm = max(
        ARM_IDS,
        key=lambda arm: float(
            experiment["arms"][arm]["metrics"][
                "development.selection_score_delta"
            ]["mean"]
        ),
    )
    metrics = experiment["arms"][selected_arm]["metrics"]
    gate_config = resolved["policy_gate"]
    value_delta = float(metrics["development.value_sign_delta"]["mean"])
    mass_delta = float(metrics["development.optimal_mass_delta"]["mean"])
    selection_interval = metrics["development.selection_score_delta"]["confidence_95"]
    target_mass = float(metrics["targets.overall.policy_optimal_mass"]["mean"])
    target_argmax = float(
        metrics["targets.overall.policy_argmax_optimal_rate"]["mean"]
    )
    root_coverage = float(metrics["root.action_coverage"]["mean"])
    root_imbalance = max(metrics["root.maximum_budget_imbalance"]["raw"])
    eligible = float(metrics["promotion.eligible_generation_count"]["mean"])
    criteria = {
        "mean_development_value_sign_delta": value_delta
        > float(gate_config["minimum_mean_value_sign_delta"]),
        "mean_development_optimal_mass_delta": mass_delta
        > float(gate_config["minimum_mean_optimal_mass_delta"]),
        "selection_confidence_interval_above_zero": float(selection_interval[0]) > 0.0,
        "minimum_target_optimal_mass": target_mass
        >= float(gate_config["minimum_target_optimal_mass"]),
        "minimum_target_argmax_optimal_rate": target_argmax
        >= float(gate_config["minimum_target_argmax_optimal_rate"]),
        "complete_root_action_coverage": root_coverage == 1.0,
        "maximum_root_node_imbalance": root_imbalance
        <= float(gate_config["maximum_root_node_imbalance"]),
        "at_least_one_eligible_candidate": eligible > 0.0,
    }
    passed = all(criteria.values())
    return {
        "schema": "mini_jass.policy_target_recommendation.v1",
        "decision": (
            "rerun_frozen_M6_gate_before_L2"
            if passed
            else "continue_L1_policy_target_repair"
        ),
        "l2_transfer_authorized": False,
        "direct_10x10_transfer_authorized": False,
        "gate": {"status": "PASS" if passed else "FAIL", "criteria": criteria},
        "evidence": {
            "selected_arm": selected_arm,
            "mean_development_value_sign_delta": value_delta,
            "mean_development_optimal_mass_delta": mass_delta,
            "selection_score_confidence_95": selection_interval,
            "mean_target_optimal_mass": target_mass,
            "mean_target_argmax_optimal_rate": target_argmax,
            "mean_root_action_coverage": root_coverage,
            "maximum_root_node_imbalance": root_imbalance,
            "mean_eligible_generation_count": eligible,
        },
        "reason": (
            "A target encoding now improves value and optimal-move mass with a "
            "positive joint confidence interval under fair root allocation."
            if passed
            else "No target encoding yet clears every joint value, policy, and "
            "candidate-eligibility criterion under fair root allocation."
        ),
        "next_gate": (
            "Freeze the selected target and rerun the full M6 L1 gate before L2."
            if passed
            else "Keep work on L1 and repair the policy-target mechanism."
        ),
    }


def _summary_markdown(
    result: dict[str, Any], comparison: dict[str, Any], recommendation: dict[str, Any]
) -> str:
    lines = [
        "# Mini-Jass M7 policy-target gate",
        "",
        f"- Execution gate: **{result['gate']['status']}**",
        f"- Scientific gate: **{recommendation['gate']['status']}**",
        f"- Runs: {result['run_count']} ({result['successful_run_count']} successful)",
        f"- Decision: **{recommendation['decision']}**",
        f"- Protocol hash: `{result['protocol_hash']}`",
        "",
        "| Target | Dev value delta | Dev mass delta | Target mass | Root coverage |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm_name, arm in comparison["experiments"]["E10"]["arms"].items():
        metrics = arm["metrics"]
        if arm["run_count"]:
            lines.append(
                f"| {arm_name} | "
                f"{metrics['development.value_sign_delta']['mean']:.4f} | "
                f"{metrics['development.optimal_mass_delta']['mean']:.4f} | "
                f"{metrics['targets.overall.policy_optimal_mass']['mean']:.4f} | "
                f"{metrics['root.action_coverage']['mean']:.4f} |"
            )
    lines.extend(["", recommendation["reason"], ""])
    return "\n".join(lines)


def _compact_record(
    result: dict[str, Any],
    recommendation: dict[str, Any],
    m6_evidence: dict[str, Any],
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
        "schema": "mini_jass.m7_policy_target_gate.v1",
        "milestone": "M7",
        "status": result["gate"]["status"],
        "protocol_hash": result["protocol_hash"],
        "result_hash": result["result_hash"],
        "m6_result_hash": m6_evidence["result_hash"],
        "pack": {
            "experiments": list(EXPERIMENT_IDS),
            "arm_count": len(ARM_IDS),
            "paired_seeds": result["paired_seeds"],
            "run_count": result["run_count"],
            "successful_run_count": result["successful_run_count"],
        },
        "gate": result["gate"],
        "scientific_gate": recommendation["gate"],
        "evidence": recommendation["evidence"],
        "recommendation": {
            "decision": recommendation["decision"],
            "l2_transfer_authorized": False,
            "direct_10x10_transfer_authorized": False,
            "reason": recommendation["reason"],
            "next_gate": recommendation["next_gate"],
        },
        "contracts": result["contracts"],
        "artifact_hashes": {
            name: _file_sha256(run_dir / name) for name in artefact_names
        },
    }


def run_policy_gate(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path | None = None,
) -> dict[str, Any]:
    loaded = resolve_policy_gate_config(config_path)
    resolved = loaded.resolved
    run_dir = ensure_artefact_path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    oracle = load_oracle(oracle_path)
    split = build_split(oracle, int(resolved["base_loop"]["split_seed"]))
    if split.manifest["manifest_hash"] != resolved["base_loop"][
        "expected_split_manifest_hash"
    ]:
        raise ValueError("M7 split differs from the frozen contract")
    development_indices = split.indices("development")
    training_start_indices = split.indices("train")
    frozen_indices = split.indices("frozen_test")
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    tensors = _oracle_tensors(oracle, graph)

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
        "m6_result_hash": loaded.m6_evidence["result_hash"],
        "m6_evidence_sha256": _file_sha256(loaded.m6_path),
    }
    protocol = {
        "schema": resolved["schema"],
        "paired_seeds": resolved["paired_seeds"],
        "experiments": resolved["experiments"],
        "base_loop": resolved["base_loop"],
        "report_procedure": resolved["report_procedure"],
        "policy_gate": resolved["policy_gate"],
        "frozen_test_policy": "evaluate_all_fixed_candidates_after_protocol_hash",
        "contracts": contracts,
    }
    protocol_hash = _digest(protocol)

    pending: list[PendingRun] = []
    expanded = expand_policy_gate_configs(resolved)
    for experiment, arm, seed, loop_config in expanded:
        try:
            execution = execute_loop(
                loop_config,
                oracle,
                development_indices,
                training_start_indices,
            )
            pending.append(PendingRun(experiment, arm, seed, loop_config, execution))
        except Exception as error:
            pending.append(PendingRun(experiment, arm, seed, loop_config, None, repr(error)))

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
        development = _evaluation_delta(initial_development, candidate_development)
        development["selection_score_delta"] = (
            development["value_sign_delta"] + development["optimal_mass_delta"]
        )
        generations = execution.core["generations"]
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
            "coverage": {
                "unique_states": int(np.count_nonzero(execution.state_sample_counts)),
                "state_fraction": float(
                    np.count_nonzero(execution.state_sample_counts) / oracle.state_count
                ),
            },
            "development": development,
            "frozen_test": {
                "unsealed_after_protocol_hash": True,
                "initial": initial_frozen,
                "candidate": candidate_frozen,
            },
            "targets": target_diagnostics(execution.samples, oracle, split),
            "root": _root_diagnostics(execution),
            "promotion": {
                "eligible_generation_count": sum(
                    item["promotion"]["eligible_after_development_and_arena"]
                    for item in generations
                )
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
        metric_paths=M7_SUMMARY_METRICS,
        schema="mini_jass.policy_target_comparison.v1",
    )
    recommendation = build_policy_recommendation(resolved, comparison)
    successful = [record for record in records if record["status"] == "PASS"]
    paired_initial_weights = all(
        len(
            {
                record["initial_model_hash"]
                for record in successful
                if record["seed"] == seed
            }
        )
        == 1
        for seed in resolved["paired_seeds"]
    )
    complete_root_coverage = all(
        record["root"]["action_coverage"] == 1.0 for record in successful
    )
    root_balance = all(
        record["root"]["maximum_budget_imbalance"]
        <= int(resolved["policy_gate"]["maximum_root_node_imbalance"])
        for record in successful
    )
    all_runs_successful = len(successful) == len(records)
    gate = {
        "status": "PASS"
        if all_runs_successful
        and paired_initial_weights
        and complete_root_coverage
        and root_balance
        else "FAIL",
        "all_runs_reported": len(records) == len(expanded),
        "all_runs_successful": all_runs_successful,
        "paired_initial_weights": paired_initial_weights,
        "minimum_five_paired_seeds": len(resolved["paired_seeds"]) >= 5,
        "target_only_causal_contrast": True,
        "complete_root_action_coverage": complete_root_coverage,
        "balanced_root_node_allocation": root_balance,
        "frozen_test_unsealed_after_protocol_fixed": all(
            record["frozen_test"]["unsealed_after_protocol_hash"]
            for record in successful
        ),
    }
    result: dict[str, Any] = {
        "schema": "mini_jass.policy_target_gate_result.v1",
        "protocol_hash": protocol_hash,
        "paired_seeds": resolved["paired_seeds"],
        "run_count": len(records),
        "successful_run_count": len(successful),
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
                _compact_record(result, recommendation, loaded.m6_evidence, run_dir)
            )
        )
    return result
