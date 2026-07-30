#!/usr/bin/env python3
"""Aggregate the preregistered FAILED_X2-vs-UNWEIGHTED force readout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_reverse_seed_readout as common


ABOVE_95 = "L3_PURE_FAILED_X2_ABOVE_UNWEIGHTED_IC95"
ABOVE_90 = "L3_PURE_FAILED_X2_ABOVE_UNWEIGHTED_IC90"
DIRECTIONAL = "L3_PURE_FAILED_X2_DIRECTIONAL"
BELOW = "L3_PURE_FAILED_X2_BELOW_UNWEIGHTED"
INCONCLUSIVE = "L3_PURE_FAILED_X2_VS_UNWEIGHTED_INCONCLUSIVE"


def _validate_training(
    training: dict[str, Any],
    source_code_sha: str,
    control_sha: str,
    treatment_sha: str,
) -> dict[str, Any]:
    design = training.get("design", {})
    arms = training.get("arms", {})
    if (
        training.get("verdict")
        != "L3_PURE_FAILED_CONVERSION_WEIGHTS_CAUSAL_AB_ARMS_READY"
        or training.get("code_sha") != source_code_sha
        or training.get("primary_contrast") != "FAILED_X2 minus UNWEIGHTED"
        or design.get("single_factor") != "train_failed_conversion_weight"
        or design.get("control_weight") != 1.0
        or design.get("treatment_weight") != 2.0
        or design.get("same_records") is not True
        or design.get("same_opening_split") is not True
        or design.get("same_feature_matrix") is not True
        or design.get("same_warm_start") is not True
        or design.get("same_fit") is not True
        or design.get("holdout_weighted") is not False
        or design.get("oversampling") is not False
        or design.get("control_reproduced_historical_model") is not True
        or training.get("external_teacher_inputs") != 0
        or training.get("scientific_result") is not False
        or training.get("promotion_authorized") is not False
        or training.get("automatic_next_job", "missing") is not None
    ):
        raise ValueError("failed-conversion weights training certificate mismatch")

    for arm, expected_sha, uniform, sw_used in (
        ("UNWEIGHTED", control_sha, True, False),
        ("FAILED_X2", treatment_sha, False, True),
    ):
        row = arms.get(arm, {})
        trainer = row.get("trainer_weights", {})
        if (
            row.get("model_sha256") != expected_sha
            or row.get("optimizer", {}).get("success") is not True
            or trainer.get("split", {}).get("holdout_weighted") is not False
            or trainer.get("optimizer", {}).get("uniform_after_normalization")
            is not uniform
            or trainer.get("optimizer", {}).get("sw_all_used") is not sw_used
        ):
            raise ValueError(f"{arm} model/fit/weight certificate mismatch")
    treatment_ess = arms["FAILED_X2"]["trainer_weights"].get(
        "effective_sample_size", {}
    )
    if treatment_ess.get("ess_fraction", 0.0) < 0.80:
        raise ValueError("FAILED_X2 effective sample size below preregistered floor")

    coverage = training.get("training_coverage", {})
    if coverage.get("common_to_both_arms") is not True:
        raise ValueError("training coverage is not certified common")
    compact = common.compact_coverage(coverage.get("common", {}))
    delta = coverage.get("control_minus_treatment", {})
    if any(delta.get(key) != 0 for key in compact):
        raise ValueError("common-corpus training coverage delta is nonzero")
    return compact


def _choose_verdict(
    force: dict[str, dict[str, Any]],
    summed: dict[str, Any],
) -> tuple[str, dict[str, bool]]:
    both_point_positive = all(
        force[view]["rate_treatment"] > 0.5 for view in force
    )
    any_view_regressed_90 = any(
        force[view]["ci90"][1] < 0.5 for view in force
    )
    if both_point_positive and summed["ci95"][0] > 0.5:
        verdict = ABOVE_95
    elif both_point_positive and summed["ci90"][0] > 0.5:
        verdict = ABOVE_90
    elif summed["ci90"][1] < 0.5 or any_view_regressed_90:
        verdict = BELOW
    elif summed["rate_treatment"] > 0.5 and not any_view_regressed_90:
        verdict = DIRECTIONAL
    else:
        verdict = INCONCLUSIVE
    evidence = {
        "both_force_views_point_positive": both_point_positive,
        "summed_force_superiority_90": summed["ci90"][0] > 0.5,
        "summed_force_superiority_95": summed["ci95"][0] > 0.5,
        "any_force_view_regressed_90": any_view_regressed_90,
    }
    return verdict, evidence


def build_readout(
    *,
    force_dir: Path,
    training_summary_path: Path,
    opening_manifest_path: Path,
    expected_games_per_view: int,
    expected_openings: int,
    code_sha: str,
    source_job: str,
    source_attempt: str,
    source_code_sha: str,
    expected_control_sha: str,
    expected_treatment_sha: str,
) -> dict[str, Any]:
    training = common.load(training_summary_path)
    openings = common.load(opening_manifest_path)
    coverage = _validate_training(
        training,
        source_code_sha,
        expected_control_sha,
        expected_treatment_sha,
    )
    if (
        openings.get("records") != expected_openings
        or openings.get("unique_records") != expected_openings
        or openings.get("overlap_records") != 0
    ):
        raise ValueError("independent opening-pool contract mismatch")

    force = {
        view: common.force_cell(
            force_dir / f"force-{view}-FAILED_X2-vs-UNWEIGHTED.json",
            expected_games_per_view,
        )
        for view in ("q00", "native")
    }
    summed = common.summarize_counts(
        sum(force[view]["wins_treatment"] for view in force),
        sum(force[view]["draws"] for view in force),
        sum(force[view]["wins_control"] for view in force),
    )
    verdict, evidence = _choose_verdict(force, summed)
    return {
        "schema": 1,
        "verdict": verdict,
        "code_sha": code_sha,
        "source": {
            "job_id": source_job,
            "attempt_id": source_attempt,
            "code_sha": source_code_sha,
        },
        "models": {
            "control_name": "UNWEIGHTED",
            "control_sha256": expected_control_sha,
            "treatment_name": "FAILED_X2",
            "treatment_sha256": expected_treatment_sha,
        },
        "protocol": {
            "primary_contrast": "FAILED_X2 minus UNWEIGHTED",
            "single_training_factor": "train_failed_conversion_weight",
            "paired_colours": True,
            "fresh_disjoint_openings": True,
            "openings": expected_openings,
            "games_per_view": expected_games_per_view,
            "views": ["q00_depth9", "native_movetime_0.1"],
            "holdout_is_diagnostic_only": True,
            "holdout_not_used_for_selection": True,
        },
        "opening_manifest": openings,
        "force": force,
        "force_views_summed": summed,
        "training_coverage": {
            "common_to_both_arms": True,
            "common": coverage,
            "treatment_minus_control": {key: 0 for key in coverage},
        },
        "decision_evidence": evidence,
        "scientific_result": True,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--training-summary", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--expected-games-per-view", required=True, type=int)
    parser.add_argument("--expected-openings", required=True, type=int)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--source-job", required=True)
    parser.add_argument("--source-attempt", required=True)
    parser.add_argument("--source-code-sha", required=True)
    parser.add_argument("--control-model-sha", required=True)
    parser.add_argument("--treatment-model-sha", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args(argv)
    payload = build_readout(
        force_dir=args.force_dir,
        training_summary_path=args.training_summary,
        opening_manifest_path=args.opening_manifest,
        expected_games_per_view=args.expected_games_per_view,
        expected_openings=args.expected_openings,
        code_sha=args.code_sha,
        source_job=args.source_job,
        source_attempt=args.source_attempt,
        source_code_sha=args.source_code_sha,
        expected_control_sha=args.control_model_sha,
        expected_treatment_sha=args.treatment_model_sha,
    )
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialized, encoding="utf-8")
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
