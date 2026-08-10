#!/usr/bin/env python3
"""M15-C2: screen the preregistered interior conditional-target dose."""

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
from mini_jass_lab.conditional_targets import (  # noqa: E402
    cross_fitted_conditional_wdl,
    permute_predictions_within_folds,
)
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
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402
from run_pattern_conditional_target_screen import (  # noqa: E402
    _fit,
    _model_state_hash,
    _random_schedule,
    _sample_structure_fingerprint,
    estimate_power,
)

SCHEMA = "mini_jass.pattern_conditional_dose_screen.v1"
PROBE_SCHEMA = "mini_jass.pattern_conditional_dose_screen_probe.v1"
ARM_ORDER = (
    "OUTCOME",
    "SHUFFLED_CONTEXT_20",
    "CONTEXT_20",
    "SHUFFLED_CONTEXT_30",
    "CONTEXT_30",
    "SHUFFLED_CONTEXT_40",
    "CONTEXT_40",
)
DOSES = (0.20, 0.30, 0.40)
PRIMARY_ALPHA = 0.30
ARENA_ARMS = ("OUTCOME", "SHUFFLED_CONTEXT_30", "CONTEXT_30")
STATIC_ENDPOINTS = (
    "zero_regret_gain",
    "value_sign_gain",
    "value_mae",
    "mean_selected_regret",
)
CONTRASTS = {
    "attribution_20": ("CONTEXT_20", "SHUFFLED_CONTEXT_20"),
    "operational_20": ("CONTEXT_20", "OUTCOME"),
    "attribution_30": ("CONTEXT_30", "SHUFFLED_CONTEXT_30"),
    "operational_30": ("CONTEXT_30", "OUTCOME"),
    "attribution_40": ("CONTEXT_40", "SHUFFLED_CONTEXT_40"),
    "operational_40": ("CONTEXT_40", "OUTCOME"),
}
ARENA_CONTRASTS = {
    "attribution_30": ("CONTEXT_30", "SHUFFLED_CONTEXT_30"),
    "operational_30": ("CONTEXT_30", "OUTCOME"),
}

