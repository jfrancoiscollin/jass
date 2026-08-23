#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Freeze the post-hoc endgame-abstention hypothesis for new-pool confirmation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "jass.l3_curriculum_error_endgame_abstention_preregistration.v1"
READY = "JASS_CURRICULUM_ERROR_ENDGAME_ABSTENTION_PREREGISTERED"
AUDIT_SCHEMA = "jass.curriculum_error_endgame_abstention_final_audit.v1"
AUDIT_READY = "JASS_CURRICULUM_ERROR_ENDGAME_ABSTENTION_DISCOVERY_READY"

FRESH_PAIRS = 600
OPENINGS_PER_POOL = 3840
SOURCE_GAMES = 15360
MIN_ERROR_INTERVENTIONS = 60
MIN_CONTROL_INTERVENTIONS = 40
MIN_TOTAL_INTERVENTIONS = 100
MIN_ERROR_INTERVENTIONS_PER_POOL = 25
MIN_CONTROL_INTERVENTIONS_PER_POOL = 18
BOOTSTRAP_SAMPLES = 200_000
SHAM_REPLICATES = 1_000
POOL_SEEDS = (2026082301, 2026082302)
SPLIT_SEED = 2026082303
MINING_SEED = 2026082304
BOOTSTRAP_SEED = 2026082305
SHAM_SEED = 2026082306

