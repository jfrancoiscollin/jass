#!/usr/bin/env python3
"""M16-P: screen temporal value targets on scalar PatternEval."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
from typing import Any

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

import mini_jass_lab.loop as loop_module  # noqa: E402
from mini_jass_lab.arena import ArenaConfig, run_arena  # noqa: E402
from mini_jass_lab.game_graph import GameGraph  # noqa: E402
from mini_jass_lab.model_factory import build_model, model_descriptor  # noqa: E402
from mini_jass_lab.oracle import load_oracle  # noqa: E402
from mini_jass_lab.pattern_reconstruction import (  # noqa: E402
    assert_pattern_value_model,
    digest,
    mean,
    paired_interval,
    replay_fingerprint,
    response_metrics,
    solved_tensors,
)
from mini_jass_lab.replay import ReplaySample  # noqa: E402
from mini_jass_lab.selfplay import generate_self_play  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402
from run_pattern_value_target_screen import (  # noqa: E402
    _fit,
    _model_state_hash,
    _random_schedule,
    _sample_structure_fingerprint,
    estimate_power,
)

SCHEMA = "mini_jass.pattern_temporal_value_target_screen.v1"
PROBE_SCHEMA = "mini_jass.pattern_temporal_value_target_probe.v1"
ARM_ORDER = (
    "OUTCOME",
    "NEXT_SEARCH",
    "LAMBDA_50",
    "LAMBDA_80",
    "EXACT_ORACLE",
)
CANDIDATE_ARMS = ("NEXT_SEARCH", "LAMBDA_50", "LAMBDA_80")
TEMPORAL_LAMBDAS = {
    "NEXT_SEARCH": 0.0,
    "LAMBDA_50": 0.5,
    "LAMBDA_80": 0.8,
}
CONTRASTS = {
    "next_search": ("NEXT_SEARCH", "OUTCOME"),
    "primary_lambda_50": ("LAMBDA_50", "OUTCOME"),
    "lambda_80": ("LAMBDA_80", "OUTCOME"),
    "oracle_gap": ("EXACT_ORACLE", "OUTCOME"),
}
ENDPOINTS = (
    "zero_regret_gain",
    "value_sign_gain",
    "value_mae",
    "mean_selected_regret",
    "arena_score_minus_half",
)

EXPECTED_M15P_PROTOCOL = (
    "e9ac2e5e34b3dceb0cf3830f3aa2fd10ae70ea56a9b360ed87eb21185e55ce3a"
)
EXPECTED_M15P_RESULT = (
    "443129d7b523b4c1ea94bd76c887a8defbeb1ce3f70c115dd85b81ab7869d645"
)


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M16-P":
        raise ValueError("unexpected M16-P schema")
    if tuple(config.get("arms", [])) != ARM_ORDER:
        raise ValueError("M16-P arms changed after preregistration")
    seeds = [int(seed) for seed in config.get("paired_seeds", [])]
    if seeds != list(range(274001, 274021)):
        raise ValueError("M16-P paired seeds changed or overlap prior evidence")

    evidence = config.get("source_evidence", {}).get("m15p", {})
    if (
        evidence.get("protocol_hash") != EXPECTED_M15P_PROTOCOL
        or evidence.get("result_hash") != EXPECTED_M15P_RESULT
        or evidence.get("status") != "FAIL"
        or evidence.get("finding")
        != "blend_does_not_recover_practical_fraction_of_pattern_oracle_gap"
        or evidence.get("decision") != "prepare_M16P_temporal_targets"
        or float(evidence.get("blend_zero_regret_ci95", [0.0])[0]) <= 0.0
        or float(evidence.get("blend_zero_regret_ci95", [0.0, math.inf])[1])
        >= float(evidence.get("required_primary_mean", -1.0))
        or float(evidence.get("oracle_gap_zero_regret_ci95", [0.0])[0]) <= 0.0
    ):
        raise ValueError("M16-P source evidence is not frozen")

    replay = config.get("replay", {})
    if (
        replay.get("source") != "G1_WIDE_OUTCOME"
        or int(replay.get("games_per_seed", 0)) != 1024
        or int(replay.get("generation", 0)) != 1
        or int(replay.get("seed_offset", 0)) != 980000
        or replay.get("row_selection") != "all_generated_train_rows"
        or replay.get("temporal_returns_built_before_train_row_filter") is not True
        or replay.get("immutable_structure_across_arms") is not True
    ):
        raise ValueError("M16-P replay contract changed")

    targets = config.get("targets", {})
    if tuple(targets) != ARM_ORDER:
        raise ValueError("M16-P target order changed")
    if (
        targets["OUTCOME"].get("source") != "terminal_selfplay_wdl"
        or targets["NEXT_SEARCH"].get("source") != "temporal_lambda_return"
        or float(targets["NEXT_SEARCH"].get("lambda", -1.0)) != 0.0
        or targets["LAMBDA_50"].get("source") != "temporal_lambda_return"
        or float(targets["LAMBDA_50"].get("lambda", -1.0)) != 0.5
        or targets["LAMBDA_50"].get("confirmatory_primary") is not True
        or targets["LAMBDA_80"].get("source") != "temporal_lambda_return"
        or float(targets["LAMBDA_80"].get("lambda", -1.0)) != 0.8
        or targets["EXACT_ORACLE"].get("source") != "exact_train_value"
        or targets["EXACT_ORACLE"].get("diagnostic_only") is not True
        or targets["EXACT_ORACLE"].get("promotable") is not False
    ):
        raise ValueError("M16-P target definitions changed")
    if any(
        targets[arm].get("oracle_training_signal") is not False
        for arm in ("OUTCOME", *CANDIDATE_ARMS)
    ) or targets["EXACT_ORACLE"].get("oracle_training_signal") is not True:
        raise ValueError("M16-P oracle boundary changed")

    temporal = config.get("temporal_contract", {})
    if (
        temporal.get("successor_bootstrap") != "negated_successor_root_score"
        or temporal.get("recurrence")
        != "-((1-lambda)*successor_search+lambda*successor_return)"
        or temporal.get("terminal_or_last_sample_fallback")
        != "terminal_selfplay_wdl"
        or temporal.get("search_score_clip") != [-1.0, 1.0]
        or temporal.get("complete_trajectory_grouping") is not True
        or temporal.get("contiguous_ply_required") is not True
        or temporal.get("full_generated_trace_used_before_train_filter") is not True
        or temporal.get("oracle_training_signal") is not False
    ):
        raise ValueError("M16-P temporal recurrence changed")

    gate = config.get("scientific_gate", {})
    required = 0.5 * float(evidence["oracle_gap_zero_regret_mean"])
    if (
        gate.get("primary_contrast") != "LAMBDA_50_minus_OUTCOME"
        or gate.get("primary_endpoint") != "development_zero_regret_gain"
        or gate.get("require_primary_ci_above_zero") is not True
        or float(gate.get("minimum_oracle_gain_recovery_fraction", -1.0)) != 0.5
        or not math.isclose(
            float(gate.get("minimum_absolute_response_gain", -1.0)),
            required,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        or gate.get("oracle_gap_must_replicate_with_ci_above_zero") is not True
        or gate.get("exploratory_arms") != ["NEXT_SEARCH", "LAMBDA_80"]
        or gate.get("exploratory_arms_cannot_rescue_primary") is not True
        or gate.get("automatic_promotion") is not False
    ):
        raise ValueError("M16-P scientific gate changed")

    power = config.get("power_sizing", {})
    if (
        int(power.get("paired_seed_count", 0)) != len(seeds)
        or float(power.get("minimum_effect", -1.0))
        != float(gate["minimum_absolute_response_gain"])
        or int(power.get("seed", 0)) != 44120260814
        or int(power.get("repetitions", 0)) != 100000
    ):
        raise ValueError("M16-P power input differs from the decision gate")
    observed_power = estimate_power(power)
    if not math.isclose(
        observed_power,
        float(power.get("estimated_power_ci_above_zero", -1.0)),
        rel_tol=0.0,
        abs_tol=5.0e-6,
    ):
        raise ValueError("M16-P frozen power result did not reproduce")
    if observed_power < float(power.get("minimum_required_power", 1.0)):
        raise ValueError("M16-P is underpowered before training")

    probe = config.get("probe", {})
    if (
        int(probe.get("seed", -1)) != 274000
        or probe.get("overlaps_scientific_seeds") is not False
        or probe.get("purpose") != "home_runtime_calibration_only"
        or probe.get("reporting") != "timing_and_contract_only"
        or probe.get("scientific_metrics_must_not_be_published") is not True
    ):
        raise ValueError("M16-P runtime probe contract changed")

    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("cohorts_read") != ["train", "development"]
        or boundaries.get("cohorts_never_read_by_this_cell") != ["frozen_test"]
        or int(boundaries.get("existing_frozen_test_read_count", -1)) != 1
        or int(boundaries.get("additional_frozen_test_reads_authorized", -1)) != 0
        or boundaries.get("oracle_training_signal_isolated_to")
        != ["EXACT_ORACLE"]
        or boundaries.get("deployable_arms_oracle_blind") is not True
        or boundaries.get("automatic_selection_or_promotion") is not False
        or boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
    ):
        raise ValueError("M16-P crossed a scientific boundary")

    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M16-P requires the frozen PatternEval loop")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M16-P requires folded PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M16-P cannot train a policy head")
    if int(replay["games_per_seed"]) != 8 * int(loop["self_play"]["games"]):
        raise ValueError("M16-P G1_WIDE dose differs from the selected source")
    schedule = config["training_schedule"]
    if (
        int(schedule["total_steps"]) != int(loop["training"]["steps"])
        or int(schedule["batch_size"]) != int(loop["training"]["batch_size"])
        or int(schedule.get("seed_offset", 0)) != 990000
        or schedule.get("explicit_identical_batch_schedule_all_arms") is not True
    ):
        raise ValueError("M16-P training schedule changed")
    arena = config["descriptive_strength_arena"]
    if (
        int(arena.get("pairs", 0)) != 128
        or int(arena.get("seed_base", 0)) != 981000
        or float(arena.get("epsilon", -1.0)) != 0.0
        or arena.get("confidence_unit") != "pairs"
        or arena.get("start_state_source") != "development"
    ):
        raise ValueError("M16-P descriptive arena changed")
    return deepcopy(config), loop


def build_target_arms(
    samples: list[ReplaySample],
    search_trace: list[dict[str, Any]],
    exact_values: np.ndarray,
    train_mask: np.ndarray,
) -> tuple[dict[str, list[ReplaySample]], dict[str, Any]]:
    """Build all returns on full games, then retain only train-cohort rows."""

    if not samples:
        raise ValueError("M16-P requires generated replay rows")
    trace_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for row in search_trace:
        key = (int(row["game_id"]), int(row["ply"]))
        if key in trace_by_key:
            raise ValueError(f"M16-P duplicate search trace row {key}")
        trace_by_key[key] = row

    game_indices: dict[int, list[int]] = {}
    for index, sample in enumerate(samples):
        game_indices.setdefault(int(sample.game_id), []).append(index)

    outcomes = np.asarray([sample.value_target for sample in samples], dtype=np.float64)
    if not np.all(np.isin(outcomes, (-1.0, 0.0, 1.0))):
        raise ValueError("M16-P temporal inputs must be terminal WDL targets")
    temporal_values = {
        arm: outcomes.copy() for arm in CANDIDATE_ARMS
    }
    trace_payload: list[dict[str, Any]] = []
    clipped_count = 0
    bootstrap_count = 0
    for game_id, indices in game_indices.items():
        ordered = sorted(indices, key=lambda index: int(samples[index].ply))
        plies = [int(samples[index].ply) for index in ordered]
        if plies != list(range(plies[0], plies[0] + len(plies))):
            raise ValueError(
                f"M16-P requires contiguous per-ply samples for game {game_id}"
            )
        root_scores: list[float] = []
        for source_index in ordered:
            sample = samples[source_index]
            key = (game_id, int(sample.ply))
            if key not in trace_by_key:
                raise ValueError(f"M16-P missing root score for replay row {key}")
            trace = trace_by_key[key]
            if int(trace["state_id"]) != int(sample.state_id):
                raise ValueError(f"M16-P search trace identity mismatch for row {key}")
            raw = float(trace["root_score"])
            if not math.isfinite(raw):
                raise ValueError(f"M16-P non-finite root score for replay row {key}")
            clipped = float(np.clip(raw, -1.0, 1.0))
            clipped_count += int(clipped != raw)
            root_scores.append(clipped)
            trace_payload.append(
                {
                    "game_id": game_id,
                    "ply": int(sample.ply),
                    "state_id": int(sample.state_id),
                    "root_score": clipped,
                    "search_best_action": int(trace["selected_action"]),
                    "behavior_action": (
                        -1
                        if sample.selected_action is None
                        else int(sample.selected_action)
                    ),
                }
            )

        for arm, lambda_value in TEMPORAL_LAMBDAS.items():
            returns = np.empty(len(ordered), dtype=np.float64)
            returns[-1] = float(samples[ordered[-1]].value_target)
            for local_index in range(len(ordered) - 2, -1, -1):
                returns[local_index] = -(
                    (1.0 - lambda_value) * root_scores[local_index + 1]
                    + lambda_value * returns[local_index + 1]
                )
            temporal_values[arm][np.asarray(ordered, dtype=np.int64)] = returns
        bootstrap_count += max(0, len(ordered) - 1)

    if len(trace_by_key) != len(samples) or len(trace_payload) != len(samples):
        raise ValueError("M16-P search trace and replay row counts diverged")

    selected = np.asarray(
        [bool(train_mask[int(sample.state_id)]) for sample in samples],
        dtype=np.bool_,
    )
    selected_indices = np.flatnonzero(selected)
    if selected_indices.size == 0:
        raise RuntimeError("M16-P generated no train-cohort replay rows")
    selected_samples = [samples[int(index)] for index in selected_indices]
    selected_outcomes = outcomes[selected]
    state_ids = np.asarray(
        [sample.state_id for sample in selected_samples], dtype=np.int64
    )
    exact = np.asarray(exact_values)[state_ids].astype(np.float64)
    target_values: dict[str, np.ndarray] = {
        "OUTCOME": selected_outcomes,
        "NEXT_SEARCH": temporal_values["NEXT_SEARCH"][selected],
        "LAMBDA_50": temporal_values["LAMBDA_50"][selected],
        "LAMBDA_80": temporal_values["LAMBDA_80"][selected],
        "EXACT_ORACLE": exact,
    }
    arms = {
        arm: [
            replace(sample, value_target=float(value))
            for sample, value in zip(
                selected_samples, target_values[arm], strict=True
            )
        ]
        for arm in ARM_ORDER
    }
    structures = {arm: _sample_structure_fingerprint(rows) for arm, rows in arms.items()}
    if len(set(structures.values())) != 1:
        raise RuntimeError("M16-P target arms changed replay structure")
    target_metrics = {
        arm: {
            "sample_count": len(selected_samples),
            "value_mae_vs_exact_train": float(
                np.mean(np.abs(target_values[arm] - exact))
            ),
            "value_exact_rate_vs_exact_train": float(
                np.mean(target_values[arm] == exact)
            ),
            "changed_from_outcome_fraction": float(
                np.mean(target_values[arm] != selected_outcomes)
            ),
            "target_mean": float(target_values[arm].mean()),
            "target_standard_deviation": float(
                target_values[arm].std(ddof=0)
            ),
        }
        for arm in ARM_ORDER
    }
    return arms, {
        "raw_generated_sample_count": len(samples),
        "train_sample_count": len(selected_samples),
        "full_game_count": len(game_indices),
        "temporal_bootstrap_row_count": bootstrap_count,
        "temporal_returns_built_before_train_row_filter": True,
        "search_trace_hash": digest(trace_payload),
        "search_trace_rows_consumed": len(trace_payload),
        "search_root_scores_clipped": clipped_count,
        "shared_structure_fingerprint": next(iter(structures.values())),
        "structure_fingerprints": structures,
        "targets": target_metrics,
    }


def _interval(values: list[float], critical: float) -> dict[str, Any]:
    result = paired_interval(values, critical)
    result["standard_deviation"] = float(
        result["standard_error"] * math.sqrt(result["count"])
    )
    result["positive_seed_count"] = sum(value > 0.0 for value in values)
    result["zero_seed_count"] = sum(value == 0.0 for value in values)
    result["negative_seed_count"] = sum(value < 0.0 for value in values)
    return result


def build_contrasts(rows: list[dict[str, Any]], critical: float) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, (high, low) in CONTRASTS.items():
        result: dict[str, Any] = {"high": high, "low": low}
        for endpoint in ENDPOINTS:
            result[endpoint] = _interval(
                [
                    float(row["arms"][high][endpoint])
                    - float(row["arms"][low][endpoint])
                    for row in rows
                ],
                critical,
            )
        output[name] = result
    return output


def build_recommendation(
    contrasts: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    primary = contrasts["primary_lambda_50"]["zero_regret_gain"]
    oracle = contrasts["oracle_gap"]["zero_regret_gain"]
    fixed_minimum = float(gate["minimum_absolute_response_gain"])
    recovery_minimum = (
        float(gate["minimum_oracle_gain_recovery_fraction"])
        * float(oracle["mean"])
    )
    required = max(fixed_minimum, recovery_minimum)
    recovery = (
        float(primary["mean"]) / float(oracle["mean"])
        if float(oracle["mean"]) > 0.0
        else None
    )
    common = {
        "primary_contrast": "LAMBDA_50_minus_OUTCOME",
        "primary_endpoint": "development_zero_regret_gain",
        "primary_mean": float(primary["mean"]),
        "primary_ci95": [float(primary["lower"]), float(primary["upper"])],
        "oracle_gap_mean": float(oracle["mean"]),
        "oracle_gap_ci95": [float(oracle["lower"]), float(oracle["upper"])],
        "oracle_gain_recovery_fraction": recovery,
        "required_primary_mean": required,
        "exploratory_arms_can_rescue_primary": False,
        "promotable": False,
    }
    if float(oracle["upper"]) <= 0.0:
        return {
            **common,
            "status": "FAIL",
            "finding": "pattern_oracle_gap_did_not_replicate",
            "decision": "close_M16P_temporal_target_axis",
        }
    if float(oracle["lower"]) <= 0.0:
        return {
            **common,
            "status": "INCONCLUSIVE",
            "finding": "pattern_oracle_gap_is_not_precise",
            "decision": "replicate_M16P_oracle_gap_before_interpretation",
        }
    if float(primary["lower"]) > 0.0 and float(primary["mean"]) >= required:
        return {
            **common,
            "status": "PASS",
            "finding": "lambda_50_recovers_practical_pattern_oracle_fraction",
            "decision": "replicate_LAMBDA_50_strength_on_fresh_seeds",
        }
    if float(primary["upper"]) <= 0.0 or float(primary["upper"]) < required:
        return {
            **common,
            "status": "FAIL",
            "finding": "lambda_50_excludes_practical_temporal_recovery",
            "decision": "close_M16P_temporal_target_axis",
        }
    return {
        **common,
        "status": "INCONCLUSIVE",
        "finding": "lambda_50_temporal_recovery_is_not_precise",
        "decision": "power_size_fresh_M16P_replication",
    }


def _write_json_roundtrip(payload: dict[str, Any], paths: list[Path]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
        replayed = json.loads(path.read_text(encoding="utf-8"))
        if replayed.get("result_hash") != payload.get("result_hash"):
            raise RuntimeError(f"M16-P reporting round-trip failed: {path}")


def _write_outputs(result: dict[str, Any], run_dir: Path, compact_output: Path) -> None:
    _write_json_roundtrip(result, [run_dir / "result.json", compact_output])
    for path in (run_dir / "result.json", compact_output):
        replayed = json.loads(path.read_text(encoding="utf-8"))
        if (
            replayed.get("schema") != SCHEMA
            or replayed.get("milestone") != "M16-P"
            or replayed.get("recommendation", {}).get("finding")
            != result.get("recommendation", {}).get("finding")
        ):
            raise RuntimeError(f"M16-P scientific report changed on read: {path}")


def _write_progress(
    path: Path | None, completed: int, total: int, last_seed: int, started: float
) -> None:
    if path is None:
        return
    elapsed = max(time.monotonic() - started, 1.0e-9)
    rate = completed / (elapsed / 60.0)
    payload = {
        "schema": "mini_jass.pattern_temporal_value_target_screen_progress.v1",
        "milestone": "M16-P",
        "completed_seeds": completed,
        "total_seeds": total,
        "last_completed_seed": last_seed,
        "elapsed_seconds": elapsed,
        "seeds_per_minute": rate,
        "eta_remaining_seconds": (total - completed) / rate * 60.0 if rate > 0 else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_m16p(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
    progress_output: Path | None = None,
    probe_only: bool = False,
) -> dict[str, Any]:
    config, base_loop = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M16-P requires User, got {host}")
    seeds = (
        [int(config["probe"]["seed"])]
        if probe_only
        else [int(seed) for seed in config["paired_seeds"]]
    )
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M16-P split differs from the frozen L1 contract")
    train = split.indices("train")
    development = split.indices("development")
    train_mask = np.zeros(graph.state_count, dtype=np.bool_)
    train_mask[train] = True
    train_starts = np.asarray(
        [state for state in train if graph.terminal_value(int(state)) is None],
        dtype=np.int64,
    )
    tensors = solved_tensors(oracle, graph)
    response_batch = int(base_loop["development"]["batch_size"])

    schedule_config = config["training_schedule"]
    steps = int(schedule_config["total_steps"])
    batch_size = int(schedule_config["batch_size"])
    schedule_offset = int(schedule_config["seed_offset"])
    arena_spec = config["descriptive_strength_arena"]
    arena_config = ArenaConfig(
        pairs=int(arena_spec["pairs"]),
        max_plies=int(base_loop["arena"]["max_plies"]),
        search_depth=int(base_loop["arena"]["search_depth"]),
        node_budget=int(base_loop["arena"]["node_budget"]),
        epsilon=float(arena_spec["epsilon"]),
        confidence_z=float(arena_spec["confidence_z"]),
        confidence_unit=str(arena_spec["confidence_unit"]),
        start_state_source="provided",
    )

    rows: list[dict[str, Any]] = []
    timings: list[dict[str, Any]] = []
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    for seed in seeds:
        seed_started = time.monotonic()
        fit_seed = seed + schedule_offset
        seed_everything(fit_seed, int(base_loop["runtime"]["threads"]))
        initial = build_model(base_loop["model"])
        assert_pattern_value_model(initial)
        initial_hash = _model_state_hash(initial)
        before = response_metrics(
            initial, graph, tensors, oracle, development, response_batch
        )

        generation_started = time.monotonic()
        wide_config = deepcopy(base_loop["self_play"])
        wide_config["games"] = int(config["replay"]["games_per_seed"])
        wide_config["game_schedule"] = None
        generated = generate_self_play(
            graph,
            initial,
            loop_module._parse_self_play(wide_config),
            int(config["replay"]["generation"]),
            seed + int(config["replay"]["seed_offset"]),
            train_starts,
        )
        generation_seconds = time.monotonic() - generation_started
        arms, replay_contract = build_target_arms(
            generated.samples,
            generated.metrics["search_trace"],
            oracle.values,
            train_mask,
        )
        schedule = _random_schedule(
            len(arms["OUTCOME"]), steps, batch_size, fit_seed + 15
        )

        training_started = time.monotonic()
        models: dict[str, Any] = {}
        arm_rows: dict[str, Any] = {}
        for arm in ARM_ORDER:
            model, training, arm_initial_hash = _fit(
                base_loop, graph, arms[arm], schedule, fit_seed
            )
            if arm_initial_hash != initial_hash:
                raise RuntimeError("M16-P arms did not share the initial PatternEval")
            after = response_metrics(
                model, graph, tensors, oracle, development, response_batch
            )
            models[arm] = model
            arm_rows[arm] = {
                "after": after,
                "zero_regret_gain": float(after["zero_regret_rate"])
                - float(before["zero_regret_rate"]),
                "value_sign_gain": float(after["value_sign_accuracy"])
                - float(before["value_sign_accuracy"]),
                "value_mae": float(after["value_mae"]),
                "mean_selected_regret": float(after["mean_selected_regret"]),
                "training": training,
                "target": replay_contract["targets"][arm],
                "replay_fingerprint": replay_fingerprint(arms[arm]),
                "replay_structure_fingerprint": replay_contract[
                    "shared_structure_fingerprint"
                ],
                "initial_model_hash": arm_initial_hash,
                "trained_model_hash": _model_state_hash(model),
                "oracle_training_signal": arm == "EXACT_ORACLE",
                "promotable": False,
            }
        training_seconds = time.monotonic() - training_started

        arena_started = time.monotonic()
        arena_seed = int(arena_spec["seed_base"]) + seed
        arena_start_hash: str | None = None
        outcome_model = models["OUTCOME"]
        for arm in ARM_ORDER:
            arena = run_arena(
                graph,
                models[arm],
                outcome_model,
                arena_config,
                arena_seed,
                development,
            )
            start_hash = digest(arena["start_state_ids"])
            if arena_start_hash is None:
                arena_start_hash = start_hash
            elif start_hash != arena_start_hash:
                raise RuntimeError("M16-P arena starts diverged across arms")
            arm_rows[arm]["arena_score_minus_half"] = float(arena["score"]) - 0.5
            arm_rows[arm]["arena_vs_outcome"] = arena
        if arm_rows["OUTCOME"]["arena_score_minus_half"] != 0.0:
            raise RuntimeError("M16-P symmetric OUTCOME arena did not score 0.5")
        arena_seconds = time.monotonic() - arena_started

        row = {
            "seed": seed,
            "initial": before,
            "replay": {
                "source": config["replay"]["source"],
                "raw_replay_fingerprint": replay_fingerprint(generated.samples),
                "outcome_replay_fingerprint": replay_fingerprint(arms["OUTCOME"]),
                "shared_batch_schedule_hash": hashlib.sha256(
                    schedule.tobytes(order="C")
                ).hexdigest(),
                "shared_initial_model_hash": initial_hash,
                "shared_arena_start_hash": arena_start_hash,
                "all_rows_train_only": all(
                    bool(train_mask[int(sample.state_id)])
                    for sample in arms["OUTCOME"]
                ),
                **replay_contract,
            },
            "arms": arm_rows,
        }
        rows.append(row)
        timing = {
            "seed": seed,
            "generation_seconds": generation_seconds,
            "training_and_response_seconds": training_seconds,
            "arena_seconds": arena_seconds,
            "total_seconds": time.monotonic() - seed_started,
        }
        timings.append(timing)
        if not probe_only:
            (run_dir / f"seed-{seed}.json").write_text(
                json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            _write_progress(progress_output, len(rows), len(seeds), seed, started)

    if probe_only:
        probe_result: dict[str, Any] = {
            "schema": PROBE_SCHEMA,
            "milestone": "M16-P-PROBE",
            "status": "PROBE_ONLY",
            "seed": seeds[0],
            "execution_host": host,
            "timing": timings[0],
            "workload": {
                "selfplay_games": int(config["replay"]["games_per_seed"]),
                "arm_count": len(ARM_ORDER),
                "training_steps": len(ARM_ORDER) * steps,
                "arena_pairs": len(ARM_ORDER) * int(arena_spec["pairs"]),
                "arena_games": 2 * len(ARM_ORDER) * int(arena_spec["pairs"]),
                "train_sample_count": int(rows[0]["replay"]["train_sample_count"]),
            },
            "scientific_metrics_published": False,
            "scientific_seed_overlap": False,
            "additional_frozen_test_reads": 0,
            "promotable": False,
        }
        probe_result["result_hash"] = digest(probe_result)
        _write_json_roundtrip(
            probe_result, [run_dir / "probe.json", compact_output]
        )
        return probe_result

    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    contrasts = build_contrasts(rows, critical)
    aggregate = {
        "paired_seed_count": len(rows),
        "arms": {
            arm: {
                "mean_zero_regret_gain": mean(
                    row["arms"][arm]["zero_regret_gain"] for row in rows
                ),
                "mean_value_sign_gain": mean(
                    row["arms"][arm]["value_sign_gain"] for row in rows
                ),
                "mean_value_mae": mean(
                    row["arms"][arm]["value_mae"] for row in rows
                ),
                "mean_arena_score_minus_half": mean(
                    row["arms"][arm]["arena_score_minus_half"] for row in rows
                ),
                "mean_target_mae_vs_exact_train": mean(
                    row["arms"][arm]["target"]["value_mae_vs_exact_train"]
                    for row in rows
                ),
            }
            for arm in ARM_ORDER
        },
        "contrasts": contrasts,
        "mean_train_sample_count": mean(
            row["replay"]["train_sample_count"] for row in rows
        ),
        "mean_seed_total_seconds": mean(row["total_seconds"] for row in timings),
        "all_training_rows_train_only": all(
            bool(row["replay"]["all_rows_train_only"]) for row in rows
        ),
        "all_temporal_returns_built_before_train_filter": all(
            bool(row["replay"]["temporal_returns_built_before_train_row_filter"])
            for row in rows
        ),
        "all_batch_schedules_paired_within_seed": True,
        "all_initial_models_paired_within_seed": True,
        "all_arena_starts_paired_within_seed": True,
        "additional_frozen_test_reads": 0,
    }
    recommendation = build_recommendation(contrasts, config["scientific_gate"])
    protocol = {
        "schema": SCHEMA,
        "milestone": "M16-P",
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": seeds,
        "arms": list(ARM_ORDER),
        "replay": config["replay"],
        "targets": config["targets"],
        "temporal_contract": config["temporal_contract"],
        "training_schedule": config["training_schedule"],
        "descriptive_strength_arena": config["descriptive_strength_arena"],
        "power_sizing": {
            **config["power_sizing"],
            "recomputed_power": estimate_power(config["power_sizing"]),
        },
        "scientific_gate": config["scientific_gate"],
        "source_evidence": config["source_evidence"],
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": "M16-P",
        "status": recommendation["status"],
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
        "timings": timings,
        "recommendation": recommendation,
        "sealed_cohort_contract": {
            "cohorts_read": ["train", "development"],
            "cohorts_not_read": ["frozen_test"],
            "existing_frozen_test_read_count": 1,
            "additional_frozen_test_reads": 0,
            "oracle_training_signal_isolated_to": ["EXACT_ORACLE"],
        },
        "promotable": False,
    }
    result["result_hash"] = digest(
        {key: value for key, value in result.items() if key != "result_hash"}
    )
    _write_outputs(result, run_dir, compact_output)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--oracle", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--compact-output", type=Path, required=True)
    parser.add_argument("--execution-host")
    parser.add_argument("--progress-output", type=Path)
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    result = run_m16p(
        args.config,
        args.oracle,
        args.run_dir,
        args.compact_output,
        args.execution_host,
        args.progress_output,
        args.probe_only,
    )
    print(json.dumps({"status": result["status"], "result_hash": result["result_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
