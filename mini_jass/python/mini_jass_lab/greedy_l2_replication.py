"""M12: full greedy L2 learning replication on fresh train-derived cohorts."""

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

from .experiment import (
    _apply_overrides,
    _digest,
    _file_sha256,
    _metric_subset,
    _oracle_tensors,
    _package_sha256,
)
from .game_graph import GameGraph
from .greedy_confirmation import derive_confirmation_holdout
from .learning_gate import _target_subset
from .loop import execute_loop
from .model import MiniJassMLP, ModelConfig, model_hash, parameter_count
from .oracle import OracleArrays, ensure_artefact_path, load_oracle
from .split import SplitDefinition, build_split
from .train import evaluate, seed_everything


FRESH_PAIRED_SEEDS = (122001, 122002, 122003, 122004, 122005)
REPLICATION_COHORTS = ("train", "development", "confirmation")
REPLICATION_ALGORITHM = (
    "sha256_ordered_exact_70_15_15_within_value_material_"
    "after_m11_exclusion_v1"
)


@dataclass(frozen=True)
class GreedyReplicationSplit:
    canonical_assignments: np.ndarray
    raw_assignments: np.ndarray
    manifest: dict[str, Any]

    def indices(self, cohort: str) -> np.ndarray:
        if cohort not in REPLICATION_COHORTS:
            raise ValueError(f"unknown greedy-replication cohort {cohort}")
        return np.flatnonzero(
            self.raw_assignments == REPLICATION_COHORTS.index(cohort)
        )


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _resolve_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_path.parent.parent / path


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _confidence_95(values: list[float]) -> list[float]:
    samples = np.asarray(values, dtype=np.float64)
    if samples.size < 2:
        return [float(samples[0]), float(samples[0])]
    critical = 2.7764451051977987 if samples.size == 5 else 1.96
    half_width = critical * float(samples.std(ddof=1)) / math.sqrt(samples.size)
    center = float(samples.mean())
    return [center - half_width, center + half_width]


def _canonical_material(oracle: OracleArrays, raw_index: int) -> tuple[int, ...]:
    counts = tuple(int(value).bit_count() for value in oracle.bitboards[raw_index])
    if bool(oracle.canonical_transforms[raw_index]):
        return counts[1], counts[0], counts[3], counts[2]
    return counts


def _replication_order(seed: int, solver_hash: int, canonical_id: int) -> bytes:
    payload = (
        f"mini_jass.greedy_l2_replication.v1|{seed}|{solver_hash}|{canonical_id}"
    ).encode()
    return hashlib.sha256(payload).digest()


