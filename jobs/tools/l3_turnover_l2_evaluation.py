#!/usr/bin/env python3
"""Aggregate the preregistered L3-PURE TURNOVER L2 screen."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from l3_corrected_conversion_matrix import paired_conversion
    from l3_replay25_evaluation import force_row, load
except ModuleNotFoundError:
    from jobs.tools.l3_corrected_conversion_matrix import paired_conversion
    from jobs.tools.l3_replay25_evaluation import force_row, load


LEAD = "TURNOVER_L2_SCREEN_LEAD_REVIEW"
MULTIPLE = "TURNOVER_L2_SCREEN_MULTIPLE_LEADS_REVIEW"
DIRECTIONAL = "TURNOVER_L2_SCREEN_DIRECTIONAL_CONFIRMATION_REVIEW"
NO_LEAD = "TURNOVER_L2_SCREEN_NO_LEAD_REVIEW"

F2M_MODEL_SHA = "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
TURNOVER_MODEL_SHA = (
    "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
)
TURNOVER_CORPUS_SHA = (
    "9b7db67a87025baf9115c72512312ac13ace076cef700c54ff1862f4ab240a2d"
)
TURNOVER_META_SHA = (
    "acf3bbf4a28e7b44a1077df06bca9658cd4b189fc4cf11ee7f56720661626682"
)
TURNOVER_CODE_SHA = "336bb98451a205266d6646c4d801027af4b30294"
ARMS = ("L2_1E5", "L2_1E4")
STRATA = ("p3_mince", "p4_egal")


def _compact_conversion(report: dict[str, Any]) -> dict[str, Any]:
    if int(report.get("n_pos", 0)) != 300:
        raise ValueError("expected 300 conversion positions")
    return {
        key: report[key]
        for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
    }


def build_evaluation(
    *,
    force_dir: Path,
    conversion_dir: Path,
    training_summary_path: Path,
    preflight_path: Path,
    turnover_training_path: Path,
    turnover_confirmation_path: Path,
    opening_manifest_path: Path,
    expected_opening_seed: int,
    expected_opening_sha256: str,
    bootstrap_samples: int = 200_000,
    seed: int = 986_001,
) -> dict[str, Any]:
    training = load(training_summary_path)
    preflight = load(preflight_path)
    turnover = load(turnover_training_path)
    confirmation = load(turnover_confirmation_path)
    openings = load(opening_manifest_path)

    if (
        training.get("verdict") != "TURNOVER_L2_TRAINING_SCREEN_READY"
        or training.get("experiment_variant") != "TURNOVER_1_1_L2_SCREEN"
        or training.get("parent") != "F2M"
        or training.get("parent_model_sha256") != F2M_MODEL_SHA
        or training.get("control", {}).get("model_sha256") != TURNOVER_MODEL_SHA
        or training.get("control", {}).get("l2") != 3e-5
        or training.get("control", {}).get("source_code_sha")
        != TURNOVER_CODE_SHA
        or training.get("training_records") != 2_000_000
        or training.get("training_corpus_sha256") != TURNOVER_CORPUS_SHA
        or training.get("training_meta_sha256") != TURNOVER_META_SHA
        or training.get("historical_replay_records") != 1_000_000
        or training.get("fresh_records") != 1_000_000
        or training.get("new_generation_performed") is not False
        or training.get("external_teacher_inputs") != 0
        or training.get("evaluation_authorized") is not True
        or training.get("promotion_authorized") is not False
        or training.get("automatic_next_job") is not None
    ):
        raise ValueError("L2 training contract mismatch")
    expected_l2 = {"L2_1E5": 1e-5, "L2_1E4": 1e-4}
    for arm, l2 in expected_l2.items():
        value = training.get("arms", {}).get(arm, {})
        if (
            value.get("l2") != l2
            or not isinstance(value.get("model_sha256"), str)
            or len(value["model_sha256"]) != 64
            or value.get("optimizer", {}).get("success") is not True
        ):
            raise ValueError(f"{arm}: invalid converged training arm")

    if (
        preflight.get("verdict") != "TURNOVER_L2_PREFLIGHT_READY"
        or preflight.get("experiment_variant") != "TURNOVER_1_1_L2_SCREEN"
        or preflight.get("jnnw_sha256") != TURNOVER_CORPUS_SHA
        or preflight.get("jsm_sha256") != TURNOVER_META_SHA
        or preflight.get("l2_levels") != [1e-5, 3e-5, 1e-4]
        or preflight.get("control_l2") != 3e-5
        or preflight.get("control_source_code_sha") != TURNOVER_CODE_SHA
        or preflight.get("training_authorized") is not True
        or preflight.get("promotion_authorized") is not False
        or preflight.get("automatic_next_job") is not None
        or training.get("preflight_job") is None
        or training.get("preflight_code_sha") != preflight.get("code_sha")
    ):
        raise ValueError("L2 preflight contract mismatch")
    if (
        turnover.get("experiment_variant") != "TURNOVER_1_1"
        or turnover.get("code_sha") != TURNOVER_CODE_SHA
        or turnover.get("model_sha256") != TURNOVER_MODEL_SHA
        or turnover.get("training_corpus_sha256") != TURNOVER_CORPUS_SHA
        or turnover.get("training_meta_sha256") != TURNOVER_META_SHA
        or confirmation.get("verdict") != "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW"
        or confirmation.get("all_guardrails_pass") is not True
        or confirmation.get("promotion_authorized") is not False
        or confirmation.get("automatic_next_job") is not None
    ):
        raise ValueError("TURNOVER control contract mismatch")

    preflight_openings = preflight.get("evaluation_openings", {})
    excluded = openings.get("excluded_sources", {})
    if (
        openings.get("records") != 500
        or openings.get("unique_records") != 500
        or openings.get("overlap_records") != 0
        or openings.get("generator_seed") != expected_opening_seed
        or openings.get("sha256") != expected_opening_sha256
        or preflight_openings.get("seed") != expected_opening_seed
        or preflight_openings.get("sha256") != expected_opening_sha256
        or preflight_openings.get("manifest") != openings
        or not any(str(path).endswith("prior-replay25.fen") for path in excluded)
    ):
        raise ValueError("L2 independent opening-pool contract mismatch")

    force: dict[str, Any] = {}
    primary: dict[str, Any] = {}
    eligible: list[str] = []
    for arm in ARMS:
        for view in ("q00", "native"):
            key = f"{view}_{arm}_vs_TURNOVER"
            force[key] = force_row(
                force_dir / f"force-{view}-{arm}-vs-TURNOVER.json"
            )
        primary[arm] = {
            view: {
                "positive_point_estimate":
                    force[f"{view}_{arm}_vs_TURNOVER"]["rate"] > 0.5,
                "superiority_established":
                    force[f"{view}_{arm}_vs_TURNOVER"]["ci_low"] > 0.5,
                "regression_not_established":
                    force[f"{view}_{arm}_vs_TURNOVER"]["ci_high"] >= 0.5,
            }
            for view in ("q00", "native")
        }
        if all(
            primary[arm][view]["positive_point_estimate"]
            for view in ("q00", "native")
        ):
            eligible.append(arm)

    guardrails: dict[str, Any] = {}
    conversion: dict[str, Any] = {}
    for arm_index, arm in enumerate(eligible):
        arm_guards: dict[str, bool] = {}
        for opponent in ("F2M", "GEN2"):
            for view in ("q00", "native"):
                key = f"{view}_{arm}_vs_{opponent}"
                force[key] = force_row(
                    force_dir / f"force-{view}-{arm}-vs-{opponent}.json"
                )
                arm_guards[
                    f"{opponent.lower()}_{view}_regression_not_established"
                ] = force[key]["ci_high"] >= 0.5
        conversion[arm] = {}
        for stratum_index, stratum in enumerate(STRATA):
            candidate = load(conversion_dir / f"{arm}-{stratum}.json")
            control = load(conversion_dir / f"TURNOVER-{stratum}.json")
            paired = paired_conversion(
                candidate,
                control,
                seed=seed + 10 * arm_index + stratum_index,
                bootstrap_samples=bootstrap_samples,
            )
            conversion[arm][stratum] = {
                "candidate": _compact_conversion(candidate),
                "control": _compact_conversion(control),
                "paired_delta_candidate_minus_control": paired,
            }
            arm_guards[f"{stratum}_absolute_conversion_floor"] = (
                float(candidate["conversion"]) >= 0.95
            )
            arm_guards[f"{stratum}_regression_over_3pp_not_established"] = (
                paired["ci_high"] >= -0.03
            )
        guardrails[arm] = {
            "checks": arm_guards,
            "all_pass": all(arm_guards.values()),
        }

    confirmed = [
        arm
        for arm in eligible
        if all(
            primary[arm][view]["superiority_established"]
            for view in ("q00", "native")
        )
        and guardrails[arm]["all_pass"]
    ]
    directional = [
        arm
        for arm in eligible
        if arm not in confirmed
        and all(
            primary[arm][view]["regression_not_established"]
            for view in ("q00", "native")
        )
        and guardrails[arm]["all_pass"]
    ]
    if len(confirmed) == 1:
        verdict = LEAD
        recommendation = "human_review_l2_lead_before_replay_cross"
        selected = confirmed[0]
    elif len(confirmed) > 1:
        verdict = MULTIPLE
        recommendation = "direct_independent_comparison_of_multiple_l2_leads"
        selected = None
    elif directional:
        verdict = DIRECTIONAL
        recommendation = "independent_confirmation_of_directional_l2_arms"
        selected = directional[0] if len(directional) == 1 else None
    else:
        verdict = NO_LEAD
        recommendation = "retain_l2_3e5_and_close_l2_factor"
        selected = "L2_3E5_CONTROL"

    return {
        "schema": 1,
        "verdict": verdict,
        "protocol": {
            "candidate_arms": list(ARMS),
            "control": "L2_3E5_CONTROL",
            "changed_factor": "l2_regularization",
            "fixed_corpus": "TURNOVER_1_1",
            "fixed_training_volume": 2_000_000,
            "games_per_force_cell": 1_000,
            "openings": 500,
            "paired_colors": True,
            "staged_guard_evaluation": True,
        },
        "force": force,
        "primary_checks": primary,
        "eligible_for_guard_cells": eligible,
        "guardrails": guardrails,
        "conversion": conversion,
        "confirmed_leads": confirmed,
        "directional_arms": directional,
        "recommended_l2_arm": selected,
        "recommendation": recommendation,
        "training_summary": training,
        "preflight_certificate": preflight,
        "turnover_training_summary": turnover,
        "turnover_confirmation_certificate": confirmation,
        "opening_manifest": openings,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--conversion-dir", required=True, type=Path)
    parser.add_argument("--training-summary", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--turnover-training", required=True, type=Path)
    parser.add_argument("--turnover-confirmation", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--expected-opening-seed", required=True, type=int)
    parser.add_argument("--expected-opening-sha256", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=986_001)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()
    payload = build_evaluation(
        force_dir=args.force_dir,
        conversion_dir=args.conversion_dir,
        training_summary_path=args.training_summary,
        preflight_path=args.preflight,
        turnover_training_path=args.turnover_training,
        turnover_confirmation_path=args.turnover_confirmation,
        opening_manifest_path=args.opening_manifest,
        expected_opening_seed=args.expected_opening_seed,
        expected_opening_sha256=args.expected_opening_sha256,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
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
