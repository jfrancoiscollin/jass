#!/usr/bin/env python3
"""Aggregate the preregistered L3-PURE 25% replay-dose evaluation."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from l3_corrected_conversion_matrix import paired_conversion
except ModuleNotFoundError:
    from jobs.tools.l3_corrected_conversion_matrix import paired_conversion


CHAMPION_REVIEW = "REPLAY25_CHAMPION_REVIEW_READY"
CAUSAL_BETTER = "REPLAY25_CAUSAL_DOSE_BETTER_REVIEW"
DIRECTIONAL = "REPLAY25_DIRECTIONAL_CONFIRMATION_REVIEW"
CLOSED = "REPLAY25_DOSE_CLOSED_REVIEW"
F2M_MODEL_SHA = "be675b6c1c6360a0a9aa5977ed492284bc8dcc1861ee47bc2e3139046ed769f2"
M2_MODEL_SHA = "75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
TURNOVER_MODEL_SHA = (
    "b2c79b3617c41087191fee04d9aee0e1929ea63ad621c2efeaebc14ae53a7c16"
)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def force_row(path: Path) -> dict[str, Any]:
    value = load(path)
    keys = ("n", "wins_a", "draws", "wins_b", "rate", "elo", "ci_low", "ci_high")
    row = {key: value[key] for key in keys}
    if int(row["n"]) != 1_000:
        raise ValueError(f"{path}: expected 1000 games")
    return row


def compact_coverage(path: Path) -> dict[str, Any]:
    report = load(path)
    if report.get("stage") != "l3_bucket_visits":
        raise ValueError(f"{path}: unexpected coverage stage")
    if int(report["geometry"]["trained_buckets_total"]) != 2_125_768:
        raise ValueError(f"{path}: unexpected 8cf geometry")
    coverage = report["coverage"]
    return {
        "records": int(report["corpus"]["total_records"]),
        "visited_buckets": int(coverage["visited_buckets"]),
        "ge_10": int(coverage["buckets_with_at_least"]["ge_10"]),
        "ge_100": int(coverage["buckets_with_at_least"]["ge_100"]),
        "gini": float(report["concentration"]["gini"]),
    }


def independent_delta(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    p1, p0 = float(candidate["rate"]), float(baseline["rate"])
    n1, n0 = int(candidate["n"]), int(baseline["n"])
    delta = p1 - p0
    se = math.sqrt(p1 * (1.0 - p1) / n1 + p0 * (1.0 - p0) / n0)
    return {
        "delta": delta,
        "ci_low": delta - 1.96 * se,
        "ci_high": delta + 1.96 * se,
        "independent_pools": True,
    }


def build_evaluation(
    *,
    force_dir: Path,
    conversion_dir: Path,
    coverage_dir: Path,
    training_summary_path: Path,
    preflight_path: Path,
    turnover_training_path: Path,
    turnover_evaluation_path: Path,
    turnover_confirmation_path: Path,
    m2_training_path: Path,
    m2_evaluation_path: Path,
    opening_manifest_path: Path,
    expected_opening_seed: int,
    expected_opening_sha256: str,
    bootstrap_samples: int = 200_000,
    seed: int = 983_001,
) -> dict[str, Any]:
    training = load(training_summary_path)
    preflight = load(preflight_path)
    turnover_training = load(turnover_training_path)
    turnover_evaluation = load(turnover_evaluation_path)
    turnover_confirmation = load(turnover_confirmation_path)
    m2_training = load(m2_training_path)
    m2_evaluation = load(m2_evaluation_path)
    openings = load(opening_manifest_path)

    if (
        training.get("verdict") != "REPLAY25_TRAINING_SCREEN_READY"
        or training.get("experiment_variant") != "REPLAY25_RECENCY75"
        or training.get("parent") != "F2M"
        or training.get("parent_model_sha256") != F2M_MODEL_SHA
        or training.get("training_records") != 2_000_000
        or training.get("historical_replay_records") != 500_000
        or training.get("fresh_records") != 1_500_000
        or training.get("temporal_distribution_records")
        != {"fresh_m2": 1_500_000, "parent_f2m": 500_000}
        or training.get("new_generation_performed") is not False
        or training.get("external_teacher_inputs") != 0
        or training.get("evaluation_authorized") is not True
        or training.get("promotion_authorized") is not False
        or training.get("automatic_next_job") is not None
    ):
        raise ValueError("REPLAY25 training contract mismatch")
    if (
        preflight.get("verdict") != "REPLAY25_PREFLIGHT_READY"
        or preflight.get("experiment_variant") != "REPLAY25_RECENCY75"
        or preflight.get("records") != 2_000_000
        or preflight.get("historical_replay_records") != 500_000
        or preflight.get("fresh_records") != 1_500_000
        or preflight.get("jnnw_sha256") != training.get("training_corpus_sha256")
        or preflight.get("jsm_sha256") != training.get("training_meta_sha256")
        or preflight.get("training_authorized") is not True
        or preflight.get("promotion_authorized") is not False
        or preflight.get("automatic_next_job") is not None
    ):
        raise ValueError("REPLAY25 preflight contract mismatch")
    if (
        turnover_training.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or turnover_training.get("experiment_variant") != "TURNOVER_1_1"
        or turnover_training.get("model_sha256") != TURNOVER_MODEL_SHA
        or turnover_training.get("historical_replay_records") != 1_000_000
        or turnover_training.get("fresh_records") != 1_000_000
        or turnover_training.get("new_generation_performed") is not False
        or turnover_evaluation.get("verdict")
        != "TURNOVER_DIRECTIONAL_CONFIRMATION_REVIEW"
        or turnover_evaluation.get("training_summary", {}).get("model_sha256")
        != TURNOVER_MODEL_SHA
        or turnover_confirmation.get("verdict")
        != "TURNOVER_EFFECT_CONFIRMED_HUMAN_REVIEW"
        or turnover_confirmation.get("all_guardrails_pass") is not True
        or turnover_confirmation.get("previous_evaluation_certificate", {}).get(
            "model_sha256"
        )
        != TURNOVER_MODEL_SHA
        or turnover_confirmation.get("promotion_authorized") is not False
        or turnover_confirmation.get("automatic_next_job") is not None
    ):
        raise ValueError("TURNOVER control contract mismatch")
    if (
        m2_training.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or m2_training.get("model_sha256") != M2_MODEL_SHA
        or m2_training.get("fresh_only") is not True
        or m2_training.get("training_records") != 2_000_000
        or m2_evaluation.get("verdict") != "M2_PLATEAU_OR_REGRESSION_REVIEW"
        or m2_evaluation.get("all_guardrails_pass") is not True
        or m2_evaluation.get("training_summary", {}).get("model_sha256")
        != M2_MODEL_SHA
    ):
        raise ValueError("M2 control contract mismatch")

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
        or not any(
            str(path).endswith("prior-turnover-confirmation.fen")
            for path in excluded
        )
    ):
        raise ValueError("REPLAY25 independent opening-pool contract mismatch")

    controls = ("M2", "TURNOVER", "F2M")
    force = {
        f"{view}_vs_{opponent}": force_row(
            force_dir / f"force-{view}-REPLAY25-vs-{opponent}.json"
        )
        for view in ("q00", "native")
        for opponent in (*controls, "GEN2")
    }
    primary = {
        opponent: {
            view: {
                "positive_point_estimate": force[f"{view}_vs_{opponent}"]["rate"] > 0.5,
                "superiority_established": force[f"{view}_vs_{opponent}"]["ci_low"]
                > 0.5,
                "regression_not_established": force[f"{view}_vs_{opponent}"]["ci_high"]
                >= 0.5,
            }
            for view in ("q00", "native")
        }
        for opponent in controls
    }

    conversion: dict[str, Any] = {}
    for stratum_index, stratum in enumerate(("p3_mince", "p4_egal")):
        reports = {
            model: load(conversion_dir / f"{model}-{stratum}.json")
            for model in ("REPLAY25", *controls)
        }
        conversion[stratum] = {
            model: {
                key: reports[model][key]
                for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
            }
            for model in reports
        }
        for control_index, control in enumerate(controls):
            conversion[stratum][f"paired_delta_replay25_minus_{control.lower()}"] = (
                paired_conversion(
                    reports["REPLAY25"],
                    reports[control],
                    seed=seed + 10 * stratum_index + control_index,
                    bootstrap_samples=bootstrap_samples,
                )
            )

    coverage = {
        model: compact_coverage(coverage_dir / f"{model}-coverage.json")
        for model in ("REPLAY25", *controls)
    }
    coverage_delta = {
        control: {
            "visited_buckets": (
                coverage["REPLAY25"]["visited_buckets"]
                - coverage[control]["visited_buckets"]
            ),
            "ge_100": coverage["REPLAY25"]["ge_100"] - coverage[control]["ge_100"],
        }
        for control in controls
    }
    gen2_delta = {
        view: independent_delta(
            force[f"{view}_vs_GEN2"],
            m2_evaluation["force"][f"{view}_vs_GEN2"],
        )
        for view in ("q00", "native")
    }

    guardrails: dict[str, bool] = {}
    for control in controls:
        for view in ("q00", "native"):
            guardrails[f"{control.lower()}_{view}_regression_not_established"] = (
                primary[control][view]["regression_not_established"]
            )
    for view in ("q00", "native"):
        guardrails[f"gen2_{view}_gross_regression_not_observed"] = (
            force[f"{view}_vs_GEN2"]["ci_high"] >= 0.5
            and gen2_delta[view]["delta"] >= -0.03
        )
    for stratum in ("p3_mince", "p4_egal"):
        guardrails[f"{stratum}_absolute_conversion_floor"] = (
            float(conversion[stratum]["REPLAY25"]["conversion"]) >= 0.95
        )
        for control in controls:
            guardrails[
                f"{stratum}_regression_over_3pp_vs_{control.lower()}_not_established"
            ] = (
                conversion[stratum][
                    f"paired_delta_replay25_minus_{control.lower()}"
                ]["ci_high"]
                >= -0.03
            )
    for control in controls:
        guardrails[f"visited_coverage_no_5pct_collapse_vs_{control.lower()}"] = (
            coverage["REPLAY25"]["visited_buckets"]
            >= 0.95 * coverage[control]["visited_buckets"]
        )
        guardrails[f"ge100_coverage_no_5pct_collapse_vs_{control.lower()}"] = (
            coverage["REPLAY25"]["ge_100"] >= 0.95 * coverage[control]["ge_100"]
        )

    all_guardrails = all(guardrails.values())
    champion_superior = all(
        primary[control][view]["superiority_established"]
        for control in controls
        for view in ("q00", "native")
    )
    dose_better = all(
        primary[control][view]["superiority_established"]
        for control in ("M2", "TURNOVER")
        for view in ("q00", "native")
    ) and all(
        primary["F2M"][view]["regression_not_established"]
        for view in ("q00", "native")
    )
    directional = all(
        primary[control][view]["positive_point_estimate"]
        for control in ("M2", "TURNOVER")
        for view in ("q00", "native")
    ) and all(
        primary[control][view]["regression_not_established"]
        for control in controls
        for view in ("q00", "native")
    )
    if champion_superior and all_guardrails:
        verdict = CHAMPION_REVIEW
        recommendation = "human_review_replay25_champion"
    elif dose_better and all_guardrails:
        verdict = CAUSAL_BETTER
        recommendation = "human_review_replay25_causal_dose_before_promotion"
    elif directional and all_guardrails:
        verdict = DIRECTIONAL
        recommendation = "independent_replay25_confirmation"
    else:
        verdict = CLOSED
        recommendation = "close_replay25_and_preregister_one_new_factor"

    return {
        "schema": 1,
        "verdict": verdict,
        "protocol": {
            "candidate": "REPLAY25_RECENCY75",
            "causal_controls": ["M2_D8_FRESH2M", "TURNOVER_1_1"],
            "champion": "F2M",
            "historical_guardrail": "GEN2_MMTO",
            "games_per_force_cell": 1_000,
            "openings": 500,
            "paired_colors": True,
            "force_views": ["q00_depth9", "native_movetime_0.1"],
            "conversion_positions_per_stratum": 300,
            "changed_factor": "historical_replay_dose",
            "fixed_training_volume": 2_000_000,
            "parent_replay_records": 500_000,
            "fresh_m2_records": 1_500_000,
        },
        "force": force,
        "replay25_minus_m2_gen2_independent_delta": gen2_delta,
        "conversion": conversion,
        "coverage": coverage,
        "coverage_delta_replay25_minus_controls": coverage_delta,
        "primary_checks": primary,
        "guardrails": guardrails,
        "all_guardrails_pass": all_guardrails,
        "recommendation": recommendation,
        "training_summary": training,
        "preflight_certificate": preflight,
        "turnover_training_summary": turnover_training,
        "turnover_evaluation_certificate": turnover_evaluation,
        "turnover_confirmation_certificate": turnover_confirmation,
        "m2_training_summary": m2_training,
        "m2_evaluation_certificate": m2_evaluation,
        "opening_manifest": openings,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--conversion-dir", required=True, type=Path)
    parser.add_argument("--coverage-dir", required=True, type=Path)
    parser.add_argument("--training-summary", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--turnover-training", required=True, type=Path)
    parser.add_argument("--turnover-evaluation", required=True, type=Path)
    parser.add_argument("--turnover-confirmation", required=True, type=Path)
    parser.add_argument("--m2-training", required=True, type=Path)
    parser.add_argument("--m2-evaluation", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--expected-opening-seed", required=True, type=int)
    parser.add_argument("--expected-opening-sha256", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=983_001)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()
    payload = build_evaluation(
        force_dir=args.force_dir,
        conversion_dir=args.conversion_dir,
        coverage_dir=args.coverage_dir,
        training_summary_path=args.training_summary,
        preflight_path=args.preflight,
        turnover_training_path=args.turnover_training,
        turnover_evaluation_path=args.turnover_evaluation,
        turnover_confirmation_path=args.turnover_confirmation,
        m2_training_path=args.m2_training,
        m2_evaluation_path=args.m2_evaluation,
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