EXPECTED_M15C_PROTOCOL = "74dc555948e0191c09814098918c35e2e23935cf6ff44801c6c09165ad97502d"
EXPECTED_M15C_RESULT = "b63008f3e685c5cf20ae18af4e389fa8f7308ae31aa6525e549244f6f80e499d"


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M15-C2":
        raise ValueError("unexpected M15-C2 schema")
    if tuple(config.get("arms", [])) != ARM_ORDER:
        raise ValueError("M15-C2 arms changed after preregistration")
    seeds = [int(seed) for seed in config.get("paired_seeds", [])]
    if seeds != list(range(273001, 273021)):
        raise ValueError("M15-C2 paired seeds changed or overlap prior evidence")
    probe = config.get("probe", {})
    if (
        int(probe.get("seed", -1)) != 273000
        or probe.get("overlaps_scientific_seeds") is not False
        or probe.get("purpose") != "cpx62_runtime_calibration_only"
        or probe.get("reporting") != "timing_and_contract_only"
        or probe.get("scientific_metrics_must_not_be_published") is not True
    ):
        raise ValueError("M15-C2 probe contract changed")

    evidence = config.get("source_evidence", {}).get("m15c", {})
    if (
        evidence.get("protocol_hash") != EXPECTED_M15C_PROTOCOL
        or evidence.get("result_hash") != EXPECTED_M15C_RESULT
        or evidence.get("frozen_status") != "FAIL"
        or evidence.get("frozen_finding")
        != "conditional_blend_excludes_practical_operational_gain"
        or evidence.get("interpretation_for_followup")
        != "MECHANISM_CONFIRMED_PRACTICAL_GATE_MISSED"
        or float(evidence.get("attribution_ci95", [0.0])[0]) <= 0.0
        or float(evidence.get("operational_ci95", [0.0])[0]) <= 0.0
        or float(evidence.get("operational_ci95", [0.0, 0.0])[1])
        >= float(evidence.get("old_minimum_operational_gain", -1.0))
    ):
        raise ValueError("M15-C2 source evidence is not frozen")

    replay = config.get("replay", {})
    if (
        replay.get("source") != "G1_WIDE_OUTCOME"
        or int(replay.get("games_per_seed", 0)) != 1024
        or int(replay.get("generation", 0)) != 1
        or int(replay.get("seed_offset", 0)) != 900000
        or replay.get("row_selection") != "all_generated_train_rows"
        or replay.get("immutable_structure_across_arms") is not True
    ):
        raise ValueError("M15-C2 replay contract changed")

    mapping = config.get("conditional_mapping", {})
    if (
        mapping.get("family") != "odd_tanh_linear_wdl_oof_v1"
        or int(mapping.get("fold_count", 0)) != 5
        or mapping.get("fold_unit") != "complete_game"
        or mapping.get("fold_assignment") != "sha256_rank_round_robin_v1"
        or mapping.get("fold_namespace") != "m15c2_conditional_wdl_game_folds_v1"
        or mapping.get("shuffle_control") != "within_fold_hash_order_rotate_one_v1"
        or mapping.get("shuffle_namespace") != "m15c2_conditional_shuffle_v1"
        or mapping.get("initialization") != "zero"
        or mapping.get("training_label") != "terminal_selfplay_wdl"
        or mapping.get("oracle_training_signal") is not False
        or mapping.get("manual_coefficients_used") is not False
        or float(mapping.get("ridge", -1.0)) != 1.0e-4
        or int(mapping.get("max_iterations", 0)) != 64
        or float(mapping.get("tolerance", -1.0)) != 1.0e-10
        or int(mapping.get("line_search_steps", 0)) != 24
    ):
        raise ValueError("M15-C2 conditional mapping changed")

    dose = config.get("dose_screen", {})
    if (
        dose.get("target_formula")
        != "(1-alpha)*outcome+alpha*conditional_prediction"
        or float(dose.get("primary_alpha", -1.0)) != PRIMARY_ALPHA
        or dose.get("exploratory_alphas") != [0.20, 0.40]
        or dose.get("exploratory_doses_cannot_rescue_primary") is not True
        or dose.get("every_target_oracle_blind") is not True
        or dose.get("selection_basis", {}).get("source_result") != "M15-C"
    ):
        raise ValueError("M15-C2 dose contract changed")

    gate = config.get("scientific_gate", {})
    if (
        float(gate.get("primary_alpha", -1.0)) != PRIMARY_ALPHA
        or gate.get("primary_endpoint") != "development_zero_regret_gain"
        or gate.get("attribution_contrast")
        != "CONTEXT_30_minus_SHUFFLED_CONTEXT_30"
        or gate.get("operational_contrast") != "CONTEXT_30_minus_OUTCOME"
        or gate.get("mechanism_pass_requires_attribution_ci_above_zero") is not True
        or gate.get("operational_pass_requires_outcome_ci_above_zero") is not True
        or float(gate.get("minimum_effect_floor", -1.0)) != 0.0
        or gate.get("strength_is_separate_from_static_pass") is not True
        or gate.get("strength_pass_requires_both_arena_ci_above_zero") is not True
        or gate.get("exploratory_doses_can_rescue_primary") is not False
        or gate.get("automatic_promotion") is not False
    ):
        raise ValueError("M15-C2 scientific gate changed")

    power = config.get("power_sizing", {})
    if (
        power.get("contrasts_sized")
        != [
            "CONTEXT_30_minus_SHUFFLED_CONTEXT_30",
            "CONTEXT_30_minus_OUTCOME",
        ]
        or int(power.get("repetitions", 0)) != 100000
        or int(power.get("seed", 0)) != 44120260813
        or int(power.get("paired_seed_count", 0)) != len(seeds)
        or float(power.get("conservative_paired_sd", -1.0)) != 0.0025
        or float(power.get("minimum_effect", -1.0)) != 0.002
        or float(power.get("paired_confidence_critical_95", -1.0))
        != 2.093024054408263
        or power.get("gate_has_no_minimum_effect_floor") is not True
    ):
        raise ValueError("M15-C2 power contract changed")
    observed_power = estimate_power(power)
    if not math.isclose(
        observed_power,
        float(power.get("estimated_power_ci_above_zero", -1.0)),
        rel_tol=0.0,
        abs_tol=5.0e-6,
    ):
        raise ValueError("M15-C2 frozen power result did not reproduce")
    if observed_power < float(power.get("minimum_required_power", 1.0)):
        raise ValueError("M15-C2 is underpowered before training")

    boundaries = config.get("boundaries", {})
    if (
        boundaries.get("cohorts_read") != ["train", "development"]
        or boundaries.get("cohorts_never_read_by_this_cell") != ["frozen_test"]
        or int(boundaries.get("existing_frozen_test_read_count", -1)) != 1
        or int(boundaries.get("additional_frozen_test_reads_authorized", -1)) != 0
        or boundaries.get("all_training_targets_oracle_blind") is not True
        or boundaries.get("automatic_selection_or_promotion") is not False
        or boundaries.get("promotable") is not False
        or boundaries.get("production_jass_changes_authorized") is not False
        or boundaries.get("direct_10x10_transfer_authorized") is not False
        or boundaries.get("execution_is_not_queued_by_this_pr") is not True
    ):
        raise ValueError("M15-C2 crossed a scientific boundary")

    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M15-C2 requires the frozen PatternEval loop")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M15-C2 requires folded PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M15-C2 cannot train a policy head")
    schedule = config["training_schedule"]
    if (
        int(schedule["total_steps"]) != int(loop["training"]["steps"])
        or int(schedule["batch_size"]) != int(loop["training"]["batch_size"])
        or int(schedule.get("seed_offset", 0)) != 910000
        or schedule.get("explicit_identical_batch_schedule_all_arms") is not True
    ):
        raise ValueError("M15-C2 training schedule changed")
    arena = config["strength_arena"]
    if (
        tuple(arena.get("arms", [])) != ARENA_ARMS
        or int(arena.get("pairs", 0)) != 512
        or int(arena.get("seed_base", 0)) != 961000
        or float(arena.get("epsilon", -1.0)) != 0.0
        or arena.get("confidence_unit") != "pairs"
        or arena.get("start_state_source") != "development"
        or arena.get("role") != "separate_strength_verdict"
    ):
        raise ValueError("M15-C2 strength arena changed")
    return deepcopy(config), loop


