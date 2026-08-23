#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pre-register the single target-free trace proxy selected by 1506."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from jobs.tools import l3_curriculum_error_action_ranker as ranker
    from jobs.tools import l3_curriculum_error_trace_variability_screen as trace
except ModuleNotFoundError:  # pragma: no cover
    import l3_curriculum_error_action_ranker as ranker  # type: ignore
    import l3_curriculum_error_trace_variability_screen as trace  # type: ignore


SCHEMA = "jass.l3_curriculum_error_trace_proxy_preregistration.v1"
READY = "JASS_CURRICULUM_ERROR_TRACE_PROXY_PREREGISTERED"
SELECTED_PROXY = "max_depth_score_spread_cp"
LOWER_OPEN = 52.0
UPPER_CLOSED = 154.0
ALPHA = 100.0
CAP_CP = 75.0
FOLDS = 5
FOLD_SEED = 2026082251
THRESHOLDS_CP = (0.0, 5.0, 10.0, 15.0, 25.0, 40.0, 60.0)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def analyze(
    trace_report: dict[str, Any],
    coverage_report: dict[str, Any],
    action_source: dict[str, Any],
    action_identity: tuple[str, str, str],
) -> dict[str, Any]:
    if trace_report.get("schema") != trace.SCHEMA or trace_report.get("verdict") != trace.READY or trace_report.get("passed") is not True:
        raise ValueError("pre-registration requires the passed trace variability screen")
    if trace_report.get("preregistration_authorized") is not True:
        raise ValueError("trace screen did not authorize pre-registration")
    for key in ("exact_action_value_reads", "outer_confirm_profile_rows_examined", "outer_confirm_action_value_reads", "diagnostic_fits", "pattern_eval_fits", "strength_games", "new_selfplay_games", "frozen_reads"):
        if int(trace_report.get(key, -1)) != 0:
            raise ValueError(f"trace sealed/forbidden counter drift: {key}")
    selected = trace_report.get("selected_proxy") or {}
    if selected.get("name") != SELECTED_PROXY or int(selected.get("priority", -1)) != 0 or selected.get("passed") is not True:
        raise ValueError("first predeclared trace proxy identity drift")
    if float(selected.get("lower_open", -1.0)) != LOWER_OPEN or float(selected.get("upper_closed", -1.0)) != UPPER_CLOSED:
        raise ValueError("selected trace proxy threshold drift")
    candidates = trace_report.get("candidates", [])
    passing = [row for row in candidates if row.get("passed") is True]
    if not passing or passing[0].get("name") != SELECTED_PROXY:
        raise ValueError("selected proxy is not the first passing predeclared proxy")

    if coverage_report.get("verdict") != "JASS_CURRICULUM_ERROR_PAIRED_COVERAGE_SCREEN_NOT_ESTABLISHED":
        raise ValueError("coverage source verdict drift")
    action_job, action_attempt, action_code = action_identity
    if coverage_report.get("source_job") != action_job or coverage_report.get("source_attempt") != action_attempt:
        raise ValueError("coverage/action-source chain drift")
    if coverage_report.get("source_code_sha") != action_code or action_source.get("source_code_sha") != action_code:
        raise ValueError("coverage/action-source code drift")
    if coverage_report.get("champion_sha256") != action_source.get("champion_sha256"):
        raise ValueError("coverage/action-source champion drift")
    if action_source.get("verdict") != "JASS_CURRICULUM_ERROR_ACTION_SOURCE_READY":
        raise ValueError("action source verdict drift")
    for key in ("pattern_bucket_aggregate_reads", "pattern_eval_fits", "production_model_fits", "strength_games", "frozen_reads"):
        if int(action_source.get(key, -1)) != 0:
            raise ValueError(f"action-source forbidden counter drift: {key}")

    architecture = {
        "family": "canonical_paired_trace_pairwise_ridge_residual_with_fixed_variability_gate",
        "anchor": "unaltered_CURRICULUM_Q00_d9_action",
        "features": list(ranker.FEATURE_NAMES),
        "feature_depths": list(ranker.FEATURE_DEPTHS),
        "alpha": ALPHA,
        "correction_cap_cp": CAP_CP,
        "risk_gate": {
            "proxy": SELECTED_PROXY,
            "definition": "max_over_original_and_mapped_exact_image_and_d6_d9_of_root_action_score_max_minus_min",
            "lower_open": LOWER_OPEN,
            "upper_closed": UPPER_CLOSED,
            "outside_gate": "byte_identical_CURRICULUM_action",
        },
        "training": {
            "population": "1506_gate_fit_components_only",
            "weighting": "pair_equal_role_equal_one_decision_per_opening_role",
            "folds": FOLDS,
            "fold_unit": "opening_game_exact_state_connected_component",
            "fold_seed": FOLD_SEED,
            "rms": "fold_local",
            "threshold_candidates_cp": list(THRESHOLDS_CP),
            "threshold_selection": "maximize_OOF_paired_error_minus_control_lower_ci_then_higher_threshold",
            "minimum_error_interventions": 12,
            "minimum_control_interventions": 8,
            "minimum_total_interventions": 20,
            "required_error_positive_realization_rate": 0.60,
            "required_control_mean_gain_floor_cp": -2.0,
        },
        "decision": {
            "paired_features": "average_original_and_mapped_exact_image_features_in_canonical_coordinates",
            "score_base": "each_orientation_unaltered_CURRICULUM_root_scores",
            "consensus": "original_and_mapped_image_corrected_argmax_must_match_and_both_advantages_meet_threshold",
            "abstention": "unaltered_CURRICULUM_action",
            "symmetry": "canonical_action_mapping_with_exact_image_consensus",
        },
        "required_validation_controls": [
            "same_cost_shuffled_residual",
            "same_cost_zero_residual_anchored_to_CURRICULUM",
            "unaltered_CURRICULUM_secondary",
        ],
        "validation": {
            "population": "1506_feature_audit_components_once",
            "outer_confirm": "sealed_until_validation_pass",
            "error_vs_anchor_ci95_lower_gt_cp": 0.0,
            "paired_error_minus_control_ci95_lower_gt_cp": 0.0,
            "control_vs_anchor_ci95_lower_ge_cp": -2.0,
            "minimum_error_interventions": 6,
            "minimum_error_positive_realization_rate": 0.60,
            "maximum_absolute_mean_calibration_bias_cp": 75.0,
            "minimum_aligned_symmetry": 0.70,
            "maximum_symmetry_drop": 0.02,
            "sham_replicates": 100,
        },
    }
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "coverage_source": {
            "job": trace_report.get("coverage_job"),
            "attempt": trace_report.get("coverage_attempt"),
            "code_sha": trace_report.get("coverage_code_sha"),
            "pairs_sha256": trace_report.get("pairs_sha256"),
        },
        "champion_sha256": action_source["champion_sha256"],
        "jass_sha256": action_source["jass_sha256"],
        "search_params_sha256": action_source["search_params_sha256"],
        "selected_proxy_evidence": selected,
        "fixed_architecture": architecture,
        "architectures_considered": 1,
        "validation_action_value_reads": 0,
        "outer_confirm_profile_rows_examined": 0,
        "outer_confirm_action_value_reads": 0,
        "diagnostic_fits": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "validation_fit_authorized": True,
        "production_rule_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "one_shot_trace_proxy_feature_audit_validation",
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--trace-report", type=Path, required=True)
    root.add_argument("--trace-job", required=True)
    root.add_argument("--trace-attempt", required=True)
    root.add_argument("--trace-code", required=True)
    root.add_argument("--coverage-report", type=Path, required=True)
    root.add_argument("--action-source", type=Path, required=True)
    root.add_argument("--action-job", required=True)
    root.add_argument("--action-attempt", required=True)
    root.add_argument("--action-code", required=True)
    root.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    output = analyze(
        json.loads(args.trace_report.read_text()),
        json.loads(args.coverage_report.read_text()),
        json.loads(args.action_source.read_text()),
        (args.action_job, args.action_attempt, args.action_code),
    )
    output["trace_report_sha256"] = _sha256(args.trace_report)
    output["trace_screen"] = {
        "job": args.trace_job,
        "attempt": args.trace_attempt,
        "code_sha": args.trace_code,
    }
    output["coverage_report_sha256"] = _sha256(args.coverage_report)
    output["action_source_sha256"] = _sha256(args.action_source)
    _publish(args.output, output)
    print(json.dumps({"verdict": output["verdict"], "proxy": SELECTED_PROXY}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
