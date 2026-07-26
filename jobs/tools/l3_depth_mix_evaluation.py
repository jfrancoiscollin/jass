#!/usr/bin/env python3
"""Aggregate the preregistered L3-PURE d10/d12 5:1 distribution test."""
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


PROMOTION_SCALE = "DEPTH_MIX_PROMOTION_AND_SCALE_REVIEW_READY"
DISTRIBUTION_CONFIRMED = "DEPTH_MIX_DISTRIBUTION_EFFECT_CONFIRMED_REVIEW"
DIRECTIONAL = "DEPTH_MIX_DIRECTIONAL_CONFIRMATION_REVIEW"
PLATEAU = "DEPTH_MIX_PLATEAU_OR_REGRESSION_REVIEW"


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
    d10_training_summary_path: Path,
    d12_training_summary_path: Path,
    d12_evaluation_path: Path,
    opening_manifest_path: Path,
    expected_opening_seed: int,
    expected_opening_sha256: str,
    bootstrap_samples: int = 200_000,
    seed: int = 975_001,
) -> dict[str, Any]:
    training = load(training_summary_path)
    d10_training = load(d10_training_summary_path)
    d12_training = load(d12_training_summary_path)
    d12_evaluation = load(d12_evaluation_path)
    openings = load(opening_manifest_path)
    if (
        training.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or training.get("parent") != "F2M"
        or training.get("fresh_only") is not True
        or training.get("experiment_variant") != "D10_D12_MIX_5_1"
        or training.get("play_depth") is not None
        or training.get("training_records") != 2_000_000
        or training.get("depth_distribution_records")
        != {"d10": 1_666_667, "d12": 333_333}
        or training.get("new_generation_performed") is not False
    ):
        raise ValueError("depth-mix training contract mismatch")
    if (
        d10_training.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or d10_training.get("parent") != "F2M"
        or d10_training.get("experiment_variant") != "D10_CAUSAL_FRESH2M"
        or d10_training.get("play_depth") != 10
    ):
        raise ValueError("D10 control contract mismatch")
    if (
        d12_training.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or d12_training.get("parent") != "F2M"
        or d12_training.get("experiment_variant") != "D12_CAUSAL_FRESH2M"
        or d12_training.get("play_depth") != 12
    ):
        raise ValueError("D12 control contract mismatch")
    if (
        d12_evaluation.get("verdict") != "D12_PLATEAU_OR_REGRESSION_REVIEW"
        or d12_evaluation.get("recommendation")
        != "stop_single_depth_escalation_and_prepare_distribution_factor"
        or d12_evaluation.get("all_guardrails_pass") is not True
        or d12_evaluation.get("training_summary", {}).get("model_sha256")
        != d12_training.get("model_sha256")
        or d12_evaluation.get("d10_training_summary", {}).get("model_sha256")
        != d10_training.get("model_sha256")
    ):
        raise ValueError("D12 plateau certificate mismatch")
    excluded = openings.get("excluded_sources", {})
    if (
        openings.get("records") != 500
        or openings.get("unique_records") != 500
        or openings.get("overlap_records") != 0
        or openings.get("generator_seed") != expected_opening_seed
        or openings.get("sha256") != expected_opening_sha256
        or not any(str(path).endswith("prior-m2-independent.fen") for path in excluded)
        or not any(str(path).endswith("prior-d10-independent.fen") for path in excluded)
        or not any(str(path).endswith("prior-d12-independent.fen") for path in excluded)
    ):
        raise ValueError("depth-mix independent opening-pool contract mismatch")

    force: dict[str, dict[str, Any]] = {}
    for view in ("q00", "native"):
        for opponent in ("D10", "D12", "F2M", "GEN2"):
            force[f"{view}_vs_{opponent}"] = force_row(
                force_dir / f"force-{view}-MIX-vs-{opponent}.json"
            )

    conversion: dict[str, Any] = {}
    for stratum_index, stratum in enumerate(("p3_mince", "p4_egal")):
        reports = {
            model: load(conversion_dir / f"{model}-{stratum}.json")
            for model in ("MIX", "D10", "D12", "F2M")
        }
        conversion[stratum] = {
            model: {
                key: reports[model][key]
                for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
            }
            for model in reports
        }
        for control_index, control in enumerate(("D10", "D12")):
            conversion[stratum][f"paired_delta_mix_minus_{control.lower()}"] = (
                paired_conversion(
                    reports["MIX"],
                    reports[control],
                    seed=seed + 10 * stratum_index + control_index,
                    bootstrap_samples=bootstrap_samples,
                )
            )

    coverage = {
        model: compact_coverage(coverage_dir / f"{model}-coverage.json")
        for model in ("MIX", "D10", "D12", "F2M")
    }
    primary = {
        control: {
            view: {
                "positive_point_estimate": force[f"{view}_vs_{control}"]["rate"] > 0.5,
                "superiority_established": force[f"{view}_vs_{control}"]["ci_low"] > 0.5,
                "regression_not_established": force[f"{view}_vs_{control}"]["ci_high"]
                >= 0.5,
            }
            for view in ("q00", "native")
        }
        for control in ("D10", "D12")
    }
    versus_f2m = {
        view: {
            "positive_point_estimate": force[f"{view}_vs_F2M"]["rate"] > 0.5,
            "superiority_established": force[f"{view}_vs_F2M"]["ci_low"] > 0.5,
            "regression_not_established": force[f"{view}_vs_F2M"]["ci_high"] >= 0.5,
        }
        for view in ("q00", "native")
    }
    d10_force = d12_evaluation["d10_plateau_certificate"]["force"]
    control_gen2_force = {
        "D10": {
            view: d10_force[f"{view}_vs_GEN2"] for view in ("q00", "native")
        },
        "D12": {
            view: d12_evaluation["force"][f"{view}_vs_GEN2"]
            for view in ("q00", "native")
        },
    }
    gen2_delta = {
        control: {
            view: independent_delta(
                force[f"{view}_vs_GEN2"], control_gen2_force[control][view]
            )
            for view in ("q00", "native")
        }
        for control in ("D10", "D12")
    }

    guardrails: dict[str, bool] = {}
    for control in ("D10", "D12"):
        for view in ("q00", "native"):
            guardrails[f"{control.lower()}_{view}_regression_not_established"] = (
                primary[control][view]["regression_not_established"]
            )
            guardrails[
                f"gen2_{view}_gross_regression_not_observed_vs_{control.lower()}"
            ] = (
                force[f"{view}_vs_GEN2"]["ci_high"] >= 0.5
                and gen2_delta[control][view]["delta"] >= -0.03
            )
    for view in ("q00", "native"):
        guardrails[f"f2m_{view}_regression_not_established"] = (
            versus_f2m[view]["regression_not_established"]
        )
    for stratum in ("p3_mince", "p4_egal"):
        guardrails[f"{stratum}_absolute_conversion_floor"] = (
            float(conversion[stratum]["MIX"]["conversion"]) >= 0.95
        )
        for control in ("d10", "d12"):
            guardrails[f"{stratum}_regression_over_3pp_vs_{control}_not_established"] = (
                conversion[stratum][f"paired_delta_mix_minus_{control}"]["ci_high"]
                >= -0.03
            )
    for control in ("D10", "D12"):
        guardrails[f"visited_coverage_no_5pct_collapse_vs_{control.lower()}"] = (
            coverage["MIX"]["visited_buckets"]
            >= 0.95 * coverage[control]["visited_buckets"]
        )
        guardrails[f"ge100_coverage_no_5pct_collapse_vs_{control.lower()}"] = (
            coverage["MIX"]["ge_100"] >= 0.95 * coverage[control]["ge_100"]
        )

    all_guardrails = all(guardrails.values())
    distribution_superior = all(
        primary[control][view]["superiority_established"]
        for control in ("D10", "D12")
        for view in ("q00", "native")
    )
    distribution_directional = all(
        primary[control][view]["positive_point_estimate"]
        and primary[control][view]["regression_not_established"]
        for control in ("D10", "D12")
        for view in ("q00", "native")
    )
    f2m_superior = all(
        versus_f2m[view]["superiority_established"] for view in ("q00", "native")
    )
    if distribution_superior and f2m_superior and all_guardrails:
        verdict = PROMOTION_SCALE
        recommendation = "human_review_depth_mix_promotion_and_scale"
    elif distribution_superior and all_guardrails:
        verdict = DISTRIBUTION_CONFIRMED
        recommendation = "confirm_depth_mix_against_f2m_then_scale"
    elif distribution_directional and all_guardrails:
        verdict = DIRECTIONAL
        recommendation = "independent_depth_mix_confirmation"
    else:
        verdict = PLATEAU
        recommendation = "stop_depth_distribution_and_prepare_replay_or_volume_factor"

    return {
        "schema": 1,
        "verdict": verdict,
        "protocol": {
            "candidate": "MIX",
            "causal_controls": ["D10", "D12"],
            "incumbent": "F2M",
            "historical_guardrail": "GEN2_MMTO",
            "games_per_force_view_and_opponent": 1_000,
            "openings": 500,
            "paired_colors": True,
            "force_views": ["q00_depth9", "native_movetime_0.1"],
            "changed_training_factor": "depth_distribution_5_to_1_at_constant_2m",
        },
        "force": force,
        "conversion": conversion,
        "coverage": coverage,
        "coverage_delta_mix_minus_controls": {
            control: {
                "visited_buckets": (
                    coverage["MIX"]["visited_buckets"]
                    - coverage[control]["visited_buckets"]
                ),
                "ge_100": coverage["MIX"]["ge_100"] - coverage[control]["ge_100"],
            }
            for control in ("D10", "D12")
        },
        "mix_minus_controls_gen2_independent_delta": gen2_delta,
        "primary_distribution_checks": primary,
        "versus_f2m_checks": versus_f2m,
        "guardrails": guardrails,
        "all_guardrails_pass": all_guardrails,
        "recommendation": recommendation,
        "training_summary": training,
        "d10_training_summary": d10_training,
        "d12_training_summary": d12_training,
        "d12_plateau_certificate": d12_evaluation,
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
    parser.add_argument("--d10-training-summary", required=True, type=Path)
    parser.add_argument("--d12-training-summary", required=True, type=Path)
    parser.add_argument("--d12-evaluation", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--expected-opening-seed", required=True, type=int)
    parser.add_argument("--expected-opening-sha256", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=975_001)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()
    payload = build_evaluation(
        force_dir=args.force_dir,
        conversion_dir=args.conversion_dir,
        coverage_dir=args.coverage_dir,
        training_summary_path=args.training_summary,
        d10_training_summary_path=args.d10_training_summary,
        d12_training_summary_path=args.d12_training_summary,
        d12_evaluation_path=args.d12_evaluation,
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
