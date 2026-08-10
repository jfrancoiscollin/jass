#!/usr/bin/env python3
"""M15-C: inject cross-fitted conditional information into PatternEval targets.

One oracle-blind ``G1_WIDE_OUTCOME`` replay is generated per paired seed.
Complete games are assigned to deterministic folds, and every row receives a
conditional WDL prediction fitted without any row from its game.  The primary
causal comparison holds the amount of target smoothing fixed and changes only
whether the smoothing signal depends on the current state.
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
from run_pattern_value_target_screen import (  # noqa: E402
    _fit,
    _model_state_hash,
    _random_schedule,
    _sample_structure_fingerprint,
    estimate_power,
)

SCHEMA = "mini_jass.pattern_conditional_target_screen.v1"
ARM_ORDER = (
    "OUTCOME",
    "GLOBAL_BLEND_50",
    "SHUFFLED_CONTEXT_BLEND_50",
    "CONTEXT_BLEND_50",
    "CONTEXT_ONLY",
)
CONTRASTS = {
    "attribution_conditional_vs_shuffled": (
        "CONTEXT_BLEND_50",
        "SHUFFLED_CONTEXT_BLEND_50",
    ),
    "conditional_vs_global": ("CONTEXT_BLEND_50", "GLOBAL_BLEND_50"),
    "operational_conditional_vs_outcome": ("CONTEXT_BLEND_50", "OUTCOME"),
    "generic_smoothing_vs_outcome": ("GLOBAL_BLEND_50", "OUTCOME"),
    "mechanistic_context_only_vs_outcome": ("CONTEXT_ONLY", "OUTCOME"),
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
EXPECTED_C2_RESULT = "5bce01343ca2385485484ba6f46b7c0cf8c9d7bedc857010e9762de63abff9bd"
EXPECTED_C2_FREEZE = "b9cd48bf1469aa53765a3cf8fee5419b83ad772a3c42972b6c39d29f51a306eb"
EXPECTED_C3_RESULT = "15c4457809e73ef9e8db8f379433a3ac62c136c7e8ad02b62e3ca91707488ee3"
EXPECTED_C3_FREEZE = "3c4c795ce336b535c3c9d0ef98d99cd0c967719805848e6002914ad254f47cd4"


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != "M15-C":
        raise ValueError("unexpected M15-C schema")
    if tuple(config.get("arms", [])) != ARM_ORDER:
        raise ValueError("M15-C arms changed after preregistration")
    seeds = [int(seed) for seed in config.get("paired_seeds", [])]
    if seeds != list(range(272001, 272021)):
        raise ValueError("M15-C paired seeds changed or overlap prior evidence")

    evidence = config.get("source_evidence", {})
    expected = {
        "m14p": EXPECTED_M14_RESULT,
        "m21p": EXPECTED_M21_RESULT,
        "context_c2": EXPECTED_C2_RESULT,
        "context_c3": EXPECTED_C3_RESULT,
    }
    if any(evidence.get(name, {}).get("result_hash") != value for name, value in expected.items()):
        raise ValueError("M15-C source evidence result hashes are not frozen")
    if (
        evidence.get("m21p", {}).get("freeze_report_hash") != EXPECTED_M21_FREEZE
        or evidence.get("context_c2", {}).get("freeze_report_hash") != EXPECTED_C2_FREEZE
        or evidence.get("context_c3", {}).get("freeze_report_hash") != EXPECTED_C3_FREEZE
        or evidence.get("context_c2", {}).get("decision")
        != "REJECTED_COMBINED_EFFECT_NONPOSITIVE"
        or evidence.get("context_c3", {}).get("interpretation")
        != "LINEAR_CALIBRATION_GAP_OBSERVED"
        or evidence.get("m21p", {}).get("selected_replay_source")
        != "G1_WIDE_OUTCOME"
    ):
        raise ValueError("M15-C contextual evidence is not frozen")

    replay = config.get("replay", {})
    if (
        replay.get("source") != "G1_WIDE_OUTCOME"
        or int(replay.get("games_per_seed", 0)) != 1024
        or int(replay.get("generation", 0)) != 1
        or int(replay.get("seed_offset", 0)) != 880000
        or replay.get("row_selection") != "all_generated_train_rows"
        or replay.get("immutable_structure_across_arms") is not True
    ):
        raise ValueError("M15-C replay contract changed")

    mapping = config.get("conditional_mapping", {})
    if (
        mapping.get("family") != "odd_tanh_linear_wdl_oof_v1"
        or int(mapping.get("fold_count", 0)) != 5
        or mapping.get("fold_unit") != "complete_game"
        or mapping.get("fold_assignment") != "sha256_rank_round_robin_v1"
        or mapping.get("fold_namespace") != "m15c_conditional_wdl_game_folds_v1"
        or mapping.get("shuffle_control") != "within_fold_hash_order_rotate_one_v1"
        or mapping.get("shuffle_namespace") != "m15c_conditional_shuffle_v1"
        or mapping.get("initialization") != "zero"
        or mapping.get("training_label") != "terminal_selfplay_wdl"
        or mapping.get("oracle_training_signal") is not False
        or mapping.get("manual_coefficients_used") is not False
        or float(mapping.get("ridge", -1.0)) != 1.0e-4
        or int(mapping.get("max_iterations", 0)) != 64
        or float(mapping.get("tolerance", -1.0)) != 1.0e-10
        or int(mapping.get("line_search_steps", 0)) != 24
    ):
        raise ValueError("M15-C conditional mapping changed")

    targets = config.get("targets", {})
    if tuple(targets) != ARM_ORDER:
        raise ValueError("M15-C target order changed")
    if (
        targets["OUTCOME"].get("source") != "terminal_selfplay_wdl"
        or targets["GLOBAL_BLEND_50"].get("source") != "outcome_global_oof_blend"
        or targets["SHUFFLED_CONTEXT_BLEND_50"].get("source")
        != "outcome_shuffled_conditional_oof_blend"
        or targets["CONTEXT_BLEND_50"].get("source") != "outcome_conditional_oof_blend"
        or targets["CONTEXT_ONLY"].get("source") != "conditional_oof_prediction"
        or float(targets["GLOBAL_BLEND_50"].get("smoothing_weight", -1.0)) != 0.5
        or float(
            targets["SHUFFLED_CONTEXT_BLEND_50"].get("smoothing_weight", -1.0)
        )
        != 0.5
        or float(targets["CONTEXT_BLEND_50"].get("smoothing_weight", -1.0)) != 0.5
        or targets["CONTEXT_ONLY"].get("mechanistic_only") is not True
        or targets["SHUFFLED_CONTEXT_BLEND_50"].get("control_role")
        != "marginal_matched_broken_state_alignment"
    ):
        raise ValueError("M15-C target definitions changed")
    if any(targets[arm].get("oracle_training_signal") is not False for arm in ARM_ORDER):
        raise ValueError("M15-C targets must all be oracle-blind")

    gate = config.get("scientific_gate", {})
    minimum = 0.5 * float(evidence["m14p"]["zero_regret_exact_minus_outcome_mean"])
    if (
        gate.get("attribution_contrast")
        != "CONTEXT_BLEND_50_minus_SHUFFLED_CONTEXT_BLEND_50"
        or gate.get("operational_contrast") != "CONTEXT_BLEND_50_minus_OUTCOME"
        or gate.get("primary_endpoint") != "development_zero_regret_gain"
        or gate.get("require_both_contrasts_ci_above_zero") is not True
        or not math.isclose(
            float(gate.get("minimum_operational_gain", -1.0)),
            minimum,
            rel_tol=0.0,
            abs_tol=1.0e-15,
        )
        or gate.get("CONTEXT_ONLY_can_rescue_primary") is not False
        or gate.get("automatic_promotion") is not False
    ):
        raise ValueError("M15-C scientific gate changed")

    power = config.get("power_sizing", {})
    if (
        int(power.get("paired_seed_count", 0)) != len(seeds)
        or power.get("contrasts_sized")
        != [
            "CONTEXT_BLEND_50_minus_SHUFFLED_CONTEXT_BLEND_50",
            "CONTEXT_BLEND_50_minus_OUTCOME",
        ]
        or float(power.get("minimum_effect", -1.0)) != float(gate["minimum_operational_gain"])
        or int(power.get("repetitions", 0)) != 100000
        or int(power.get("seed", 0)) != 44120260812
        or float(power.get("conservative_paired_sd", -1.0)) != 0.005
        or float(power.get("paired_confidence_critical_95", -1.0))
        != 2.093024054408263
        or float(power.get("minimum_required_power", -1.0)) != 0.80
    ):
        raise ValueError("M15-C power input differs from the decision gate")
    observed_power = estimate_power(power)
    if not math.isclose(
        observed_power,
        float(power.get("estimated_power_ci_above_zero", -1.0)),
        rel_tol=0.0,
        abs_tol=5.0e-6,
    ):
        raise ValueError("M15-C frozen power result did not reproduce")
    if observed_power < float(power.get("minimum_required_power", 1.0)):
        raise ValueError("M15-C is underpowered before training")

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
        or boundaries.get("scientific_dependency_on_m15p_result") != "none"
    ):
        raise ValueError("M15-C crossed a scientific boundary")
    coordination = config.get("coordination", {})
    if (
        coordination.get("m15p_result_read_or_used_for_this_protocol") is not False
        or coordination.get("execution_is_not_queued_by_this_pr") is not True
    ):
        raise ValueError("M15-C became conditioned on M15-P or a queue action")

    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M15-C requires the frozen PatternEval loop")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M15-C requires folded PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M15-C cannot train a policy head")
    if int(replay["games_per_seed"]) != 8 * int(loop["self_play"]["games"]):
        raise ValueError("M15-C G1_WIDE dose differs from M21-P")
    schedule = config["training_schedule"]
    if (
        int(schedule["total_steps"]) != int(loop["training"]["steps"])
        or int(schedule["batch_size"]) != int(loop["training"]["batch_size"])
        or int(schedule.get("seed_offset", 0)) != 890000
        or schedule.get("explicit_identical_batch_schedule_all_arms") is not True
    ):
        raise ValueError("M15-C training schedule changed")
    arena = config["descriptive_strength_arena"]
    if (
        int(arena["pairs"]) != 128
        or int(arena.get("seed_base", 0)) != 951000
        or float(arena["epsilon"]) != 0.0
        or arena["confidence_unit"] != "pairs"
        or arena["start_state_source"] != "development"
    ):
        raise ValueError("M15-C descriptive arena changed")
    return deepcopy(config), loop


def build_target_arms(
    samples: list[ReplaySample],
    conditional_predictions: np.ndarray,
    shuffled_conditional_predictions: np.ndarray,
    state_blind_predictions: np.ndarray,
    exact_values: np.ndarray,
) -> tuple[dict[str, list[ReplaySample]], dict[str, Any]]:
    conditional = np.asarray(conditional_predictions, dtype=np.float64)
    shuffled = np.asarray(shuffled_conditional_predictions, dtype=np.float64)
    state_blind = np.asarray(state_blind_predictions, dtype=np.float64)
    if (
        conditional.shape != (len(samples),)
        or shuffled.shape != (len(samples),)
        or state_blind.shape != (len(samples),)
    ):
        raise ValueError("M15-C predictions must align with replay rows")
    if (
        not np.all(np.isfinite(conditional))
        or not np.all(np.isfinite(shuffled))
        or not np.all(np.isfinite(state_blind))
    ):
        raise ValueError("M15-C predictions must be finite")
    if (
        np.any(np.abs(conditional) > 1.0)
        or np.any(np.abs(shuffled) > 1.0)
        or np.any(np.abs(state_blind) > 1.0)
    ):
        raise ValueError("M15-C predictions left the WDL range")

    arms: dict[str, list[ReplaySample]] = {arm: [] for arm in ARM_ORDER}
    outcomes = np.asarray([sample.value_target for sample in samples], dtype=np.float64)
    for index, sample in enumerate(samples):
        values = {
            "OUTCOME": outcomes[index],
            "GLOBAL_BLEND_50": 0.5 * outcomes[index] + 0.5 * state_blind[index],
            "SHUFFLED_CONTEXT_BLEND_50": 0.5 * outcomes[index]
            + 0.5 * shuffled[index],
            "CONTEXT_BLEND_50": 0.5 * outcomes[index] + 0.5 * conditional[index],
            "CONTEXT_ONLY": conditional[index],
        }
        for arm, value in values.items():
            arms[arm].append(replace(sample, value_target=float(value)))

    structures = {arm: _sample_structure_fingerprint(rows) for arm, rows in arms.items()}
    if len(set(structures.values())) != 1:
        raise RuntimeError("M15-C target arms changed replay structure")
    state_ids = np.asarray([sample.state_id for sample in samples], dtype=np.int64)
    exact = np.asarray(exact_values)[state_ids].astype(np.float64)
    target_metrics: dict[str, Any] = {}
    for arm, rows in arms.items():
        values = np.asarray([sample.value_target for sample in rows], dtype=np.float64)
        target_metrics[arm] = {
            "sample_count": len(rows),
            "value_mae_vs_exact_train": float(np.mean(np.abs(values - exact))),
            "value_exact_rate_vs_exact_train": float(np.mean(values == exact)),
            "changed_from_outcome_fraction": float(np.mean(values != outcomes)),
            "target_mean": float(values.mean()),
            "target_standard_deviation": float(values.std(ddof=0)),
        }
    return arms, {
        "shared_structure_fingerprint": next(iter(structures.values())),
        "structure_fingerprints": structures,
        "targets": target_metrics,
    }


def build_contrasts(rows: list[dict[str, Any]], critical: float) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, (high, low) in CONTRASTS.items():
        result: dict[str, Any] = {"high": high, "low": low}
        for endpoint in ENDPOINTS:
            values = [
                float(row["arms"][high][endpoint]) - float(row["arms"][low][endpoint])
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
    attribution = contrasts["attribution_conditional_vs_shuffled"]["zero_regret_gain"]
    operational = contrasts["operational_conditional_vs_outcome"]["zero_regret_gain"]
    minimum = float(gate["minimum_operational_gain"])
    common = {
        "attribution_contrast": "CONTEXT_BLEND_50_minus_SHUFFLED_CONTEXT_BLEND_50",
        "attribution_mean": float(attribution["mean"]),
        "attribution_ci95": [float(attribution["lower"]), float(attribution["upper"])],
        "operational_contrast": "CONTEXT_BLEND_50_minus_OUTCOME",
        "operational_mean": float(operational["mean"]),
        "operational_ci95": [float(operational["lower"]), float(operational["upper"])],
        "minimum_operational_gain": minimum,
        "context_only_can_rescue_primary": False,
        "promotable": False,
    }
    if (
        float(attribution["lower"]) > 0.0
        and float(operational["lower"]) > 0.0
        and float(operational["mean"]) >= minimum
    ):
        return {
            **common,
            "status": "PASS",
            "finding": "aligned_conditional_targets_beat_marginal_matched_shuffle",
            "conditional_target_signal": True,
            "decision": "replicate_CONTEXT_BLEND_50_strength_on_fresh_seeds",
        }
    if float(attribution["upper"]) <= 0.0:
        return {
            **common,
            "status": "FAIL",
            "finding": "aligned_context_does_not_beat_marginal_matched_shuffle",
            "conditional_target_signal": False,
            "decision": "close_linear_conditional_target_injection",
        }
    if float(operational["upper"]) < minimum:
        return {
            **common,
            "status": "FAIL",
            "finding": "conditional_blend_excludes_practical_operational_gain",
            "conditional_target_signal": False,
            "decision": "close_linear_conditional_target_injection",
        }
    return {
        **common,
        "status": "INCONCLUSIVE",
        "finding": "conditional_target_effect_not_precise_at_preregistered_threshold",
        "conditional_target_signal": None,
        "decision": "power_size_fresh_M15C_replication_before_any_mechanism_claim",
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
            or replayed.get("milestone") != "M15-C"
            or replayed.get("result_hash") != result.get("result_hash")
            or replayed.get("recommendation", {}).get("finding")
            != result.get("recommendation", {}).get("finding")
        ):
            raise RuntimeError(f"M15-C reporting round-trip failed: {path}")


def _write_progress(
    path: Path | None, completed: int, total: int, last_seed: int, started: float
) -> None:
    if path is None:
        return
    elapsed = max(time.monotonic() - started, 1.0e-9)
    rate = completed / (elapsed / 60.0)
    payload = {
        "schema": "mini_jass.pattern_conditional_target_screen_progress.v1",
        "milestone": "M15-C",
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


def run_m15c(
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
        raise ValueError(f"M15-C requires cpx62, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError("M15-C split differs from the frozen L1 contract")
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
    mapping_spec = config["conditional_mapping"]
    for raw_seed in config["paired_seeds"]:
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
            sample for sample in generated.samples if bool(train_mask[int(sample.state_id)])
        ]
        if not train_samples:
            raise RuntimeError("M15-C generated no train-cohort replay rows")
        if not all(bool(train_mask[int(sample.state_id)]) for sample in train_samples):
            raise RuntimeError("M15-C consumed a non-train replay row")

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
            cross_fit["state_blind_predictions"],
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
                raise RuntimeError("M15-C arms did not share the initial PatternEval")
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
        for arm in ARM_ORDER:
            arena = run_arena(
                graph, models[arm], outcome_model, arena_config, arena_seed, development
            )
            start_hash = digest(arena["start_state_ids"])
            if arena_start_hash is None:
                arena_start_hash = start_hash
            elif start_hash != arena_start_hash:
                raise RuntimeError("M15-C arena starts diverged across arms")
            arm_rows[arm]["arena_score_minus_half"] = float(arena["score"]) - 0.5
            arm_rows[arm]["arena_vs_outcome"] = arena
        if arm_rows["OUTCOME"]["arena_score_minus_half"] != 0.0:
            raise RuntimeError("M15-C symmetric OUTCOME arena did not score 0.5")

        cross_fit_report = {
            key: value
            for key, value in cross_fit.items()
            if key not in {"fold_ids", "conditional_predictions", "state_blind_predictions"}
        }
        shuffle_report = {
            key: value
            for key, value in shuffled.items()
            if key not in {"predictions", "source_row_indices"}
        }
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
            "conditional_mapping": cross_fit_report,
            "shuffle_control": shuffle_report,
            "arms": arm_rows,
        }
        rows.append(row)
        (run_dir / f"seed-{seed}.json").write_text(
            json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        _write_progress(progress_output, len(rows), len(config["paired_seeds"]), seed, started)

    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    contrasts = build_contrasts(rows, critical)
    mapping_gain = paired_interval(
        [
            float(row["conditional_mapping"]["conditional_mse_gain_vs_state_blind"])
            for row in rows
        ],
        critical,
    )
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
        "conditional_mapping_oof_mse_gain_vs_state_blind": mapping_gain,
        "mean_train_sample_count": mean(row["replay"]["train_sample_count"] for row in rows),
        "all_training_rows_train_only": True,
        "all_cross_fit_games_disjoint": all(
            bool(row["conditional_mapping"]["all_games_fold_disjoint"]) for row in rows
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
    recommendation = build_recommendation(contrasts, config["scientific_gate"])
    protocol = {
        "schema": SCHEMA,
        "milestone": "M15-C",
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "arms": list(ARM_ORDER),
        "replay": config["replay"],
        "conditional_mapping": config["conditional_mapping"],
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
        "milestone": "M15-C",
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
    args = parser.parse_args()
    result = run_m15c(
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
