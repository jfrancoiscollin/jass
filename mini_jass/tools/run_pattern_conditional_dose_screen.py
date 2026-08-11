#!/usr/bin/env python3
"""M15-C2/M15-C2R: screen and replicate conditional-target doses."""

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
from run_pattern_temporal_value_target_screen import (  # noqa: E402
    build_target_arms as build_temporal_target_arms,
)

SCHEMA = "mini_jass.pattern_conditional_dose_screen.v1"
PROBE_SCHEMA = "mini_jass.pattern_conditional_dose_screen_probe.v1"
REPLICATION_SCHEMA = "mini_jass.pattern_conditional_dose_replication.v1"
REPLICATION_PROBE_SCHEMA = "mini_jass.pattern_conditional_dose_replication_probe.v1"
COMPOSITION_SCHEMA = "mini_jass.pattern_conditional_temporal_composition.v1"
COMPOSITION_PROBE_SCHEMA = (
    "mini_jass.pattern_conditional_temporal_composition_probe.v1"
)
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

REPLICATION_ARM_ORDER = (
    "OUTCOME",
    "SHUFFLED_CONTEXT_30",
    "CONTEXT_30",
    "SHUFFLED_CONTEXT_40",
    "CONTEXT_40",
)
REPLICATION_DOSES = (0.30, 0.40)
REPLICATION_ARENA_ARMS = REPLICATION_ARM_ORDER
REPLICATION_CONTRASTS = {
    "attribution_30": ("CONTEXT_30", "SHUFFLED_CONTEXT_30"),
    "operational_30": ("CONTEXT_30", "OUTCOME"),
    "attribution_40": ("CONTEXT_40", "SHUFFLED_CONTEXT_40"),
    "operational_40": ("CONTEXT_40", "OUTCOME"),
    "dose_40_minus_30": ("CONTEXT_40", "CONTEXT_30"),
}
REPLICATION_ARENA_CONTRASTS = REPLICATION_CONTRASTS

COMPOSITION_ARM_ORDER = (
    "OUTCOME",
    "LAMBDA_50",
    "SHUFFLED_CONTEXT_30",
    "CONTEXT_30",
    "SHUFFLED_COMPOSED_30",
    "COMPOSED_30",
)
COMPOSITION_ARENA_ARMS = COMPOSITION_ARM_ORDER
COMPOSITION_CONTRASTS = {
    "primary_temporal_increment": ("COMPOSED_30", "CONTEXT_30"),
    "temporal_increment_control": (
        "SHUFFLED_COMPOSED_30",
        "SHUFFLED_CONTEXT_30",
    ),
    "composition_attribution": ("COMPOSED_30", "SHUFFLED_COMPOSED_30"),
    "context_attribution": ("CONTEXT_30", "SHUFFLED_CONTEXT_30"),
    "composition_operational": ("COMPOSED_30", "OUTCOME"),
    "context_operational": ("CONTEXT_30", "OUTCOME"),
    "temporal_operational": ("LAMBDA_50", "OUTCOME"),
    "composition_vs_temporal": ("COMPOSED_30", "LAMBDA_50"),
}
COMPOSITION_ARENA_CONTRASTS = COMPOSITION_CONTRASTS

EXPECTED_M15C_PROTOCOL = "74dc555948e0191c09814098918c35e2e23935cf6ff44801c6c09165ad97502d"
EXPECTED_M15C_RESULT = "b63008f3e685c5cf20ae18af4e389fa8f7308ae31aa6525e549244f6f80e499d"
EXPECTED_M15C2_PROTOCOL = "b561f1feab4b21012a80f1e3c5e402bacfccded37ccc738020c47e065a0662bf"
EXPECTED_M15C2_RESULT = "2f839078622bc8c5393fc16a46060ef20a47d0c3545b95caedcad1ae0f927b0d"


