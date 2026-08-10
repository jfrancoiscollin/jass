#!/usr/bin/env python3
"""M15-P: screen deployable value targets on scalar PatternEval.

One oracle-blind ``G1_WIDE_OUTCOME`` replay is generated per paired seed from
the shared initial PatternEval.  Every arm consumes the same rows, ordering,
batch schedule and initialization; only ``ReplaySample.value_target`` changes.
The exact arm is a train-only diagnostic upper bound and is never promotable.
"""

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
from typing import Any, Iterable

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
from mini_jass_lab.selfplay_train import train_from_replay  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402

SCHEMA = "mini_jass.pattern_value_target_screen.v1"
ARM_ORDER = ("OUTCOME", "SEARCH_ROOT", "BLEND_50", "EXACT_ORACLE")
CONTRASTS = {
    "primary_blend": ("BLEND_50", "OUTCOME"),
    "mechanistic_search": ("SEARCH_ROOT", "OUTCOME"),
    "oracle_gap": ("EXACT_ORACLE", "OUTCOME"),
}
ENDPOINTS = (
    "zero_regret_gain",
    "value_sign_gain",
    "value_mae",
    "mean_selected_regret",
    "arena_score_minus_half",
)

EXPECTED_M14_RESULT = "80b3240be0fbaa20506d60d65f26619cfe188b11f5a1fd56273de1e19f1d8380"
EXPECTED_M21_RESULT = "2a376c7215212777e466fe41c7bf30a1af1d700f706ee7ca882c0fe2b3ac2745"
EXPECTED_M21_FREEZE = "db870aec453cf8876191b1624edd13045be50cf589aca33184d6175f67bae86c"