def build_target_arms(
    samples: list[ReplaySample],
    conditional_predictions: np.ndarray,
    shuffled_predictions: np.ndarray,
    exact_values: np.ndarray,
) -> tuple[dict[str, list[ReplaySample]], dict[str, Any]]:
    conditional = np.asarray(conditional_predictions, dtype=np.float64)
    shuffled = np.asarray(shuffled_predictions, dtype=np.float64)
    if conditional.shape != (len(samples),) or shuffled.shape != (len(samples),):
        raise ValueError("M15-C2 predictions must align with replay rows")
    if not np.all(np.isfinite(conditional)) or not np.all(np.isfinite(shuffled)):
        raise ValueError("M15-C2 predictions must be finite")
    if np.any(np.abs(conditional) > 1.0) or np.any(np.abs(shuffled) > 1.0):
        raise ValueError("M15-C2 predictions left the WDL range")

    outcomes = np.asarray([sample.value_target for sample in samples], dtype=np.float64)
    values: dict[str, np.ndarray] = {"OUTCOME": outcomes}
    for alpha in DOSES:
        suffix = int(round(100 * alpha))
        values[f"SHUFFLED_CONTEXT_{suffix}"] = (1.0 - alpha) * outcomes + alpha * shuffled
        values[f"CONTEXT_{suffix}"] = (1.0 - alpha) * outcomes + alpha * conditional
    arms = {
        arm: [
            replace(sample, value_target=float(value))
            for sample, value in zip(samples, values[arm], strict=True)
        ]
        for arm in ARM_ORDER
    }
    structures = {arm: _sample_structure_fingerprint(rows) for arm, rows in arms.items()}
    if len(set(structures.values())) != 1:
        raise RuntimeError("M15-C2 target arms changed replay structure")
    state_ids = np.asarray([sample.state_id for sample in samples], dtype=np.int64)
    exact = np.asarray(exact_values)[state_ids].astype(np.float64)
    target_metrics = {
        arm: {
            "sample_count": len(samples),
            "value_mae_vs_exact_train": float(np.mean(np.abs(values[arm] - exact))),
            "value_exact_rate_vs_exact_train": float(np.mean(values[arm] == exact)),
            "changed_from_outcome_fraction": float(np.mean(values[arm] != outcomes)),
            "target_mean": float(values[arm].mean()),
            "target_standard_deviation": float(values[arm].std(ddof=0)),
        }
        for arm in ARM_ORDER
    }
    return arms, {
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
        for endpoint in STATIC_ENDPOINTS:
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


def build_arena_contrasts(
    rows: list[dict[str, Any]], critical: float
) -> dict[str, Any]:
    return {
        name: {
            "high": high,
            "low": low,
            "arena_score_minus_half": _interval(
                [
                    float(row["arms"][high]["arena_score_minus_half"])
                    - float(row["arms"][low]["arena_score_minus_half"])
                    for row in rows
                ],
                critical,
            ),
        }
        for name, (high, low) in ARENA_CONTRASTS.items()
    }


def _axis_status(interval: dict[str, Any]) -> str:
    if float(interval["lower"]) > 0.0:
        return "PASS"
    if float(interval["upper"]) <= 0.0:
        return "FAIL"
    return "INCONCLUSIVE"


def build_recommendation(
    contrasts: dict[str, Any], arena_contrasts: dict[str, Any]
) -> dict[str, Any]:
    attribution = contrasts["attribution_30"]["zero_regret_gain"]
    operational = contrasts["operational_30"]["zero_regret_gain"]
    arena_attribution = arena_contrasts["attribution_30"]["arena_score_minus_half"]
    arena_operational = arena_contrasts["operational_30"]["arena_score_minus_half"]
    mechanism_status = _axis_status(attribution)
    operational_status = _axis_status(operational)
    arena_axes = (_axis_status(arena_attribution), _axis_status(arena_operational))
    if arena_axes == ("PASS", "PASS"):
        strength_status = "PASS"
    elif "FAIL" in arena_axes:
        strength_status = "FAIL"
    else:
        strength_status = "INCONCLUSIVE"

    common = {
        "primary_alpha": PRIMARY_ALPHA,
        "mechanism_status": mechanism_status,
        "operational_status": operational_status,
        "strength_status": strength_status,
        "attribution_mean": float(attribution["mean"]),
        "attribution_ci95": [float(attribution["lower"]), float(attribution["upper"])],
        "operational_mean": float(operational["mean"]),
        "operational_ci95": [float(operational["lower"]), float(operational["upper"])],
        "arena_attribution_mean": float(arena_attribution["mean"]),
        "arena_attribution_ci95": [
            float(arena_attribution["lower"]),
            float(arena_attribution["upper"]),
        ],
        "arena_operational_mean": float(arena_operational["mean"]),
        "arena_operational_ci95": [
            float(arena_operational["lower"]),
            float(arena_operational["upper"]),
        ],
        "minimum_effect_floor": 0.0,
        "exploratory_doses_can_rescue_primary": False,
        "promotable": False,
    }
    if mechanism_status == "PASS" and operational_status == "PASS":
        return {
            **common,
            "status": "PASS",
            "finding": "interior_conditional_dose_confirms_positive_static_signal",
            "decision": (
                "prepare_independent_strength_replication"
                if strength_status != "PASS"
                else "prepare_independent_static_and_strength_replication"
            ),
        }
    if mechanism_status == "FAIL" or operational_status == "FAIL":
        return {
            **common,
            "status": "FAIL",
            "finding": "primary_interior_conditional_dose_has_no_positive_static_signal",
            "decision": "close_conditional_dose_axis_and_prepare_M16P",
        }
    return {
        **common,
        "status": "INCONCLUSIVE",
        "finding": "primary_interior_conditional_dose_is_not_precise",
        "decision": "power_size_fresh_M15C2_replication",
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
            or replayed.get("milestone") != "M15-C2"
            or replayed.get("result_hash") != result.get("result_hash")
            or replayed.get("recommendation", {}).get("finding")
            != result.get("recommendation", {}).get("finding")
        ):
            raise RuntimeError(f"M15-C2 reporting round-trip failed: {path}")


def _write_probe_outputs(
    result: dict[str, Any], run_dir: Path, compact_output: Path
) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "probe.json").write_text(payload, encoding="utf-8")
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(payload, encoding="utf-8")
    for path in (run_dir / "probe.json", compact_output):
        replayed = json.loads(path.read_text(encoding="utf-8"))
        if (
            replayed.get("schema") != PROBE_SCHEMA
            or replayed.get("status") != "PROBE_COMPLETE"
            or replayed.get("result_hash") != result.get("result_hash")
            or replayed.get("scientific_metrics_published") is not False
            or replayed.get("promotable") is not False
        ):
            raise RuntimeError(f"M15-C2 probe reporting round-trip failed: {path}")


