"""M13: powered seed-variance replication on a CPX-only fresh L2 split."""

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
from .greedy_l2_replication import (
    _canonical_material,
    _json_bytes,
    _model_hash_from_state,
    _resolve_path,
    derive_greedy_replication_split,
    resolve_greedy_l2_replication_config,
)
from .learning_gate import _target_subset
from .loop import execute_loop
from .model import MiniJassMLP, ModelConfig, model_hash, parameter_count
from .oracle import OracleArrays, ensure_artefact_path, load_oracle
from .split import build_split
from .train import evaluate, seed_everything


FRESH_POWERED_SEEDS = tuple(range(132001, 132021))
NESTED_COHORTS = ("train", "development", "confirmation")
NESTED_ASSIGNMENTS = (
    *NESTED_COHORTS,
    "excluded_m12_development",
    "excluded_m12_confirmation",
    "excluded_m11",
    "historical_nontrain",
)
NESTED_ALGORITHM = (
    "sha256_ordered_exact_70_15_15_within_value_material_"
    "from_m12_train_only_v1"
)
EXPECTED_HOST = "cpx62"


@dataclass(frozen=True)
class SeedVarianceSplit:
    canonical_assignments: np.ndarray
    raw_assignments: np.ndarray
    manifest: dict[str, Any]

    def indices(self, cohort: str) -> np.ndarray:
        if cohort not in NESTED_COHORTS:
            raise ValueError(f"unknown M13 cohort {cohort}")
        return np.flatnonzero(
            self.raw_assignments == NESTED_COHORTS.index(cohort)
        )


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float64)))


def _confidence_95(values: list[float], critical: float) -> list[float]:
    samples = np.asarray(values, dtype=np.float64)
    if samples.size < 2:
        return [float(samples[0]), float(samples[0])]
    half_width = critical * float(samples.std(ddof=1)) / math.sqrt(samples.size)
    center = float(samples.mean())
    return [center - half_width, center + half_width]


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _m12_effect(
    aggregate: dict[str, Any], cohort: str, source_critical: float
) -> dict[str, float]:
    mean = float(aggregate[f"mean_{cohort}_value_sign_delta"]) + float(
        aggregate[f"mean_{cohort}_optimal_mass_delta"]
    )
    interval = aggregate[f"{cohort}_selection_score_confidence_95"]
    half_width = (float(interval[1]) - float(interval[0])) / 2.0
    standard_deviation = half_width * math.sqrt(5.0) / source_critical
    if standard_deviation <= 0.0:
        raise ValueError("M12 selection-score variance must be positive")
    return {
        "mean_selection_score_delta": mean,
        "reconstructed_standard_deviation": standard_deviation,
        "standardized_effect": mean / standard_deviation,
    }


def _power_analysis(
    m12: dict[str, Any], power_design: dict[str, Any]
) -> dict[str, Any]:
    source_critical = float(power_design["m12_confidence_critical_95"])
    target_critical = float(power_design["m13_confidence_critical_95"])
    count = int(power_design["fixed_replication_seed_count"])
    effects = {
        cohort: _m12_effect(m12["aggregate"], cohort, source_critical)
        for cohort in ("development", "confirmation")
    }
    floor = min(row["standardized_effect"] for row in effects.values())
    noncentrality = floor * math.sqrt(count)
    anticipated_power = (
        1.0
        - _normal_cdf(target_critical - noncentrality)
        + _normal_cdf(-target_critical - noncentrality)
    )
    return {
        "source": "M12_selection_score_effects_without_pooling_results",
        "effects": effects,
        "standardized_effect_floor": floor,
        "fixed_replication_seed_count": count,
        "anticipated_power": anticipated_power,
        "minimum_anticipated_power": float(
            power_design["minimum_anticipated_power"]
        ),
        "approximation": power_design["approximation"],
    }


def _nested_order(seed: int, solver_hash: int, canonical_id: int) -> bytes:
    payload = (
        f"mini_jass.seed_variance_replication.v1|{seed}|"
        f"{solver_hash}|{canonical_id}"
    ).encode()
    return hashlib.sha256(payload).digest()


