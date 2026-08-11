#!/usr/bin/env python3
"""M15-C6: keep temporal value and conditional context separate until decision."""

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
from mini_jass_lab.search import (  # noqa: E402
    InferenceCache,
    SearchConfig,
    apply_contextual_tiebreak,
    bounded_negamax,
)
from mini_jass_lab.selfplay import generate_self_play  # noqa: E402
from mini_jass_lab.split import build_split  # noqa: E402
from mini_jass_lab.train import seed_everything  # noqa: E402
from run_pattern_temporal_value_target_screen import (  # noqa: E402
    build_target_arms as build_temporal_target_arms,
)
from run_pattern_value_target_screen import (  # noqa: E402
    _fit,
    _model_state_hash,
    _random_schedule,
    _sample_structure_fingerprint,
    estimate_power,
)


SCHEMA = "mini_jass.pattern_contextual_decision_channel.v1"
PROBE_SCHEMA = "mini_jass.pattern_contextual_decision_channel_probe.v1"
MILESTONE = "M15-C6"
ARM_ORDER = (
    "OUTCOME",
    "LAMBDA_50",
    "CONTEXT_30",
    "ALIGNED_CONTEXT_CHANNEL",
    "SHUFFLED_CONTEXT_CHANNEL",
)
TRAINED_TABLES = (
    "OUTCOME",
    "LAMBDA_50",
    "CONTEXT_30",
    "ALIGNED_CONTEXT_HEAD",
    "SHUFFLED_CONTEXT_HEAD",
)
MATCHUPS = (
    "LAMBDA_50_SELF",
    "LAMBDA_50_VS_OUTCOME",
    "CONTEXT_30_VS_OUTCOME",
    "ALIGNED_VS_SHUFFLED",
    "ALIGNED_VS_LAMBDA_50",
    "SHUFFLED_VS_LAMBDA_50",
)
PRIMARY_MATCHUPS = ("ALIGNED_VS_SHUFFLED", "ALIGNED_VS_LAMBDA_50")

EXPECTED_M16P_RESULT = (
    "23eeaf1d310dc95a1aa8eb0d7937125d4304d641a843b9261cf7b154dfd2b385"
)
EXPECTED_M15C2R_RESULT = (
    "d240e5c006b9e7463221bbae4e639d80dbc8773840c2310b64ed9df1bd45ae25"
)
EXPECTED_M15C3_RESULT = (
    "be36b212e495c004dcc44e31a98f1968bce68ed32264cd9660a27cb0761aed87"
)
EXPECTED_M15C5_RESULT = (
    "bc75242ffceab3b04706c54ca37aa0ad5fdfc7488405e07dd90d4538cc4f4f40"
)


