"""Fail-closed M21-P evidence freeze and C1 arena power sizing."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

import numpy as np


CONFIG_SCHEMA = "mini_jass.contextual_outcome_supervision.v3"
M21P_SCHEMA = "mini_jass.pattern_learning_signal_composition.v1"
PENDING = "PENDING_M21P_RESULT_MUST_BE_REPLACED_BEFORE_C0"
M21P_SEEDS = tuple(range(266001, 266021))


def digest(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_result_hash(result: dict[str, Any]) -> None:
    claimed = result.get("result_hash")
    calculated = digest(
        {key: value for key, value in result.items() if key != "result_hash"}
    )
    if claimed != calculated:
        raise ValueError("M21-P result hash does not match its payload")


def validate_m21p_evidence(
    config: dict[str, Any], result: dict[str, Any], status: dict[str, Any]
) -> dict[str, Any]:
    """Validate runner/science evidence and freeze the upstream replay choice."""
    if config.get("schema") != CONFIG_SCHEMA:
        raise ValueError("contextual supervision requires the v3 preregistration")
    prereq = config["data_contract"]["prerequisites"]["M21_P_strength_source"]
    expected_hash = str(prereq["result_hash"])
    if expected_hash != PENDING and expected_hash != result.get("result_hash"):
        raise ValueError("M21-P result differs from the frozen contextual pin")
    if (
        status.get("job_id") != prereq["job_id"]
        or status.get("attempt_id") != prereq["attempt_id"]
        or status.get("code_sha") != prereq["code_sha"]
        or status.get("state") != "completed"
        or status.get("exit_code") != 0
        or not status.get("result_uri")
    ):
        raise ValueError("M21-P runner evidence is incomplete or incompatible")
    if result.get("schema") != M21P_SCHEMA or result.get("milestone") != "M21-P":
        raise ValueError("unexpected M21-P scientific schema")
    _validate_result_hash(result)
    if result.get("promotable") is not False:
        raise ValueError("M21-P evidence unexpectedly authorizes promotion")
    aggregate = result.get("aggregate", {})
    if aggregate.get("all_arena_starts_paired") is not True:
        raise ValueError("M21-P common-search arenas were not paired")
    if float(aggregate.get("mean_ladder_advance_count", 0.0)) < float(
        prereq["minimum_mean_advancing_generations"]
    ):
        raise ValueError("ABORT_AND_RESOLVE_M21P: ladder did not advance")

    verdict = str(result.get("recommendation", {}).get("status", result.get("status")))
    if result.get("status") != verdict:
        raise ValueError("M21-P top-level and recommendation verdicts disagree")
    decision = config["replay_source_decision_v1"]
    if verdict == "PASS":
        selected = decision["on_M21_P_PASS"]
    elif verdict == "FAIL":
        selected = decision["on_M21_P_FAIL"]
    elif verdict == "INCONCLUSIVE":
        raise ValueError("ABORT_AND_RESOLVE_M21P: strength result is inconclusive")
    else:
        raise ValueError(f"unexpected M21-P verdict: {verdict}")
    frozen_source = str(decision["selected_source"])
    if frozen_source != PENDING and frozen_source != selected:
        raise ValueError("M21-P verdict differs from the frozen replay source")

    rows = result.get("seed_results", [])
    seeds = tuple(int(row["seed"]) for row in rows)
    if seeds != M21P_SEEDS:
        raise ValueError("M21-P per-seed evidence is missing, reordered or reused")
    deltas = [
        float(row["arms"]["MIX_OUTCOME"]["arena_score"])
        - float(row["arms"]["G1_WIDE_OUTCOME"]["arena_score"])
        for row in rows
    ]
    if not all(math.isfinite(value) and -1.0 <= value <= 1.0 for value in deltas):
        raise ValueError("M21-P per-seed arena contrast is invalid")
    return {
        "job_id": status["job_id"],
        "attempt_id": status["attempt_id"],
        "code_sha": status["code_sha"],
        "result_uri": status["result_uri"],
        "result_hash": result["result_hash"],
        "protocol_hash": result["protocol_hash"],
        "verdict": verdict,
        "selected_replay_source": selected,
        "paired_seeds": list(seeds),
        "per_seed_primary_arena_deltas": deltas,
        "mean_ladder_advance_count": float(aggregate["mean_ladder_advance_count"]),
    }


def estimate_power(
    *,
    seed_count: int,
    between_seed_sd: float,
    pairs_per_seed: int,
    true_delta: float,
    repetitions: int,
    seed: int,
    critical: float = 2.093024054408263,
    within_arm_variance: float = 0.25,
) -> float:
    """Frozen normal random-effects simulation for the paired Student-t gate."""
    if seed_count < 2 or between_seed_sd < 0.0 or pairs_per_seed < 1:
        raise ValueError("invalid contextual power inputs")
    if repetitions < 1 or not 0.0 < true_delta <= 1.0:
        raise ValueError("invalid contextual power target")
    total_sd = math.sqrt(
        between_seed_sd**2 + 2.0 * within_arm_variance / pairs_per_seed
    )
    draws = np.random.default_rng(seed).normal(
        loc=true_delta, scale=total_sd, size=(repetitions, seed_count)
    )
    means = draws.mean(axis=1)
    errors = draws.std(axis=1, ddof=1) / math.sqrt(seed_count)
    return float(np.mean(means - critical * errors > 0.0))


def build_power_freeze_report(
    config: dict[str, Any], result: dict[str, Any], status: dict[str, Any]
) -> dict[str, Any]:
    evidence = validate_m21p_evidence(config, result, status)
    power = config["power_sizing_v1"]
    measured_sd = float(
        np.std(evidence["per_seed_primary_arena_deltas"], ddof=1)
    )
    if not math.isfinite(measured_sd):
        raise ValueError("M21-P between-seed variance is invalid")
    used_sd = max(
        measured_sd,
        float(power["variance_source"]["minimum_between_seed_standard_deviation"]),
    )
    target = power["target"]
    simulation = power["simulation"]
    candidates: list[dict[str, Any]] = []
    selected: int | None = None
    for pairs in (int(value) for value in power["candidate_pairs_per_seed"]):
        estimated = estimate_power(
            seed_count=len(evidence["paired_seeds"]),
            between_seed_sd=used_sd,
            pairs_per_seed=pairs,
            true_delta=float(target["true_score_delta"]),
            repetitions=int(simulation["replicates"]),
            seed=int(simulation["seed"]),
            within_arm_variance=float(simulation["within_game_variance_upper_bound"]),
        )
        candidates.append({"pairs_per_seed": pairs, "estimated_power": estimated})
        if selected is None and estimated >= float(target["minimum_power"]):
            selected = pairs
    if selected is None:
        raise ValueError("ABORT_AND_REVISE_PREREGISTRATION: no powered arena size")
    report: dict[str, Any] = {
        "schema": "mini_jass.contextual_power_freeze.v1",
        "source_evidence": evidence,
        "measured_primary_delta_sd": measured_sd,
        "used_random_effect_sd": used_sd,
        "target_true_score_delta": float(target["true_score_delta"]),
        "minimum_power": float(target["minimum_power"]),
        "simulation_repetitions": int(simulation["replicates"]),
        "simulation_seed": int(simulation["seed"]),
        "candidates": candidates,
        "selected_pairs_per_seed": selected,
        "c0_or_training_authorized": False,
        "next_action": "freeze_report_hash_and_selected_source_in_pr_441",
    }
    report["report_hash"] = digest(report)
    return report
