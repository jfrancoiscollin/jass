"""M9: preregistered replication of the frozen M8 mechanism on exact L2."""

from __future__ import annotations

from copy import deepcopy
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

from .experiment import _digest, _file_sha256, _metric_subset, _oracle_tensors, _package_sha256
from .game_graph import GameGraph
from .learning_gate import target_diagnostics
from .loop import execute_loop
from .model import MiniJassMLP, ModelConfig, model_hash, parameter_count
from .oracle import ensure_artefact_path, load_oracle
from .split import build_split
from .train import evaluate, seed_everything


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _confidence_95(values: list[float]) -> list[float]:
    """Student interval; M9 preregisters exactly five independent seeds."""
    samples = np.asarray(values, dtype=np.float64)
    if samples.size < 2:
        return [float(samples[0]), float(samples[0])]
    critical = 2.7764451051977987 if samples.size == 5 else 1.96
    half_width = critical * float(samples.std(ddof=1)) / math.sqrt(samples.size)
    center = float(samples.mean())
    return [center - half_width, center + half_width]


def _resolve_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_path.parent.parent / path


def resolve_l2_transfer_config(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != "mini_jass.l2_transfer_gate.v1":
        raise ValueError("unexpected L2 transfer-gate schema")
    seeds = [int(seed) for seed in config["paired_seeds"]]
    if len(seeds) != 5 or len(set(seeds)) != 5:
        raise ValueError("M9 requires exactly five distinct paired seeds")

    upstream_path = _resolve_path(config_path, config["m8_evidence"])
    upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
    if (
        upstream.get("schema") != "mini_jass.m8_learning_gate_replication.v1"
        or upstream.get("result_hash") != config["expected_m8_result_hash"]
        or upstream.get("scientific_gate", {}).get("status") != "PASS"
        or upstream.get("recommendation", {}).get("decision") != "advance_to_L2_not_10x10"
    ):
        raise ValueError("M9 requires the exact passing M8 transfer authorization")
    if upstream["evidence"]["frozen_policy_target"] != config["frozen_mechanism"]["policy_target"]:
        raise ValueError("M9 policy target differs from the frozen M8 mechanism")
    if upstream["evidence"]["selected_arm"] != config["frozen_mechanism"]["dose_arm"]:
        raise ValueError("M9 optimizer dose differs from the M8-selected arm")

    loop_path = _resolve_path(config_path, config["loop_config"])
    loop = yaml.safe_load(loop_path.read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M9 loop must use the stable self-play interface")
    model = loop["model"]
    self_play = loop["self_play"]
    if (model.get("input_count"), model.get("action_count")) != (74, 122):
        raise ValueError("M9 must bind the 74-input/122-action L2 model")
    if (
        self_play.get("policy_target") != "score_softmax"
        or self_play.get("behavior_policy") != "search_scores"
        or self_play.get("root_allocation") != "balanced"
        or self_play.get("start_state_source") != "train_split"
        or int(loop["training"]["steps"]) != 1024
    ):
        raise ValueError("M9 loop changes the frozen M8 learning mechanism")

    resolved = deepcopy(config)
    resolved["paired_seeds"] = seeds
    resolved["m8_evidence"] = str(upstream_path.resolve())
    resolved["m8"] = upstream
    resolved["loop_config"] = str(loop_path.resolve())
    resolved["loop"] = loop
    resolved["split_manifest"] = str(
        _resolve_path(config_path, config["split_manifest"]).resolve()
    )
    return resolved


def build_l2_transfer_recommendation(
    aggregate: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, Any]:
    criteria = {
        "exactly_five_successful_paired_seeds": aggregate["successful_runs"] == 5,
        "deterministic_replay": bool(aggregate["deterministic_replay"]),
        "mean_development_value_sign_delta":
            aggregate["mean_development_value_sign_delta"]
            > float(thresholds["minimum_mean_value_sign_delta"]),
        "mean_development_optimal_mass_delta":
            aggregate["mean_development_optimal_mass_delta"]
            > float(thresholds["minimum_mean_optimal_mass_delta"]),
        "selection_confidence_interval_above_zero":
            aggregate["selection_score_confidence_95"][0] > 0.0,
        "minimum_target_value_exact_rate":
            aggregate["mean_target_value_exact_rate"]
            >= float(thresholds["minimum_target_value_exact_rate"]),
        "minimum_target_optimal_mass":
            aggregate["mean_target_optimal_mass"]
            >= float(thresholds["minimum_target_optimal_mass"]),
        "at_least_one_eligible_candidate": aggregate["eligible_candidate_count"] >= 1,
    }
    passed = all(criteria.values())
    return {
        "decision": "l2_replication_confirmed" if passed else "keep_l2_gate_closed",
        "l2_replication_confirmed": passed,
        "implementation_preparation_authorized": passed,
        "direct_10x10_transfer_authorized": False,
        "gate": {"status": "PASS" if passed else "FAIL", "criteria": criteria},
        "next_gate": (
            "Prepare an isolated 10x10 integration contract; do not modify Jass production paths."
            if passed
            else "Diagnose L2 transfer without reopening or tuning on the frozen test cohort."
        ),
    }


def run_l2_transfer_gate(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path | None = None,
) -> dict[str, Any]:
    resolved = resolve_l2_transfer_config(config_path)
    oracle = load_oracle(oracle_path)
    if (
        oracle.manifest.get("schema") != "mini_jass.oracle_dataset.l2.v1"
        or oracle.state_count != 49690
        or oracle.action_count != 122
        or oracle.feature_count != 74
    ):
        raise ValueError("M9 requires the frozen selected-scope L2 oracle")
    split = build_split(oracle, int(resolved["split_seed"]))
    frozen_split = json.loads(Path(resolved["split_manifest"]).read_text(encoding="utf-8"))
    if split.manifest != frozen_split:
        raise ValueError("M9 computed split differs from the frozen L2 contract")

    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    tensors = _oracle_tensors(oracle, graph)
    development = split.indices("development")
    frozen_test = split.indices("frozen_test")
    train = split.indices("train")
    protocol = {
        "schema": resolved["schema"],
        "paired_seeds": resolved["paired_seeds"],
        "frozen_mechanism": resolved["frozen_mechanism"],
        "loop": resolved["loop"],
        "thresholds": resolved["scientific_gate"],
        "m8_result_hash": resolved["expected_m8_result_hash"],
        "solver_hash": oracle.manifest["solver_hash"],
        "split_manifest_hash": split.manifest["manifest_hash"],
    }
    protocol_hash = _digest(protocol)

    pending: list[dict[str, Any]] = []
    for seed in resolved["paired_seeds"]:
        loop_config = deepcopy(resolved["loop"])
        loop_config["seed"] = seed
        execution = execute_loop(loop_config, oracle, development, train)
        pending.append({"seed": seed, "config": loop_config, "execution": execution})

    replay_config = deepcopy(pending[0]["config"])
    replay = execute_loop(replay_config, oracle, development, train)
    deterministic_replay = (
        replay.core["execution_hash"] == pending[0]["execution"].core["execution_hash"]
        and model_hash_from_state(replay.candidate_states[-1])
        == model_hash_from_state(pending[0]["execution"].candidate_states[-1])
    )

    # The five candidates and protocol are now fixed. Exact target diagnostics
    # and the frozen-test cohort are unsealed only below this point.
    seed_results: list[dict[str, Any]] = []
    for item in pending:
        seed = item["seed"]
        loop_config = item["config"]
        execution = item["execution"]
        seed_everything(seed, int(loop_config["runtime"]["threads"]))
        initial = MiniJassMLP(ModelConfig(**loop_config["model"]))
        candidate = MiniJassMLP(ModelConfig(**loop_config["model"]))
        candidate.load_state_dict(execution.candidate_states[-1])
        initial_dev = _metric_subset(evaluate(initial, tensors, oracle, development,
                                               int(loop_config["development"]["batch_size"])))
        candidate_dev = _metric_subset(evaluate(candidate, tensors, oracle, development,
                                                 int(loop_config["development"]["batch_size"])))
        initial_frozen = _metric_subset(evaluate(initial, tensors, oracle, frozen_test,
                                                  int(loop_config["development"]["batch_size"])))
        candidate_frozen = _metric_subset(evaluate(candidate, tensors, oracle, frozen_test,
                                                    int(loop_config["development"]["batch_size"])))
        diagnostics = target_diagnostics(execution.samples, oracle, split)["overall"]
        last = execution.core["generations"][-1]
        value_delta = candidate_dev["value_sign_accuracy"] - initial_dev["value_sign_accuracy"]
        mass_delta = candidate_dev["optimal_probability_mass"] - initial_dev["optimal_probability_mass"]
        seed_results.append({
            "seed": seed,
            "initial_model_hash": execution.core["initial_model_hash"],
            "candidate_model_hash": model_hash(candidate),
            "parameter_count": parameter_count(candidate),
            "development": {
                "initial": initial_dev,
                "candidate": candidate_dev,
                "value_sign_delta": value_delta,
                "optimal_mass_delta": mass_delta,
                "selection_score_delta": value_delta + mass_delta,
            },
            "frozen_test": {"initial": initial_frozen, "candidate": candidate_frozen},
            "targets": diagnostics,
            "coverage": last["coverage"],
            "promotion": last["promotion"],
            "execution_hash": execution.core["execution_hash"],
        })

    value_deltas = [float(row["development"]["value_sign_delta"]) for row in seed_results]
    mass_deltas = [float(row["development"]["optimal_mass_delta"]) for row in seed_results]
    selection_deltas = [float(row["development"]["selection_score_delta"]) for row in seed_results]
    aggregate = {
        "successful_runs": len(seed_results),
        "deterministic_replay": deterministic_replay,
        "mean_development_value_sign_delta": _mean(value_deltas),
        "mean_development_optimal_mass_delta": _mean(mass_deltas),
        "selection_score_confidence_95": _confidence_95(selection_deltas),
        "mean_target_value_exact_rate": _mean([
            float(row["targets"]["value_exact_rate"]) for row in seed_results
        ]),
        "mean_target_optimal_mass": _mean([
            float(row["targets"]["policy_optimal_mass"]) for row in seed_results
        ]),
        "mean_unique_state_coverage": _mean([
            float(row["coverage"]["state_coverage"]) for row in seed_results
        ]),
        "eligible_candidate_count": sum(
            bool(row["promotion"]["eligible_after_development_and_arena"])
            for row in seed_results
        ),
    }
    recommendation = build_l2_transfer_recommendation(aggregate, resolved["scientific_gate"])
    oracle_sha = hashlib.sha256(oracle_path.read_bytes()).hexdigest()
    contracts = {
        "m8_result_hash": resolved["expected_m8_result_hash"],
        "m8_evidence_sha256": _file_sha256(Path(resolved["m8_evidence"])),
        "rule_schema": "mini_jass.rules.l2.selected_2v1.v1",
        "action_schema": "mini_jass.actions.l2.v1",
        "action_count": oracle.action_count,
        "action_vocabulary_hash": 4900887392723183309,
        "solver_hash": oracle.manifest["solver_hash"],
        "solver_manifest_hash": oracle.manifest["manifest_hash"],
        "oracle_export_sha256": oracle_sha,
        "split_manifest_hash": split.manifest["manifest_hash"],
        "python_package_sha256": _package_sha256(),
        "jass_production_paths_modified": False,
    }
    result: dict[str, Any] = {
        "schema": "mini_jass.m9_l2_transfer_gate.v1",
        "milestone": "M9",
        "status": recommendation["gate"]["status"],
        "protocol_hash": protocol_hash,
        "pack": {"paired_seed_count": 5, "run_count": 5, "successful_run_count": len(seed_results)},
        "contracts": contracts,
        "aggregate": aggregate,
        "scientific_gate": recommendation["gate"],
        "recommendation": {key: value for key, value in recommendation.items() if key != "gate"},
        "frozen_test_usage": "unsealed_after_protocol_and_all_five_candidates_fixed",
        "seed_results": seed_results,
    }
    result["result_hash"] = _digest(result)

    output_dir = ensure_artefact_path(run_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "config.resolved.yaml").write_text(
        yaml.safe_dump(resolved, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "protocol.json").write_bytes(_json_bytes(protocol))
    (output_dir / "seed_results.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in seed_results),
        encoding="utf-8",
    )
    (output_dir / "result.json").write_bytes(_json_bytes(result))
    (output_dir / "environment.json").write_bytes(_json_bytes({
        "python": sys.version, "platform": platform.platform(), "torch": torch.__version__,
        "numpy": np.__version__, "threads": resolved["loop"]["runtime"]["threads"],
    }))

    compact = deepcopy(result)
    compact.pop("seed_results")
    if compact_output is not None:
        compact_path = ensure_artefact_path(compact_output)
        compact_path.write_bytes(_json_bytes(compact))
    return result


def model_hash_from_state(state: dict[str, torch.Tensor]) -> str:
    hasher = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        hasher.update(name.encode())
        hasher.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return hasher.hexdigest()
