"""End-to-end deterministic M4 generation, training, arena, and promotion loop."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np
import torch
import yaml

from .arena import ArenaConfig, run_arena
from .game_graph import GameGraph
from .model import MiniJassMLP, ModelConfig, model_hash, parameter_count
from .oracle import OracleArrays, ensure_artefact_path, load_oracle, uniform_optimal_targets
from .replay import ReplayBuffer, ReplaySample
from .selfplay import ExplorationConfig, SelfPlayConfig, generate_self_play
from .selfplay_train import train_from_replay
from .split import build_split
from .train import evaluate, seed_everything


@dataclass(frozen=True)
class LoopExecution:
    core: dict[str, Any]
    candidate_states: list[dict[str, torch.Tensor]]
    final_state: dict[str, torch.Tensor]
    state_sample_counts: np.ndarray
    samples: list[ReplaySample]


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _jsonl_bytes(values: list[Any]) -> bytes:
    return b"".join(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for value in values
    )


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _development_tensors(oracle: OracleArrays, graph: GameGraph) -> dict[str, torch.Tensor]:
    """Solved labels exist only in this promotion-gate data structure."""
    return {
        "features": torch.from_numpy(graph.features),
        "values": torch.from_numpy(oracle.values.astype(np.float32)),
        "legal": torch.from_numpy(graph.legal_mask),
        "optimal": torch.from_numpy(uniform_optimal_targets(oracle.optimal_mask)),
    }


def _selection_score(metrics: dict[str, Any]) -> float:
    return float(metrics["value_sign_accuracy"]) + float(metrics["optimal_probability_mass"])


def _parse_self_play(config: dict[str, Any]) -> SelfPlayConfig:
    exploration = ExplorationConfig(**config["exploration"])
    return SelfPlayConfig(
        mode=config["mode"],
        games=int(config["games"]),
        max_plies=int(config["max_plies"]),
        search_depth=int(config["search_depth"]),
        budget_policy=config["budget_policy"],
        node_budgets=tuple(int(value) for value in config["node_budgets"]),
        search_enabled=config.get("search_enabled"),
        game_schedule=(
            tuple(int(value) for value in config["game_schedule"])
            if config.get("game_schedule") is not None
            else None
        ),
        start_state_source=config.get("start_state_source", "initial"),
        root_allocation=config.get("root_allocation", "sequential"),
        policy_target=config.get("policy_target", "visit_distribution"),
        policy_target_temperature=float(config.get("policy_target_temperature", 1.0)),
        behavior_policy=config.get("behavior_policy", "visit_distribution"),
        exploration=exploration,
    )


def execute_loop(
    config: dict[str, Any],
    oracle: OracleArrays,
    development_indices: np.ndarray,
    training_start_indices: np.ndarray | None = None,
) -> LoopExecution:
    """Execute once without filesystem writes, enabling an independent replay."""
    threads = int(config["runtime"]["threads"])
    seed = int(config["seed"])
    seed_everything(seed, threads)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    model_config = ModelConfig(**config["model"])
    parent = MiniJassMLP(model_config)
    initial_hash = model_hash(parent)
    replay_config = config["replay"]
    replay = ReplayBuffer(int(replay_config["capacity"]))
    development_tensors = _development_tensors(oracle, graph)
    self_play_config = _parse_self_play(config["self_play"])
    arena_config = ArenaConfig(**config["arena"])
    training = config["training"]
    promotion = config["promotion"]
    generation_records: list[dict[str, Any]] = []
    candidate_states: list[dict[str, torch.Tensor]] = []
    state_sample_counts = np.zeros(graph.state_count, dtype=np.uint32)
    all_samples: list[ReplaySample] = []
    start_state_ids: np.ndarray | None = None
    if self_play_config.start_state_source == "train_split":
        if training_start_indices is None:
            raise ValueError("train-split starts require the immutable train cohort")
        start_state_ids = np.asarray(
            [
                int(state_id)
                for state_id in training_start_indices
                if graph.terminal_value(int(state_id)) is None
            ],
            dtype=np.int64,
        )
        if not start_state_ids.size:
            raise ValueError("the train cohort has no non-terminal start state")

    for generation in range(1, int(config["generations"]) + 1):
        generated = generate_self_play(
            graph,
            parent,
            self_play_config,
            generation,
            seed + generation * 10_000,
            start_state_ids,
        )
        all_samples.extend(generated.samples)
        replay.extend(generated.samples)
        if generated.samples:
            np.add.at(
                state_sample_counts,
                np.asarray([sample.state_id for sample in generated.samples], dtype=np.int64),
                1,
            )
        replay_rng = np.random.default_rng(seed + generation * 15_000)
        if replay_config["strategy"] == "disabled":
            training_pool = generated.samples
        else:
            training_pool = replay.sample(
                int(replay_config["training_samples"]),
                replay_config["strategy"],
                replay_rng,
                generation,
            )
        candidate = deepcopy(parent)
        train_metrics = train_from_replay(
            candidate,
            graph,
            training_pool,
            steps=int(training["steps"]),
            batch_size=int(training["batch_size"]),
            learning_rate=float(training["learning_rate"]),
            weight_decay=float(training["weight_decay"]),
            value_weight=float(training["value_weight"]),
            policy_weight=float(training["policy_weight"]),
            seed=seed + generation * 30_000,
        )
        parent_development = evaluate(
            parent,
            development_tensors,
            oracle,
            development_indices,
            int(config["development"]["batch_size"]),
        )
        candidate_development = evaluate(
            candidate,
            development_tensors,
            oracle,
            development_indices,
            int(config["development"]["batch_size"]),
        )
        improvement = _selection_score(candidate_development) - _selection_score(parent_development)
        arena = run_arena(
            graph,
            candidate,
            parent,
            arena_config,
            seed + generation * 20_000,
        )
        development_pass = improvement >= float(promotion["minimum_development_improvement"])
        arena_pass = arena["score_lower_confidence_bound"] >= float(
            promotion["minimum_arena_lower_bound"]
        )
        eligible = development_pass and arena_pass
        provisional_advance = eligible and bool(config["deterministic"])
        candidate_hash = model_hash(candidate)
        candidate_states.append(deepcopy(candidate.state_dict()))
        if provisional_advance:
            parent = candidate

        generation_records.append(
            {
                "generation": generation,
                "self_play": generated.metrics,
                "coverage": generated.coverage,
                "replay": replay.metrics(),
                "training": train_metrics,
                "development": {
                    "parent": parent_development,
                    "candidate": candidate_development,
                    "selection_score_improvement": improvement,
                },
                "arena": arena,
                "promotion": {
                    "development_pass": development_pass,
                    "arena_pass": arena_pass,
                    "deterministic_mode": bool(config["deterministic"]),
                    "eligible_after_development_and_arena": eligible,
                    "provisional_advance": provisional_advance,
                },
                "candidate_model_hash": candidate_hash,
                "deployed_model_hash": model_hash(parent),
            }
        )

    core: dict[str, Any] = {
        "schema": "mini_jass.selfplay_result.v1",
        "mode": self_play_config.mode,
        "seed": seed,
        "deterministic": bool(config["deterministic"]),
        "parameter_count": parameter_count(parent),
        "initial_model_hash": initial_hash,
        "final_model_hash": model_hash(parent),
        "generations": generation_records,
        "oracle_contract": {
            "solver_hash": int(oracle.manifest["solver_hash"]),
            "split_manifest_hash": config["expected_split_manifest_hash"],
            "usage": "development_promotion_gate_only",
        },
        "training_target_contract": {
            "value": "final_self_play_wdl",
            "policy": self_play_config.policy_target,
            "search_root_allocation": self_play_config.root_allocation,
            "self_play_behavior": self_play_config.behavior_policy,
            "start_states": self_play_config.start_state_source,
            "forbidden_fields": ["oracle_value", "dtw", "optimal_actions"],
        },
    }
    core["execution_hash"] = _digest(core)
    return LoopExecution(
        core,
        candidate_states,
        deepcopy(parent.state_dict()),
        state_sample_counts,
        all_samples,
    )


def _deterministic_payloads(config: dict[str, Any], execution: LoopExecution) -> dict[str, bytes]:
    generations = execution.core["generations"]
    return {
        "config.resolved.yaml": yaml.safe_dump(config, sort_keys=True).encode(),
        "metrics.jsonl": _jsonl_bytes(generations),
        "coverage.json": _json_bytes([record["coverage"] for record in generations]),
        "arena.json": _json_bytes([record["arena"] for record in generations]),
        "seeds.json": _json_bytes(
            {
                "root": config["seed"],
                "split": config["split_seed"],
                "schedule": "selfplay=seed+10000*g,replay=seed+15000*g,arena=seed+20000*g,train=seed+30000*g",
            }
        ),
        "execution.json": _json_bytes(execution.core),
    }


def _summary(result: dict[str, Any]) -> str:
    promoted = sum(record["promotion"]["promoted"] for record in result["generations"])
    return "\n".join(
        [
            "# Mini-Jass M4 self-play report",
            "",
            f"- Gate: **{result['gate']['status']}**",
            f"- Mode: `{result['mode']}`",
            f"- Generations: {len(result['generations'])}",
            f"- Promotions: {promoted}",
            f"- Final model: `{result['final_model_hash']}`",
            f"- Execution hash: `{result['execution_hash']}`",
            "- Frozen test usage: **none**",
            "",
        ]
    )


def run_selfplay_loop(config_path: Path, oracle_path: Path, run_dir: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("unexpected self-play config schema")
    if not config.get("deterministic"):
        raise ValueError("the M4 gate requires deterministic mode")

    run_dir = ensure_artefact_path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    oracle = load_oracle(oracle_path)
    split = build_split(oracle, int(config["split_seed"]))
    if split.manifest["manifest_hash"] != config["expected_split_manifest_hash"]:
        raise ValueError("self-play config expects a different split manifest")
    frozen_path = Path(config["frozen_split_manifest"])
    if not frozen_path.is_absolute():
        frozen_path = config_path.parent.parent / frozen_path
    frozen_manifest = json.loads(frozen_path.read_text(encoding="utf-8"))
    if split.manifest != frozen_manifest:
        raise ValueError("computed development split differs from frozen manifest")
    development_indices = split.indices("development")

    first = execute_loop(config, oracle, development_indices)
    second = execute_loop(config, oracle, development_indices)
    first_payloads = _deterministic_payloads(config, first)
    second_payloads = _deterministic_payloads(config, second)
    first_hashes = {name: _sha256(payload) for name, payload in first_payloads.items()}
    second_hashes = {name: _sha256(payload) for name, payload in second_payloads.items()}
    reproducible = first_hashes == second_hashes
    result = deepcopy(first.core)
    result["gate"] = {
        "name": "repeated_seeded_artifact_hashes",
        "status": "PASS" if reproducible else "FAIL",
        "matching_artifact_count": sum(
            first_hashes[name] == second_hashes[name] for name in first_hashes
        ),
        "artifact_count": len(first_hashes),
    }
    for record in result["generations"]:
        provisional = record["promotion"].pop("provisional_advance")
        record["promotion"]["reproducibility_pass"] = reproducible
        record["promotion"]["promoted"] = provisional and reproducible

    for name, payload in first_payloads.items():
        if name == "execution.json":
            continue
        (run_dir / name).write_bytes(payload)
    (run_dir / "result.json").write_bytes(_json_bytes(result))
    (run_dir / "summary.md").write_text(_summary(result), encoding="utf-8")
    for generation, state in enumerate(first.candidate_states, start=1):
        torch.save(
            {"model": state, "config": config["model"], "generation": generation},
            run_dir / f"checkpoint_candidate_{generation:03d}.pt",
        )
    torch.save(
        {"model": first.final_state, "config": config["model"]},
        run_dir / "checkpoint_final.pt",
    )
    solver_manifest_path = ensure_artefact_path(
        Path(__file__).resolve().parents[2] / "artefacts/solver_manifest.v1.json"
    )
    (run_dir / "solver_manifest.json").write_bytes(solver_manifest_path.read_bytes())
    solver_manifest = json.loads(solver_manifest_path.read_text(encoding="utf-8"))
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
    (run_dir / "split_manifest.json").write_bytes(_json_bytes(split.manifest))
    (run_dir / "environment.json").write_bytes(
        _json_bytes(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "torch": torch.__version__,
                "numpy": np.__version__,
                "threads": config["runtime"]["threads"],
                "cuda_available": torch.cuda.is_available(),
            }
        )
    )
    reproducibility = {
        "schema": "mini_jass.reproducibility.v1",
        "status": result["gate"]["status"],
        "first_run_artifact_hashes": first_hashes,
        "second_run_artifact_hashes": second_hashes,
        "checkpoint_model_hashes": [
            record["candidate_model_hash"] for record in result["generations"]
        ]
        + [result["final_model_hash"]],
    }
    (run_dir / "reproducibility.json").write_bytes(_json_bytes(reproducibility))
    return result
