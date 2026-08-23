#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Freeze one ridge hypothesis for a fresh, powered confirmation corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge


SCHEMA = "jass.l3_curriculum_error_residual_power_extension_preregistration.v1"
READY = "JASS_CURRICULUM_ERROR_RESIDUAL_POWER_EXTENSION_PREREGISTERED"
AUDIT_SCHEMA = "jass.curriculum_error_residual_ridge_path_final_audit.v1"
AUDIT_READY = "JASS_CURRICULUM_ERROR_RESIDUAL_RIDGE_PATH_FINAL_AUDIT_READY"
PAIRED_GATE = "paired_ci95_lower_gt_0cp"
FRESH_PAIRS = 300
MIN_ERROR_INTERVENTIONS = 30
MIN_CONTROL_INTERVENTIONS = 20
MIN_TOTAL_INTERVENTIONS = 50
BOOTSTRAP_SAMPLES = 200_000
SHAM_REPLICATES = 1_000
MINING_SEED = 2026082261
BOOTSTRAP_SEED = 2026082262
SHAM_SEED = 2026082263


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _all_gates(row: dict[str, Any]) -> dict[str, bool]:
    gates = {key: bool(value) for key, value in row["base_gates"].items()}
    gates["stable_neighbor_plateau"] = bool(row["plateau_gate"])
    return gates


