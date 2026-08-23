#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Joint preregistration for the confirmed, support-limited residual refit."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_curriculum_error_endgame_abstention_confirmation as confirmation
from jobs.tools import l3_curriculum_error_residual_stable_subspace_screen as subspace


SCHEMA = "jass.l3_curriculum_error_anchored_local_refit_preregistration.v1"
READY = "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_PREREGISTERED"
CONFIRMATION_TERMINAL_SCHEMA = confirmation.SCHEMA_TERMINAL
SUBSPACE_TERMINAL_SCHEMA = "jass.curriculum_error_residual_stable_subspace_terminal.v1"
DELTA_RIDGE = 300.0
MAX_DELTA_L2_FRACTION = 0.20
MAX_PER_COEFFICIENT_DELTA_FRACTION = 0.25
HISTORICAL_CORPUS_WEIGHT = 0.50
CONFIRMED_FRESH_CORPUS_WEIGHT = 0.50
OOS_PAIRS = 600
OOS_POOL1_SEED = 2026082311
OOS_POOL2_SEED = 2026082312
OOS_SPLIT_SEED = 2026082313
OOS_BOOTSTRAP_SEED = 2026082314
OOS_BOOTSTRAP_SAMPLES = 200_000
MIN_OOS_ERROR_DECISION_CHANGES = 20
MIN_OOS_CONTROL_DECISION_CHANGES = 12
MIN_OOS_TOTAL_DECISION_CHANGES = 32


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _check_confirmation(report: dict[str, Any]) -> None:
    if (
        report.get("schema") != CONFIRMATION_TERMINAL_SCHEMA
        or report.get("verdict") != confirmation.READY
        or report.get("passed") is not True
        or report.get("fresh_pairs") != 600
        or report.get("fresh_labels_used_for_fit") is not False
        or report.get("anchored_local_refit_preregistration_authorized") is not True
        or report.get("failed_gates") != []
        or not report.get("gates")
        or not all(report["gates"].values())
    ):
        raise ValueError("anchored refit requires the passed 600-pair confirmation")
    selected = report.get("selected_hypothesis") or {}
    if (
        float(selected.get("alpha", -1.0)) != 300.0
        or float(selected.get("cap_cp", -1.0)) != 100.0
        or selected.get("mode") != "strict_both_change"
        or float(selected.get("threshold_cp", -1.0)) != 10.0
    ):
        raise ValueError("confirmed residual hypothesis drift")
    proof = report.get("rule_proof") or {}
    if (
        int(proof.get("endgame_interventions", -1)) != 0
        or proof.get("endgame_decisions_bit_identical_to_anchor") is not True
        or proof.get("non_endgame_decisions_bit_identical_to_frozen_residual")
        is not True
    ):
        raise ValueError("confirmed endgame abstention proof drift")
    for key in (
        "pattern_eval_fits",
        "production_model_fits",
        "strength_games",
        "new_selfplay_games",
        "frozen_reads",
    ):
        if int(report.get(key, -1)) != 0:
            raise ValueError(f"confirmation forbidden counter drift: {key}")