def estimate_power(config: dict[str, Any]) -> float:
    repetitions = int(config["repetitions"])
    count = int(config["paired_seed_count"])
    rng = np.random.default_rng(int(config["seed"]))
    draws = rng.normal(
        float(config["minimum_effect"]),
        float(config["conservative_paired_sd"]),
        size=(repetitions, count),
    )
    centers = draws.mean(axis=1)
    errors = draws.std(axis=1, ddof=1) / math.sqrt(count)
    critical = float(config["paired_confidence_critical_95"])
    return float(np.mean(centers - critical * errors > 0.0))


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M15-P":
        raise ValueError("unexpected M15-P schema")
    if tuple(config.get("arms", [])) != ARM_ORDER:
        raise ValueError("M15-P arms changed after preregistration")
    seeds = [int(seed) for seed in config.get("paired_seeds", [])]
    if seeds != list(range(271001, 271021)):
        raise ValueError("M15-P paired seeds changed or overlap prior evidence")

    source = config.get("source_evidence", {})
    if (
        source.get("m14p", {}).get("result_hash") != EXPECTED_M14_RESULT
        or source.get("m21p", {}).get("result_hash") != EXPECTED_M21_RESULT
        or source.get("m21p", {}).get("freeze_report_hash") != EXPECTED_M21_FREEZE
        or source.get("m21p", {}).get("status") != "FAIL"
        or source.get("m21p", {}).get("selected_replay_source")
        != "G1_WIDE_OUTCOME"
    ):
        raise ValueError("M15-P source evidence is not frozen")

    replay = config.get("replay", {})
    if (
        replay.get("source") != "G1_WIDE_OUTCOME"
        or int(replay.get("games_per_seed", 0)) != 1024
        or replay.get("row_selection") != "all_generated_train_rows"
        or replay.get("immutable_structure_across_arms") is not True
    ):
        raise ValueError("M15-P replay contract changed")

    targets = config.get("targets", {})
    if tuple(targets) != ARM_ORDER:
        raise ValueError("M15-P target order changed")
    if (
        targets["OUTCOME"].get("source") != "terminal_selfplay_wdl"
        or targets["SEARCH_ROOT"].get("source")
        != "bounded_negamax_root_score"
        or targets["SEARCH_ROOT"].get("clip") != [-1.0, 1.0]
        or targets["BLEND_50"].get("source") != "outcome_search_blend"
        or float(targets["BLEND_50"].get("search_weight", -1.0)) != 0.5
        or targets["EXACT_ORACLE"].get("source") != "exact_train_value"
        or targets["EXACT_ORACLE"].get("diagnostic_only") is not True
        or targets["EXACT_ORACLE"].get("promotable") is not False
    ):
        raise ValueError("M15-P target definitions changed")
    if any(
        targets[arm].get("oracle_training_signal") is not False
        for arm in ("OUTCOME", "SEARCH_ROOT", "BLEND_50")
    ) or targets["EXACT_ORACLE"].get("oracle_training_signal") is not True:
        raise ValueError("M15-P oracle boundary changed")

    gate = config.get("scientific_gate", {})
    m14_mean = float(source["m14p"]["zero_regret_exact_minus_outcome_mean"])
    if (
        gate.get("primary_contrast") != "BLEND_50_minus_OUTCOME"
        or gate.get("primary_endpoint") != "development_zero_regret_gain"
        or float(gate.get("minimum_oracle_gain_recovery_fraction", -1.0)) != 0.5
        or not math.isclose(
            float(gate.get("minimum_absolute_response_gain", -1.0)),
            0.5 * m14_mean,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        or gate.get("oracle_gap_must_replicate_with_ci_above_zero") is not True
        or gate.get("SEARCH_ROOT_is_mechanistic_only") is not True
        or gate.get("exploratory_arm_cannot_rescue_primary") is not True
    ):
        raise ValueError("M15-P scientific gate changed")

    power = config.get("power_sizing", {})
    if (
        int(power.get("paired_seed_count", 0)) != len(seeds)
        or float(power.get("minimum_effect", -1.0))
        != float(gate["minimum_absolute_response_gain"])
    ):
        raise ValueError("M15-P power input differs from the decision gate")
    observed_power = estimate_power(power)
    if not math.isclose(
        observed_power,
        float(power.get("estimated_power_ci_above_zero", -1.0)),
        rel_tol=0.0,
        abs_tol=5.0e-6,
    ):
        raise ValueError("M15-P frozen power result did not reproduce")
    if observed_power < float(power.get("minimum_required_power", 1.0)):
        raise ValueError("M15-P is underpowered before training")

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
        raise ValueError("M15-P crossed a scientific boundary")

    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M15-P requires the frozen PatternEval loop")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M15-P requires folded PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M15-P cannot train a policy head")
    if int(replay["games_per_seed"]) != 8 * int(loop["self_play"]["games"]):
        raise ValueError("M15-P G1_WIDE dose differs from M21-P")
    schedule = config["training_schedule"]
    if (
        int(schedule["total_steps"]) != int(loop["training"]["steps"])
        or int(schedule["batch_size"]) != int(loop["training"]["batch_size"])
        or schedule.get("explicit_identical_batch_schedule_all_arms") is not True
    ):
        raise ValueError("M15-P training schedule changed")
    arena = config["descriptive_strength_arena"]
    if (
        int(arena["pairs"]) != 128
        or float(arena["epsilon"]) != 0.0
        or arena["confidence_unit"] != "pairs"
        or arena["start_state_source"] != "development"
    ):
        raise ValueError("M15-P descriptive strength arena changed")
    return deepcopy(config), loop


def _sample_structure_fingerprint(samples: Iterable[ReplaySample]) -> str:
    hasher = hashlib.sha256()
    for sample in samples:
        selected = -1 if sample.selected_action is None else int(sample.selected_action)
        hasher.update(
            (
                f"{sample.state_id}|{sample.generation}|{sample.game_id}|"
                f"{sample.ply}|{selected}|"
            ).encode("ascii")
        )
        policy = np.asarray(sample.policy_target, dtype=np.float32)
        hasher.update(policy.shape[0].to_bytes(4, "little", signed=False))
        hasher.update(policy.tobytes(order="C"))
        hasher.update(b"\n")
    return hasher.hexdigest()