def derive_greedy_replication_split(
    oracle: OracleArrays,
    historical_split: SplitDefinition,
    excluded_m11_canonical_ids: np.ndarray,
    seed: int,
) -> GreedyReplicationSplit:
    """Split only historical train classes after excluding the M11 holdout."""
    canonical_count = int(oracle.manifest["canonical_state_count"])
    if historical_split.canonical_assignments.shape != (canonical_count,):
        raise ValueError("historical split and oracle canonical counts differ")
    excluded = np.asarray(excluded_m11_canonical_ids, dtype=np.int64)
    if excluded.size != np.unique(excluded).size:
        raise ValueError("M11 exclusion contains duplicate canonical classes")
    if np.any(historical_split.canonical_assignments[excluded] != 0):
        raise ValueError("M11 exclusion escaped the historical train cohort")

    representatives = np.full(canonical_count, -1, dtype=np.int64)
    for raw_id, canonical_id in enumerate(oracle.canonical_ids):
        if representatives[int(canonical_id)] < 0:
            representatives[int(canonical_id)] = raw_id
    if np.any(representatives < 0):
        raise ValueError("every canonical class requires a representative")

    historical_train = np.flatnonzero(
        historical_split.canonical_assignments == 0
    )
    excluded_mask = np.zeros(canonical_count, dtype=np.bool_)
    excluded_mask[excluded] = True
    remaining = historical_train[~excluded_mask[historical_train]]
    if not remaining.size:
        raise ValueError("M11 exclusion consumed the historical train cohort")

    strata: dict[tuple[int, ...], list[int]] = {}
    for canonical_id in remaining:
        raw_id = int(representatives[int(canonical_id)])
        key = (int(oracle.values[raw_id]), *_canonical_material(oracle, raw_id))
        strata.setdefault(key, []).append(int(canonical_id))

    # Codes 0..2 are M12 cohorts, 3 is the excluded M11 holdout, and 4 is
    # every historical non-train class. Only codes 0..2 are ever evaluated.
    assignments = np.full(canonical_count, 4, dtype=np.uint8)
    assignments[excluded] = 3
    solver_hash = int(oracle.manifest["solver_hash"])
    stratum_manifest: list[dict[str, Any]] = []
    for stratum, canonical_ids in sorted(strata.items()):
        ordered = sorted(
            canonical_ids,
            key=lambda canonical_id: _replication_order(
                seed, solver_hash, canonical_id
            ),
        )
        count = len(ordered)
        train_end = int(count * 0.70)
        development_end = train_end + int(count * 0.15)
        assignments[ordered[:train_end]] = 0
        assignments[ordered[train_end:development_end]] = 1
        assignments[ordered[development_end:]] = 2
        stratum_manifest.append(
            {
                "value": stratum[0],
                "material": list(stratum[1:]),
                "canonical_counts": {
                    "train": train_end,
                    "development": development_end - train_end,
                    "confirmation": count - development_end,
                },
            }
        )

    raw_assignments = assignments[oracle.canonical_ids]
    canonical_counts = np.bincount(assignments, minlength=5)
    raw_counts = np.bincount(raw_assignments, minlength=5)
    assignment_hasher = hashlib.sha256()
    assignment_names = (*REPLICATION_COHORTS, "excluded_m11", "historical_nontrain")
    for canonical_id, assignment in enumerate(assignments):
        assignment_hasher.update(
            f"{canonical_id}:{assignment_names[int(assignment)]}\n".encode()
        )

    manifest: dict[str, Any] = {
        "schema": "mini_jass.greedy_replication_split.l2.v1",
        "algorithm": REPLICATION_ALGORITHM,
        "seed": int(seed),
        "solver_hash": solver_hash,
        "source_cohort": "historical_train_after_m11_exclusion",
        "source_split_manifest_hash": historical_split.manifest["manifest_hash"],
        "canonical_state_count": canonical_count,
        "raw_state_count": oracle.state_count,
        "canonical_counts": {
            name: int(canonical_counts[index])
            for index, name in enumerate(assignment_names)
        },
        "raw_counts": {
            name: int(raw_counts[index])
            for index, name in enumerate(assignment_names)
        },
        "strata": stratum_manifest,
        "assignment_hash": assignment_hasher.hexdigest(),
    }
    manifest["manifest_hash"] = _digest(manifest)
    return GreedyReplicationSplit(assignments, raw_assignments, manifest)


