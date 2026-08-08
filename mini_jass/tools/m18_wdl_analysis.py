"""Paired causal contrasts and scientific decision for M18."""
from __future__ import annotations

from typing import Any

from m18_wdl_config import ARM_ORDER, EXPECTED_SEEDS, _paired_summary


def _seed_map(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result = {int(row["seed"]): row for row in rows}
    if sorted(result) != EXPECTED_SEEDS:
        raise ValueError("M18 arm does not contain the five paired seeds")
    return result


def _exact_at(row: dict[str, Any], rung: int) -> float:
    return float(row["by_rung"][str(rung)]["probe_start_wdl"]["exact_rate"])


def _build_contrasts(
    arm_rows: dict[str, list[dict[str, Any]]], critical: float
) -> dict[str, Any]:
    mapped = {arm: _seed_map(rows) for arm, rows in arm_rows.items()}
    evolving = mapped["evolving_arena_gate"]
    frozen = mapped["frozen_generator"]
    shallow = mapped["shallow_search"]
    forced = mapped["forced_advance"]
    values = {
        "evolving_g8_minus_g0": [
            _exact_at(evolving[seed], 8) - _exact_at(evolving[seed], 0)
            for seed in EXPECTED_SEEDS
        ],
        "evolving_gain_minus_frozen_gain": [
            (_exact_at(evolving[seed], 8) - _exact_at(evolving[seed], 0))
            - (_exact_at(frozen[seed], 8) - _exact_at(frozen[seed], 0))
            for seed in EXPECTED_SEEDS
        ],
        "evolving_gain_minus_shallow_gain": [
            (_exact_at(evolving[seed], 8) - _exact_at(evolving[seed], 0))
            - (_exact_at(shallow[seed], 8) - _exact_at(shallow[seed], 0))
            for seed in EXPECTED_SEEDS
        ],
        "evolving_gain_minus_forced_gain": [
            (_exact_at(evolving[seed], 8) - _exact_at(evolving[seed], 0))
            - (_exact_at(forced[seed], 8) - _exact_at(forced[seed], 0))
            for seed in EXPECTED_SEEDS
        ],
    }
    return {
        name: _paired_summary(samples, critical) for name, samples in values.items()
    }


def _assert_paired_start_schedules(
    arm_rows: dict[str, list[dict[str, Any]]]
) -> None:
    mapped = {arm: _seed_map(rows) for arm, rows in arm_rows.items()}
    for seed in EXPECTED_SEEDS:
        probe = {
            mapped[arm][seed]["probe_start_signature"] for arm in ARM_ORDER
        }
        if len(probe) != 1:
            raise ValueError("M18 fixed-probe start schedule diverged across arms")
        for generation in range(1, 9):
            signatures = {
                mapped[arm][seed]["training_start_signatures"][str(generation)]
                for arm in ARM_ORDER
            }
            if len(signatures) != 1:
                raise ValueError(
                    f"M18 training start schedule diverged at seed={seed} g={generation}"
                )


def build_recommendation(
    aggregate: dict[str, Any], gate: dict[str, Any]
) -> dict[str, Any]:
    evolving = aggregate["arms"]["evolving_arena_gate"]
    if float(evolving["mean_advancing_generations"]) < float(
        gate["minimum_mean_advancing_generations"]
    ):
        return {
            "status": "INCONCLUSIVE",
            "finding": "arena_gate_blocked_real_iteration",
            "loop_is_virtuous": None,
            "generator_feedback_is_causal": None,
            "search_is_cliquet": None,
            "promotable": False,
            "next_step": "recalibrate_arena_gate_before_interpreting_WDL_iteration",
        }

    contrasts = aggregate["contrasts"]
    require_ci = bool(gate["require_paired_confidence_95_above_zero"])

    def passes(name: str, floor: float) -> bool:
        row = contrasts[name]
        return float(row["mean"]) >= float(floor) and (
            not require_ci or float(row["confidence_95"][0]) > 0.0
        )

    loop_gain = passes(
        "evolving_g8_minus_g0", gate["minimum_practical_loop_gain"]
    )
    feedback = passes(
        "evolving_gain_minus_frozen_gain", gate["minimum_practical_feedback_gain"]
    )
    search = passes(
        "evolving_gain_minus_shallow_gain", gate["minimum_practical_search_gain"]
    )
    final_value = float(evolving["mean_final_development_value_sign_delta"]) > float(
        gate["minimum_final_development_value_sign_delta"]
    )
    final_policy = float(
        evolving["mean_final_development_optimal_mass_delta"]
    ) > float(gate["minimum_final_development_optimal_mass_delta"])
    final_arena = float(evolving["mean_final_arena_score_vs_initial"]) > float(
        gate["minimum_final_arena_score_vs_initial"]
    )
    execution = aggregate["execution"]
    criteria = {
        "all_runs_completed": bool(execution["all_runs_completed"]),
        "start_schedules_paired": bool(execution["start_schedules_paired"]),
        "loop_gain_practical_and_confident": loop_gain,
        "generator_feedback_practical_and_confident": feedback,
        "search_gain_practical_and_confident": search,
        "final_value_improves": final_value,
        "final_policy_improves": final_policy,
        "final_arena_beats_initial": final_arena,
        "oracle_has_no_causal_role": bool(execution["oracle_has_no_causal_role"]),
    }
    passed = all(criteria.values())
    return {
        "status": "PASS" if passed else "FAIL",
        "finding": (
            "self_improving_WDL_policy_iteration_mechanism_identified"
            if passed
            else "WDL_iteration_did_not_pass_all_causal_controls"
        ),
        "loop_is_virtuous": loop_gain,
        "generator_feedback_is_causal": feedback,
        "search_is_cliquet": search,
        "arena_gate_effect_on_final_label_quality": contrasts[
            "evolving_gain_minus_forced_gain"
        ],
        "criteria": criteria,
        "promotable": False,
        "next_step": (
            "replicate_M18_on_fresh_seeds_before_any_scale_transfer"
            if passed
            else "inspect_failed_control_before_changing_targets_or_scaling"
        ),
    }