def build_target_arms(
    samples: list[ReplaySample],
    search_trace: list[dict[str, Any]],
    exact_values: np.ndarray,
) -> tuple[dict[str, list[ReplaySample]], dict[str, Any]]:
    trace_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    for row in search_trace:
        key = (int(row["game_id"]), int(row["ply"]))
        if key in trace_by_key:
            raise ValueError(f"M15-P duplicate search trace row {key}")
        trace_by_key[key] = row

    arms: dict[str, list[ReplaySample]] = {arm: [] for arm in ARM_ORDER}
    trace_payload: list[dict[str, Any]] = []
    clipped = 0
    for sample in samples:
        key = (int(sample.game_id), int(sample.ply))
        if key not in trace_by_key:
            raise ValueError(f"M15-P missing root score for replay row {key}")
        trace = trace_by_key[key]
        if int(trace["state_id"]) != int(sample.state_id):
            raise ValueError(f"M15-P search trace identity mismatch for row {key}")
        raw_search = float(trace["root_score"])
        if not math.isfinite(raw_search):
            raise ValueError(f"M15-P non-finite root score for replay row {key}")
        search = float(np.clip(raw_search, -1.0, 1.0))
        clipped += int(search != raw_search)
        outcome = float(sample.value_target)
        exact = float(exact_values[int(sample.state_id)])
        values = {
            "OUTCOME": outcome,
            "SEARCH_ROOT": search,
            "BLEND_50": 0.5 * outcome + 0.5 * search,
            "EXACT_ORACLE": exact,
        }
        for arm, value in values.items():
            arms[arm].append(replace(sample, value_target=float(value)))
        trace_payload.append(
            {
                "game_id": key[0],
                "ply": key[1],
                "state_id": int(sample.state_id),
                "search_best_action": int(trace["selected_action"]),
                "behavior_action": int(sample.selected_action),
                "root_score": search,
            }
        )

    structures = {arm: _sample_structure_fingerprint(rows) for arm, rows in arms.items()}
    if len(set(structures.values())) != 1:
        raise RuntimeError("M15-P target arms changed replay structure")
    state_ids = np.asarray([sample.state_id for sample in samples], dtype=np.int64)
    exact = exact_values[state_ids].astype(np.float64)
    outcome = np.asarray([sample.value_target for sample in samples], dtype=np.float64)
    target_metrics: dict[str, Any] = {}
    for arm, rows in arms.items():
        values = np.asarray([sample.value_target for sample in rows], dtype=np.float64)
        target_metrics[arm] = {
            "sample_count": len(rows),
            "value_mae_vs_exact_train": float(np.mean(np.abs(values - exact))),
            "value_exact_rate_vs_exact_train": float(np.mean(values == exact)),
            "changed_from_outcome_fraction": float(np.mean(values != outcome)),
            "target_mean": float(values.mean()),
            "target_standard_deviation": float(values.std(ddof=0)),
        }
    return arms, {
        "shared_structure_fingerprint": next(iter(structures.values())),
        "structure_fingerprints": structures,
        "search_trace_hash": digest(trace_payload),
        "search_trace_rows_consumed": len(trace_payload),
        "search_root_scores_clipped": clipped,
        "targets": target_metrics,
    }


def _random_schedule(
    pool_size: int, steps: int, batch_size: int, seed: int
) -> np.ndarray:
    return np.random.default_rng(seed).integers(
        0, pool_size, size=(steps, batch_size), dtype=np.int64
    )


def _model_state_hash(model: Any) -> str:
    hasher = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        hasher.update(name.encode("utf-8"))
        hasher.update(tensor.detach().cpu().numpy().tobytes(order="C"))
    return hasher.hexdigest()


def _fit(
    loop: dict[str, Any],
    graph: GameGraph,
    samples: list[ReplaySample],
    schedule: np.ndarray,
    seed: int,
) -> tuple[Any, dict[str, Any], str]:
    seed_everything(seed, int(loop["runtime"]["threads"]))
    model = build_model(loop["model"])
    assert_pattern_value_model(model)
    initial_hash = _model_state_hash(model)
    training = loop["training"]
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
        seed=seed,
        batch_indices=schedule,
    )
    return model, metrics, initial_hash