FROZEN_HYPOTHESIS = {
    "alpha": 300.0,
    "cap_cp": 100.0,
    "mode": "strict_both_change",
    "threshold_cp": 10.0,
    "phase_rule": {
        "feature": "production_piece_features.phase",
        "abstain_exact_value": "endgame",
        "operation_when_abstaining": "unaltered_CURRICULUM_anchor",
        "applies_symmetrically_to_error_and_control": True,
        "applies_symmetrically_to_original_and_exact_image": True,
        "all_other_phases_use_frozen_residual_bit_identically": True,
    },
}


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def preregister(audit: dict[str, Any], identity: tuple[str, str, str]) -> dict[str, Any]:
    if (
        audit.get("schema") != AUDIT_SCHEMA
        or audit.get("verdict") != AUDIT_READY
        or audit.get("passed") is not True
        or audit.get("rule") != "abstain_when_phase_equals_endgame"
        or audit.get("status") != "posthoc_discovery_only_not_confirmed"
    ):
        raise ValueError("endgame preregistration requires the certified positive 1519a discovery audit")
    if audit.get("fresh_1517_reuse_for_validation_forbidden") is not True:
        raise ValueError("1519a does not forbid reuse of 1517 for validation")
    if audit.get("preregistration_on_new_fresh_pools_recommended") is not True:
        raise ValueError("1519a did not recommend new-pool preregistration")
    if not audit.get("gates") or not all(bool(value) for value in audit["gates"].values()):
        raise ValueError("1519a discovery gates are incomplete")
    for key in (
        "production_refit_authorized", "strength_gate_authorized",
        "promotion_authorized", "automatic_continuation",
    ):
        if audit.get(key) is not False:
            raise ValueError(f"1519a authorization drift: {key}")
    for key in ("new_exact_targets", "fits", "strength_games", "new_selfplay", "frozen_reads"):
        if int(audit.get(key, -1)) != 0:
            raise ValueError(f"1519a forbidden accounting drift: {key}")
    source = audit.get("source_identity", {})
    if (
        source.get("job_id") != identity[0]
        or source.get("attempt_id") != identity[1]
        or source.get("code_sha") != identity[2]
    ):
        raise ValueError("1519a source identity drift")

    protocol = {
        "status": "new_confirmatory_branch_from_posthoc_phase_discovery",
        "hypotheses_considered": 1,
        "discovery_source_is_not_validation": True,
        "model_training": {
            "population": "immutable_1508_gate_fit_pairs_only",
            "targets": "immutable_1508_exact_action_values_only",
            "fit": "one_full_training_fit_with_alpha_300",
            "fresh_labels_used_for_fit": False,
            "1517_labels_used_for_fit": False,
        },
        "decision_rule": FROZEN_HYPOTHESIS,
        "fresh_campaign": {
            "pools": 2,
            "openings_per_pool": OPENINGS_PER_POOL,
            "games_exact": SOURCE_GAMES,
            "pool_seeds": list(POOL_SEEDS),
            "split_seed": SPLIT_SEED,
            "same_byte_identical_CURRICULUM_both_sides": True,
            "opening_disjoint_from_1492_1504_1515_and_between_new_pools": True,
            "source_game_disjoint_from_all_training_discovery_and_validation_sources": True,
            "target_free_before_candidate_order": True,
        },
        "fresh_pair_mining": {
            "pair_count_exact": FRESH_PAIRS,
            "seed": MINING_SEED,
            "candidate_order": "seeded_canonical_hash_order_before_action_targets",
            "matching": "same_phase_material_WDL_branching_contract_as_1515",
            "maximum_states_per_source_game": 2,
            "canonical_state_unique": True,
            "stop_rule": "first_600_valid_pairs_in_frozen_pre_target_order",
        },
        "fresh_confirmation": {
            "bootstrap_samples": BOOTSTRAP_SAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "sham_replicates": SHAM_REPLICATES,
            "sham_seed": SHAM_SEED,
            "minimum_error_interventions": MIN_ERROR_INTERVENTIONS,
            "minimum_control_interventions": MIN_CONTROL_INTERVENTIONS,
            "minimum_total_interventions": MIN_TOTAL_INTERVENTIONS,
            "minimum_error_interventions_per_pool": MIN_ERROR_INTERVENTIONS_PER_POOL,
            "minimum_control_interventions_per_pool": MIN_CONTROL_INTERVENTIONS_PER_POOL,
            "error_improvement_ci95_lower_gt_cp": 0.0,
            "paired_error_minus_control_ci95_lower_gt_cp": 0.0,
            "each_pool_error_point_gt_cp": 0.0,
            "each_pool_paired_point_gt_cp": 0.0,
            "global_control_mean_floor_cp": -2.0,
            "each_pool_control_mean_floor_cp": -2.0,
            "minimum_error_positive_realization_rate": 0.60,
            "minimum_aligned_symmetry": 0.70,
            "maximum_symmetry_drop": 0.02,
            "endgame_interventions_exactly": 0,
            "endgame_decisions_bit_identical_to_CURRICULUM_anchor": True,
            "non_endgame_decisions_bit_identical_to_frozen_1517_residual": True,
            "real_paired_mean_must_exceed_sham_q99": True,
            "all_gates_required_jointly": True,
        },
        "after_pass": "separate_anchored_local_refit_and_oos_audit_preregistration",
        "after_fail": "close_alpha300_cap100_residual_family",
    }
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "discovery_audit_source": {
            "job": identity[0], "attempt": identity[1], "code_sha": identity[2],
            "verdict": audit["verdict"],
        },
        "discovery_readout": {
            "baseline_global": audit["baseline_global"],
            "adjusted_global": audit["adjusted_global"],
            "baseline_by_pool": audit["baseline_by_pool"],
            "adjusted_by_pool": audit["adjusted_by_pool"],
            "removed_interventions": audit["removed_interventions"],
            "remaining_error_positive_realization_rate": audit["remaining_error_positive_realization_rate"],
        },
        "frozen_hypothesis": FROZEN_HYPOTHESIS,
        "protocol": protocol,
        "new_targets": 0, "fits": 0, "strength_games": 0,
        "new_selfplay_games": 0, "frozen_reads": 0,
        "fresh_pair_availability_authorized": True,
        "fresh_target_reconstruction_authorized": False,
        "production_refit_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "two_new_pool_target_free_availability_and_cost_preflight",
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--audit", type=Path, required=True)
    root.add_argument("--audit-job", required=True)
    root.add_argument("--audit-attempt", required=True)
    root.add_argument("--audit-code", required=True)
    root.add_argument("--output", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    report = preregister(
        json.loads(args.audit.read_text()),
        (args.audit_job, args.audit_attempt, args.audit_code),
    )
    report["audit_sha256"] = hashlib.sha256(args.audit.read_bytes()).hexdigest()
    _publish(args.output, report)
    print(json.dumps({
        "verdict": report["verdict"], "fresh_pairs": FRESH_PAIRS,
        "phase_rule": report["frozen_hypothesis"]["phase_rule"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