def derive_seed_variance_split(
    oracle: OracleArrays,
    m12_assignments: np.ndarray,
    m12_manifest_hash: str,
    seed: int,
) -> SeedVarianceSplit:
    """Derive M13 exclusively from M12 train canonical classes."""
    canonical_count = int(oracle.manifest["canonical_state_count"])
    previous = np.asarray(m12_assignments, dtype=np.uint8)
    if previous.shape != (canonical_count,):
        raise ValueError("M12 split and oracle canonical counts differ")
    if np.any(previous > 4):
        raise ValueError("M12 split contains an unknown assignment")

    representatives = np.full(canonical_count, -1, dtype=np.int64)
    for raw_id, canonical_id in enumerate(oracle.canonical_ids):
        if representatives[int(canonical_id)] < 0:
            representatives[int(canonical_id)] = raw_id
    if np.any(representatives < 0):
        raise ValueError("every canonical class requires a representative")

    source = np.flatnonzero(previous == 0)
    if not source.size:
        raise ValueError("M12 train cohort is empty")
    strata: dict[tuple[int, ...], list[int]] = {}
    for canonical_id in source:
        raw_id = int(representatives[int(canonical_id)])
        key = (int(oracle.values[raw_id]), *_canonical_material(oracle, raw_id))
        strata.setdefault(key, []).append(int(canonical_id))

    assignments = np.full(canonical_count, 6, dtype=np.uint8)
    assignments[previous == 1] = 3
    assignments[previous == 2] = 4
    assignments[previous == 3] = 5
    assignments[previous == 4] = 6
    solver_hash = int(oracle.manifest["solver_hash"])
    stratum_manifest: list[dict[str, Any]] = []
    for stratum, canonical_ids in sorted(strata.items()):
        ordered = sorted(
            canonical_ids,
            key=lambda canonical_id: _nested_order(
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

    if np.any(assignments[source] > 2):
        raise ValueError("M13 failed to partition every M12 train class")
    raw_assignments = assignments[oracle.canonical_ids]
    canonical_counts = np.bincount(assignments, minlength=7)
    raw_counts = np.bincount(raw_assignments, minlength=7)
    assignment_hasher = hashlib.sha256()
    for canonical_id, assignment in enumerate(assignments):
        assignment_hasher.update(
            f"{canonical_id}:{NESTED_ASSIGNMENTS[int(assignment)]}\n".encode()
        )

    manifest: dict[str, Any] = {
        "schema": "mini_jass.seed_variance_split.l2.v1",
        "algorithm": NESTED_ALGORITHM,
        "seed": int(seed),
        "solver_hash": solver_hash,
        "source_cohort": "m12_train_only",
        "source_m12_split_manifest_hash": m12_manifest_hash,
        "canonical_state_count": canonical_count,
        "raw_state_count": oracle.state_count,
        "canonical_counts": {
            name: int(canonical_counts[index])
            for index, name in enumerate(NESTED_ASSIGNMENTS)
        },
        "raw_counts": {
            name: int(raw_counts[index])
            for index, name in enumerate(NESTED_ASSIGNMENTS)
        },
        "strata": stratum_manifest,
        "assignment_hash": assignment_hasher.hexdigest(),
    }
    manifest["manifest_hash"] = _digest(manifest)
    return SeedVarianceSplit(assignments, raw_assignments, manifest)


def resolve_seed_variance_replication_config(
    config_path: Path,
) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != "mini_jass.seed_variance_replication.v1":
        raise ValueError("unexpected seed-variance replication schema")
    seeds = tuple(int(seed) for seed in config["paired_seeds"])
    if seeds != FRESH_POWERED_SEEDS:
        raise ValueError("M13 powered fresh seeds changed after preregistration")
    if "frozen_test" in json.dumps(config).lower():
        raise ValueError("M13 must not name or consume the M9 frozen-test cohort")
    if config.get("expected_execution_host") != EXPECTED_HOST:
        raise ValueError("M13 execution host must remain cpx62")
    if config.get("primary_inference") != (
        "independent_m13_only_no_pooling_with_m12"
    ):
        raise ValueError("M13 primary inference must remain independent")
    if config.get("nested_split") != {
        "seed": 20260810,
        "train_fraction": 0.70,
        "development_fraction": 0.15,
        "confirmation_fraction": 0.15,
    }:
        raise ValueError("M13 nested split changed after preregistration")

    power_design = config.get("power_design", {})
    if power_design != {
        "source_seed_count": 5,
        "fixed_replication_seed_count": 20,
        "m12_confidence_critical_95": 2.7764451051977987,
        "m13_confidence_critical_95": 2.093024054408263,
        "minimum_anticipated_power": 0.80,
        "approximation": "two_sided_normal_approximation_with_t19_critical",
    }:
        raise ValueError("M13 power design changed after preregistration")

    m12_config_path = _resolve_path(config_path, config["m12_config"])
    m12_config = resolve_greedy_l2_replication_config(m12_config_path)
    if config.get("scientific_gate") != m12_config["scientific_gate"]:
        raise ValueError("M13 must retain the unchanged M9/M12 thresholds")

    m12_path = _resolve_path(config_path, config["m12_evidence"])
    m12 = json.loads(m12_path.read_text(encoding="utf-8"))
    criteria = m12.get("scientific_gate", {}).get("criteria", {})
    failed = {name for name, passed in criteria.items() if passed is False}
    if (
        m12.get("schema") != "mini_jass.m12_greedy_l2_replication.v1"
        or m12.get("result_hash") != config["expected_m12_result_hash"]
        or m12.get("protocol_hash") != config["expected_m12_protocol_hash"]
        or m12.get("execution_gate", {}).get("status") != "PASS"
        or m12.get("scientific_gate", {}).get("status") != "FAIL"
        or failed
        != {
            "development_selection_confidence_above_zero",
            "confirmation_selection_confidence_above_zero",
        }
        or not all(
            bool(passed) for name, passed in criteria.items() if name not in failed
        )
        or m12.get("recommendation", {}).get("decision")
        != "keep_l2_gate_closed"
        or m12.get("recommendation", {}).get(
            "implementation_preparation_authorized"
        )
        is not False
        or m12.get("recommendation", {}).get(
            "production_jass_changes_authorized"
        )
        is not False
        or m12.get("recommendation", {}).get(
            "direct_10x10_transfer_authorized"
        )
        is not False
    ):
        raise ValueError("M13 requires the exact variance-only M12 failure")

    power_analysis = _power_analysis(m12, power_design)
    if power_analysis["anticipated_power"] < float(
        power_design["minimum_anticipated_power"]
    ):
        raise ValueError("M13 fixed sample count does not meet its power floor")

    resolved = deepcopy(config)
    resolved["paired_seeds"] = list(seeds)
    resolved["m12_config"] = str(m12_config_path.resolve())
    resolved["m12_resolved"] = m12_config
    resolved["m12_evidence"] = str(m12_path.resolve())
    resolved["m12"] = m12
    resolved["power_analysis"] = power_analysis
    return resolved


def build_seed_variance_recommendation(
    aggregate: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, Any]:
    criteria = {
        "exactly_twenty_successful_runs": aggregate["successful_run_count"] == 20,
        "deterministic_replay": bool(aggregate["deterministic_replay"]),
        "cpx62_execution_proven": aggregate["execution_host"] == EXPECTED_HOST,
        "independent_m13_inference_only": not bool(
            aggregate["m12_results_pooled_for_primary_inference"]
        ),
        "greedy_behavior_only": bool(aggregate["greedy_behavior_only"]),
        "training_sample_filter_enforced": bool(
            aggregate["training_sample_filter_enforced"]
        ),
        "m12_train_source_only": bool(aggregate["m12_train_source_only"]),
        "m12_development_untouched": aggregate[
            "m12_development_evaluation_reads"
        ]
        == 0,
        "m12_confirmation_untouched": aggregate[
            "m12_confirmation_evaluation_reads"
        ]
        == 0,
        "m11_holdout_untouched": aggregate["m11_holdout_evaluation_reads"] == 0,
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
            "l2_seed_variance_resolved_prepare_isolated_10x10_contract"
            if passed
            else "l2_seed_variance_not_resolved_keep_gate_closed"
        ),
        "seed_variance_resolved": passed,
        "implementation_preparation_authorized": passed,
        "production_jass_changes_authorized": False,
        "direct_10x10_transfer_authorized": False,
        "gate": {"status": "PASS" if passed else "FAIL", "criteria": criteria},
        "next_gate": (
            "Prepare an isolated 10x10 contract below mini_jass; production Jass remains untouched."
            if passed
            else "Keep the L2 gate closed; retain the independent powered result without post-hoc pooling."
        ),
    }


def run_seed_variance_replication(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path | None = None,
    execution_host: str | None = None,
) -> dict[str, Any]:
    resolved = resolve_seed_variance_replication_config(config_path)
    actual_host = execution_host or platform.node()
    if actual_host != resolved["expected_execution_host"]:
        raise ValueError(
            f"M13 requires {resolved['expected_execution_host']}, got {actual_host}"
        )

    oracle = load_oracle(oracle_path)
    if (
        oracle.manifest.get("schema") != "mini_jass.oracle_dataset.l2.v1"
        or oracle.state_count != 49690
        or oracle.action_count != 122
        or oracle.feature_count != 74
    ):
        raise ValueError("M13 requires the frozen selected-scope L2 oracle")

    m12_config = resolved["m12_resolved"]
    historical_split = build_split(
        oracle, int(m12_config["historical_split_seed"])
    )
    historical_manifest = json.loads(
        Path(m12_config["historical_split_manifest"]).read_text(encoding="utf-8")
    )
    if historical_split.manifest != historical_manifest:
        raise ValueError("M13 historical split differs from the frozen L2 contract")

    m11_manifest = m12_config["m11"]["confirmation_holdout"]
    m11_holdout = derive_confirmation_holdout(
        oracle,
        historical_split,
        int(m11_manifest["seed"]),
        float(m11_manifest["fraction"]),
    )
    if m11_holdout.manifest != m11_manifest:
        raise ValueError("M13 could not reproduce the excluded M11 holdout")
    m12_split = derive_greedy_replication_split(
        oracle,
        historical_split,
        m11_holdout.canonical_ids,
        int(m12_config["replication_split"]["seed"]),
    )
    if m12_split.manifest != resolved["m12"]["replication_split"]:
        raise ValueError("M13 could not reproduce the exact M12 split")
    replication = derive_seed_variance_split(
        oracle,
        m12_split.canonical_assignments,
        m12_split.manifest["manifest_hash"],
        int(resolved["nested_split"]["seed"]),
    )

    greedy_loop = deepcopy(m12_config["loop"])
    _apply_overrides(greedy_loop, m12_config["mechanism_overrides"])
    greedy_loop["split_seed"] = int(resolved["nested_split"]["seed"])
    greedy_loop["expected_split_manifest_hash"] = replication.manifest[
        "manifest_hash"
    ]
    protocol = {
        "schema": resolved["schema"],
        "paired_seeds": resolved["paired_seeds"],
        "execution_host": resolved["expected_execution_host"],
        "primary_inference": resolved["primary_inference"],
        "power_design": resolved["power_design"],
        "power_analysis": resolved["power_analysis"],
        "greedy_loop": greedy_loop,
        "mechanism_overrides": m12_config["mechanism_overrides"],
        "replication_split": replication.manifest,
        "training_sample_scope": "m13_nested_train_only",
        "scientific_gate": resolved["scientific_gate"],
        "m12_result_hash": resolved["expected_m12_result_hash"],
        "m12_protocol_hash": resolved["expected_m12_protocol_hash"],
        "m12_split_manifest_hash": m12_split.manifest["manifest_hash"],
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

    replay = execute_loop(
        deepcopy(pending[0]["config"]),
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

    # The protocol and every one of the 20 candidates are fixed before the
    # independent M13 confirmation labels are opened below.
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
        float(row["development"]["selection_score_delta"])
        for row in seed_results
    ]
    confirmation_value_deltas = [
        float(row["confirmation"]["value_sign_delta"]) for row in seed_results
    ]
    confirmation_mass_deltas = [
        float(row["confirmation"]["optimal_mass_delta"]) for row in seed_results
    ]
    confirmation_selection_deltas = [
        float(row["confirmation"]["selection_score_delta"])
        for row in seed_results
    ]
    critical = float(resolved["power_design"]["m13_confidence_critical_95"])
    aggregate = {
        "successful_run_count": len(seed_results),
        "deterministic_replay": deterministic_replay,
        "execution_host": actual_host,
        "m12_results_pooled_for_primary_inference": False,
        "greedy_behavior_only": True,
        "training_sample_filter_enforced": True,
        "m12_train_source_only": True,
        "m12_development_evaluation_reads": 0,
        "m12_confirmation_evaluation_reads": 0,
        "m11_holdout_evaluation_reads": 0,
        "historical_nontrain_evaluation_reads": 0,
        "mean_development_value_sign_delta": _mean(development_value_deltas),
        "mean_development_optimal_mass_delta": _mean(development_mass_deltas),
        "development_selection_score_confidence_95": _confidence_95(
            development_selection_deltas, critical
        ),
        "mean_confirmation_value_sign_delta": _mean(confirmation_value_deltas),
        "mean_confirmation_optimal_mass_delta": _mean(confirmation_mass_deltas),
        "confirmation_selection_score_confidence_95": _confidence_95(
            confirmation_selection_deltas, critical
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
    recommendation = build_seed_variance_recommendation(
        aggregate, resolved["scientific_gate"]
    )
    execution_passed = len(seed_results) == 20 and deterministic_replay
    result: dict[str, Any] = {
        "schema": "mini_jass.m13_seed_variance_replication.v1",
        "milestone": "M13",
        "status": recommendation["gate"]["status"],
        "protocol_hash": protocol_hash,
        "pack": {
            "paired_seed_count": len(resolved["paired_seeds"]),
            "run_count": len(seed_results),
            "successful_run_count": len(seed_results),
        },
        "execution_gate": {
            "status": "PASS" if execution_passed else "FAIL",
            "criteria": {
                "all_twenty_runs_successful": len(seed_results) == 20,
                "deterministic_replay": deterministic_replay,
                "cpx62_execution_proven": actual_host == EXPECTED_HOST,
                "independent_m13_inference_only": True,
                "greedy_behavior_only": True,
                "training_sample_filter_enforced": True,
                "m12_train_source_only": True,
                "m12_development_untouched": True,
                "m12_confirmation_untouched": True,
                "m11_holdout_untouched": True,
                "historical_nontrain_untouched": True,
            },
        },
        "scientific_gate": recommendation["gate"],
        "power_analysis": resolved["power_analysis"],
        "contracts": {
            "execution_host": actual_host,
            "m12_result_hash": resolved["expected_m12_result_hash"],
            "m12_protocol_hash": resolved["expected_m12_protocol_hash"],
            "m12_evidence_sha256": _file_sha256(Path(resolved["m12_evidence"])),
            "m12_split_manifest_hash": m12_split.manifest["manifest_hash"],
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
            "m12_results_pooled_for_primary_inference": False,
            "jass_production_paths_modified": False,
        },
        "replication_split": replication.manifest,
        "aggregate": aggregate,
        "recommendation": {
            key: value for key, value in recommendation.items() if key != "gate"
        },
        "confirmation_usage": (
            "unsealed_after_protocol_and_all_twenty_candidates_fixed"
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
                "execution_host": actual_host,
                "python": sys.version,
                "platform": platform.platform(),
                "torch": torch.__version__,
                "numpy": np.__version__,
                "threads": m12_config["loop"]["runtime"]["threads"],
            }
        )
    )
    compact = deepcopy(result)
    compact.pop("seed_results")
    if compact_output is not None:
        ensure_artefact_path(compact_output).write_bytes(_json_bytes(compact))
    return result