def _check_subspace(report: dict[str, Any]) -> dict[str, Any]:
    if (
        report.get("schema") != SUBSPACE_TERMINAL_SCHEMA
        or report.get("verdict") != subspace.READY
        or report.get("passed") is not True
        or report.get("stable_subspace_candidate_established") is not True
        or report.get("failed_gates") != []
        or not report.get("gates")
        or not all(report["gates"].values())
        or float(report.get("alpha", -1.0)) != 300.0
    ):
        raise ValueError("anchored refit requires the passed stable-subspace screen")
    analysis = report.get("analysis") or {}
    names = list(analysis.get("selected_feature_names") or [])
    indices = list(analysis.get("selected_feature_indices") or [])
    count = int(analysis.get("selected_feature_count", -1))
    support_hash = str(analysis.get("support_sha256", ""))
    if (
        count != len(names)
        or count != len(indices)
        or not 2 <= count <= 8
        or len(set(names)) != count
        or len(set(indices)) != count
        or len(support_hash) != 64
    ):
        raise ValueError("stable subspace support drift")
    for key in (
        "new_exact_target_computations",
        "fresh_label_reads",
        "feature_audit_action_value_reads",
        "outer_confirm_action_value_reads",
        "pattern_eval_fits",
        "production_model_fits",
        "strength_games",
        "new_selfplay_games",
        "frozen_reads",
    ):
        if int(report.get(key, -1)) != 0:
            raise ValueError(f"subspace forbidden counter drift: {key}")
    return {
        "feature_names": names,
        "feature_indices": indices,
        "feature_count": count,
        "support_sha256": support_hash,
        "signed_features": [
            {
                "index": int(row["index"]),
                "name": str(row["name"]),
                "sign": int(row["sign"]),
            }
            for row in analysis.get("features", [])
            if row.get("selected") is True
        ],
    }