def _write_progress(
    path: Path | None, completed: int, total: int, last_seed: int, started: float
) -> None:
    if path is None:
        return
    elapsed = max(time.monotonic() - started, 1.0e-9)
    rate = completed / (elapsed / 60.0)
    payload = {
        "schema": "mini_jass.pattern_conditional_dose_screen_progress.v1",
        "milestone": "M15-C2",
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


def run_m15c2(
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
        raise ValueError(f"M15-C2 requires cpx62, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M15-C2 split differs from the frozen L1 contract")
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
    arena_spec = config["strength_arena"]
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
    mapping_spec = config["conditional_mapping"]
    rows: list[dict[str, Any]] = []
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    run_seeds = (
        [int(config["probe"]["seed"])]
        if probe_only
        else [int(seed) for seed in config["paired_seeds"]]
    )
    for raw_seed in run_seeds:
        seed = int(raw_seed)
        fit_seed = seed + schedule_offset
        seed_everything(fit_seed, int(base_loop["runtime"]["threads"]))
        initial = build_model(base_loop["model"])
        assert_pattern_value_model(initial)
        initial_hash = _model_state_hash(initial)
        before = response_metrics(initial, graph, tensors, oracle, development, response_batch)

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
            raise RuntimeError("M15-C2 generated no train-cohort replay rows")
        if not all(bool(train_mask[int(sample.state_id)]) for sample in train_samples):
            raise RuntimeError("M15-C2 retained a row outside the train cohort")
        contexts = context_matrix(oracle, [sample.state_id for sample in train_samples])
        outcomes = np.asarray(
            [sample.value_target for sample in train_samples], dtype=np.float64
        )
        cross_fit = cross_fitted_conditional_wdl(
            contexts,
            outcomes,
            train_samples,
            fold_count=int(mapping_spec["fold_count"]),
            namespace=str(mapping_spec["fold_namespace"]),
            ridge=float(mapping_spec["ridge"]),
            max_iterations=int(mapping_spec["max_iterations"]),
            tolerance=float(mapping_spec["tolerance"]),
            line_search_steps=int(mapping_spec["line_search_steps"]),
        )
        shuffled = permute_predictions_within_folds(
            cross_fit["conditional_predictions"],
            cross_fit["fold_ids"],
            train_samples,
            namespace=str(mapping_spec["shuffle_namespace"]),
        )
        arms, replay_contract = build_target_arms(
            train_samples,
            cross_fit["conditional_predictions"],
            shuffled["predictions"],
            oracle.values,
        )
        schedule = _random_schedule(len(train_samples), steps, batch_size, fit_seed + 15)

        models: dict[str, Any] = {}
        arm_rows: dict[str, Any] = {}
        for arm in ARM_ORDER:
            model, training, arm_initial_hash = _fit(
                base_loop, graph, arms[arm], schedule, fit_seed
            )
            if arm_initial_hash != initial_hash:
                raise RuntimeError("M15-C2 arms did not share the initial PatternEval")
            after = response_metrics(model, graph, tensors, oracle, development, response_batch)
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
                "oracle_training_signal": False,
                "promotable": False,
            }

        arena_seed = int(arena_spec["seed_base"]) + seed
        arena_start_hash: str | None = None
        outcome_model = models["OUTCOME"]
        for arm in ARENA_ARMS:
            arena = run_arena(
                graph, models[arm], outcome_model, arena_config, arena_seed, development
            )
            start_hash = digest(arena["start_state_ids"])
            if arena_start_hash is None:
                arena_start_hash = start_hash
            elif start_hash != arena_start_hash:
                raise RuntimeError("M15-C2 arena starts diverged across arms")
            arm_rows[arm]["arena_score_minus_half"] = float(arena["score"]) - 0.5
            arm_rows[arm]["arena_vs_outcome"] = arena
        if arm_rows["OUTCOME"]["arena_score_minus_half"] != 0.0:
            raise RuntimeError("M15-C2 symmetric OUTCOME arena did not score 0.5")

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
            "conditional_mapping": {
                key: value
                for key, value in cross_fit.items()
                if key not in {
                    "fold_ids",
                    "conditional_predictions",
                    "state_blind_predictions",
                }
            },
            "shuffle_control": {
                key: value
                for key, value in shuffled.items()
                if key not in {"predictions", "source_row_indices"}
            },
            "arms": arm_rows,
        }
        rows.append(row)
        if not probe_only:
            (run_dir / f"seed-{seed}.json").write_text(
                json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            _write_progress(progress_output, len(rows), len(run_seeds), seed, started)

    if probe_only:
        elapsed = time.monotonic() - started
        result = {
            "schema": PROBE_SCHEMA,
            "milestone": "M15-C2-PROBE",
            "status": "PROBE_COMPLETE",
            "seed": int(run_seeds[0]),
            "timing": {"total_seconds": elapsed},
            "workload": {
                "selfplay_games": int(config["replay"]["games_per_seed"]),
                "training_arms": len(ARM_ORDER),
                "training_steps": len(ARM_ORDER) * steps,
                "arena_arms": len(ARENA_ARMS),
                "arena_pairs": len(ARENA_ARMS) * int(arena_spec["pairs"]),
                "arena_games": 2 * len(ARENA_ARMS) * int(arena_spec["pairs"]),
                "train_sample_count": int(rows[0]["replay"]["train_sample_count"]),
            },
            "reporting": "timing_and_contract_only",
            "scientific_metrics_published": False,
            "promotable": False,
        }
        result["result_hash"] = digest(
            {key: value for key, value in result.items() if key != "result_hash"}
        )
        _write_probe_outputs(result, run_dir, compact_output)
        return result

    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    contrasts = build_contrasts(rows, critical)
    arena_contrasts = build_arena_contrasts(rows, critical)
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
                "mean_value_mae": mean(row["arms"][arm]["value_mae"] for row in rows),
                "mean_target_mae_vs_exact_train": mean(
                    row["arms"][arm]["target"]["value_mae_vs_exact_train"]
                    for row in rows
                ),
                **(
                    {
                        "mean_arena_score_minus_half": mean(
                            row["arms"][arm]["arena_score_minus_half"] for row in rows
                        )
                    }
                    if arm in ARENA_ARMS
                    else {}
                ),
            }
            for arm in ARM_ORDER
        },
        "contrasts": contrasts,
        "arena_contrasts": arena_contrasts,
        "conditional_mapping_oof_mse_gain_vs_state_blind": paired_interval(
            [
                float(row["conditional_mapping"]["conditional_mse_gain_vs_state_blind"])
                for row in rows
            ],
            critical,
        ),
        "mean_train_sample_count": mean(row["replay"]["train_sample_count"] for row in rows),
        "all_training_rows_train_only": all(
            bool(row["replay"]["all_rows_train_only"]) for row in rows
        ),
        "all_cross_fit_games_disjoint": all(
            bool(row["conditional_mapping"]["all_games_fold_disjoint"])
            for row in rows
        ),
        "all_shuffle_marginals_preserved": all(
            bool(row["shuffle_control"]["all_fold_marginals_preserved"])
            for row in rows
        ),
        "all_batch_schedules_paired_within_seed": True,
        "all_initial_models_paired_within_seed": True,
        "all_arena_starts_paired_within_seed": True,
        "additional_frozen_test_reads": 0,
    }
    recommendation = build_recommendation(contrasts, arena_contrasts)
    protocol = {
        "schema": SCHEMA,
        "milestone": "M15-C2",
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "arms": list(ARM_ORDER),
        "replay": config["replay"],
        "conditional_mapping": config["conditional_mapping"],
        "dose_screen": config["dose_screen"],
        "training_schedule": config["training_schedule"],
        "strength_arena": config["strength_arena"],
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
        "milestone": "M15-C2",
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
    result = run_m15c2(
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