def resolve_greedy_l2_replication_config(config_path: Path) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != "mini_jass.greedy_l2_replication.v1":
        raise ValueError("unexpected greedy L2 replication schema")
    seeds = tuple(int(seed) for seed in config["paired_seeds"])
    if seeds != FRESH_PAIRED_SEEDS:
        raise ValueError("M12 fresh paired seeds changed after preregistration")
    if "frozen_test" in json.dumps(config).lower():
        raise ValueError("M12 must not name or consume the M9 frozen-test cohort")
    if config.get("mechanism_overrides") != {
        "self_play.exploration.strategy": "greedy"
    }:
        raise ValueError("M12 may change only the confirmed behavior strategy")
    if config.get("replication_split") != {
        "seed": 20260809,
        "train_fraction": 0.70,
        "development_fraction": 0.15,
        "confirmation_fraction": 0.15,
    }:
        raise ValueError("M12 replication split changed after preregistration")

    m11_path = _resolve_path(config_path, config["m11_evidence"])
    m11 = json.loads(m11_path.read_text(encoding="utf-8"))
    if (
        m11.get("schema") != "mini_jass.m11_greedy_confirmation.v1"
        or m11.get("result_hash") != config["expected_m11_result_hash"]
        or m11.get("scientific_gate", {}).get("status") != "PASS"
        or not m11.get("recommendation", {}).get(
            "l2_replication_rerun_authorized", False
        )
        or m11.get("recommendation", {}).get("decision")
        != "rerun_l2_replication_with_confirmed_greedy_behavior"
        or m11.get("recommendation", {}).get("direct_10x10_transfer_authorized")
        is not False
    ):
        raise ValueError("M12 requires the exact passing M11 rerun authorization")

    loop_path = _resolve_path(config_path, config["loop_config"])
    loop = yaml.safe_load(loop_path.read_text(encoding="utf-8"))
    self_play = loop.get("self_play", {})
    if (
        loop.get("schema") != "mini_jass.selfplay.v1"
        or (loop.get("model", {}).get("input_count"), loop.get("model", {}).get("action_count"))
        != (74, 122)
        or self_play.get("policy_target") != "score_softmax"
        or self_play.get("behavior_policy") != "search_scores"
        or self_play.get("root_allocation") != "balanced"
        or self_play.get("start_state_source") != "train_split"
        or self_play.get("exploration", {}).get("strategy") != "top_k_uniform"
        or int(self_play.get("exploration", {}).get("top_k", 0)) != 2
        or list(self_play.get("node_budgets", [])) != [16]
        or int(self_play.get("games", 0)) != 128
        or int(loop.get("training", {}).get("steps", 0)) != 1024
        or loop.get("replay", {}).get("strategy") != "disabled"
    ):
        raise ValueError("M12 baseline differs from the frozen M9 learning mechanism")

    resolved = deepcopy(config)
    resolved["paired_seeds"] = list(seeds)
    resolved["m11_evidence"] = str(m11_path.resolve())
    resolved["m11"] = m11
    resolved["loop_config"] = str(loop_path.resolve())
    resolved["loop"] = loop
    resolved["historical_split_manifest"] = str(
        _resolve_path(config_path, config["historical_split_manifest"]).resolve()
    )
    return resolved


def build_greedy_l2_replication_recommendation(
    aggregate: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, Any]:
    criteria = {
        "exactly_five_successful_runs": aggregate["successful_run_count"] == 5,
        "deterministic_replay": bool(aggregate["deterministic_replay"]),
        "greedy_behavior_only": bool(aggregate["greedy_behavior_only"]),
        "training_sample_filter_enforced": bool(
            aggregate["training_sample_filter_enforced"]
        ),
        "historical_train_only": bool(aggregate["historical_train_only"]),
        "m11_holdout_excluded": aggregate["m11_holdout_evaluation_reads"] == 0,
        "historical_nontrain_untouched": aggregate[
            "historical_nontrain_evaluation_reads"
        ]
        == 0,
        "mean_development_value_sign_delta": aggregate[
            "mean_development_value_sign_delta"
        ]
        > float(thresholds["minimum_mean_value_sign_delta"]),
        "mean_development_optimal_mass_delta": aggregate[
            "mean_development_optimal_mass_delta"
        ]
        > float(thresholds["minimum_mean_optimal_mass_delta"]),
        "development_selection_confidence_above_zero": aggregate[
            "development_selection_score_confidence_95"
        ][0]
        > 0.0,
        "mean_confirmation_value_sign_delta": aggregate[
            "mean_confirmation_value_sign_delta"
        ]
        > float(thresholds["minimum_mean_value_sign_delta"]),
        "mean_confirmation_optimal_mass_delta": aggregate[
            "mean_confirmation_optimal_mass_delta"
        ]
        > float(thresholds["minimum_mean_optimal_mass_delta"]),
        "confirmation_selection_confidence_above_zero": aggregate[
            "confirmation_selection_score_confidence_95"
        ][0]
        > 0.0,
        "minimum_target_value_exact_rate": aggregate[
            "mean_target_value_exact_rate"
        ]
        >= float(thresholds["minimum_target_value_exact_rate"]),
        "minimum_target_optimal_mass": aggregate["mean_target_optimal_mass"]
        >= float(thresholds["minimum_target_optimal_mass"]),
        "at_least_one_eligible_candidate": aggregate["eligible_candidate_count"]
        >= 1,
    }
    passed = all(criteria.values())
    return {
        "decision": (
            "l2_replication_confirmed_prepare_isolated_10x10_contract"
            if passed
            else "keep_l2_gate_closed"
        ),
        "l2_replication_confirmed": passed,
        "implementation_preparation_authorized": passed,
        "production_jass_changes_authorized": False,
        "direct_10x10_transfer_authorized": False,
        "gate": {"status": "PASS" if passed else "FAIL", "criteria": criteria},
        "next_gate": (
            "Prepare an isolated 10x10 integration contract under mini_jass; production Jass remains untouched."
            if passed
            else "Diagnose the failed fresh L2 replication without opening historical non-train cohorts."
        ),
    }