def preregister(
    confirmation_report: dict[str, Any],
    subspace_report: dict[str, Any],
    confirmation_identity: tuple[str, str, str],
    subspace_identity: tuple[str, str, str],
) -> dict[str, Any]:
    _check_confirmation(confirmation_report)
    support = _check_subspace(subspace_report)
    confirmation_identities = confirmation_report.get("identities") or {}
    subspace_identities = {
        key: subspace_report.get(key)
        for key in ("champion_sha256", "jass_sha256", "search_params_sha256")
    }
    if confirmation_identities != subspace_identities or any(
        not value for value in confirmation_identities.values()
    ):
        raise ValueError("confirmation/subspace scientific identity drift")

    protocol = {
        "status": "jointly_preregistered_before_any_oos_label",
        "single_hypothesis": True,
        "base_champion": {
            "model": "CURRICULUM",
            "pattern_eval_bytes": "must_remain_sha256_identical",
            "search_and_engine": "must_remain_byte_identical_to_1508_and_1524",
        },
        "training_population": {
            "historical": "immutable_1508_gate_fit_pairs_and_exact_targets",
            "confirmed_fresh": "exactly_600_pairs_certified_by_1524",
            "fresh_confirmation_reclassified_after_terminal_pass": "training_only_never_oos",
            "endgame_states": "excluded_from_delta_fit_because_production_rule_forces_anchor",
            "weighting": "pair_equal_role_equal_then_corpus_equal",
            "historical_weight": HISTORICAL_CORPUS_WEIGHT,
            "confirmed_fresh_weight": CONFIRMED_FRESH_CORPUS_WEIGHT,
        },
        "fit": {
            "family": "support_limited_pairwise_residual_delta_around_alpha300_full_1508_model",
            "base_feature_mean_and_rms": "frozen_exactly_from_full_immutable_1508_alpha300_fit",
            "mutable_feature_indices": support["feature_indices"],
            "mutable_feature_names": support["feature_names"],
            "signed_support_sha256": support["support_sha256"],
            "all_other_coefficients": "bit_identical_to_full_1508_alpha300_model",
            "delta_ridge": DELTA_RIDGE,
            "maximum_delta_l2_fraction_of_base_support_norm": MAX_DELTA_L2_FRACTION,
            "maximum_per_coefficient_delta_fraction_of_base_absolute_value": MAX_PER_COEFFICIENT_DELTA_FRACTION,
            "coefficient_sign_flip": "forbidden",
            "candidate_models": 1,
            "hyperparameter_search": False,
        },
        "production_rule": {
            "endgame": "exact_CURRICULUM_anchor_action",
            "outside_fixed_risk_gate": "exact_CURRICULUM_anchor_action",
            "non_endgame_inside_gate": "anchored_local_residual_alpha300_cap100_strict_both_change_threshold10",
            "cap_cp": 100.0,
            "mode": "strict_both_change",
            "threshold_cp": 10.0,
        },
        "sealed_oos": {
            "pair_count_exact": OOS_PAIRS,
            "two_pools": True,
            "pool1_seed": OOS_POOL1_SEED,
            "pool2_seed": OOS_POOL2_SEED,
            "split_seed": OOS_SPLIT_SEED,
            "opening_and_game_disjoint_from_all_1504_1508_1515_1517_1523_1524_sources": True,
            "target_free_candidate_order": True,
            "maximum_states_per_source_game": 2,
            "canonical_state_unique": True,
            "bootstrap_samples": OOS_BOOTSTRAP_SAMPLES,
            "bootstrap_seed": OOS_BOOTSTRAP_SEED,
            "minimum_error_decision_changes": MIN_OOS_ERROR_DECISION_CHANGES,
            "minimum_control_decision_changes": MIN_OOS_CONTROL_DECISION_CHANGES,
            "minimum_total_decision_changes": MIN_OOS_TOTAL_DECISION_CHANGES,
            "no_oos_label_used_for_fit_or_selection": True,
        },
        "oos_gates_all_required": {
            "fresh_pairs_exactly_600": True,
            "enough_incremental_decision_changes": True,
            "incremental_error_regret_improvement_ci95_lower_gt_0cp": True,
            "incremental_paired_error_minus_control_ci95_lower_gt_0cp": True,
            "incremental_error_and_paired_point_estimates_gt_0cp_in_each_pool": True,
            "incremental_control_mean_ge_minus_1cp_global_and_each_pool": True,
            "error_positive_realization_rate_ge_0_60": True,
            "calibration_absolute_bias_not_worse_by_more_than_2cp": True,
            "aligned_symmetry_ge_0_70": True,
            "symmetry_drop_le_0_02": True,
            "endgame_and_outside_gate_decisions_bit_identical_to_CURRICULUM": True,
            "pattern_eval_sha256_identical": True,
            "mean_rms_and_coefficients_outside_support_bit_identical": True,
        },
        "after_oos_pass": "two_native_primary_strength_gates_on_fresh_disjoint_pools_with_Q00_d9_diagnostic",
        "after_oos_fail": "close_anchored_refit_without_strength_games",
    }
    protocol_hash = hashlib.sha256(_canonical(protocol)).hexdigest()
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "confirmation_source": {
            "job": confirmation_identity[0],
            "attempt": confirmation_identity[1],
            "code_sha": confirmation_identity[2],
            "verdict": confirmation_report["verdict"],
        },
        "subspace_source": {
            "job": subspace_identity[0],
            "attempt": subspace_identity[1],
            "code_sha": subspace_identity[2],
            "verdict": subspace_report["verdict"],
        },
        "identities": confirmation_identities,
        "support": support,
        "protocol": protocol,
        "protocol_sha256": protocol_hash,
        "new_targets": 0,
        "oos_reads": 0,
        "diagnostic_fits": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "anchored_local_refit_authorized": True,
        "oos_campaign_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "anchored_local_refit_and_target_free_oos_availability",
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--confirmation", type=Path, required=True)
    root.add_argument("--confirmation-job", required=True)
    root.add_argument("--confirmation-attempt", required=True)
    root.add_argument("--confirmation-code", required=True)
    root.add_argument("--subspace", type=Path, required=True)
    root.add_argument("--subspace-job", required=True)
    root.add_argument("--subspace-attempt", required=True)
    root.add_argument("--subspace-code", required=True)
    root.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    report = preregister(
        json.loads(args.confirmation.read_text()),
        json.loads(args.subspace.read_text()),
        (args.confirmation_job, args.confirmation_attempt, args.confirmation_code),
        (args.subspace_job, args.subspace_attempt, args.subspace_code),
    )
    report["confirmation_sha256"] = hashlib.sha256(
        args.confirmation.read_bytes()
    ).hexdigest()
    report["subspace_sha256"] = hashlib.sha256(args.subspace.read_bytes()).hexdigest()
    _publish(args.output, report)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "support_sha256": report["support"]["support_sha256"],
                "protocol_sha256": report["protocol_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