def build_contrasts(rows: list[dict[str, Any]], critical: float) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, (high, low) in CONTRASTS.items():
        result: dict[str, Any] = {"high": high, "low": low}
        for endpoint in ENDPOINTS:
            values = [
                float(row["arms"][high][endpoint])
                - float(row["arms"][low][endpoint])
                for row in rows
            ]
            interval = paired_interval(values, critical)
            interval["standard_deviation"] = float(
                interval["standard_error"] * math.sqrt(interval["count"])
            )
            interval["positive_seed_count"] = sum(value > 0.0 for value in values)
            interval["zero_seed_count"] = sum(value == 0.0 for value in values)
            interval["negative_seed_count"] = sum(value < 0.0 for value in values)
            result[endpoint] = interval
        output[name] = result
    return output


def build_recommendation(
    contrasts: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    primary = contrasts["primary_blend"]["zero_regret_gain"]
    oracle = contrasts["oracle_gap"]["zero_regret_gain"]
    absolute = float(gate["minimum_absolute_response_gain"])
    recovery = float(gate["minimum_oracle_gain_recovery_fraction"])
    required = max(absolute, recovery * float(oracle["mean"]))
    common = {
        "primary_contrast": "BLEND_50_minus_OUTCOME",
        "primary_endpoint": "development_zero_regret_gain",
        "primary_mean": float(primary["mean"]),
        "primary_ci95": [float(primary["lower"]), float(primary["upper"])],
        "oracle_gap_mean": float(oracle["mean"]),
        "oracle_gap_ci95": [float(oracle["lower"]), float(oracle["upper"])],
        "minimum_oracle_gain_recovery_fraction": recovery,
        "minimum_absolute_response_gain": absolute,
        "required_primary_mean": required,
        "search_root_arm_can_rescue_primary": False,
        "promotable": False,
    }
    if float(oracle["lower"]) <= 0.0:
        if float(oracle["upper"]) < absolute:
            return {
                **common,
                "status": "FAIL",
                "finding": "selected_replay_has_no_practical_oracle_target_gap",
                "deployable_target_signal": False,
                "decision": "close_M15P_and_do_not_launch_M16P",
            }
        return {
            **common,
            "status": "INCONCLUSIVE",
            "finding": "oracle_target_gap_did_not_replicate_precisely_on_selected_replay",
            "deployable_target_signal": None,
            "decision": "replicate_or_power_size_before_M16P",
        }
    if float(primary["lower"]) > 0.0 and float(primary["mean"]) >= required:
        return {
            **common,
            "status": "PASS",
            "finding": "blend_recovers_preregistered_fraction_of_pattern_oracle_gap",
            "deployable_target_signal": True,
            "decision": "replicate_BLEND_50_strength_on_fresh_seeds",
        }
    if float(primary["upper"]) < required:
        return {
            **common,
            "status": "FAIL",
            "finding": "blend_does_not_recover_practical_fraction_of_pattern_oracle_gap",
            "deployable_target_signal": False,
            "decision": "prepare_M16P_temporal_targets",
        }
    return {
        **common,
        "status": "INCONCLUSIVE",
        "finding": "blend_recovery_effect_underpowered_at_practical_threshold",
        "deployable_target_signal": None,
        "decision": "replicate_M15P_with_power_sized_fresh_seeds",
    }


def _write_outputs(result: dict[str, Any], run_dir: Path, compact_output: Path) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(payload, encoding="utf-8")
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(payload, encoding="utf-8")
    for path in (run_dir / "result.json", compact_output):
        replayed = json.loads(path.read_text(encoding="utf-8"))
        if (
            replayed.get("schema") != SCHEMA
            or replayed.get("milestone") != "M15-P"
            or replayed.get("result_hash") != result.get("result_hash")
            or replayed.get("recommendation", {}).get("finding")
            != result.get("recommendation", {}).get("finding")
        ):
            raise RuntimeError(f"M15-P reporting round-trip failed: {path}")


def _write_progress(
    path: Path | None,
    completed: int,
    total: int,
    last_seed: int,
    started: float,
) -> None:
    if path is None:
        return
    elapsed = max(time.monotonic() - started, 1.0e-9)
    rate = completed / (elapsed / 60.0)
    payload = {
        "schema": "mini_jass.pattern_value_target_screen_progress.v1",
        "milestone": "M15-P",
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


def run_m15p(
    config_path: Path,
    oracle_path: Path,
    run_dir: Path,
    compact_output: Path,
    execution_host: str | None = None,
    progress_output: Path | None = None,
) -> dict[str, Any]:
    config, base_loop = _resolve(config_path)
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"M15-P requires cpx62, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M15-P split differs from the frozen L1 contract")
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
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    for raw_seed in config["paired_seeds"]:
        seed = int(raw_seed)
        fit_seed = seed + schedule_offset
        seed_everything(fit_seed, int(base_loop["runtime"]["threads"]))
        initial = build_model(base_loop["model"])
        assert_pattern_value_model(initial)
        initial_hash = _model_state_hash(initial)
        before = response_metrics(
            initial, graph, tensors, oracle, development, response_batch
        )

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
        train_samples = [
            sample
            for sample in generated.samples
            if bool(train_mask[int(sample.state_id)])
        ]
        if not train_samples:
            raise RuntimeError("M15-P generated no train-cohort replay rows")
        if not all(bool(train_mask[int(sample.state_id)]) for sample in train_samples):
            raise RuntimeError("M15-P consumed a non-train replay row")
        arms, replay_contract = build_target_arms(
            train_samples,
            generated.metrics["search_trace"],
            oracle.values,
        )
        schedule = _random_schedule(
            len(train_samples), steps, batch_size, fit_seed + 15
        )

        models: dict[str, Any] = {}
        arm_rows: dict[str, Any] = {}
        for arm in ARM_ORDER:
            model, training, arm_initial_hash = _fit(
                base_loop, graph, arms[arm], schedule, fit_seed
            )
            if arm_initial_hash != initial_hash:
                raise RuntimeError("M15-P arms did not share the initial PatternEval")
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
                raise RuntimeError("M15-P arena starts diverged across arms")
            arm_rows[arm]["arena_score_minus_half"] = float(arena["score"]) - 0.5
            arm_rows[arm]["arena_vs_outcome"] = arena
        if arm_rows["OUTCOME"]["arena_score_minus_half"] != 0.0:
            raise RuntimeError("M15-P symmetric OUTCOME arena did not score 0.5")

        row = {
            "seed": seed,
            "initial": before,
            "replay": {
                "source": config["replay"]["source"],
                "raw_generated_sample_count": len(generated.samples),
                "train_sample_count": len(train_samples),
                "raw_replay_fingerprint": replay_fingerprint(generated.samples),
                "outcome_replay_fingerprint": replay_fingerprint(train_samples),
                "shared_batch_schedule_hash": hashlib.sha256(
                    schedule.tobytes(order="C")
                ).hexdigest(),
                "shared_initial_model_hash": initial_hash,
                "shared_arena_start_hash": arena_start_hash,
                "all_rows_train_only": True,
                **replay_contract,
            },
            "arms": arm_rows,
        }
        rows.append(row)
        (run_dir / f"seed-{seed}.json").write_text(
            json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write_progress(
            progress_output, len(rows), len(config["paired_seeds"]), seed, started
        )

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
        "all_training_rows_train_only": True,
        "all_batch_schedules_paired_within_seed": True,
        "all_initial_models_paired_within_seed": True,
        "all_arena_starts_paired_within_seed": True,
        "additional_frozen_test_reads": 0,
    }
    recommendation = build_recommendation(contrasts, config["scientific_gate"])
    protocol = {
        "schema": SCHEMA,
        "milestone": "M15-P",
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "arms": list(ARM_ORDER),
        "primary_contrast": config["scientific_gate"]["primary_contrast"],
        "primary_endpoint": config["scientific_gate"]["primary_endpoint"],
        "replay": config["replay"],
        "targets": config["targets"],
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
        "milestone": "M15-P",
        "status": recommendation["status"],
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
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
    args = parser.parse_args()
    result = run_m15p(
        args.config,
        args.oracle,
        args.run_dir,
        args.compact_output,
        args.execution_host,
        args.progress_output,
    )
    print(json.dumps({"status": result["status"], "result_hash": result["result_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
