#!/usr/bin/env python3
"""M15-C5: test whether CONTEXT_30 survives one on-policy feedback step.

G1 holds replay, initialisation, and optimiser batches fixed between OUTCOME and
CONTEXT_30.  Each G1 model then generates a paired G2 replay.  The primary G2
contrast follows each model on its own distribution.  A third arm continues the
G1 context model on the OUTCOME replay with the same conditional recipe, which
isolates the replay-distribution contribution without adding inference state.
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
from typing import Any

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

import numpy as np  # noqa: E402
import yaml  # noqa: E402

import mini_jass_lab.loop as loop_module  # noqa: E402
from mini_jass_lab.arena import ArenaConfig, run_arena  # noqa: E402
from mini_jass_lab.conditional_targets import cross_fitted_conditional_wdl  # noqa: E402
from mini_jass_lab.context import context_matrix  # noqa: E402
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
from run_pattern_value_target_screen import (  # noqa: E402
    _fit,
    _model_state_hash,
    _random_schedule,
    _sample_structure_fingerprint,
)

SCHEMA = "mini_jass.pattern_conditional_feedback.v1"
MILESTONE = "M15-C5"
ARMS = (
    "OUTCOME_G1",
    "CONTEXT_30_G1",
    "OUTCOME_G2",
    "CONTEXT_30_G2_OWN_REPLAY",
    "CONTEXT_30_G2_ON_OUTCOME_REPLAY",
)
ENDPOINTS = ("zero_regret_rate", "value_sign_accuracy")
CONTRASTS = {
    "g1_context_effect": ("CONTEXT_30_G1", "OUTCOME_G1"),
    "g2_on_policy_context_effect": ("CONTEXT_30_G2_OWN_REPLAY", "OUTCOME_G2"),
    "g2_feedback_distribution_effect": (
        "CONTEXT_30_G2_OWN_REPLAY",
        "CONTEXT_30_G2_ON_OUTCOME_REPLAY",
    ),
}


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != MILESTONE:
        raise ValueError("unexpected M15-C5 schema")
    if tuple(config.get("arms", [])) != ARMS:
        raise ValueError("M15-C5 arms changed after preregistration")
    seeds = [int(seed) for seed in config.get("paired_seeds", [])]
    if seeds != list(range(278001, 278025)):
        raise ValueError("M15-C5 seeds changed or overlap prior evidence")
    if config.get("expected_execution_host") != "User":
        raise ValueError("M15-C5 is reserved for HOME hostname User")
    feedback = config.get("feedback", {})
    if (
        int(feedback.get("generations", 0)) != 2
        or float(feedback.get("alpha", -1.0)) != 0.30
        or feedback.get("g1_shared_replay") is not True
        or feedback.get("g2_each_primary_arm_generates_own_replay") is not True
        or feedback.get("decomposition_starts_from_context_g1") is not True
        or feedback.get("extra_inference_parameters") != 0
    ):
        raise ValueError("M15-C5 feedback contract changed")
    mapping = config.get("conditional_mapping", {})
    if (
        mapping.get("family") != "odd_tanh_linear_wdl_oof_v1"
        or mapping.get("fold_unit") != "complete_game"
        or int(mapping.get("fold_count", 0)) != 5
        or mapping.get("training_label") != "terminal_selfplay_wdl"
        or mapping.get("oracle_training_signal") is not False
    ):
        raise ValueError("M15-C5 conditional mapping changed")
    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("cohorts_read") != ["train", "development"]
        or boundaries.get("cohorts_never_read_by_this_cell") != ["frozen_test"]
        or int(boundaries.get("additional_frozen_test_reads_authorized", -1)) != 0
        or boundaries.get("all_training_targets_oracle_blind") is not True
        or boundaries.get("automatic_selection_or_promotion") is not False
        or boundaries.get("promotable") is not False
        or boundaries.get("execution_is_not_queued_by_this_pr") is not True
    ):
        raise ValueError("M15-C5 crossed a scientific boundary")
    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    schedule = config.get("training_schedule", {})
    if (
        loop.get("schema") != "mini_jass.selfplay.v1"
        or loop["model"].get("architecture") != "folded_pattern_value"
        or float(loop["training"].get("policy_weight", -1.0)) != 0.0
        or int(schedule.get("steps_per_generation", 0)) != int(loop["training"]["steps"])
        or int(schedule.get("batch_size", 0)) != int(loop["training"]["batch_size"])
    ):
        raise ValueError("M15-C5 architecture or training schedule changed")
    arena = config.get("strength_arena", {})
    if (
        int(arena.get("pairs", 0)) != 512
        or float(arena.get("epsilon", -1.0)) != 0.0
        or arena.get("confidence_unit") != "pairs"
        or arena.get("start_state_source") != "development"
    ):
        raise ValueError("M15-C5 arena changed")
    return deepcopy(config), loop


def build_context_target(
    samples: list[ReplaySample], predictions: np.ndarray, alpha: float
) -> list[ReplaySample]:
    values = np.asarray(predictions, dtype=np.float64)
    if values.shape != (len(samples),) or not np.all(np.isfinite(values)):
        raise ValueError("M15-C5 conditional predictions must align and be finite")
    if np.any(np.abs(values) > 1.0) or not 0.0 < alpha < 1.0:
        raise ValueError("M15-C5 target inputs left their preregistered range")
    rows = [
        replace(
            sample,
            value_target=float((1.0 - alpha) * sample.value_target + alpha * prediction),
        )
        for sample, prediction in zip(samples, values, strict=True)
    ]
    if _sample_structure_fingerprint(rows) != _sample_structure_fingerprint(samples):
        raise RuntimeError("M15-C5 target rewrite changed replay structure")
    return rows


def _conditional_replay(
    oracle: Any,
    samples: list[ReplaySample],
    mapping: dict[str, Any],
    *,
    namespace: str,
    alpha: float,
) -> tuple[list[ReplaySample], dict[str, Any]]:
    contexts = context_matrix(oracle, [sample.state_id for sample in samples])
    outcomes = np.asarray([sample.value_target for sample in samples], dtype=np.float64)
    fit = cross_fitted_conditional_wdl(
        contexts,
        outcomes,
        samples,
        fold_count=int(mapping["fold_count"]),
        namespace=f"{mapping['fold_namespace']}|{namespace}",
        ridge=float(mapping["ridge"]),
        max_iterations=int(mapping["max_iterations"]),
        tolerance=float(mapping["tolerance"]),
        line_search_steps=int(mapping["line_search_steps"]),
    )
    rows = build_context_target(samples, fit["conditional_predictions"], alpha)
    report = {
        key: value
        for key, value in fit.items()
        if key not in {"fold_ids", "conditional_predictions", "state_blind_predictions"}
    }
    report["target_alpha"] = alpha
    report["target_fingerprint"] = replay_fingerprint(rows)
    report["outcome_structure_fingerprint"] = _sample_structure_fingerprint(samples)
    report["target_structure_fingerprint"] = _sample_structure_fingerprint(rows)
    return rows, report


def _continue_fit(
    parent: Any,
    graph: GameGraph,
    samples: list[ReplaySample],
    schedule: np.ndarray,
    loop: dict[str, Any],
    seed: int,
) -> tuple[Any, dict[str, Any], str]:
    seed_everything(seed, int(loop["runtime"]["threads"]))
    model = deepcopy(parent)
    assert_pattern_value_model(model)
    parent_hash = _model_state_hash(model)
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
    return model, metrics, parent_hash


def _filter_train(samples: tuple[ReplaySample, ...], train_mask: np.ndarray) -> list[ReplaySample]:
    rows = [sample for sample in samples if bool(train_mask[int(sample.state_id)])]
    if not rows:
        raise RuntimeError("M15-C5 generated no train replay rows")
    if not all(bool(train_mask[int(sample.state_id)]) for sample in rows):
        raise RuntimeError("M15-C5 consumed a non-train row")
    return rows


def _arena_config(base_loop: dict[str, Any], spec: dict[str, Any]) -> ArenaConfig:
    return ArenaConfig(
        pairs=int(spec["pairs"]),
        max_plies=int(base_loop["arena"]["max_plies"]),
        search_depth=int(base_loop["arena"]["search_depth"]),
        node_budget=int(base_loop["arena"]["node_budget"]),
        epsilon=float(spec["epsilon"]),
        confidence_z=float(spec["confidence_z"]),
        confidence_unit=str(spec["confidence_unit"]),
        start_state_source="provided",
    )


def _run_seed(
    seed: int,
    config: dict[str, Any],
    base_loop: dict[str, Any],
    oracle: Any,
    graph: GameGraph,
    train_mask: np.ndarray,
    train_starts: np.ndarray,
    development: np.ndarray,
    tensors: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, float]]:
    started = time.monotonic()
    timings: dict[str, float] = {}
    schedule_spec = config["training_schedule"]
    steps = int(schedule_spec["steps_per_generation"])
    batch_size = int(schedule_spec["batch_size"])
    fit_seed = seed + int(schedule_spec["seed_offset"])
    generation_spec = config["feedback"]
    mapping = config["conditional_mapping"]
    alpha = float(generation_spec["alpha"])
    response_batch = int(base_loop["development"]["batch_size"])

    seed_everything(fit_seed, int(base_loop["runtime"]["threads"]))
    initial = build_model(base_loop["model"])
    assert_pattern_value_model(initial)
    initial_hash = _model_state_hash(initial)
    initial_metrics = response_metrics(
        initial, graph, tensors, oracle, development, response_batch
    )

    replay_config = deepcopy(base_loop["self_play"])
    replay_config["games"] = int(generation_spec["games_per_generation"])
    replay_config["game_schedule"] = None
    mark = time.monotonic()
    generated_g1 = generate_self_play(
        graph,
        initial,
        loop_module._parse_self_play(replay_config),
        1,
        seed + int(generation_spec["g1_seed_offset"]),
        train_starts,
    )
    g1_outcome_rows = _filter_train(generated_g1.samples, train_mask)
    g1_context_rows, g1_mapping = _conditional_replay(
        oracle,
        g1_outcome_rows,
        mapping,
        namespace=f"seed={seed}|generation=1|shared",
        alpha=alpha,
    )
    timings["g1_replay_and_mapping_seconds"] = time.monotonic() - mark
    g1_schedule = _random_schedule(
        len(g1_outcome_rows), steps, batch_size, fit_seed + 1
    )
    mark = time.monotonic()
    outcome_g1, outcome_g1_training, outcome_initial_hash = _fit(
        base_loop, graph, g1_outcome_rows, g1_schedule, fit_seed
    )
    context_g1, context_g1_training, context_initial_hash = _fit(
        base_loop, graph, g1_context_rows, g1_schedule, fit_seed
    )
    if outcome_initial_hash != initial_hash or context_initial_hash != initial_hash:
        raise RuntimeError("M15-C5 G1 arms did not share initial PatternEval")
    timings["g1_fit_seconds"] = time.monotonic() - mark

    mark = time.monotonic()
    outcome_g2_generated = generate_self_play(
        graph,
        outcome_g1,
        loop_module._parse_self_play(replay_config),
        2,
        seed + int(generation_spec["g2_seed_offset"]),
        train_starts,
    )
    context_g2_generated = generate_self_play(
        graph,
        context_g1,
        loop_module._parse_self_play(replay_config),
        2,
        seed + int(generation_spec["g2_seed_offset"]),
        train_starts,
    )
    outcome_g2_rows = _filter_train(outcome_g2_generated.samples, train_mask)
    context_g2_own_outcomes = _filter_train(context_g2_generated.samples, train_mask)
    context_g2_own_rows, context_g2_own_mapping = _conditional_replay(
        oracle,
        context_g2_own_outcomes,
        mapping,
        namespace=f"seed={seed}|generation=2|context-own",
        alpha=alpha,
    )
    context_g2_on_outcome_rows, context_g2_outcome_mapping = _conditional_replay(
        oracle,
        outcome_g2_rows,
        mapping,
        namespace=f"seed={seed}|generation=2|outcome-replay",
        alpha=alpha,
    )
    timings["g2_replays_and_mappings_seconds"] = time.monotonic() - mark

    outcome_schedule = _random_schedule(
        len(outcome_g2_rows), steps, batch_size, fit_seed + 2
    )
    context_own_schedule = _random_schedule(
        len(context_g2_own_rows), steps, batch_size, fit_seed + 2
    )
    mark = time.monotonic()
    outcome_g2, outcome_g2_training, outcome_parent_hash = _continue_fit(
        outcome_g1, graph, outcome_g2_rows, outcome_schedule, base_loop, fit_seed + 3
    )
    context_g2_own, context_g2_own_training, context_parent_hash = _continue_fit(
        context_g1,
        graph,
        context_g2_own_rows,
        context_own_schedule,
        base_loop,
        fit_seed + 3,
    )
    context_g2_on_outcome, context_g2_outcome_training, decomposition_parent_hash = (
        _continue_fit(
            context_g1,
            graph,
            context_g2_on_outcome_rows,
            outcome_schedule,
            base_loop,
            fit_seed + 3,
        )
    )
    if outcome_parent_hash != _model_state_hash(outcome_g1):
        raise RuntimeError("M15-C5 outcome G2 parent drift")
    if context_parent_hash != _model_state_hash(context_g1):
        raise RuntimeError("M15-C5 context G2 parent drift")
    if decomposition_parent_hash != context_parent_hash:
        raise RuntimeError("M15-C5 decomposition did not share context G1 parent")
    timings["g2_fit_seconds"] = time.monotonic() - mark

    models = {
        "OUTCOME_G1": outcome_g1,
        "CONTEXT_30_G1": context_g1,
        "OUTCOME_G2": outcome_g2,
        "CONTEXT_30_G2_OWN_REPLAY": context_g2_own,
        "CONTEXT_30_G2_ON_OUTCOME_REPLAY": context_g2_on_outcome,
    }
    training = {
        "OUTCOME_G1": outcome_g1_training,
        "CONTEXT_30_G1": context_g1_training,
        "OUTCOME_G2": outcome_g2_training,
        "CONTEXT_30_G2_OWN_REPLAY": context_g2_own_training,
        "CONTEXT_30_G2_ON_OUTCOME_REPLAY": context_g2_outcome_training,
    }
    arm_rows: dict[str, Any] = {}
    for arm, model in models.items():
        metrics = response_metrics(
            model, graph, tensors, oracle, development, response_batch
        )
        arm_rows[arm] = {
            **metrics,
            "zero_regret_gain_from_initial": float(metrics["zero_regret_rate"])
            - float(initial_metrics["zero_regret_rate"]),
            "training": training[arm],
            "model_hash": _model_state_hash(model),
            "promotable": False,
        }

    arena_spec = config["strength_arena"]
    arena_config = _arena_config(base_loop, arena_spec)
    arena_seed = int(arena_spec["seed_base"]) + seed
    mark = time.monotonic()
    arena_pairs = {
        "g1_context_effect": ("CONTEXT_30_G1", "OUTCOME_G1"),
        "g2_on_policy_context_effect": (
            "CONTEXT_30_G2_OWN_REPLAY",
            "OUTCOME_G2",
        ),
        "g2_feedback_distribution_effect": (
            "CONTEXT_30_G2_OWN_REPLAY",
            "CONTEXT_30_G2_ON_OUTCOME_REPLAY",
        ),
    }
    arenas: dict[str, Any] = {}
    start_hash: str | None = None
    for name, (candidate, reference) in arena_pairs.items():
        arena = run_arena(
            graph,
            models[candidate],
            models[reference],
            arena_config,
            arena_seed,
            development,
        )
        observed_hash = digest(arena["start_state_ids"])
        if start_hash is None:
            start_hash = observed_hash
        elif observed_hash != start_hash:
            raise RuntimeError("M15-C5 paired arena starts diverged")
        arenas[name] = {
            **arena,
            "score_minus_half": float(arena["score"]) - 0.5,
            "candidate": candidate,
            "reference": reference,
        }
    timings["arenas_seconds"] = time.monotonic() - mark
    timings["total_seconds"] = time.monotonic() - started

    row = {
        "seed": seed,
        "initial": initial_metrics,
        "arms": arm_rows,
        "replay": {
            "g1": {
                "generated_rows": len(generated_g1.samples),
                "train_rows": len(g1_outcome_rows),
                "outcome_fingerprint": replay_fingerprint(g1_outcome_rows),
                "structure_fingerprint": _sample_structure_fingerprint(g1_outcome_rows),
                "shared_schedule_hash": hashlib.sha256(
                    g1_schedule.tobytes(order="C")
                ).hexdigest(),
                "shared_initial_model_hash": initial_hash,
            },
            "g2_outcome": {
                "generated_rows": len(outcome_g2_generated.samples),
                "train_rows": len(outcome_g2_rows),
                "fingerprint": replay_fingerprint(outcome_g2_rows),
                "schedule_hash": hashlib.sha256(
                    outcome_schedule.tobytes(order="C")
                ).hexdigest(),
            },
            "g2_context_own": {
                "generated_rows": len(context_g2_generated.samples),
                "train_rows": len(context_g2_own_rows),
                "fingerprint": replay_fingerprint(context_g2_own_outcomes),
                "schedule_hash": hashlib.sha256(
                    context_own_schedule.tobytes(order="C")
                ).hexdigest(),
            },
            "all_rows_train_only": True,
        },
        "conditional_mapping": {
            "g1": g1_mapping,
            "g2_context_own": context_g2_own_mapping,
            "g2_on_outcome_replay": context_g2_outcome_mapping,
        },
        "arenas": arenas,
        "shared_arena_start_hash": start_hash,
        "timing": timings,
    }
    return row, timings


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
        result["arena_score_minus_half"] = _interval(
            [float(row["arenas"][name]["score_minus_half"]) for row in rows],
            critical,
        )
        output[name] = result
    output["g2_minus_g1_context_effect"] = {
        endpoint: _interval(
            [
                (
                    float(row["arms"]["CONTEXT_30_G2_OWN_REPLAY"][endpoint])
                    - float(row["arms"]["OUTCOME_G2"][endpoint])
                )
                - (
                    float(row["arms"]["CONTEXT_30_G1"][endpoint])
                    - float(row["arms"]["OUTCOME_G1"][endpoint])
                )
                for row in rows
            ],
            critical,
        )
        for endpoint in ENDPOINTS
    }
    output["g2_minus_g1_context_effect"]["arena_score_minus_half"] = _interval(
        [
            float(row["arenas"]["g2_on_policy_context_effect"]["score_minus_half"])
            - float(row["arenas"]["g1_context_effect"]["score_minus_half"])
            for row in rows
        ],
        critical,
    )
    return output


def build_recommendation(contrasts: dict[str, Any]) -> dict[str, Any]:
    primary = contrasts["g2_on_policy_context_effect"]
    static = primary["zero_regret_rate"]
    strength = primary["arena_score_minus_half"]
    common = {
        "primary_contrast": "CONTEXT_30_G2_OWN_REPLAY_minus_OUTCOME_G2",
        "static_mean": float(static["mean"]),
        "static_ci95": [float(static["lower"]), float(static["upper"])],
        "strength_mean": float(strength["mean"]),
        "strength_ci95": [float(strength["lower"]), float(strength["upper"])],
        "minimum_effect_floor": 0.0,
        "promotable": False,
    }
    if float(static["lower"]) > 0.0 and float(strength["lower"]) > 0.0:
        return {
            **common,
            "status": "PASS",
            "finding": "conditional_target_gain_survives_one_on_policy_feedback_step",
            "decision": "retain_CONTEXT_30_feedback_recipe_and_test_longer_ladder",
        }
    if float(static["upper"]) <= 0.0 or float(strength["upper"]) <= 0.0:
        return {
            **common,
            "status": "FAIL",
            "finding": "conditional_target_gain_does_not_survive_on_policy_feedback",
            "decision": "keep_static_CONTEXT_30_evidence_but_close_feedback_transfer",
        }
    return {
        **common,
        "status": "INCONCLUSIVE",
        "finding": "conditional_feedback_effect_not_precise",
        "decision": "power_size_only_from_observed_paired_variance_before_replication",
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
            replayed.get("schema") != result.get("schema")
            or replayed.get("result_hash") != result.get("result_hash")
        ):
            raise RuntimeError(f"M15-C5 reporting round-trip failed: {path}")


def _write_progress(
    path: Path | None, completed: int, total: int, last_seed: int, started: float
) -> None:
    if path is None:
        return
    elapsed = max(time.monotonic() - started, 1e-9)
    rate = completed / (elapsed / 60.0)
    payload = {
        "schema": "mini_jass.pattern_conditional_feedback_progress.v1",
        "milestone": MILESTONE,
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


def run_m15c5(
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
        raise ValueError(f"M15-C5 requires HOME hostname User, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M15-C5 split differs from frozen L1 contract")
    train = split.indices("train")
    development = split.indices("development")
    train_mask = np.zeros(graph.state_count, dtype=np.bool_)
    train_mask[train] = True
    train_starts = np.asarray(
        [state for state in train if graph.terminal_value(int(state)) is None],
        dtype=np.int64,
    )
    tensors = solved_tensors(oracle, graph)

    if probe_only:
        seed = int(config["probe"]["seed"])
        _row, timings = _run_seed(
            seed,
            config,
            base_loop,
            oracle,
            graph,
            train_mask,
            train_starts,
            development,
            tensors,
        )
        result = {
            "schema": "mini_jass.pattern_conditional_feedback_probe.v1",
            "milestone": MILESTONE,
            "status": "TIMING_ONLY",
            "seed": seed,
            "execution_host": host,
            "nproc": int(config["probe"]["expected_nproc"]),
            "timing": timings,
            "scientific_metrics_published": False,
            "frozen_test_reads": 0,
            "promotable": False,
        }
        result["result_hash"] = digest(result)
        _write_outputs(result, run_dir, compact_output)
        return result

    rows: list[dict[str, Any]] = []
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    for raw_seed in config["paired_seeds"]:
        seed = int(raw_seed)
        row, _timing = _run_seed(
            seed,
            config,
            base_loop,
            oracle,
            graph,
            train_mask,
            train_starts,
            development,
            tensors,
        )
        rows.append(row)
        (run_dir / f"seed-{seed}.json").write_text(
            json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write_progress(
            progress_output, len(rows), len(config["paired_seeds"]), seed, started
        )

    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    contrasts = build_contrasts(rows, critical)
    recommendation = build_recommendation(contrasts)
    aggregate = {
        "paired_seed_count": len(rows),
        "arms": {
            arm: {
                "mean_zero_regret_rate": mean(
                    row["arms"][arm]["zero_regret_rate"] for row in rows
                ),
                "mean_value_sign_accuracy": mean(
                    row["arms"][arm]["value_sign_accuracy"] for row in rows
                ),
            }
            for arm in ARMS
        },
        "contrasts": contrasts,
        "mean_seed_seconds": mean(row["timing"]["total_seconds"] for row in rows),
        "all_training_rows_train_only": True,
        "all_cross_fit_games_disjoint": all(
            all(
                bool(mapping["all_games_fold_disjoint"])
                for mapping in row["conditional_mapping"].values()
            )
            for row in rows
        ),
        "additional_frozen_test_reads": 0,
    }
    protocol = {
        "schema": SCHEMA,
        "milestone": MILESTONE,
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "arms": list(ARMS),
        "feedback": config["feedback"],
        "conditional_mapping": config["conditional_mapping"],
        "training_schedule": config["training_schedule"],
        "strength_arena": config["strength_arena"],
        "scientific_gate": config["scientific_gate"],
        "source_evidence": config["source_evidence"],
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "milestone": MILESTONE,
        "status": recommendation["status"],
        "protocol_hash": digest(protocol),
        "protocol": protocol,
        "aggregate": aggregate,
        "seed_results": rows,
        "recommendation": recommendation,
        "sealed_cohort_contract": {
            "cohorts_read": ["train", "development"],
            "cohorts_not_read": ["frozen_test"],
            "additional_frozen_test_reads": 0,
            "all_training_targets_oracle_blind": True,
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
    result = run_m15c5(
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