def _resolve(config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA or config.get("milestone") != MILESTONE:
        raise ValueError("unexpected M15-C6 schema")
    if tuple(config.get("arms", [])) != ARM_ORDER:
        raise ValueError("M15-C6 arms changed after preregistration")
    if [int(seed) for seed in config.get("paired_seeds", [])] != list(
        range(279001, 279025)
    ):
        raise ValueError("M15-C6 seeds changed or overlap prior evidence")
    if config.get("expected_execution_host") != "User":
        raise ValueError("M15-C6 is reserved for HOME")

    evidence = config.get("source_evidence", {})
    if (
        evidence.get("m16p", {}).get("result_hash") != EXPECTED_M16P_RESULT
        or evidence.get("m16p", {}).get("retained_target") != "LAMBDA_50"
        or evidence.get("m15c2r", {}).get("result_hash")
        != EXPECTED_M15C2R_RESULT
        or evidence.get("m15c2r", {}).get("retained_target") != "CONTEXT_30"
        or evidence.get("m15c3", {}).get("result_hash") != EXPECTED_M15C3_RESULT
        or evidence.get("m15c3", {}).get("status") != "FAIL"
        or evidence.get("m15c4", {}).get("status") != "FAIL"
        or evidence.get("m15c5", {}).get("result_hash") != EXPECTED_M15C5_RESULT
        or evidence.get("m15c5", {}).get("status") != "FAIL"
    ):
        raise ValueError("M15-C6 source evidence is not frozen")

    replay = config.get("replay", {})
    if (
        replay.get("source") != "G1_WIDE_OUTCOME"
        or int(replay.get("games_per_seed", 0)) != 1024
        or int(replay.get("generation", 0)) != 1
        or int(replay.get("seed_offset", 0)) != 1130000
        or replay.get("temporal_returns_built_before_train_filter") is not True
        or replay.get("immutable_structure_across_training_targets") is not True
    ):
        raise ValueError("M15-C6 replay contract changed")

    temporal = config.get("temporal_target", {})
    if (
        temporal.get("retained_arm") != "LAMBDA_50"
        or float(temporal.get("lambda", -1.0)) != 0.5
        or temporal.get("oracle_training_signal") is not False
    ):
        raise ValueError("M15-C6 temporal target changed")

    mapping = config.get("conditional_mapping", {})
    if (
        mapping.get("family") != "odd_tanh_linear_wdl_oof_v1"
        or int(mapping.get("fold_count", 0)) != 5
        or mapping.get("fold_unit") != "complete_game"
        or mapping.get("fold_namespace")
        != "m15c6_conditional_wdl_game_folds_v1"
        or mapping.get("shuffle_namespace")
        != "m15c6_conditional_decision_shuffle_v1"
        or float(mapping.get("ridge", -1.0)) != 0.0001
        or mapping.get("oracle_training_signal") is not False
    ):
        raise ValueError("M15-C6 conditional mapping changed")

    targets = config.get("training_targets", {})
    if (
        targets.get("ALIGNED_CONTEXT_HEAD") != "conditional_oof_prediction"
        or targets.get("SHUFFLED_CONTEXT_HEAD")
        != "within_fold_permuted_conditional_oof_prediction"
        or targets.get("scalar_temporal_context_blend_for_candidate") is not False
        or targets.get("separate_context_parameter_table_at_inference") is not True
    ):
        raise ValueError("M15-C6 crossed the separate-channel boundary")

    schedule = config.get("training_schedule", {})
    if (
        int(schedule.get("total_steps_per_table", 0)) != 1024
        or int(schedule.get("batch_size", 0)) != 128
        or int(schedule.get("seed_offset", 0)) != 1140000
        or schedule.get("explicit_identical_batch_schedule_all_tables") is not True
        or schedule.get("shared_zero_initialization") is not True
    ):
        raise ValueError("M15-C6 training schedule changed")

    tiebreak = config.get("contextual_tiebreak", {})
    if (
        tiebreak.get("temporal_value_model") != "LAMBDA_50"
        or tiebreak.get("aligned_context_model") != "ALIGNED_CONTEXT_HEAD"
        or tiebreak.get("shuffled_context_model") != "SHUFFLED_CONTEXT_HEAD"
        or int(tiebreak.get("calibration_state_count", 0)) != 512
        or int(tiebreak.get("calibration_seed_offset", 0)) != 1150000
        or float(tiebreak.get("calibration_quantile", -1.0)) != 0.25
        or int(tiebreak.get("minimum_valid_calibration_states", 0)) != 128
        or tiebreak.get("same_delta_for_aligned_and_shuffled") is not True
        or tiebreak.get("temporal_search_scores_unchanged") is not True
        or tiebreak.get("context_never_changes_internal_search") is not True
    ):
        raise ValueError("M15-C6 contextual tie-break changed")

    arena = config.get("strength_arena", {})
    if (
        int(arena.get("pairs", 0)) != 512
        or int(arena.get("seed_base", 0)) != 1160000
        or float(arena.get("epsilon", -1.0)) != 0.0
        or arena.get("confidence_unit") != "pairs"
        or arena.get("start_state_source") != "development"
        or tuple(arena.get("matchups", [])) != MATCHUPS
        or arena.get("paired_starts_across_all_matchups") is not True
    ):
        raise ValueError("M15-C6 strength arena changed")

    power = config.get("power_sizing", {})
    if (
        int(power.get("paired_seed_count", 0)) != 24
        or float(power.get("conservative_paired_sd", -1.0)) != 0.0025
        or float(power.get("minimum_effect", -1.0)) != 0.0015
        or float(power.get("paired_confidence_critical_95", -1.0))
        != 2.0686576104190406
        or power.get("gate_has_no_minimum_effect_floor") is not True
    ):
        raise ValueError("M15-C6 power contract changed")
    recomputed_power = estimate_power(power)
    if abs(recomputed_power - float(power["estimated_power_ci_above_zero"])) > 1e-12:
        raise ValueError("M15-C6 frozen power estimate did not reproduce")
    if recomputed_power < float(power["minimum_required_power"]):
        raise ValueError("M15-C6 is underpowered before training")

    gate = config.get("scientific_gate", {})
    boundaries = config.get("boundaries", {})
    if (
        tuple(gate.get("primary_contrasts", []))
        != (
            "ALIGNED_CONTEXT_CHANNEL_minus_SHUFFLED_CONTEXT_CHANNEL",
            "ALIGNED_CONTEXT_CHANNEL_minus_LAMBDA_50",
        )
        or gate.get("require_both_strength_ci95_lower_bounds_above_zero")
        is not True
        or float(gate.get("minimum_effect_floor", -1.0)) != 0.0
        or gate.get("static_diagnostics_cannot_rescue_strength_failure") is not True
        or gate.get("automatic_promotion") is not False
        or boundaries.get("cohorts_never_read_by_this_cell") != ["frozen_test"]
        or int(boundaries.get("additional_frozen_test_reads_authorized", -1)) != 0
        or boundaries.get("all_training_targets_oracle_blind") is not True
        or boundaries.get("megacorpus_not_consumed") is not True
        or boundaries.get("promotable") is not False
    ):
        raise ValueError("M15-C6 scientific boundary changed")

    base_path = config_path.parent.parent / str(config["base_loop_config"])
    loop = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    if loop.get("model", {}).get("architecture") != "folded_pattern_value":
        raise ValueError("M15-C6 must use the production-shaped PatternEval")
    if float(loop.get("training", {}).get("policy_weight", -1.0)) != 0.0:
        raise ValueError("M15-C6 cannot train a policy head")
    return deepcopy(config), loop


def _target_rows(
    samples: list[ReplaySample], values: np.ndarray
) -> list[ReplaySample]:
    array = np.asarray(values, dtype=np.float64)
    if array.shape != (len(samples),) or not np.all(np.isfinite(array)):
        raise ValueError("M15-C6 target values do not align")
    if np.any(np.abs(array) > 1.0):
        raise ValueError("M15-C6 target left the WDL range")
    return [
        replace(sample, value_target=float(value))
        for sample, value in zip(samples, array, strict=True)
    ]


def build_training_targets(
    outcome_rows: list[ReplaySample],
    lambda_rows: list[ReplaySample],
    conditional_predictions: np.ndarray,
    shuffled_predictions: np.ndarray,
    exact_values: np.ndarray,
) -> tuple[dict[str, list[ReplaySample]], dict[str, Any]]:
    if not outcome_rows or len(outcome_rows) != len(lambda_rows):
        raise ValueError("M15-C6 temporal and conditional rows must align")
    for outcome, temporal in zip(outcome_rows, lambda_rows, strict=True):
        if (
            int(outcome.state_id) != int(temporal.state_id)
            or int(outcome.game_id) != int(temporal.game_id)
            or int(outcome.ply) != int(temporal.ply)
        ):
            raise ValueError("M15-C6 temporal row identity diverged")

    outcome = np.asarray(
        [sample.value_target for sample in outcome_rows], dtype=np.float64
    )
    temporal = np.asarray(
        [sample.value_target for sample in lambda_rows], dtype=np.float64
    )
    conditional = np.asarray(conditional_predictions, dtype=np.float64)
    shuffled = np.asarray(shuffled_predictions, dtype=np.float64)
    if any(
        component.shape != outcome.shape
        for component in (temporal, conditional, shuffled)
    ):
        raise ValueError("M15-C6 target components do not align")
    if any(
        not np.all(np.isfinite(component))
        or np.any(np.abs(component) > 1.0)
        for component in (outcome, temporal, conditional, shuffled)
    ):
        raise ValueError("M15-C6 target component is invalid")

    values = {
        "OUTCOME": outcome,
        "LAMBDA_50": temporal,
        "CONTEXT_30": 0.70 * outcome + 0.30 * conditional,
        "ALIGNED_CONTEXT_HEAD": conditional,
        "SHUFFLED_CONTEXT_HEAD": shuffled,
    }
    tables = {name: _target_rows(outcome_rows, value) for name, value in values.items()}
    structures = {
        name: _sample_structure_fingerprint(rows) for name, rows in tables.items()
    }
    if len(set(structures.values())) != 1:
        raise RuntimeError("M15-C6 training targets changed replay structure")
    states = np.asarray([sample.state_id for sample in outcome_rows], dtype=np.int64)
    exact = np.asarray(exact_values, dtype=np.float64)[states]
    metrics = {
        name: {
            "sample_count": len(outcome_rows),
            "value_mae_vs_exact_train": float(np.mean(np.abs(value - exact))),
            "target_mean": float(value.mean()),
            "target_standard_deviation": float(value.std(ddof=0)),
            "changed_from_outcome_fraction": float(np.mean(value != outcome)),
        }
        for name, value in values.items()
    }
    winner = outcome > 0.0
    loser = outcome < 0.0
    credit = {
        "winner_row_count": int(np.count_nonzero(winner)),
        "loser_row_count": int(np.count_nonzero(loser)),
        "winner_temporal_downweight_fraction": (
            float(np.mean(temporal[winner] < outcome[winner]))
            if np.any(winner)
            else None
        ),
        "winner_mean_removed_positive_credit": (
            float(np.mean(outcome[winner] - temporal[winner]))
            if np.any(winner)
            else None
        ),
        "loser_temporal_upweight_fraction": (
            float(np.mean(temporal[loser] > outcome[loser]))
            if np.any(loser)
            else None
        ),
        "loser_mean_removed_negative_credit": (
            float(np.mean(temporal[loser] - outcome[loser]))
            if np.any(loser)
            else None
        ),
    }
    return tables, {
        "shared_structure_fingerprint": next(iter(structures.values())),
        "structure_fingerprints": structures,
        "targets": metrics,
        "credit_assignment": credit,
        "all_training_targets_oracle_blind": True,
        "scalar_temporal_context_blend_for_candidate": False,
    }


def _interval(values: Iterable[float], critical: float) -> dict[str, Any]:
    data = [float(value) for value in values]
    result = paired_interval(data, critical)
    result["standard_deviation"] = float(
        result["standard_error"] * math.sqrt(result["count"])
    )
    result["positive_seed_count"] = sum(value > 0.0 for value in data)
    result["zero_seed_count"] = sum(value == 0.0 for value in data)
    result["negative_seed_count"] = sum(value < 0.0 for value in data)
    return result


def calibrate_delta(
    graph: GameGraph,
    temporal_model: Any,
    samples: list[ReplaySample],
    search_config: SearchConfig,
    seed: int,
    spec: dict[str, Any],
) -> dict[str, Any]:
    states = sorted(
        {
            int(sample.state_id)
            for sample in samples
            if graph.terminal_value(int(sample.state_id)) is None
        }
    )
    requested = int(spec["calibration_state_count"])
    if len(states) < requested:
        raise RuntimeError("M15-C6 has too few unique train states for calibration")
    rng = np.random.default_rng(seed + int(spec["calibration_seed_offset"]))
    selected = sorted(
        int(value)
        for value in rng.choice(
            np.asarray(states, dtype=np.int64), size=requested, replace=False
        )
    )
    cache = InferenceCache()
    gaps: list[float] = []
    for state in selected:
        result = bounded_negamax(
            graph, temporal_model, state, search_config, cache
        )
        scores = sorted(
            (float(value) for value in result.action_scores.values()), reverse=True
        )
        if len(scores) >= 2:
            gaps.append(scores[0] - scores[1])
    minimum = int(spec["minimum_valid_calibration_states"])
    if len(gaps) < minimum:
        raise RuntimeError(
            f"M15-C6 calibration n={len(gaps)} below floor {minimum}"
        )
    ordered = np.sort(np.asarray(gaps, dtype=np.float64))
    quantile = float(spec["calibration_quantile"])
    index = int(math.ceil(quantile * (ordered.size - 1)))
    delta = float(ordered[index])
    if not math.isfinite(delta) or delta < 0.0:
        raise RuntimeError("M15-C6 calibrated an invalid delta")

    def q(value: float) -> float:
        position = int(math.ceil(value * (ordered.size - 1)))
        return float(ordered[position])

    return {
        "delta": delta,
        "requested_state_count": requested,
        "valid_gap_count": int(ordered.size),
        "state_ids_hash": digest(selected),
        "calibration_quantile": quantile,
        "realized_activation_fraction": float(np.mean(ordered <= delta)),
        "gap_quantiles": {
            "q10": q(0.10),
            "q25": q(0.25),
            "q50": q(0.50),
            "q75": q(0.75),
            "q90": q(0.90),
        },
        "cohort": "train_replay_unique_nonterminal_states",
        "oracle_consulted": False,
    }


def _regret(graph: GameGraph, oracle: Any, state: int, action: int) -> int:
    child = graph.child(state, action)
    return int(oracle.values[state]) - int(-oracle.values[child])


def decision_diagnostics(
    graph: GameGraph,
    oracle: Any,
    temporal_model: Any,
    aligned_context: Any,
    shuffled_context: Any,
    states: list[int],
    search_config: SearchConfig,
    delta: float,
) -> dict[str, Any]:
    temporal_cache = InferenceCache()
    aligned_cache = InferenceCache()
    shuffled_cache = InferenceCache()
    actions: dict[str, list[int]] = {
        "LAMBDA_50": [],
        "ALIGNED_CONTEXT_CHANNEL": [],
        "SHUFFLED_CONTEXT_CHANNEL": [],
    }
    regrets: dict[str, list[int]] = {name: [] for name in actions}
    active: list[bool] = []
    aligned_changed: list[bool] = []
    shuffled_changed: list[bool] = []

    for state in states:
        temporal = bounded_negamax(
            graph, temporal_model, int(state), search_config, temporal_cache
        )
        aligned = apply_contextual_tiebreak(
            graph,
            aligned_context,
            int(state),
            temporal,
            delta,
            aligned_cache,
        )
        shuffled = apply_contextual_tiebreak(
            graph,
            shuffled_context,
            int(state),
            temporal,
            delta,
            shuffled_cache,
        )
        aligned_meta = aligned.contextual_tiebreak or {}
        shuffled_meta = shuffled.contextual_tiebreak or {}
        if bool(aligned_meta.get("activated")) != bool(
            shuffled_meta.get("activated")
        ):
            raise RuntimeError("M15-C6 channels saw different temporal bands")
        active.append(bool(aligned_meta.get("activated")))
        aligned_changed.append(bool(aligned_meta.get("changed_action")))
        shuffled_changed.append(bool(shuffled_meta.get("changed_action")))
        selected = {
            "LAMBDA_50": int(temporal.selected_action),
            "ALIGNED_CONTEXT_CHANNEL": int(aligned.selected_action),
            "SHUFFLED_CONTEXT_CHANNEL": int(shuffled.selected_action),
        }
        for name, action in selected.items():
            actions[name].append(action)
            regrets[name].append(_regret(graph, oracle, int(state), action))

    active_mask = np.asarray(active, dtype=np.bool_)
    regret_arrays = {
        name: np.asarray(values, dtype=np.int16) for name, values in regrets.items()
    }

    def summarize(values: np.ndarray, mask: np.ndarray | None = None) -> dict[str, Any]:
        selected = values if mask is None else values[mask]
        if selected.size == 0:
            return {"count": 0, "zero_regret_rate": None, "mean_regret": None}
        return {
            "count": int(selected.size),
            "zero_regret_rate": float(np.mean(selected == 0)),
            "mean_regret": float(np.mean(selected)),
        }

    all_metrics = {name: summarize(values) for name, values in regret_arrays.items()}
    ambiguous_metrics = {
        name: summarize(values, active_mask) for name, values in regret_arrays.items()
    }
    aligned = regret_arrays["ALIGNED_CONTEXT_CHANNEL"]
    shuffled = regret_arrays["SHUFFLED_CONTEXT_CHANNEL"]
    temporal = regret_arrays["LAMBDA_50"]
    return {
        "state_count": len(states),
        "state_ids_hash": digest(states),
        "delta": float(delta),
        "activation_count": int(np.count_nonzero(active_mask)),
        "activation_rate": float(np.mean(active_mask)),
        "aligned_changed_action_rate": float(np.mean(aligned_changed)),
        "shuffled_changed_action_rate": float(np.mean(shuffled_changed)),
        "aligned_shuffled_action_disagreement_rate": float(
            np.mean(
                np.asarray(actions["ALIGNED_CONTEXT_CHANNEL"])
                != np.asarray(actions["SHUFFLED_CONTEXT_CHANNEL"])
            )
        ),
        "all_states": all_metrics,
        "temporal_band_states": ambiguous_metrics,
        "aligned_minus_shuffled_zero_regret": float(
            all_metrics["ALIGNED_CONTEXT_CHANNEL"]["zero_regret_rate"]
            - all_metrics["SHUFFLED_CONTEXT_CHANNEL"]["zero_regret_rate"]
        ),
        "aligned_minus_lambda_zero_regret": float(
            all_metrics["ALIGNED_CONTEXT_CHANNEL"]["zero_regret_rate"]
            - all_metrics["LAMBDA_50"]["zero_regret_rate"]
        ),
        "aligned_better_equal_worse_regret_vs_shuffled": {
            "better": int(np.count_nonzero(aligned < shuffled)),
            "equal": int(np.count_nonzero(aligned == shuffled)),
            "worse": int(np.count_nonzero(aligned > shuffled)),
        },
        "aligned_better_equal_worse_regret_vs_lambda": {
            "better": int(np.count_nonzero(aligned < temporal)),
            "equal": int(np.count_nonzero(aligned == temporal)),
            "worse": int(np.count_nonzero(aligned > temporal)),
        },
    }


def _write_json_roundtrip(payload: dict[str, Any], paths: list[Path]) -> None:
    expected = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(expected, encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8")) != payload:
            raise RuntimeError(f"M15-C6 reporting round-trip failed: {path}")


def _write_progress(
    path: Path | None,
    completed: int,
    total: int,
    seed: int,
    started: float,
) -> None:
    if path is None:
        return
    elapsed = time.monotonic() - started
    remaining = elapsed / completed * (total - completed) if completed else None
    payload = {
        "schema": "mini_jass.pattern_contextual_decision_channel_progress.v1",
        "milestone": MILESTONE,
        "completed_seeds": completed,
        "total_seeds": total,
        "last_seed": seed,
        "elapsed_seconds": elapsed,
        "estimated_remaining_seconds": remaining,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json_roundtrip(payload, [path])


def _matchup_agents(models: dict[str, Any], name: str) -> dict[str, Any]:
    value = models["LAMBDA_50"]
    aligned = models["ALIGNED_CONTEXT_HEAD"]
    shuffled = models["SHUFFLED_CONTEXT_HEAD"]
    mapping = {
        "LAMBDA_50_SELF": (value, None, value, None),
        "LAMBDA_50_VS_OUTCOME": (value, None, models["OUTCOME"], None),
        "CONTEXT_30_VS_OUTCOME": (
            models["CONTEXT_30"],
            None,
            models["OUTCOME"],
            None,
        ),
        "ALIGNED_VS_SHUFFLED": (value, aligned, value, shuffled),
        "ALIGNED_VS_LAMBDA_50": (value, aligned, value, None),
        "SHUFFLED_VS_LAMBDA_50": (value, shuffled, value, None),
    }
    candidate, candidate_context, parent, parent_context = mapping[name]
    return {
        "candidate": candidate,
        "candidate_context": candidate_context,
        "parent": parent,
        "parent_context": parent_context,
    }


def _build_aggregate(rows: list[dict[str, Any]], critical: float) -> dict[str, Any]:
    arena_contrasts = {
        matchup: _interval(
            row["arenas"][matchup]["score_minus_half"] for row in rows
        )
        for matchup in MATCHUPS
    }
    static_contrasts: dict[str, Any] = {}
    for name, high, low in (
        ("LAMBDA_50_minus_OUTCOME", "LAMBDA_50", "OUTCOME"),
        ("CONTEXT_30_minus_OUTCOME", "CONTEXT_30", "OUTCOME"),
    ):
        static_contrasts[name] = {
            endpoint: _interval(
                float(row["arms"][high]["after"][endpoint])
                - float(row["arms"][low]["after"][endpoint])
                for row in rows
            )
            for endpoint in (
                "zero_regret_rate",
                "value_sign_accuracy",
                "value_mae",
                "mean_selected_regret",
            )
        }
    decision = {
        "aligned_minus_shuffled_zero_regret": _interval(
            row["decision_diagnostics"]["aligned_minus_shuffled_zero_regret"]
            for row in rows
        ),
        "aligned_minus_lambda_zero_regret": _interval(
            row["decision_diagnostics"]["aligned_minus_lambda_zero_regret"]
            for row in rows
        ),
        "mean_activation_rate": mean(
            row["decision_diagnostics"]["activation_rate"] for row in rows
        ),
        "mean_aligned_changed_action_rate": mean(
            row["decision_diagnostics"]["aligned_changed_action_rate"]
            for row in rows
        ),
        "mean_shuffled_changed_action_rate": mean(
            row["decision_diagnostics"]["shuffled_changed_action_rate"]
            for row in rows
        ),
    }
    return {
        "paired_seed_count": len(rows),
        "arena_strength": arena_contrasts,
        "static_diagnostics": static_contrasts,
        "decision_diagnostics": decision,
        "mean_calibrated_delta": mean(
            row["delta_calibration"]["delta"] for row in rows
        ),
        "minimum_calibrated_delta": min(
            float(row["delta_calibration"]["delta"]) for row in rows
        ),
        "maximum_calibrated_delta": max(
            float(row["delta_calibration"]["delta"]) for row in rows
        ),
        "mean_conditional_oof_mse_gain_vs_state_blind": mean(
            row["conditional_mapping"]["conditional_mse_gain_vs_state_blind"]
            for row in rows
        ),
        "all_training_rows_train_only": all(
            bool(row["replay"]["all_rows_train_only"]) for row in rows
        ),
        "all_training_targets_oracle_blind": all(
            bool(row["replay"]["all_training_targets_oracle_blind"])
            for row in rows
        ),
        "all_cross_fit_games_disjoint": all(
            bool(row["conditional_mapping"]["all_games_fold_disjoint"])
            for row in rows
        ),
        "all_shuffle_marginals_preserved": all(
            bool(row["shuffle_control"]["all_fold_marginals_preserved"])
            for row in rows
        ),
        "all_arena_starts_paired": True,
        "all_temporal_models_shared_between_D_and_E": True,
        "additional_frozen_test_reads": 0,
    }


def _recommendation(aggregate: dict[str, Any]) -> dict[str, Any]:
    strength = aggregate["arena_strength"]
    attribution = strength["ALIGNED_VS_SHUFFLED"]
    operational = strength["ALIGNED_VS_LAMBDA_50"]
    common = {
        "primary_endpoint": "independent_paired_playing_strength",
        "aligned_minus_shuffled_mean": float(attribution["mean"]),
        "aligned_minus_shuffled_ci95": [
            float(attribution["lower"]),
            float(attribution["upper"]),
        ],
        "aligned_minus_lambda_mean": float(operational["mean"]),
        "aligned_minus_lambda_ci95": [
            float(operational["lower"]),
            float(operational["upper"]),
        ],
        "minimum_effect_floor": 0.0,
        "static_diagnostics_can_rescue": False,
        "promotable": False,
    }
    if float(attribution["lower"]) > 0.0 and float(operational["lower"]) > 0.0:
        return {
            **common,
            "status": "PASS",
            "finding": "separate_context_channel_improves_temporal_decisions",
            "decision": "replicate_before_feedback_or_10x10_transfer",
        }
    if float(attribution["upper"]) < 0.0 or float(operational["upper"]) < 0.0:
        return {
            **common,
            "status": "FAIL",
            "finding": "separate_context_channel_harms_a_required_strength_contrast",
            "decision": "close_this_contextual_tiebreak_rule",
        }
    return {
        **common,
        "status": "INCONCLUSIVE",
        "finding": "separate_context_channel_not_established_on_both_strength_contrasts",
        "decision": "do_not_promote_or_add_feedback",
    }


def run_m15c6(
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
        raise ValueError(f"M15-C6 requires User, got {host}")
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
        raise ValueError("M15-C6 split differs from the frozen L1 contract")
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

    training_spec = config["training_schedule"]
    steps = int(training_spec["total_steps_per_table"])
    batch_size = int(training_spec["batch_size"])
    schedule_offset = int(training_spec["seed_offset"])
    mapping_spec = config["conditional_mapping"]
    tiebreak_spec = config["contextual_tiebreak"]
    arena_spec = config["strength_arena"]
    search_config = SearchConfig(
        int(base_loop["arena"]["search_depth"]),
        int(base_loop["arena"]["node_budget"]),
    )
    arena_config = ArenaConfig(
        pairs=int(arena_spec["pairs"]),
        max_plies=int(base_loop["arena"]["max_plies"]),
        search_depth=search_config.max_depth,
        node_budget=search_config.node_budget,
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
        initial_metrics = response_metrics(
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
        temporal_arms, temporal_contract = build_temporal_target_arms(
            generated.samples,
            generated.metrics["search_trace"],
            oracle.values,
            train_mask,
        )
        outcome_rows = temporal_arms["OUTCOME"]
        lambda_rows = temporal_arms["LAMBDA_50"]
        if not outcome_rows or not all(
            bool(train_mask[int(sample.state_id)]) for sample in outcome_rows
        ):
            raise RuntimeError("M15-C6 retained a non-train or empty replay")
        contexts = context_matrix(
            oracle, [sample.state_id for sample in outcome_rows]
        )
        outcomes = np.asarray(
            [sample.value_target for sample in outcome_rows], dtype=np.float64
        )
        cross_fit = cross_fitted_conditional_wdl(
            contexts,
            outcomes,
            outcome_rows,
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
            outcome_rows,
            namespace=str(mapping_spec["shuffle_namespace"]),
        )
        tables, target_contract = build_training_targets(
            outcome_rows,
            lambda_rows,
            cross_fit["conditional_predictions"],
            shuffled["predictions"],
            oracle.values,
        )
        generation_seconds = time.monotonic() - generation_started

        schedule = _random_schedule(
            len(outcome_rows), steps, batch_size, fit_seed + 15
        )
        training_started = time.monotonic()
        models: dict[str, Any] = {}
        training_rows: dict[str, Any] = {}
        for name in TRAINED_TABLES:
            model, training, arm_initial_hash = _fit(
                base_loop, graph, tables[name], schedule, fit_seed
            )
            if arm_initial_hash != initial_hash:
                raise RuntimeError("M15-C6 tables did not share zero initialization")
            models[name] = model
            training_rows[name] = {
                "training": training,
                "initial_model_hash": arm_initial_hash,
                "trained_model_hash": _model_state_hash(model),
                "target": target_contract["targets"][name],
                "replay_fingerprint": replay_fingerprint(tables[name]),
                "replay_structure_fingerprint": target_contract[
                    "shared_structure_fingerprint"
                ],
                "oracle_training_signal": False,
                "promotable": False,
            }
        arms: dict[str, Any] = {}
        for name in ("OUTCOME", "LAMBDA_50", "CONTEXT_30"):
            after = response_metrics(
                models[name], graph, tensors, oracle, development, response_batch
            )
            arms[name] = {"after": after, **training_rows[name]}
        arms["ALIGNED_CONTEXT_CHANNEL"] = {
            "temporal_model_hash": training_rows["LAMBDA_50"]["trained_model_hash"],
            "context_model_hash": training_rows["ALIGNED_CONTEXT_HEAD"][
                "trained_model_hash"
            ],
            "context_training": training_rows["ALIGNED_CONTEXT_HEAD"],
            "scalar_target_blend": False,
            "promotable": False,
        }
        arms["SHUFFLED_CONTEXT_CHANNEL"] = {
            "temporal_model_hash": training_rows["LAMBDA_50"]["trained_model_hash"],
            "context_model_hash": training_rows["SHUFFLED_CONTEXT_HEAD"][
                "trained_model_hash"
            ],
            "context_training": training_rows["SHUFFLED_CONTEXT_HEAD"],
            "scalar_target_blend": False,
            "promotable": False,
        }
        if (
            arms["ALIGNED_CONTEXT_CHANNEL"]["temporal_model_hash"]
            != arms["SHUFFLED_CONTEXT_CHANNEL"]["temporal_model_hash"]
        ):
            raise RuntimeError("M15-C6 D and E do not share LAMBDA_50")
        training_seconds = time.monotonic() - training_started

        calibration_started = time.monotonic()
        delta_calibration = calibrate_delta(
            graph,
            models["LAMBDA_50"],
            outcome_rows,
            search_config,
            seed,
            tiebreak_spec,
        )
        delta = float(delta_calibration["delta"])
        calibration_seconds = time.monotonic() - calibration_started

        arena_started = time.monotonic()
        arena_seed = int(arena_spec["seed_base"]) + seed
        arenas: dict[str, Any] = {}
        shared_start_hash: str | None = None
        for matchup in MATCHUPS:
            agents = _matchup_agents(models, matchup)
            contextual = (
                agents["candidate_context"] is not None
                or agents["parent_context"] is not None
            )
            arena = run_arena(
                graph,
                agents["candidate"],
                agents["parent"],
                arena_config,
                arena_seed,
                development,
                candidate_context_model=agents["candidate_context"],
                parent_context_model=agents["parent_context"],
                contextual_delta=delta if contextual else None,
            )
            if int(arena["pairs"]) == 0 or int(arena["games"]) == 0:
                raise RuntimeError("M15-C6 arena n=0 is a hard failure")
            start_hash = digest(arena["start_state_ids"])
            if shared_start_hash is None:
                shared_start_hash = start_hash
            elif start_hash != shared_start_hash:
                raise RuntimeError("M15-C6 arena starts diverged")
            arenas[matchup] = {
                **arena,
                "score_minus_half": float(arena["score"]) - 0.5,
            }
        if float(arenas["LAMBDA_50_SELF"]["score"]) != 0.5:
            raise RuntimeError("M15-C6 symmetric arena did not score 0.5")
        arena_seconds = time.monotonic() - arena_started

        decision_started = time.monotonic()
        decision = decision_diagnostics(
            graph,
            oracle,
            models["LAMBDA_50"],
            models["ALIGNED_CONTEXT_HEAD"],
            models["SHUFFLED_CONTEXT_HEAD"],
            [int(state) for state in arenas["LAMBDA_50_SELF"]["start_state_ids"]],
            search_config,
            delta,
        )
        decision_seconds = time.monotonic() - decision_started

        row = {
            "seed": seed,
            "initial": initial_metrics,
            "arms": arms,
            "replay": {
                "raw_generated_sample_count": len(generated.samples),
                "train_sample_count": len(outcome_rows),
                "raw_replay_fingerprint": replay_fingerprint(generated.samples),
                "shared_batch_schedule_hash": hashlib.sha256(
                    schedule.tobytes(order="C")
                ).hexdigest(),
                "shared_initial_model_hash": initial_hash,
                "shared_arena_start_hash": shared_start_hash,
                "all_rows_train_only": True,
                **{
                    key: value
                    for key, value in temporal_contract.items()
                    if key not in {"targets", "structure_fingerprints"}
                },
                **target_contract,
            },
            "conditional_mapping": {
                key: value
                for key, value in cross_fit.items()
                if key
                not in {
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
            "delta_calibration": delta_calibration,
            "decision_diagnostics": decision,
            "arenas": arenas,
        }
        rows.append(row)
        timing = {
            "seed": seed,
            "generation_and_targets_seconds": generation_seconds,
            "training_and_static_response_seconds": training_seconds,
            "delta_calibration_seconds": calibration_seconds,
            "arena_seconds": arena_seconds,
            "decision_diagnostics_seconds": decision_seconds,
            "total_seconds": time.monotonic() - seed_started,
        }
        timings.append(timing)
        if not probe_only:
            _write_json_roundtrip(row, [run_dir / f"seed-{seed}.json"])
            _write_progress(
                progress_output, len(rows), len(seeds), seed, started
            )

    if probe_only:
        probe = {
            "schema": PROBE_SCHEMA,
            "milestone": "M15-C6-PROBE",
            "status": "TIMING_ONLY",
            "seed": seeds[0],
            "execution_host": host,
            "timing": timings[0],
            "workload": {
                "selfplay_games": int(config["replay"]["games_per_seed"]),
                "trained_tables": len(TRAINED_TABLES),
                "training_steps": len(TRAINED_TABLES) * steps,
                "arena_matchups": len(MATCHUPS),
                "arena_pairs": len(MATCHUPS) * int(arena_spec["pairs"]),
                "arena_games": 2 * len(MATCHUPS) * int(arena_spec["pairs"]),
                "train_sample_count": int(rows[0]["replay"]["train_sample_count"]),
                "decision_diagnostic_states": int(
                    rows[0]["decision_diagnostics"]["state_count"]
                ),
            },
            "activation_contract": {
                "calibrated_delta": rows[0]["delta_calibration"]["delta"],
                "calibration_valid_gap_count": rows[0]["delta_calibration"][
                    "valid_gap_count"
                ],
                "decision_activation_count": rows[0]["decision_diagnostics"][
                    "activation_count"
                ],
            },
            "scientific_metrics_published": False,
            "scientific_seed_overlap": False,
            "additional_frozen_test_reads": 0,
            "promotable": False,
        }
        probe["result_hash"] = digest(probe)
        _write_json_roundtrip(probe, [run_dir / "probe.json", compact_output])
        return probe

    critical = float(config["scientific_gate"]["paired_confidence_critical_95"])
    aggregate = _build_aggregate(rows, critical)
    recommendation = _recommendation(aggregate)
    protocol = {
        "schema": SCHEMA,
        "milestone": MILESTONE,
        "base_loop_config": config["base_loop_config"],
        "resolved_model": model_descriptor(build_model(base_loop["model"])),
        "paired_seeds": seeds,
        "arms": list(ARM_ORDER),
        "trained_tables": list(TRAINED_TABLES),
        "replay": config["replay"],
        "temporal_target": config["temporal_target"],
        "conditional_mapping": config["conditional_mapping"],
        "training_targets": config["training_targets"],
        "training_schedule": config["training_schedule"],
        "contextual_tiebreak": config["contextual_tiebreak"],
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
        "milestone": MILESTONE,
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
            "all_training_targets_oracle_blind": True,
        },
        "promotable": False,
    }
    result["result_hash"] = digest(
        {key: value for key, value in result.items() if key != "result_hash"}
    )
    _write_json_roundtrip(
        result, [run_dir / "result.json", compact_output]
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
    result = run_m15c6(
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