def _resolve(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    identity = (config.get("schema"), config.get("milestone"))
    if identity == (SCHEMA, "M15-C2"):
        return _resolve_m15c2(path)
    if identity == (REPLICATION_SCHEMA, "M15-C2R"):
        return _resolve_replication(path, config)
    if identity == (COMPOSITION_SCHEMA, "M15-C3"):
        return _resolve_composition(path, config)
    raise ValueError("unexpected M15-C2/M15-C2R/M15-C3 schema")


def _resolve_m15c2(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
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


def _resolve_replication(
    path: Path, config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if tuple(config.get("arms", [])) != REPLICATION_ARM_ORDER:
        raise ValueError("M15-C2R arms changed after preregistration")
    seeds = [int(seed) for seed in config.get("paired_seeds", [])]
    if seeds != list(range(275001, 275021)):
        raise ValueError("M15-C2R paired seeds changed or overlap prior evidence")
    probe = config.get("probe", {})
    if (
        int(probe.get("seed", -1)) != 275000
        or probe.get("overlaps_scientific_seeds") is not False
        or probe.get("purpose") != "cpx62_runtime_calibration_only"
        or probe.get("reporting") != "timing_and_contract_only"
        or probe.get("scientific_metrics_must_not_be_published") is not True
    ):
        raise ValueError("M15-C2R probe contract changed")

    evidence = config.get("source_evidence", {}).get("m15c2", {})
    if (
        evidence.get("protocol_hash") != EXPECTED_M15C2_PROTOCOL
        or evidence.get("result_hash") != EXPECTED_M15C2_RESULT
        or evidence.get("status") != "PASS"
        or evidence.get("finding")
        != "interior_conditional_dose_confirms_positive_static_signal"
        or evidence.get("mechanism_status") != "PASS"
        or evidence.get("operational_status") != "PASS"
        or evidence.get("strength_status") != "PASS"
        or float(evidence.get("attribution_ci95", [0.0])[0]) <= 0.0
        or float(evidence.get("operational_ci95", [0.0])[0]) <= 0.0
        or float(evidence.get("arena_attribution_ci95", [0.0])[0]) <= 0.0
        or float(evidence.get("arena_operational_ci95", [0.0])[0]) <= 0.0
        or float(
            evidence.get(
                "exploratory_CONTEXT_40_minus_CONTEXT_30_static_ci95", [0.0]
            )[0]
        )
        <= 0.0
        or int(
            evidence.get(
                "exploratory_CONTEXT_40_minus_CONTEXT_30_positive_seed_count", 0
            )
        )
        != 20
        or evidence.get("alpha_40_strength_was_not_measured") is not True
        or evidence.get("interpretation_for_replication")
        != "ALPHA30_CONFIRMED_DISCOVERY_ALPHA40_STATIC_SUPERIORITY_NEEDS_FRESH_REPLICATION"
    ):
        raise ValueError("M15-C2R source evidence is not frozen")

    replay = config.get("replay", {})
    if (
        replay.get("source") != "G1_WIDE_OUTCOME"
        or int(replay.get("games_per_seed", 0)) != 1024
        or int(replay.get("generation", 0)) != 1
        or int(replay.get("seed_offset", 0)) != 1000000
        or replay.get("row_selection") != "all_generated_train_rows"
        or replay.get("immutable_structure_across_arms") is not True
    ):
        raise ValueError("M15-C2R replay contract changed")

    mapping = config.get("conditional_mapping", {})
    if (
        mapping.get("family") != "odd_tanh_linear_wdl_oof_v1"
        or int(mapping.get("fold_count", 0)) != 5
        or mapping.get("fold_unit") != "complete_game"
        or mapping.get("fold_assignment") != "sha256_rank_round_robin_v1"
        or mapping.get("fold_namespace") != "m15c2r_conditional_wdl_game_folds_v1"
        or mapping.get("shuffle_control") != "within_fold_hash_order_rotate_one_v1"
        or mapping.get("shuffle_namespace") != "m15c2r_conditional_shuffle_v1"
        or mapping.get("initialization") != "zero"
        or mapping.get("training_label") != "terminal_selfplay_wdl"
        or mapping.get("oracle_training_signal") is not False
        or mapping.get("manual_coefficients_used") is not False
        or float(mapping.get("ridge", -1.0)) != 1.0e-4
        or int(mapping.get("max_iterations", 0)) != 64
        or float(mapping.get("tolerance", -1.0)) != 1.0e-10
        or int(mapping.get("line_search_steps", 0)) != 24
    ):
        raise ValueError("M15-C2R conditional mapping changed")

    dose = config.get("dose_replication", {})
    if (
        dose.get("target_formula")
        != "(1-alpha)*outcome+alpha*conditional_prediction"
        or float(dose.get("primary_alpha", -1.0)) != 0.30
        or float(dose.get("secondary_alpha", -1.0)) != 0.40
        or dose.get("secondary_cannot_rescue_primary") is not True
        or dose.get(
            "secondary_selection_requires_direct_static_and_strength_superiority"
        )
        is not True
        or dose.get("every_target_oracle_blind") is not True
    ):
        raise ValueError("M15-C2R dose contract changed")

    gate = config.get("scientific_gate", {})
    if (
        float(gate.get("primary_alpha", -1.0)) != 0.30
        or gate.get("primary_endpoint") != "development_zero_regret_gain"
        or float(gate.get("paired_confidence_critical_95", -1.0))
        != 2.093024054408263
        or gate.get("primary_replication_requires_static_attribution_ci_above_zero")
        is not True
        or gate.get("primary_replication_requires_static_operational_ci_above_zero")
        is not True
        or gate.get("primary_replication_requires_strength_attribution_ci_above_zero")
        is not True
        or gate.get("primary_replication_requires_strength_operational_ci_above_zero")
        is not True
        or float(gate.get("minimum_effect_floor", -1.0)) != 0.0
        or float(gate.get("secondary_alpha", -1.0)) != 0.40
        or gate.get("secondary_cannot_rescue_primary") is not True
        or gate.get("secondary_requires_own_static_and_strength_controls") is not True
        or gate.get(
            "select_secondary_requires_CONTEXT_40_minus_CONTEXT_30_static_ci_above_zero"
        )
        is not True
        or gate.get(
            "select_secondary_requires_CONTEXT_40_minus_CONTEXT_30_strength_ci_above_zero"
        )
        is not True
        or gate.get("otherwise_retain_primary_alpha") is not True
        or gate.get("automatic_promotion") is not False
    ):
        raise ValueError("M15-C2R scientific gate changed")

    power = config.get("power_sizing", {})
    expected_power = {
        "primary_replication": {
            "contrasts": [
                "CONTEXT_30_minus_SHUFFLED_CONTEXT_30",
                "CONTEXT_30_minus_OUTCOME",
            ],
            "seed": 44120260816,
            "sd": 0.0025,
            "effect": 0.002,
            "estimate": 0.92362,
        },
        "secondary_40_minus_30": {
            "contrasts": ["CONTEXT_40_minus_CONTEXT_30"],
            "seed": 44120260817,
            "sd": 0.001,
            "effect": 0.0007,
            "estimate": 0.8442,
        },
    }
    for name, expected in expected_power.items():
        cell = power.get(name, {})
        if (
            cell.get("contrasts_sized") != expected["contrasts"]
            or int(cell.get("repetitions", 0)) != 100000
            or int(cell.get("seed", 0)) != expected["seed"]
            or int(cell.get("paired_seed_count", 0)) != len(seeds)
            or float(cell.get("conservative_paired_sd", -1.0)) != expected["sd"]
            or float(cell.get("minimum_effect_for_power_only", -1.0))
            != expected["effect"]
            or float(cell.get("minimum_effect", -1.0)) != expected["effect"]
            or float(cell.get("paired_confidence_critical_95", -1.0))
            != 2.093024054408263
            or cell.get("gate_has_no_minimum_effect_floor") is not True
        ):
            raise ValueError(f"M15-C2R {name} power contract changed")
        observed_power = estimate_power(cell)
        if not math.isclose(
            observed_power,
            float(cell.get("estimated_power_ci_above_zero", -1.0)),
            rel_tol=0.0,
            abs_tol=5.0e-6,
        ):
            raise ValueError(f"M15-C2R {name} frozen power did not reproduce")
        if observed_power < float(cell.get("minimum_required_power", 1.0)):
            raise ValueError(f"M15-C2R {name} is underpowered before training")

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
        raise ValueError("M15-C2R crossed a scientific boundary")

    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M15-C2R requires the frozen PatternEval loop")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M15-C2R requires folded PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M15-C2R cannot train a policy head")
    schedule = config["training_schedule"]
    if (
        int(schedule["total_steps"]) != int(loop["training"]["steps"])
        or int(schedule["batch_size"]) != int(loop["training"]["batch_size"])
        or int(schedule.get("seed_offset", 0)) != 1010000
        or schedule.get("explicit_identical_batch_schedule_all_arms") is not True
    ):
        raise ValueError("M15-C2R training schedule changed")
    arena = config["strength_arena"]
    if (
        tuple(arena.get("arms", [])) != REPLICATION_ARENA_ARMS
        or int(arena.get("pairs", 0)) != 512
        or int(arena.get("seed_base", 0)) != 1020000
        or float(arena.get("epsilon", -1.0)) != 0.0
        or arena.get("confidence_unit") != "pairs"
        or arena.get("start_state_source") != "development"
        or arena.get("role") != "confirmatory_strength_replication"
    ):
        raise ValueError("M15-C2R strength arena changed")
    return deepcopy(config), loop


def _resolve_composition(
    path: Path, config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    if tuple(config.get("arms", [])) != COMPOSITION_ARM_ORDER:
        raise ValueError("M15-C3 arms changed after preregistration")
    seeds = [int(seed) for seed in config.get("paired_seeds", [])]
    if seeds != list(range(276001, 276025)):
        raise ValueError("M15-C3 paired seeds changed or overlap prior evidence")
    probe = config.get("probe", {})
    if (
        int(probe.get("seed", -1)) != 276000
        or probe.get("overlaps_scientific_seeds") is not False
        or probe.get("purpose") != "cpx62_runtime_calibration_only"
        or probe.get("reporting") != "timing_and_contract_only"
        or probe.get("scientific_metrics_must_not_be_published") is not True
    ):
        raise ValueError("M15-C3 probe contract changed")

    evidence = config.get("source_evidence", {})
    m15c2r = evidence.get("m15c2r", {})
    if (
        m15c2r.get("protocol_hash")
        != "f355c6a1fccebd01f4b67d9b7cf59e239ebe3ab127cb38f4efedcf7e5b44ce8e"
        or m15c2r.get("result_hash")
        != "d240e5c006b9e7463221bbae4e639d80dbc8773840c2310b64ed9df1bd45ae25"
        or m15c2r.get("status") != "PASS"
        or m15c2r.get("finding") != "alpha_30_conditional_signal_replicates"
        or m15c2r.get("decision") != "prepare_alpha_30_temporal_composition"
        or float(m15c2r.get("retained_alpha", -1.0)) != 0.30
        or m15c2r.get("primary_replication_status") != "PASS"
        or any(
            float(m15c2r.get(name, [0.0])[0]) <= 0.0
            for name in (
                "primary_static_attribution_ci95",
                "primary_static_operational_ci95",
                "primary_strength_attribution_ci95",
                "primary_strength_operational_ci95",
            )
        )
        or float(m15c2r.get("alpha_40_static_superiority_ci95", [0.0])[0])
        <= 0.0
        or not (
            float(m15c2r.get("alpha_40_strength_superiority_ci95", [1.0])[0])
            < 0.0
            < float(m15c2r.get("alpha_40_strength_superiority_ci95", [-1.0, -1.0])[1])
        )
    ):
        raise ValueError("M15-C3 M15-C2R evidence is not frozen")
    m16p = evidence.get("m16p", {})
    if (
        m16p.get("protocol_hash")
        != "1b27d35edef11ff945f574cb807d6a6fee6fe4f4f41a045681bbbd223fc8c728"
        or m16p.get("result_hash")
        != "23eeaf1d310dc95a1aa8eb0d7937125d4304d641a843b9261cf7b154dfd2b385"
        or m16p.get("immutable_report_status") != "FAIL"
        or m16p.get("retained_experience_status") != "POSITIVE"
        or m16p.get("mechanism_status") != "CONFIRMED"
        or m16p.get("major_recovery_gate_status") != "NOT_MET"
        or m16p.get("downstream_decision")
        != "retain_LAMBDA_50_for_composition_and_fresh_strength_confirmation"
        or float(m16p.get("lambda_50_zero_regret_ci95", [0.0])[0]) <= 0.0
        or float(m16p.get("lambda_50_strength_ci95", [0.0])[0]) <= 0.0
    ):
        raise ValueError("M15-C3 M16-P evidence is not frozen")

    replay = config.get("replay", {})
    if (
        replay.get("source") != "G1_WIDE_OUTCOME"
        or int(replay.get("games_per_seed", 0)) != 1024
        or int(replay.get("generation", 0)) != 1
        or int(replay.get("seed_offset", 0)) != 1030000
        or replay.get("row_selection") != "all_generated_train_rows"
        or replay.get("temporal_returns_built_before_train_row_filter") is not True
        or replay.get("immutable_structure_across_arms") is not True
    ):
        raise ValueError("M15-C3 replay contract changed")

    mapping = config.get("conditional_mapping", {})
    if (
        mapping.get("family") != "odd_tanh_linear_wdl_oof_v1"
        or int(mapping.get("fold_count", 0)) != 5
        or mapping.get("fold_unit") != "complete_game"
        or mapping.get("fold_assignment") != "sha256_rank_round_robin_v1"
        or mapping.get("fold_namespace") != "m15c3_conditional_wdl_game_folds_v1"
        or mapping.get("shuffle_control") != "within_fold_hash_order_rotate_one_v1"
        or mapping.get("shuffle_namespace") != "m15c3_conditional_shuffle_v1"
        or mapping.get("initialization") != "zero"
        or mapping.get("training_label") != "terminal_selfplay_wdl"
        or mapping.get("oracle_training_signal") is not False
        or mapping.get("manual_coefficients_used") is not False
        or float(mapping.get("ridge", -1.0)) != 1.0e-4
        or int(mapping.get("max_iterations", 0)) != 64
        or float(mapping.get("tolerance", -1.0)) != 1.0e-10
        or int(mapping.get("line_search_steps", 0)) != 24
    ):
        raise ValueError("M15-C3 conditional mapping changed")

    temporal = config.get("temporal_target", {})
    if (
        temporal.get("source") != "temporal_lambda_return"
        or float(temporal.get("lambda", -1.0)) != 0.50
        or temporal.get("successor_bootstrap") != "negated_successor_root_score"
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
        raise ValueError("M15-C3 temporal target changed")

    composition = config.get("composition", {})
    if (
        float(composition.get("alpha", -1.0)) != 0.30
        or composition.get("outcome_context_formula")
        != "0.70*outcome+0.30*conditional_prediction"
        or composition.get("temporal_context_formula")
        != "0.70*lambda_50+0.30*conditional_prediction"
        or composition.get("shuffled_controls_use_same_formula") is not True
        or composition.get("every_target_convex_and_bounded") is not True
        or composition.get("every_target_oracle_blind") is not True
    ):
        raise ValueError("M15-C3 composition formula changed")

    gate = config.get("scientific_gate", {})
    if (
        gate.get("primary_question")
        != "temporal_increment_and_conditional_attribution_survive_composition"
        or gate.get("primary_endpoint")
        != "development_zero_regret_gain_and_paired_strength"
        or float(gate.get("paired_confidence_critical_95", -1.0))
        != 2.0686576104190406
        or gate.get("require_COMPOSED_30_minus_CONTEXT_30_static_ci_above_zero")
        is not True
        or gate.get("require_COMPOSED_30_minus_CONTEXT_30_strength_ci_above_zero")
        is not True
        or gate.get(
            "require_COMPOSED_30_minus_SHUFFLED_COMPOSED_30_static_ci_above_zero"
        )
        is not True
        or gate.get(
            "require_COMPOSED_30_minus_SHUFFLED_COMPOSED_30_strength_ci_above_zero"
        )
        is not True
        or float(gate.get("minimum_effect_floor", -1.0)) != 0.0
        or gate.get("singleton_confirmation_cannot_rescue_primary") is not True
        or gate.get(
            "selection_requires_COMPOSED_30_minus_LAMBDA_50_static_ci_above_zero"
        )
        is not True
        or gate.get(
            "selection_requires_COMPOSED_30_minus_LAMBDA_50_strength_ci_above_zero"
        )
        is not True
        or gate.get(
            "selection_requires_COMPOSED_30_minus_OUTCOME_static_ci_above_zero"
        )
        is not True
        or gate.get(
            "selection_requires_COMPOSED_30_minus_OUTCOME_strength_ci_above_zero"
        )
        is not True
        or gate.get("otherwise_retain_incumbent_CONTEXT_30") is not True
        or gate.get("automatic_promotion") is not False
    ):
        raise ValueError("M15-C3 scientific gate changed")

    expected_power = {
        "temporal_increment_static": (44120260818, 0.0025, 0.0015, 0.80433),
        "temporal_increment_strength": (44120260819, 0.005, 0.0035, 0.90648),
        "conditional_attribution_static": (44120260820, 0.0025, 0.002, 0.96424),
        "conditional_attribution_strength": (44120260821, 0.0025, 0.0015, 0.80359),
    }
    for name, (power_seed, sd, effect, estimate) in expected_power.items():
        cell = config.get("power_sizing", {}).get(name, {})
        if (
            int(cell.get("repetitions", 0)) != 100000
            or int(cell.get("seed", 0)) != power_seed
            or int(cell.get("paired_seed_count", 0)) != len(seeds)
            or float(cell.get("conservative_paired_sd", -1.0)) != sd
            or float(cell.get("minimum_effect_for_power_only", -1.0)) != effect
            or float(cell.get("minimum_effect", -1.0)) != effect
            or float(cell.get("paired_confidence_critical_95", -1.0))
            != 2.0686576104190406
            or cell.get("gate_has_no_minimum_effect_floor") is not True
        ):
            raise ValueError(f"M15-C3 {name} power contract changed")
        observed_power = estimate_power(cell)
        if not math.isclose(observed_power, estimate, rel_tol=0.0, abs_tol=5.0e-6):
            raise ValueError(f"M15-C3 {name} frozen power did not reproduce")
        if observed_power < float(cell.get("minimum_required_power", 1.0)):
            raise ValueError(f"M15-C3 {name} is underpowered before training")

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
        raise ValueError("M15-C3 crossed a scientific boundary")

    root = path.resolve().parent.parent
    loop = yaml.safe_load((root / config["base_loop_config"]).read_text(encoding="utf-8"))
    if loop.get("schema") != "mini_jass.selfplay.v1":
        raise ValueError("M15-C3 requires the frozen PatternEval loop")
    if loop["model"].get("architecture") != "folded_pattern_value":
        raise ValueError("M15-C3 requires folded PatternEval")
    if float(loop["training"]["policy_weight"]) != 0.0:
        raise ValueError("M15-C3 cannot train a policy head")
    schedule = config["training_schedule"]
    if (
        int(schedule["total_steps"]) != int(loop["training"]["steps"])
        or int(schedule["batch_size"]) != int(loop["training"]["batch_size"])
        or int(schedule.get("seed_offset", 0)) != 1040000
        or schedule.get("explicit_identical_batch_schedule_all_arms") is not True
    ):
        raise ValueError("M15-C3 training schedule changed")
    arena = config["strength_arena"]
    if (
        tuple(arena.get("arms", [])) != COMPOSITION_ARENA_ARMS
        or int(arena.get("pairs", 0)) != 512
        or int(arena.get("seed_base", 0)) != 1050000
        or float(arena.get("epsilon", -1.0)) != 0.0
        or arena.get("confidence_unit") != "pairs"
        or arena.get("start_state_source") != "development"
        or arena.get("role") != "confirmatory_composition_strength"
    ):
        raise ValueError("M15-C3 strength arena changed")
    return deepcopy(config), loop


def build_target_arms(
    samples: list[ReplaySample],
    conditional_predictions: np.ndarray,
    shuffled_predictions: np.ndarray,
    exact_values: np.ndarray,
    doses: tuple[float, ...] = DOSES,
    arm_order: tuple[str, ...] = ARM_ORDER,
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
    for alpha in doses:
        suffix = int(round(100 * alpha))
        values[f"SHUFFLED_CONTEXT_{suffix}"] = (1.0 - alpha) * outcomes + alpha * shuffled
        values[f"CONTEXT_{suffix}"] = (1.0 - alpha) * outcomes + alpha * conditional
    arms = {
        arm: [
            replace(sample, value_target=float(value))
            for sample, value in zip(samples, values[arm], strict=True)
        ]
        for arm in arm_order
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
        for arm in arm_order
    }
    return arms, {
        "shared_structure_fingerprint": next(iter(structures.values())),
        "structure_fingerprints": structures,
        "targets": target_metrics,
    }


def build_composition_target_arms(
    samples: list[ReplaySample],
    temporal_samples: list[ReplaySample],
    conditional_predictions: np.ndarray,
    shuffled_predictions: np.ndarray,
    exact_values: np.ndarray,
) -> tuple[dict[str, list[ReplaySample]], dict[str, Any]]:
    if len(samples) != len(temporal_samples) or not samples:
        raise ValueError("M15-C3 temporal and conditional rows must align")
    for outcome_row, temporal_row in zip(samples, temporal_samples, strict=True):
        if (
            int(outcome_row.state_id) != int(temporal_row.state_id)
            or int(outcome_row.game_id) != int(temporal_row.game_id)
            or int(outcome_row.ply) != int(temporal_row.ply)
        ):
            raise ValueError("M15-C3 temporal row identity diverged")

    conditional = np.asarray(conditional_predictions, dtype=np.float64)
    shuffled = np.asarray(shuffled_predictions, dtype=np.float64)
    temporal = np.asarray(
        [sample.value_target for sample in temporal_samples], dtype=np.float64
    )
    outcomes = np.asarray(
        [sample.value_target for sample in samples], dtype=np.float64
    )
    expected_shape = (len(samples),)
    if any(
        values.shape != expected_shape
        for values in (conditional, shuffled, temporal, outcomes)
    ):
        raise ValueError("M15-C3 target components must align with replay rows")
    if not all(
        np.all(np.isfinite(values))
        for values in (conditional, shuffled, temporal, outcomes)
    ):
        raise ValueError("M15-C3 target components must be finite")
    if any(
        np.any(np.abs(values) > 1.0)
        for values in (conditional, shuffled, temporal, outcomes)
    ):
        raise ValueError("M15-C3 target component left the WDL range")

    values: dict[str, np.ndarray] = {
        "OUTCOME": outcomes,
        "LAMBDA_50": temporal,
        "SHUFFLED_CONTEXT_30": 0.70 * outcomes + 0.30 * shuffled,
        "CONTEXT_30": 0.70 * outcomes + 0.30 * conditional,
        "SHUFFLED_COMPOSED_30": 0.70 * temporal + 0.30 * shuffled,
        "COMPOSED_30": 0.70 * temporal + 0.30 * conditional,
    }
    if any(np.any(np.abs(target) > 1.0) for target in values.values()):
        raise RuntimeError("M15-C3 convex target left the WDL range")
    arms = {
        arm: [
            replace(sample, value_target=float(value))
            for sample, value in zip(samples, values[arm], strict=True)
        ]
        for arm in COMPOSITION_ARM_ORDER
    }
    structures = {arm: _sample_structure_fingerprint(rows) for arm, rows in arms.items()}
    if len(set(structures.values())) != 1:
        raise RuntimeError("M15-C3 target arms changed replay structure")

    state_ids = np.asarray([sample.state_id for sample in samples], dtype=np.int64)
    exact = np.asarray(exact_values)[state_ids].astype(np.float64)
    target_metrics = {
        arm: {
            "sample_count": len(samples),
            "value_mae_vs_exact_train": float(np.mean(np.abs(values[arm] - exact))),
            "value_exact_rate_vs_exact_train": float(np.mean(values[arm] == exact)),
            "changed_from_outcome_fraction": float(
                np.mean(values[arm] != outcomes)
            ),
            "target_mean": float(values[arm].mean()),
            "target_standard_deviation": float(values[arm].std(ddof=0)),
        }
        for arm in COMPOSITION_ARM_ORDER
    }
    return arms, {
        "shared_structure_fingerprint": next(iter(structures.values())),
        "structure_fingerprints": structures,
        "targets": target_metrics,
        "all_targets_convex_and_bounded": True,
        "all_targets_oracle_blind": True,
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


def build_contrasts(
    rows: list[dict[str, Any]],
    critical: float,
    contrast_spec: dict[str, tuple[str, str]] = CONTRASTS,
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name, (high, low) in contrast_spec.items():
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
    rows: list[dict[str, Any]],
    critical: float,
    contrast_spec: dict[str, tuple[str, str]] = ARENA_CONTRASTS,
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
        for name, (high, low) in contrast_spec.items()
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


def _group_status(intervals: list[dict[str, Any]]) -> str:
    if all(float(interval["lower"]) > 0.0 for interval in intervals):
        return "PASS"
    if any(float(interval["upper"]) <= 0.0 for interval in intervals):
        return "FAIL"
    return "INCONCLUSIVE"


def build_replication_recommendation(
    contrasts: dict[str, Any], arena_contrasts: dict[str, Any]
) -> dict[str, Any]:
    def static(name: str) -> dict[str, Any]:
        return contrasts[name]["zero_regret_gain"]

    def strength(name: str) -> dict[str, Any]:
        return arena_contrasts[name]["arena_score_minus_half"]

    primary_axes = [
        static("attribution_30"),
        static("operational_30"),
        strength("attribution_30"),
        strength("operational_30"),
    ]
    secondary_control_axes = [
        static("attribution_40"),
        static("operational_40"),
        strength("attribution_40"),
        strength("operational_40"),
    ]
    dose_superiority_axes = [
        static("dose_40_minus_30"),
        strength("dose_40_minus_30"),
    ]
    primary_status = _group_status(primary_axes)
    secondary_control_status = _group_status(secondary_control_axes)
    dose_superiority_status = _group_status(dose_superiority_axes)

    common = {
        "primary_alpha": 0.30,
        "secondary_alpha": 0.40,
        "primary_replication_status": primary_status,
        "secondary_control_status": secondary_control_status,
        "dose_40_minus_30_status": dose_superiority_status,
        "primary_static_attribution": static("attribution_30"),
        "primary_static_operational": static("operational_30"),
        "primary_strength_attribution": strength("attribution_30"),
        "primary_strength_operational": strength("operational_30"),
        "secondary_static_attribution": static("attribution_40"),
        "secondary_static_operational": static("operational_40"),
        "secondary_strength_attribution": strength("attribution_40"),
        "secondary_strength_operational": strength("operational_40"),
        "dose_40_minus_30_static": static("dose_40_minus_30"),
        "dose_40_minus_30_strength": strength("dose_40_minus_30"),
        "secondary_can_rescue_primary": False,
        "minimum_effect_floor": 0.0,
        "promotable": False,
    }
    if primary_status == "FAIL":
        return {
            **common,
            "status": "FAIL",
            "retained_alpha": None,
            "finding": "alpha_30_conditional_signal_does_not_replicate",
            "decision": "do_not_compose_unreplicated_conditional_target",
        }
    if primary_status == "INCONCLUSIVE":
        return {
            **common,
            "status": "INCONCLUSIVE",
            "retained_alpha": None,
            "finding": "alpha_30_conditional_replication_is_not_precise",
            "decision": "power_size_fresh_alpha_30_replication",
        }
    if secondary_control_status == "PASS" and dose_superiority_status == "PASS":
        return {
            **common,
            "status": "PASS",
            "retained_alpha": 0.40,
            "finding": "alpha_30_replicates_and_alpha_40_is_superior",
            "decision": "prepare_alpha_40_temporal_composition",
        }
    return {
        **common,
        "status": "PASS",
        "retained_alpha": 0.30,
        "finding": "alpha_30_conditional_signal_replicates",
        "decision": "prepare_alpha_30_temporal_composition",
    }


def build_composition_interactions(
    rows: list[dict[str, Any]], critical: float
) -> dict[str, Any]:
    static: dict[str, Any] = {}
    for endpoint in STATIC_ENDPOINTS:
        static[endpoint] = _interval(
            [
                (
                    float(row["arms"]["COMPOSED_30"][endpoint])
                    - float(row["arms"]["SHUFFLED_COMPOSED_30"][endpoint])
                )
                - (
                    float(row["arms"]["CONTEXT_30"][endpoint])
                    - float(row["arms"]["SHUFFLED_CONTEXT_30"][endpoint])
                )
                for row in rows
            ],
            critical,
        )
    strength = _interval(
        [
            (
                float(row["arms"]["COMPOSED_30"]["arena_score_minus_half"])
                - float(
                    row["arms"]["SHUFFLED_COMPOSED_30"][
                        "arena_score_minus_half"
                    ]
                )
            )
            - (
                float(row["arms"]["CONTEXT_30"]["arena_score_minus_half"])
                - float(
                    row["arms"]["SHUFFLED_CONTEXT_30"][
                        "arena_score_minus_half"
                    ]
                )
            )
            for row in rows
        ],
        critical,
    )
    return {
        "conditional_by_temporal_difference_in_differences": {
            "static": static,
            "strength": strength,
            "role": "descriptive_interaction_not_a_primary_rescue",
        }
    }


def build_composition_recommendation(
    contrasts: dict[str, Any],
    arena_contrasts: dict[str, Any],
    interactions: dict[str, Any],
) -> dict[str, Any]:
    def static(name: str) -> dict[str, Any]:
        return contrasts[name]["zero_regret_gain"]

    def strength(name: str) -> dict[str, Any]:
        return arena_contrasts[name]["arena_score_minus_half"]

    temporal_increment_axes = [
        static("primary_temporal_increment"),
        strength("primary_temporal_increment"),
    ]
    conditional_attribution_axes = [
        static("composition_attribution"),
        strength("composition_attribution"),
    ]
    primary_axes = temporal_increment_axes + conditional_attribution_axes
    selection_axes = [
        static("composition_vs_temporal"),
        strength("composition_vs_temporal"),
        static("composition_operational"),
        strength("composition_operational"),
    ]
    temporal_confirmation_axes = [
        static("temporal_operational"),
        strength("temporal_operational"),
    ]
    context_confirmation_axes = [
        static("context_attribution"),
        strength("context_attribution"),
        static("context_operational"),
        strength("context_operational"),
    ]
    primary_status = _group_status(primary_axes)
    temporal_increment_status = _group_status(temporal_increment_axes)
    conditional_attribution_status = _group_status(conditional_attribution_axes)
    selection_status = _group_status(selection_axes)
    temporal_confirmation_status = _group_status(temporal_confirmation_axes)
    context_confirmation_status = _group_status(context_confirmation_axes)

    common = {
        "primary_status": primary_status,
        "temporal_increment_status": temporal_increment_status,
        "conditional_attribution_status": conditional_attribution_status,
        "selection_status": selection_status,
        "fresh_temporal_confirmation_status": temporal_confirmation_status,
        "fresh_context_confirmation_status": context_confirmation_status,
        "temporal_increment_static": static("primary_temporal_increment"),
        "temporal_increment_strength": strength("primary_temporal_increment"),
        "conditional_attribution_static": static("composition_attribution"),
        "conditional_attribution_strength": strength("composition_attribution"),
        "composition_vs_temporal_static": static("composition_vs_temporal"),
        "composition_vs_temporal_strength": strength("composition_vs_temporal"),
        "composition_operational_static": static("composition_operational"),
        "composition_operational_strength": strength("composition_operational"),
        "temporal_operational_static": static("temporal_operational"),
        "temporal_operational_strength": strength("temporal_operational"),
        "interaction": interactions[
            "conditional_by_temporal_difference_in_differences"
        ],
        "minimum_effect_floor": 0.0,
        "singleton_confirmation_can_rescue_primary": False,
        "promotable": False,
    }
    if primary_status == "FAIL":
        return {
            **common,
            "status": "FAIL",
            "retained_target": "CONTEXT_30",
            "finding": "composition_does_not_preserve_both_incremental_signals",
            "decision": "retain_CONTEXT_30_and_close_this_composition_formula",
        }
    if primary_status == "INCONCLUSIVE":
        return {
            **common,
            "status": "INCONCLUSIVE",
            "retained_target": "CONTEXT_30",
            "finding": "composition_primary_is_not_precise",
            "decision": "power_size_only_the_unresolved_primary_axis",
        }
    if selection_status == "PASS":
        return {
            **common,
            "status": "PASS",
            "retained_target": "COMPOSED_30",
            "finding": "conditional_and_temporal_signals_compose_and_dominate_singletons",
            "decision": "prepare_independent_COMPOSED_30_replication",
        }
    return {
        **common,
        "status": "PASS",
        "retained_target": "CONTEXT_30",
        "finding": "both_signals_survive_composition_without_full_singleton_dominance",
        "decision": "retain_CONTEXT_30_without_automatic_composition_selection",
    }


def _experiment_spec(config: dict[str, Any]) -> dict[str, Any]:
    if config["milestone"] == "M15-C3":
        return {
            "schema": COMPOSITION_SCHEMA,
            "probe_schema": COMPOSITION_PROBE_SCHEMA,
            "milestone": "M15-C3",
            "probe_milestone": "M15-C3-PROBE",
            "arm_order": COMPOSITION_ARM_ORDER,
            "doses": (),
            "arena_arms": COMPOSITION_ARENA_ARMS,
            "contrasts": COMPOSITION_CONTRASTS,
            "arena_contrasts": COMPOSITION_ARENA_CONTRASTS,
        }
    if config["milestone"] == "M15-C2R":
        return {
            "schema": REPLICATION_SCHEMA,
            "probe_schema": REPLICATION_PROBE_SCHEMA,
            "milestone": "M15-C2R",
            "probe_milestone": "M15-C2R-PROBE",
            "arm_order": REPLICATION_ARM_ORDER,
            "doses": REPLICATION_DOSES,
            "arena_arms": REPLICATION_ARENA_ARMS,
            "contrasts": REPLICATION_CONTRASTS,
            "arena_contrasts": REPLICATION_ARENA_CONTRASTS,
        }
    return {
        "schema": SCHEMA,
        "probe_schema": PROBE_SCHEMA,
        "milestone": "M15-C2",
        "probe_milestone": "M15-C2-PROBE",
        "arm_order": ARM_ORDER,
        "doses": DOSES,
        "arena_arms": ARENA_ARMS,
        "contrasts": CONTRASTS,
        "arena_contrasts": ARENA_CONTRASTS,
    }


def _write_outputs(
    result: dict[str, Any],
    run_dir: Path,
    compact_output: Path,
    schema: str = SCHEMA,
    milestone: str = "M15-C2",
) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(payload, encoding="utf-8")
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(payload, encoding="utf-8")
    for path in (run_dir / "result.json", compact_output):
        replayed = json.loads(path.read_text(encoding="utf-8"))
        if (
            replayed.get("schema") != schema
            or replayed.get("milestone") != milestone
            or replayed.get("result_hash") != result.get("result_hash")
            or replayed.get("recommendation", {}).get("finding")
            != result.get("recommendation", {}).get("finding")
        ):
            raise RuntimeError(f"M15-C2 reporting round-trip failed: {path}")


def _write_probe_outputs(
    result: dict[str, Any],
    run_dir: Path,
    compact_output: Path,
    probe_schema: str = PROBE_SCHEMA,
) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "probe.json").write_text(payload, encoding="utf-8")
    compact_output.parent.mkdir(parents=True, exist_ok=True)
    compact_output.write_text(payload, encoding="utf-8")
    for path in (run_dir / "probe.json", compact_output):
        replayed = json.loads(path.read_text(encoding="utf-8"))
        if (
            replayed.get("schema") != probe_schema
            or replayed.get("status") != "PROBE_COMPLETE"
            or replayed.get("result_hash") != result.get("result_hash")
            or replayed.get("scientific_metrics_published") is not False
            or replayed.get("promotable") is not False
        ):
            raise RuntimeError(f"M15-C2 probe reporting round-trip failed: {path}")


def _write_progress(
    path: Path | None,
    completed: int,
    total: int,
    last_seed: int,
    started: float,
    milestone: str = "M15-C2",
) -> None:
    if path is None:
        return
    elapsed = max(time.monotonic() - started, 1.0e-9)
    rate = completed / (elapsed / 60.0)
    payload = {
        "schema": (
            "mini_jass.pattern_conditional_temporal_composition_progress.v1"
            if milestone == "M15-C3"
            else (
                "mini_jass.pattern_conditional_dose_replication_progress.v1"
                if milestone == "M15-C2R"
                else "mini_jass.pattern_conditional_dose_screen_progress.v1"
            )
        ),
        "milestone": milestone,
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
    spec = _experiment_spec(config)
    milestone = str(spec["milestone"])
    arm_order = tuple(spec["arm_order"])
    doses = tuple(spec["doses"])
    arena_arms = tuple(spec["arena_arms"])
    host = execution_host or platform.node()
    if host != config["expected_execution_host"]:
        raise ValueError(f"{milestone} requires cpx62, got {host}")
    oracle = load_oracle(oracle_path)
    graph = GameGraph.from_oracle(oracle)
    graph.validate()
    split = build_split(oracle, int(base_loop["split_seed"]))
    if split.manifest["manifest_hash"] != base_loop["expected_split_manifest_hash"]:
        raise ValueError(f"{milestone} split differs from the frozen L1 contract")
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
        temporal_contract: dict[str, Any] | None = None
        if milestone == "M15-C3":
            temporal_arms, raw_temporal_contract = build_temporal_target_arms(
                generated.samples,
                generated.metrics["search_trace"],
                oracle.values,
                train_mask,
            )
            if len(temporal_arms["LAMBDA_50"]) != len(train_samples):
                raise RuntimeError("M15-C3 temporal train-row filter diverged")
            arms, replay_contract = build_composition_target_arms(
                train_samples,
                temporal_arms["LAMBDA_50"],
                cross_fit["conditional_predictions"],
                shuffled["predictions"],
                oracle.values,
            )
            temporal_contract = {
                key: value
                for key, value in raw_temporal_contract.items()
                if key
                not in {
                    "targets",
                    "structure_fingerprints",
                    "shared_structure_fingerprint",
                }
            }
        else:
            arms, replay_contract = build_target_arms(
                train_samples,
                cross_fit["conditional_predictions"],
                shuffled["predictions"],
                oracle.values,
                doses,
                arm_order,
            )
        schedule = _random_schedule(len(train_samples), steps, batch_size, fit_seed + 15)

        models: dict[str, Any] = {}
        arm_rows: dict[str, Any] = {}
        for arm in arm_order:
            model, training, arm_initial_hash = _fit(
                base_loop, graph, arms[arm], schedule, fit_seed
            )
            if arm_initial_hash != initial_hash:
                raise RuntimeError(
                    f"{milestone} arms did not share the initial PatternEval"
                )
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
        for arm in arena_arms:
            arena = run_arena(
                graph, models[arm], outcome_model, arena_config, arena_seed, development
            )
            start_hash = digest(arena["start_state_ids"])
            if arena_start_hash is None:
                arena_start_hash = start_hash
            elif start_hash != arena_start_hash:
                raise RuntimeError(f"{milestone} arena starts diverged across arms")
            arm_rows[arm]["arena_score_minus_half"] = float(arena["score"]) - 0.5
            arm_rows[arm]["arena_vs_outcome"] = arena
        if arm_rows["OUTCOME"]["arena_score_minus_half"] != 0.0:
            raise RuntimeError(
                f"{milestone} symmetric OUTCOME arena did not score 0.5"
            )

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
                **(
                    {"temporal_contract": temporal_contract}
                    if temporal_contract is not None
                    else {}
                ),
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
            _write_progress(
                progress_output,
                len(rows),
                len(run_seeds),
                seed,
                started,
                milestone,
            )

    if probe_only:
        elapsed = time.monotonic() - started
        result = {
            "schema": spec["probe_schema"],
            "milestone": spec["probe_milestone"],
            "status": "PROBE_COMPLETE",
            "seed": int(run_seeds[0]),
            "timing": {"total_seconds": elapsed},
            "workload": {
                "selfplay_games": int(config["replay"]["games_per_seed"]),
                "training_arms": len(arm_order),
                "training_steps": len(arm_order) * steps,
                "arena_arms": len(arena_arms),
                "arena_pairs": len(arena_arms) * int(arena_spec["pairs"]),
                "arena_games": 2 * len(arena_arms) * int(arena_spec["pairs"]),
                "train_sample_count": int(rows[0]["replay"]["train_sample_count"]),
            },
            "reporting": "timing_and_contract_only",
            "scientific_metrics_published": False,
            "promotable": False,
        }
        result["result_hash"] = digest(
            {key: value for key, value in result.items() if key != "result_hash"}
        )
        _write_probe_outputs(
            result, run_dir, compact_output, str(spec["probe_schema"])
        )
        return result

    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    contrasts = build_contrasts(rows, critical, spec["contrasts"])
    arena_contrasts = build_arena_contrasts(rows, critical, spec["arena_contrasts"])
    interactions = (
        build_composition_interactions(rows, critical)
        if milestone == "M15-C3"
        else {}
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
                    if arm in arena_arms
                    else {}
                ),
            }
            for arm in arm_order
        },
        "contrasts": contrasts,
        "arena_contrasts": arena_contrasts,
        **({"interactions": interactions} if interactions else {}),
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
        **(
            {
                "all_temporal_returns_built_before_train_filter": all(
                    bool(
                        row["replay"]["temporal_contract"][
                            "temporal_returns_built_before_train_row_filter"
                        ]
                    )
                    for row in rows
                ),
                "all_composition_targets_convex_and_bounded": all(
                    bool(row["replay"]["all_targets_convex_and_bounded"])
                    for row in rows
                ),
                "all_composition_targets_oracle_blind": all(
                    bool(row["replay"]["all_targets_oracle_blind"])
                    for row in rows
                ),
            }
            if milestone == "M15-C3"
            else {}
        ),
        "additional_frozen_test_reads": 0,
    }
    if milestone == "M15-C3":
        recommendation = build_composition_recommendation(
            contrasts, arena_contrasts, interactions
        )
    elif milestone == "M15-C2R":
        recommendation = build_replication_recommendation(
            contrasts, arena_contrasts
        )
    else:
        recommendation = build_recommendation(contrasts, arena_contrasts)
    power_sizing = deepcopy(config["power_sizing"])
    if milestone in {"M15-C2R", "M15-C3"}:
        for cell in power_sizing.values():
            cell["recomputed_power"] = estimate_power(cell)
    else:
        power_sizing["recomputed_power"] = estimate_power(config["power_sizing"])
    if milestone == "M15-C3":
        target_protocol = {
            "conditional_mapping": config["conditional_mapping"],
            "temporal_target": config["temporal_target"],
            "composition": config["composition"],
        }
    elif milestone == "M15-C2R":
        target_protocol = {
            "conditional_mapping": config["conditional_mapping"],
            "dose_replication": config["dose_replication"],
        }
    else:
        target_protocol = {
            "conditional_mapping": config["conditional_mapping"],
            "dose_screen": config["dose_screen"],
        }
    protocol = {
        "schema": spec["schema"],
        "milestone": milestone,
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": [int(seed) for seed in config["paired_seeds"]],
        "arms": list(arm_order),
        "replay": config["replay"],
        **target_protocol,
        "training_schedule": config["training_schedule"],
        "strength_arena": config["strength_arena"],
        "power_sizing": power_sizing,
        "scientific_gate": config["scientific_gate"],
        "source_evidence": config["source_evidence"],
        "boundaries": config["boundaries"],
        "execution_host": host,
    }
    result: dict[str, Any] = {
        "schema": spec["schema"],
        "milestone": milestone,
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
    _write_outputs(
        result, run_dir, compact_output, str(spec["schema"]), milestone
    )
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