def _compact_candidate(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row["metrics"]
    return {
        "alpha": float(row["alpha"]),
        "cap_cp": float(row["cap_cp"]),
        "mode": str(row["mode"]),
        "threshold_cp": float(row["threshold_cp"]),
        "training_evidence": {
            "error_interventions": int(metrics["error_interventions"]),
            "control_interventions": int(metrics["control_interventions"]),
            "error_positive_realization_rate": metrics[
                "error_positive_realization_rate"
            ],
            "error_improvement": metrics["error_improvement"],
            "control_improvement": metrics["control_improvement"],
            "paired_error_minus_control": metrics[
                "paired_error_minus_control"
            ],
            "stability": row["stability"],
            "plateau": row["plateau"],
            "intervention_set_sha256": row["intervention_set_sha256"],
            "failed_gates": list(row["failed_gates"]),
        },
    }


def preregister(
    screen: dict[str, Any],
    audit: dict[str, Any],
    screen_identity: tuple[str, str, str],
    audit_identity: tuple[str, str, str],
) -> dict[str, Any]:
    if (
        screen.get("schema") != ridge.SCHEMA
        or screen.get("verdict") != ridge.NOT_ESTABLISHED
        or screen.get("passed") is not False
        or screen.get("passing_candidates") != 0
        or screen.get("selected") is not None
        or screen.get("sham") is not None
    ):
        raise ValueError("power extension requires the certified negative ridge screen")
    if (
        audit.get("schema") != AUDIT_SCHEMA
        or audit.get("verdict") != AUDIT_READY
        or audit.get("passed") is not True
        or audit.get("scientific_passed") is not False
        or audit.get("family_closed") is not True
        or audit.get("mechanism")
        != "PAIRED_EFFECT_NOT_ESTABLISHED_DESPITE_OTHER_GATES"
    ):
        raise ValueError("power extension requires the certified terminal ridge audit")
    source = audit.get("source") or {}
    if (
        source.get("job") != screen_identity[0]
        or source.get("attempt") != screen_identity[1]
        or source.get("code_sha") != screen_identity[2]
        or source.get("verdict") != ridge.NOT_ESTABLISHED
    ):
        raise ValueError("ridge screen/audit identity chain drift")
    for report, name in ((screen, "screen"), (audit, "audit")):
        for key in (
            "feature_audit_profile_rows_examined",
            "feature_audit_action_value_reads",
            "outer_confirm_action_value_reads",
            "pattern_eval_fits",
            "production_model_fits",
            "strength_games",
            "new_selfplay_games",
            "frozen_reads",
            "holdout_reads",
            "new_targets",
            "fits",
        ):
            if key in report and int(report[key]) != 0:
                raise ValueError(f"{name} sealed/forbidden counter drift: {key}")

    eligible = [
        row
        for row in screen["candidates"]
        if all(value or key == PAIRED_GATE for key, value in _all_gates(row).items())
    ]
    if len(eligible) != int(audit["candidates_passing_all_except_paired"]):
        raise ValueError("all-except-paired candidate count drift")
    if not eligible:
        raise ValueError("no ridge hypothesis is eligible for fresh confirmation")
    for row in eligible:
        if row["failed_gates"] != [PAIRED_GATE]:
            raise ValueError("eligible candidate failure set drift")

    eligible.sort(
        key=lambda row: (
            -float(row["metrics"]["paired_error_minus_control"]["ci95"][0]),
            -float(row["metrics"]["paired_error_minus_control"]["mean"]),
            -float(row["metrics"]["error_improvement"]["mean"]),
            -float(row["alpha"]),
            float(row["cap_cp"]),
            -float(row["threshold_cp"]),
            ridge.MODES.index(row["mode"]),
        )
    )
    selected = _compact_candidate(eligible[0])
    protocol = {
        "status": "new_confirmatory_branch_after_discovery_family_closed",
        "hypotheses_considered": 1,
        "selection_rule": "among_candidates_passing_every_gate_except_paired_ci_choose_max_paired_lower_then_mean_then_error_mean_then_stronger_anchor_then_smaller_cap_then_higher_threshold_then_strict_mode",
        "model_training": {
            "population": "immutable_1508_gate_fit_pairs_only",
            "targets": "immutable_1508_exact_action_values_only",
            "fit": "one_full_training_fit_with_frozen_alpha_and_fold_local_feature_definition",
            "fresh_extension_labels_used_for_fit": False,
            "feature_audit_or_outer_confirm_used_for_fit": False,
        },
        "fresh_pair_mining": {
            "pair_count_exact": FRESH_PAIRS,
            "seed": MINING_SEED,
            "source": "certified_CURRICULUM_champion_game_trajectories_not_used_by_1504_1508_or_any_sealed_split",
            "candidate_order": "seeded_canonical_hash_order_before_action_target_reconstruction",
            "error_population": "CURRICULUM_loss_trajectory_state_inside_fixed_max_depth_score_spread_annulus_then_exact_teacher_disagreement_boolean",
            "control_population": "target_free_phase_material_WDL_branching_matched_state_with_exact_teacher_agreement",
            "target_free_before_selection": True,
            "label_based_ranking": False,
            "maximum_states_per_source_game": 2,
            "opening_id_disjoint_from_all_discovery_and_holdout_components": True,
            "source_game_disjoint_from_all_discovery_and_holdout_components": True,
            "canonical_state_unique": True,
            "stop_rule": "first_300_valid_pairs_in_frozen_pre_target_order",
        },
        "exact_target_reconstruction": {
            "teacher_and_search_contract": "byte_identical_to_1508_gate_fit_atlas",
            "symmetry": "original_and_exact_mapped_image",
            "targets_generated_only_after_target_free_candidate_order_is_frozen": True,
        },
        "fresh_confirmation": {
            "population": "exactly_300_new_pairs_never_used_for_model_or_candidate_selection",
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "sham_replicates": SHAM_REPLICATES,
            "sham_seed": SHAM_SEED,
            "minimum_error_interventions": MIN_ERROR_INTERVENTIONS,
            "minimum_control_interventions": MIN_CONTROL_INTERVENTIONS,
            "minimum_total_interventions": MIN_TOTAL_INTERVENTIONS,
            "error_improvement_ci95_lower_gt_cp": 0.0,
            "paired_error_minus_control_ci95_lower_gt_cp": 0.0,
            "control_mean_gain_floor_cp": -2.0,
            "minimum_error_positive_realization_rate": 0.60,
            "minimum_aligned_symmetry": 0.70,
            "maximum_symmetry_drop": 0.02,
            "real_paired_mean_must_exceed_sham_q99": True,
            "all_gates_required_jointly": True,
        },
        "after_pass": "separate_immutable_production_refit_and_sealed_feature_audit_preregistration",
        "after_fail": "close_power_extension_without_opening_historical_holdouts",
    }
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "screen_source": {
            "job": screen_identity[0],
            "attempt": screen_identity[1],
            "code_sha": screen_identity[2],
            "verdict": screen["verdict"],
        },
        "audit_source": {
            "job": audit_identity[0],
            "attempt": audit_identity[1],
            "code_sha": audit_identity[2],
            "verdict": audit["verdict"],
        },
        "discovery_family_closed": True,
        "eligible_hypotheses": len(eligible),
        "selected_hypothesis": selected,
        "protocol": protocol,
        "new_targets": 0,
        "holdout_reads": 0,
        "diagnostic_fits": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "fresh_pair_mining_authorized": True,
        "fresh_target_reconstruction_authorized": False,
        "historical_holdout_read_authorized": False,
        "production_rule_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "target_free_fresh_pair_availability_and_cost_preflight",
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--screen", type=Path, required=True)
    root.add_argument("--screen-job", required=True)
    root.add_argument("--screen-attempt", required=True)
    root.add_argument("--screen-code", required=True)
    root.add_argument("--audit", type=Path, required=True)
    root.add_argument("--audit-job", required=True)
    root.add_argument("--audit-attempt", required=True)
    root.add_argument("--audit-code", required=True)
    root.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    report = preregister(
        json.loads(args.screen.read_text()),
        json.loads(args.audit.read_text()),
        (args.screen_job, args.screen_attempt, args.screen_code),
        (args.audit_job, args.audit_attempt, args.audit_code),
    )
    report["screen_sha256"] = hashlib.sha256(args.screen.read_bytes()).hexdigest()
    report["audit_sha256"] = hashlib.sha256(args.audit.read_bytes()).hexdigest()
    _publish(args.output, report)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "eligible_hypotheses": report["eligible_hypotheses"],
                "selected_hypothesis": report["selected_hypothesis"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
