"""M5 paired-seed causal experiment pack and automatic comparison report."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np
import torch
import yaml

from .game_graph import GameGraph
from .loop import LoopExecution, execute_loop
from .model import MiniJassMLP, ModelConfig, model_hash
from .oracle import OracleArrays, ensure_artefact_path, load_oracle, uniform_optimal_targets
from .split import build_split
from .train import evaluate, seed_everything


EXPERIMENT_IDS = ("E1", "E2", "E3", "E4")


@dataclass
class PendingRun:
    experiment: str
    arm: str
    seed: int
    config: dict[str, Any]
    execution: LoopExecution | None
    error: str | None = None

    @property
    def run_id(self) -> str:
        return f"{self.experiment.lower()}-{self.arm}-seed-{self.seed}"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _package_sha256() -> str:
    package = Path(__file__).resolve().parent
    hasher = hashlib.sha256()
    for path in sorted(package.glob("*.py")):
        hasher.update(path.name.encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _apply_overrides(config: dict[str, Any], overrides: dict[str, Any]) -> None:
    for dotted_key, value in overrides.items():
        parts = dotted_key.split(".")
        target = config
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                raise ValueError(f"override path does not exist: {dotted_key}")
            target = target[part]
        target[parts[-1]] = deepcopy(value)


def resolve_pack_config(config_path: Path) -> dict[str, Any]:
    pack = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if pack.get("schema") != "mini_jass.experiment_pack.v1":
        raise ValueError("unexpected experiment-pack schema")
    seeds = [int(seed) for seed in pack["paired_seeds"]]
    if len(seeds) < 5 or len(set(seeds)) != len(seeds):
        raise ValueError("M5 requires at least five distinct paired seeds")
    if tuple(pack["experiments"].keys()) != EXPERIMENT_IDS:
        raise ValueError("M5 pack must declare E1, E2, E3, and E4 in order")
    base_path = Path(pack["base_loop_config"])
    if not base_path.is_absolute():
        base_path = config_path.parent.parent / base_path
    base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    if base.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("experiment base must be an M4 self-play config")
    _apply_overrides(base, pack.get("base_overrides", {}))
    resolved = deepcopy(pack)
    resolved["paired_seeds"] = seeds
    resolved["base_loop_config"] = str(base_path.resolve())
    resolved["base_loop"] = base
    return resolved


def expand_arm_configs(resolved: dict[str, Any]) -> list[tuple[str, str, int, dict[str, Any]]]:
    expanded: list[tuple[str, str, int, dict[str, Any]]] = []
    for experiment_id, experiment in resolved["experiments"].items():
        experiment_overrides = experiment.get("overrides", {})
        for arm_name, arm in experiment["arms"].items():
            for seed in resolved["paired_seeds"]:
                config = deepcopy(resolved["base_loop"])
                _apply_overrides(config, experiment_overrides)
                _apply_overrides(config, arm.get("overrides", {}))
                config["seed"] = seed
                config["experiment"] = {
                    "id": experiment_id,
                    "arm": arm_name,
                    "causal_factor": experiment["causal_factor"],
                }
                expanded.append((experiment_id, arm_name, seed, config))
    return expanded


def _oracle_tensors(oracle: OracleArrays, graph: GameGraph) -> dict[str, torch.Tensor]:
    return {
        "features": torch.from_numpy(graph.features),
        "values": torch.from_numpy(oracle.values.astype(np.float32)),
        "legal": torch.from_numpy(graph.legal_mask),
        "optimal": torch.from_numpy(uniform_optimal_targets(oracle.optimal_mask)),
    }


def _metric_subset(metrics: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "count",
        "value_mae",
        "value_mse",
        "value_sign_accuracy",
        "policy_count",
        "optimal_top1_accuracy",
        "optimal_probability_mass",
        "mean_selected_regret",
        "zero_regret_rate",
    )
    return {key: metrics[key] for key in keys}


def _sample_strata(
    model: MiniJassMLP,
    tensors: dict[str, torch.Tensor],
    oracle: OracleArrays,
    cohort_indices: np.ndarray,
    sample_counts: np.ndarray,
    batch_size: int,
) -> dict[str, Any]:
    cohort_counts = sample_counts[cohort_indices]
    masks = {
        "zero": cohort_counts == 0,
        "one": cohort_counts == 1,
        "two_to_four": (cohort_counts >= 2) & (cohort_counts <= 4),
        "five_plus": cohort_counts >= 5,
    }
    result: dict[str, Any] = {}
    for name, mask in masks.items():
        indices = cohort_indices[mask]
        result[name] = (
            _metric_subset(evaluate(model, tensors, oracle, indices, batch_size))
            if indices.size
            else {"count": 0}
        )
    return result


def _trace_diagnostics(oracle: OracleArrays, execution: LoopExecution) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for generation in execution.core["generations"]:
        decisions.extend(generation["self_play"]["search_trace"])
    if not decisions:
        return {
            "decision_count": 0,
            "unique_optimal_states_reached": 0,
            "optimal_selection_rate": None,
            "mean_oracle_regret": None,
            "zero_regret_rate": None,
        }
    optimal = 0
    optimal_states: set[int] = set()
    regrets: list[int] = []
    for decision in decisions:
        state = int(decision["state_id"])
        action = int(decision["selected_action"])
        if oracle.optimal_mask[state, action]:
            optimal += 1
            optimal_states.add(state)
        child = int(oracle.action_children[state, action])
        selected_value = -int(oracle.values[child])
        regrets.append(int(oracle.values[state]) - selected_value)
    return {
        "decision_count": len(decisions),
        "unique_optimal_states_reached": len(optimal_states),
        "optimal_selection_rate": optimal / len(decisions),
        "mean_oracle_regret": float(np.mean(regrets)),
        "zero_regret_rate": sum(regret == 0 for regret in regrets) / len(regrets),
    }


def _node_totals(execution: LoopExecution) -> dict[str, int]:
    requested = 0
    consumed = 0
    positions = 0
    for generation in execution.core["generations"]:
        search = generation["self_play"]["search"]
        requested += int(search["requested_nodes"])
        consumed += int(search["consumed_nodes"])
        positions += int(generation["self_play"]["positions"])
    return {"requested": requested, "consumed": consumed, "positions": positions}


def _get_metric(value: dict[str, Any], path: str) -> float:
    current: Any = value
    for part in path.split("."):
        current = current[part]
    return float(current)


def summarize_values(values: list[float]) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    count = int(array.size)
    mean = float(array.mean())
    standard_deviation = float(array.std(ddof=1)) if count > 1 else 0.0
    half_width = 1.96 * standard_deviation / math.sqrt(count) if count > 1 else 0.0
    return {
        "count": count,
        "mean": mean,
        "standard_deviation": standard_deviation,
        "confidence_95": [mean - half_width, mean + half_width],
        "raw": [float(value) for value in values],
    }


SUMMARY_METRICS = (
    "nodes.consumed",
    "nodes.requested",
    "nodes.positions",
    "coverage.unique_states",
    "development.value_sign_delta",
    "development.optimal_mass_delta",
    "frozen_test.candidate.value_sign_accuracy",
    "frozen_test.candidate.optimal_probability_mass",
    "frozen_test.value_error",
    "frozen_test.zero_sample_count",
    "frozen_test.by_training_sample_count.zero.value_sign_accuracy",
    "frozen_test.by_training_sample_count.zero.optimal_probability_mass",
    "trace.unique_optimal_states_reached",
    "trace.optimal_selection_rate",
    "trace.mean_oracle_regret",
)


def build_comparison(
    resolved: dict[str, Any],
    records: list[dict[str, Any]],
    metric_paths: tuple[str, ...] = SUMMARY_METRICS,
    schema: str = "mini_jass.experiment_comparison.v1",
) -> dict[str, Any]:
    successful = [record for record in records if record["status"] == "PASS"]
    experiments: dict[str, Any] = {}
    for experiment_id, experiment in resolved["experiments"].items():
        arms: dict[str, Any] = {}
        arm_records: dict[str, list[dict[str, Any]]] = {}
        for arm_name in experiment["arms"]:
            selected = [
                record
                for record in successful
                if record["experiment"] == experiment_id and record["arm"] == arm_name
            ]
            arm_records[arm_name] = selected
            metrics: dict[str, Any] = {}
            for path in metric_paths:
                values: list[float] = []
                for record in selected:
                    try:
                        value = _get_metric(record, path)
                    except (KeyError, TypeError, ValueError):
                        continue
                    values.append(value)
                if values and all(math.isfinite(value) for value in values):
                    metrics[path] = summarize_values(values)
            arms[arm_name] = {"run_count": len(selected), "metrics": metrics}

        reference = experiment["reference_arm"]
        paired: dict[str, Any] = {}
        reference_by_seed = {record["seed"]: record for record in arm_records[reference]}
        for arm_name, selected in arm_records.items():
            if arm_name == reference:
                continue
            arm_by_seed = {record["seed"]: record for record in selected}
            paired_metrics: dict[str, Any] = {}
            for path in metric_paths:
                differences: list[float] = []
                for seed in resolved["paired_seeds"]:
                    if seed not in arm_by_seed or seed not in reference_by_seed:
                        continue
                    try:
                        arm_value = _get_metric(arm_by_seed[seed], path)
                        reference_value = _get_metric(reference_by_seed[seed], path)
                    except (KeyError, TypeError, ValueError):
                        continue
                    if math.isfinite(arm_value) and math.isfinite(reference_value):
                        differences.append(arm_value - reference_value)
                if differences:
                    paired_metrics[path] = summarize_values(differences)
            paired[arm_name] = {
                "reference": reference,
                "paired_seed_count": len(set(arm_by_seed) & set(reference_by_seed)),
                "arm_minus_reference": paired_metrics,
            }

        node_means = [
            arm["metrics"]["nodes.consumed"]["mean"]
            for arm in arms.values()
            if "nodes.consumed" in arm["metrics"]
        ]
        node_imbalance = (
            max(node_means) / min(node_means) - 1.0
            if node_means and min(node_means) > 0
            else None
        )
        experiments[experiment_id] = {
            "causal_factor": experiment["causal_factor"],
            "reference_arm": reference,
            "arms": arms,
            "paired_comparisons": paired,
            "consumed_node_imbalance": node_imbalance,
        }
    return {
        "schema": schema,
        "paired_seeds": resolved["paired_seeds"],
        "experiments": experiments,
    }


def build_recommendation(comparison: dict[str, Any]) -> dict[str, Any]:
    experiments = comparison["experiments"]
    if any(
        arm["run_count"] == 0
        for experiment in experiments.values()
        for arm in experiment["arms"].values()
    ):
        return {
            "schema": "mini_jass.transfer_recommendation.v1",
            "decision": "incomplete_pack",
            "direct_10x10_transfer_authorized": False,
            "rationale": "At least one preregistered arm has no successful run.",
            "evidence": {},
            "next_gate": "Repair and rerun every failed arm before transfer.",
        }
    e1_arm = next(iter(experiments["E1"]["arms"].values()))
    e1_metrics = e1_arm["metrics"]
    value_delta = e1_metrics["development.value_sign_delta"]["mean"]
    mass_delta = e1_metrics["development.optimal_mass_delta"]["mean"]

    e3_arms = experiments["E3"]["arms"]
    best_budget = min(
        e3_arms,
        key=lambda arm: (
            e3_arms[arm]["metrics"]["frozen_test.value_error"]["mean"],
            -e3_arms[arm]["metrics"][
                "frozen_test.candidate.optimal_probability_mass"
            ]["mean"],
        ),
    )
    e4_arms = experiments["E4"]["arms"]
    best_exploration = max(
        e4_arms,
        key=lambda arm: (
            e4_arms[arm]["metrics"]["coverage.unique_states"]["mean"],
            -e4_arms[arm]["metrics"]["trace.mean_oracle_regret"]["mean"],
        ),
    )
    self_play_learns = value_delta > 0.0 and mass_delta > 0.0
    if self_play_learns:
        decision = "advance_to_L2_not_10x10"
        rationale = (
            "Outcome-only self-play improved both preregistered development metrics. "
            "Validate the winning mechanisms on L2 before any 10x10 integration."
        )
    else:
        decision = "continue_L1"
        rationale = (
            "The first pack does not show simultaneous development value-sign and "
            "optimal-mass improvement; direct L2 or 10x10 transfer is premature."
        )
    return {
        "schema": "mini_jass.transfer_recommendation.v1",
        "decision": decision,
        "direct_10x10_transfer_authorized": False,
        "rationale": rationale,
        "evidence": {
            "e1_mean_value_sign_delta": value_delta,
            "e1_mean_optimal_mass_delta": mass_delta,
            "best_e3_budget_arm": best_budget,
            "best_e4_exploration_arm": best_exploration,
        },
        "next_gate": "Replicate the selected mechanisms on L2 before Jass 10x10.",
    }


def _summary_markdown(
    result: dict[str, Any], comparison: dict[str, Any], recommendation: dict[str, Any]
) -> str:
    lines = [
        "# Mini-Jass M5 first experiment pack",
        "",
        f"- Gate: **{result['gate']['status']}**",
        f"- Paired seeds: {len(result['paired_seeds'])}",
        f"- Runs: {result['run_count']} ({result['successful_run_count']} successful)",
        f"- Protocol hash fixed before frozen-test read: `{result['protocol_hash']}`",
        f"- Recommendation: **{recommendation['decision']}**",
        "",
        "| Experiment | Arm | Runs | Nodes | Frozen value error | Coverage | Mean regret |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for experiment_id, experiment in comparison["experiments"].items():
        for arm_name, arm in experiment["arms"].items():
            metrics = arm["metrics"]
            if arm["run_count"]:
                lines.append(
                    f"| {experiment_id} | {arm_name} | {arm['run_count']} | "
                    f"{metrics['nodes.consumed']['mean']:.1f} | "
                    f"{metrics['frozen_test.value_error']['mean']:.4f} | "
                    f"{metrics['coverage.unique_states']['mean']:.1f} | "
                    f"{metrics['trace.mean_oracle_regret']['mean']:.4f} |"
                )
            else:
                lines.append(f"| {experiment_id} | {arm_name} | 0 | n/a | n/a | n/a | n/a |")
    lines.extend(["", recommendation["rationale"], ""])
    return "\n".join(lines)


def run_experiment_pack(
    config_path: Path, oracle_path: Path, run_dir: Path
) -> dict[str, Any]:
    resolved = resolve_pack_config(config_path)
    run_dir = ensure_artefact_path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    oracle = load_oracle(oracle_path)
    split = build_split(oracle, int(resolved["base_loop"]["split_seed"]))
    expected_hash = resolved["base_loop"]["expected_split_manifest_hash"]
    if split.manifest["manifest_hash"] != expected_hash:
        raise ValueError("experiment pack split differs from the frozen contract")
    development_indices = split.indices("development")
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
    }

    protocol = {
        "schema": resolved["schema"],
        "paired_seeds": resolved["paired_seeds"],
        "experiments": resolved["experiments"],
        "base_loop": resolved["base_loop"],
        "split_manifest_hash": expected_hash,
        "report_procedure": resolved["report_procedure"],
        "frozen_test_policy": "evaluate_all_fixed_candidates_after_protocol_hash",
        "contracts": contracts,
    }
    protocol_hash = _digest(protocol)
    pending: list[PendingRun] = []
    for experiment, arm, seed, loop_config in expand_arm_configs(resolved):
        try:
            execution = execute_loop(loop_config, oracle, development_indices)
            pending.append(PendingRun(experiment, arm, seed, loop_config, execution))
        except Exception as error:  # all failed arms must remain in the report
            pending.append(PendingRun(experiment, arm, seed, loop_config, None, repr(error)))

    # Frozen-test membership and labels are materialized only after every candidate
    # and the immutable report protocol have been fixed.
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
        nodes = _node_totals(execution)
        trace = _trace_diagnostics(oracle, execution)
        unique_states = int(np.count_nonzero(execution.state_sample_counts))
        record = {
            "run_id": pending_run.run_id,
            "experiment": pending_run.experiment,
            "arm": pending_run.arm,
            "seed": pending_run.seed,
            "status": "PASS",
            "protocol_hash_before_frozen_test": protocol_hash,
            "initial_model_hash": model_hash(initial),
            "candidate_model_hash": model_hash(candidate),
            "nodes": nodes,
            "coverage": {
                "unique_states": unique_states,
                "state_fraction": unique_states / oracle.state_count,
            },
            "development": {
                "initial": initial_development,
                "candidate": candidate_development,
                "value_sign_delta": candidate_development["value_sign_accuracy"]
                - initial_development["value_sign_accuracy"],
                "optimal_mass_delta": candidate_development["optimal_probability_mass"]
                - initial_development["optimal_probability_mass"],
            },
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
            "trace": trace,
            "promotion": execution.core["generations"][-1]["promotion"],
        }
        records.append(record)
        arm_run_dir = per_run_dir / pending_run.run_id
        arm_run_dir.mkdir()
        (arm_run_dir / "config.resolved.yaml").write_text(
            yaml.safe_dump(pending_run.config, sort_keys=True), encoding="utf-8"
        )
        (arm_run_dir / "result.json").write_bytes(_json_bytes(record))
        torch.save(
            {
                "model": execution.candidate_states[-1],
                "config": pending_run.config["model"],
            },
            checkpoint_dir / f"{pending_run.run_id}.pt",
        )

    comparison = build_comparison(resolved, records)
    recommendation = build_recommendation(comparison)
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
    all_runs_successful = len(successful) == len(records)
    maximum_node_imbalance = float(
        resolved["report_procedure"]["maximum_consumed_node_imbalance"]
    )
    node_balance = all(
        experiment["consumed_node_imbalance"] is None
        or experiment["consumed_node_imbalance"] <= maximum_node_imbalance
        for experiment in comparison["experiments"].values()
    )
    gate = {
        "status": (
            "PASS"
            if all_runs_successful
            and paired_initial_weights
            and node_balance
            and len(resolved["paired_seeds"]) >= 5
            else "FAIL"
        ),
        "all_runs_reported": len(records) == len(expand_arm_configs(resolved)),
        "all_runs_successful": all_runs_successful,
        "paired_initial_weights": paired_initial_weights,
        "consumed_node_balance": node_balance,
        "maximum_consumed_node_imbalance": maximum_node_imbalance,
        "minimum_five_paired_seeds": len(resolved["paired_seeds"]) >= 5,
        "frozen_test_unsealed_after_protocol_fixed": all(
            record["frozen_test"]["unsealed_after_protocol_hash"] for record in successful
        ),
    }
    result: dict[str, Any] = {
        "schema": "mini_jass.experiment_pack_result.v1",
        "protocol_hash": protocol_hash,
        "paired_seeds": resolved["paired_seeds"],
        "run_count": len(records),
        "successful_run_count": len(successful),
        "gate": gate,
        "recommendation": recommendation["decision"],
        "solver_hash": int(oracle.manifest["solver_hash"]),
        "split_manifest_hash": split.manifest["manifest_hash"],
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
    (run_dir / "rule_manifest.json").write_bytes(
        _json_bytes(
            {
                "schema": solver_manifest["rules"]["schema"],
                "rules": solver_manifest["rules"],
                "action_schema": solver_manifest["action_schema"],
                "action_count": solver_manifest["action_count"],
                "action_vocabulary_hash": solver_manifest["action_vocabulary_hash"],
            }
        )
    )
    (run_dir / "executable_manifest.json").write_bytes(_json_bytes(contracts))
    (run_dir / "split_manifest.json").write_bytes(_json_bytes(split.manifest))
    return result