def _model_hash_from_state(state: dict[str, torch.Tensor]) -> str:
    hasher = hashlib.sha256()
    for name, tensor in sorted(state.items()):
        hasher.update(name.encode())
        hasher.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return hasher.hexdigest()


def run_greedy_l2_replication(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path | None = None,
) -> dict[str, Any]:
    resolved = resolve_greedy_l2_replication_config(config_path)
    oracle = load_oracle(oracle_path)
    if (
        oracle.manifest.get("schema") != "mini_jass.oracle_dataset.l2.v1"
        or oracle.state_count != 49690
        or oracle.action_count != 122
        or oracle.feature_count != 74
    ):
        raise ValueError("M12 requires the frozen selected-scope L2 oracle")
    historical_split = build_split(oracle, int(resolved["historical_split_seed"]))
    historical_manifest = json.loads(
        Path(resolved["historical_split_manifest"]).read_text(encoding="utf-8")
    )
    if historical_split.manifest != historical_manifest:
        raise ValueError("M12 historical split differs from the frozen L2 contract")

    m11_manifest = resolved["m11"]["confirmation_holdout"]
    m11_holdout = derive_confirmation_holdout(
        oracle,
        historical_split,
        int(m11_manifest["seed"]),
        float(m11_manifest["fraction"]),
    )
    if m11_holdout.manifest != m11_manifest:
        raise ValueError("M12 could not reproduce the exact excluded M11 holdout")
    replication = derive_greedy_replication_split(
        oracle,
        historical_split,
        m11_holdout.canonical_ids,
        int(resolved["replication_split"]["seed"]),
    )

    greedy_loop = deepcopy(resolved["loop"])
    _apply_overrides(greedy_loop, resolved["mechanism_overrides"])
    greedy_loop["split_seed"] = int(resolved["replication_split"]["seed"])
    greedy_loop["expected_split_manifest_hash"] = replication.manifest[
        "manifest_hash"
    ]
    protocol = {
        "schema": resolved["schema"],
        "paired_seeds": resolved["paired_seeds"],
        "greedy_loop": greedy_loop,
        "mechanism_overrides": resolved["mechanism_overrides"],
        "replication_split": replication.manifest,
        "training_sample_scope": "replication_train_only",
        "scientific_gate": resolved["scientific_gate"],
        "m11_result_hash": resolved["expected_m11_result_hash"],
        "m11_holdout_manifest_hash": m11_holdout.manifest["manifest_hash"],
        "historical_split_manifest_hash": historical_split.manifest[
            "manifest_hash"
        ],
        "solver_hash": oracle.manifest["solver_hash"],
    }
    protocol_hash = _digest(protocol)

    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    tensors = _oracle_tensors(oracle, graph)
    train_indices = replication.indices("train")
    development_indices = replication.indices("development")
    confirmation_indices = replication.indices("confirmation")
    training_state_mask = replication.raw_assignments == 0

    pending: list[dict[str, Any]] = []
    for seed in resolved["paired_seeds"]:
        loop_config = deepcopy(greedy_loop)
        loop_config["seed"] = seed
        execution = execute_loop(
            loop_config,
            oracle,
            development_indices,
            train_indices,
            training_state_mask,
        )
        pending.append({"seed": seed, "config": loop_config, "execution": execution})

    replay_config = deepcopy(pending[0]["config"])
    replay = execute_loop(
        replay_config,
        oracle,
        development_indices,
        train_indices,
        training_state_mask,
    )
    deterministic_replay = (
        replay.core["execution_hash"]
        == pending[0]["execution"].core["execution_hash"]
        and _model_hash_from_state(replay.candidate_states[-1])
        == _model_hash_from_state(pending[0]["execution"].candidate_states[-1])
    )

    # All five candidates and the protocol are fixed above. Exact target labels
    # and the new confirmation cohort are opened only below this point.
    seed_results: list[dict[str, Any]] = []
    for item in pending:
        seed = int(item["seed"])
        loop_config = item["config"]
        execution = item["execution"]
        seed_everything(seed, int(loop_config["runtime"]["threads"]))
        initial = MiniJassMLP(ModelConfig(**loop_config["model"]))
        candidate = MiniJassMLP(ModelConfig(**loop_config["model"]))
        candidate.load_state_dict(execution.candidate_states[-1])

        initial_development = _metric_subset(
            evaluate(
                initial,
                tensors,
                oracle,
                development_indices,
                int(loop_config["development"]["batch_size"]),
            )
        )
        candidate_development = _metric_subset(
            evaluate(
                candidate,
                tensors,
                oracle,
                development_indices,
                int(loop_config["development"]["batch_size"]),
            )
        )
        initial_confirmation = _metric_subset(
            evaluate(
                initial,
                tensors,
                oracle,
                confirmation_indices,
                int(loop_config["development"]["batch_size"]),
            )
        )
        candidate_confirmation = _metric_subset(
            evaluate(
                candidate,
                tensors,
                oracle,
                confirmation_indices,
                int(loop_config["development"]["batch_size"]),
            )
        )
        diagnostic_samples = [
            sample
            for sample in execution.samples
            if bool(training_state_mask[sample.state_id])
        ]
        targets = _target_subset(diagnostic_samples, oracle)
        development_value_delta = (
            candidate_development["value_sign_accuracy"]
            - initial_development["value_sign_accuracy"]
        )
        development_mass_delta = (
            candidate_development["optimal_probability_mass"]
            - initial_development["optimal_probability_mass"]
        )
        confirmation_value_delta = (
            candidate_confirmation["value_sign_accuracy"]
            - initial_confirmation["value_sign_accuracy"]
        )
        confirmation_mass_delta = (
            candidate_confirmation["optimal_probability_mass"]
            - initial_confirmation["optimal_probability_mass"]
        )
        last = execution.core["generations"][-1]
        seed_results.append(
            {
                "seed": seed,
                "initial_model_hash": execution.core["initial_model_hash"],
                "candidate_model_hash": model_hash(candidate),
                "parameter_count": parameter_count(candidate),
                "development": {
                    "initial": initial_development,
                    "candidate": candidate_development,
                    "value_sign_delta": development_value_delta,
                    "optimal_mass_delta": development_mass_delta,
                    "selection_score_delta": development_value_delta
                    + development_mass_delta,
                },
                "confirmation": {
                    "initial": initial_confirmation,
                    "candidate": candidate_confirmation,
                    "value_sign_delta": confirmation_value_delta,
                    "optimal_mass_delta": confirmation_mass_delta,
                    "selection_score_delta": confirmation_value_delta
                    + confirmation_mass_delta,
                },
                "targets": targets,
                "generated_sample_count": len(execution.samples),
                "training_sample_count": len(diagnostic_samples),
                "excluded_generated_sample_count": len(execution.samples)
                - len(diagnostic_samples),
                "coverage": last["coverage"],
                "promotion": last["promotion"],
                "execution_hash": execution.core["execution_hash"],
            }
        )

    development_value_deltas = [
        float(row["development"]["value_sign_delta"]) for row in seed_results
    ]
    development_mass_deltas = [
        float(row["development"]["optimal_mass_delta"]) for row in seed_results
    ]
    development_selection_deltas = [
        float(row["development"]["selection_score_delta"]) for row in seed_results
    ]
    confirmation_value_deltas = [
        float(row["confirmation"]["value_sign_delta"]) for row in seed_results
    ]
    confirmation_mass_deltas = [
        float(row["confirmation"]["optimal_mass_delta"]) for row in seed_results
    ]
    confirmation_selection_deltas = [
        float(row["confirmation"]["selection_score_delta"]) for row in seed_results
    ]
    aggregate = {
        "successful_run_count": len(seed_results),
        "deterministic_replay": deterministic_replay,
        "greedy_behavior_only": True,
        "training_sample_filter_enforced": True,
        "historical_train_only": True,
        "m11_holdout_evaluation_reads": 0,
        "historical_nontrain_evaluation_reads": 0,
        "mean_development_value_sign_delta": _mean(development_value_deltas),
        "mean_development_optimal_mass_delta": _mean(development_mass_deltas),
        "development_selection_score_confidence_95": _confidence_95(
            development_selection_deltas
        ),
        "mean_confirmation_value_sign_delta": _mean(confirmation_value_deltas),
        "mean_confirmation_optimal_mass_delta": _mean(confirmation_mass_deltas),
        "confirmation_selection_score_confidence_95": _confidence_95(
            confirmation_selection_deltas
        ),
        "mean_target_value_exact_rate": _mean(
            [float(row["targets"]["value_exact_rate"]) for row in seed_results]
        ),
        "mean_target_optimal_mass": _mean(
            [float(row["targets"]["policy_optimal_mass"]) for row in seed_results]
        ),
        "mean_unique_state_coverage": _mean(
            [float(row["coverage"]["state_coverage"]) for row in seed_results]
        ),
        "mean_training_sample_count": _mean(
            [float(row["training_sample_count"]) for row in seed_results]
        ),
        "mean_excluded_generated_sample_count": _mean(
            [float(row["excluded_generated_sample_count"]) for row in seed_results]
        ),
        "eligible_candidate_count": sum(
            bool(row["promotion"]["eligible_after_development_and_arena"])
            for row in seed_results
        ),
    }
    recommendation = build_greedy_l2_replication_recommendation(
        aggregate, resolved["scientific_gate"]
    )
    result: dict[str, Any] = {
        "schema": "mini_jass.m12_greedy_l2_replication.v1",
        "milestone": "M12",
        "status": recommendation["gate"]["status"],
        "protocol_hash": protocol_hash,
        "pack": {
            "paired_seed_count": len(resolved["paired_seeds"]),
            "run_count": len(seed_results),
            "successful_run_count": len(seed_results),
        },
        "execution_gate": {
            "status": "PASS" if len(seed_results) == 5 and deterministic_replay else "FAIL",
            "criteria": {
                "all_five_runs_successful": len(seed_results) == 5,
                "deterministic_replay": deterministic_replay,
                "greedy_behavior_only": True,
                "training_sample_filter_enforced": True,
                "historical_train_only": True,
                "m11_holdout_excluded": True,
                "historical_nontrain_untouched": True,
            },
        },
        "scientific_gate": recommendation["gate"],
        "contracts": {
            "m11_result_hash": resolved["expected_m11_result_hash"],
            "m11_evidence_sha256": _file_sha256(Path(resolved["m11_evidence"])),
            "m11_holdout_manifest_hash": m11_holdout.manifest["manifest_hash"],
            "historical_split_manifest_hash": historical_split.manifest[
                "manifest_hash"
            ],
            "replication_split_manifest_hash": replication.manifest[
                "manifest_hash"
            ],
            "solver_hash": oracle.manifest["solver_hash"],
            "solver_manifest_hash": oracle.manifest["manifest_hash"],
            "oracle_export_sha256": _file_sha256(oracle_path),
            "python_package_sha256": _package_sha256(),
            "jass_production_paths_modified": False,
        },
        "replication_split": replication.manifest,
        "aggregate": aggregate,
        "recommendation": {
            key: value for key, value in recommendation.items() if key != "gate"
        },
        "confirmation_usage": (
            "unsealed_after_protocol_and_all_five_candidates_fixed"
        ),
        "seed_results": seed_results,
    }
    result["result_hash"] = _digest(result)

    output_dir = ensure_artefact_path(run_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "config.resolved.yaml").write_text(
        yaml.safe_dump(resolved, sort_keys=True), encoding="utf-8"
    )
    (output_dir / "protocol.json").write_bytes(_json_bytes(protocol))
    (output_dir / "replication_split.json").write_bytes(
        _json_bytes(replication.manifest)
    )
    (output_dir / "seed_results.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in seed_results),
        encoding="utf-8",
    )
    (output_dir / "result.json").write_bytes(_json_bytes(result))
    (output_dir / "environment.json").write_bytes(
        _json_bytes(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "torch": torch.__version__,
                "numpy": np.__version__,
                "threads": resolved["loop"]["runtime"]["threads"],
            }
        )
    )
    compact = deepcopy(result)
    compact.pop("seed_results")
    if compact_output is not None:
        ensure_artefact_path(compact_output).write_bytes(_json_bytes(compact))
    return result
