#!/usr/bin/env python3
"""Aggregate the preregistered L3-PURE D10-vs-D8 causal evaluation."""
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


PROMOTION_SCALE = "D10_PROMOTION_AND_SCALE_REVIEW_READY"
DEPTH_CONFIRMED = "D10_DEPTH_EFFECT_CONFIRMED_REVIEW"
DIRECTIONAL = "D10_DIRECTIONAL_CONFIRMATION_REVIEW"
PLATEAU = "D10_PLATEAU_OR_REGRESSION_REVIEW"
D10_OPENINGS_SHA256 = (
    "e41ae3875368112a99d3de2a1e6e40aa8d4d94d5cb66ed5280999a7a4e612965"
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
    d8_training_summary_path: Path,
    m2_evaluation_path: Path,
    opening_manifest_path: Path,
    bootstrap_samples: int = 200_000,
    seed: int = 971_001,
) -> dict[str, Any]:
    training = load(training_summary_path)
    d8_training = load(d8_training_summary_path)
    m2_evaluation = load(m2_evaluation_path)
    openings = load(opening_manifest_path)
    if (
        training.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or training.get("parent") != "F2M"
        or training.get("fresh_only") is not True
        or training.get("experiment_variant") != "D10_CAUSAL_FRESH2M"
        or training.get("play_depth") != 10
    ):
        raise ValueError("D10 training contract mismatch")
    if (
        d8_training.get("verdict") != "M2_TRAINING_SCREEN_READY"
        or d8_training.get("model_sha256")
        != "75ace3c0ad2ffa2b71a9b9073c3c1d1545164e3a5a048e411e91adba23ec3b45"
    ):
        raise ValueError("D8 M2 control contract mismatch")
    if (
        m2_evaluation.get("verdict") != "M2_PLATEAU_OR_REGRESSION_REVIEW"
        or not m2_evaluation.get("all_guardrails_pass")
    ):
        raise ValueError("M2 plateau certificate mismatch")
    excluded = openings.get("excluded_sources", {})
    if (
        openings.get("records") != 500
        or openings.get("unique_records") != 500
        or openings.get("overlap_records") != 0
        or openings.get("generator_seed") != 314159
        or openings.get("sha256") != D10_OPENINGS_SHA256
        or not any(str(path).endswith("prior-m2-independent.fen") for path in excluded)
    ):
        raise ValueError("D10 independent opening-pool contract mismatch")

    force: dict[str, dict[str, Any]] = {}
    for view in ("q00", "native"):
        for opponent in ("M2", "F2M", "GEN2"):
            force[f"{view}_vs_{opponent}"] = force_row(
                force_dir / f"force-{view}-D10-vs-{opponent}.json"
            )

    conversion: dict[str, Any] = {}
    for index, stratum in enumerate(("p3_mince", "p4_egal")):
        reports = {
            model: load(conversion_dir / f"{model}-{stratum}.json")
            for model in ("D10", "M2", "F2M")
        }
        comparison = paired_conversion(
            reports["D10"],
            reports["M2"],
            seed=seed + index,
            bootstrap_samples=bootstrap_samples,
        )
        conversion[stratum] = {
            model: {
                key: reports[model][key]
                for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
            }
            for model in reports
        }
        conversion[stratum]["paired_delta_d10_minus_m2"] = comparison

    coverage = {
        model: compact_coverage(coverage_dir / f"{model}-coverage.json")
        for model in ("D10", "M2", "F2M")
    }
    primary = {
        view: {
            "positive_point_estimate": force[f"{view}_vs_M2"]["rate"] > 0.5,
            "superiority_established": force[f"{view}_vs_M2"]["ci_low"] > 0.5,
            "regression_not_established": force[f"{view}_vs_M2"]["ci_high"] >= 0.5,
        }
        for view in ("q00", "native")
    }
    versus_f2m = {
        view: {
            "positive_point_estimate": force[f"{view}_vs_F2M"]["rate"] > 0.5,
            "superiority_established": force[f"{view}_vs_F2M"]["ci_low"] > 0.5,
            "regression_not_established": force[f"{view}_vs_F2M"]["ci_high"] >= 0.5,
        }
        for view in ("q00", "native")
    }
    m2_force = m2_evaluation["force"]
    gen2_delta = {
        view: independent_delta(
            force[f"{view}_vs_GEN2"], m2_force[f"{view}_vs_GEN2"]
        )
        for view in ("q00", "native")
    }
    guardrails = {
        "f2m_q00_regression_not_established": versus_f2m["q00"][
            "regression_not_established"
        ],
        "f2m_native_regression_not_established": versus_f2m["native"][
            "regression_not_established"
        ],
        "gen2_q00_gross_regression_not_observed": (
            force["q00_vs_GEN2"]["ci_high"] >= 0.5
            and gen2_delta["q00"]["delta"] >= -0.03
        ),
        "gen2_native_gross_regression_not_observed": (
            force["native_vs_GEN2"]["ci_high"] >= 0.5
            and gen2_delta["native"]["delta"] >= -0.03
        ),
        "p3_absolute_conversion_floor": (
            float(conversion["p3_mince"]["D10"]["conversion"]) >= 0.95
        ),
        "p4_absolute_conversion_floor": (
            float(conversion["p4_egal"]["D10"]["conversion"]) >= 0.95
        ),
        "p3_regression_over_3pp_not_established": (
            conversion["p3_mince"]["paired_delta_d10_minus_m2"]["ci_high"] >= -0.03
        ),
        "p4_regression_over_3pp_not_established": (
            conversion["p4_egal"]["paired_delta_d10_minus_m2"]["ci_high"] >= -0.03
        ),
        "visited_coverage_no_5pct_collapse_vs_m2": (
            coverage["D10"]["visited_buckets"]
            >= 0.95 * coverage["M2"]["visited_buckets"]
        ),
        "ge100_coverage_no_5pct_collapse_vs_m2": (
            coverage["D10"]["ge_100"] >= 0.95 * coverage["M2"]["ge_100"]
        ),
    }
    all_guardrails = all(guardrails.values())
    depth_superior = all(row["superiority_established"] for row in primary.values())
    depth_directional = all(
        row["positive_point_estimate"] and row["regression_not_established"]
        for row in primary.values()
    )
    f2m_superior = all(
        row["superiority_established"] for row in versus_f2m.values()
    )
    if depth_superior and f2m_superior and all_guardrails:
        verdict = PROMOTION_SCALE
        recommendation = "human_review_d10_promotion_and_scale"
    elif depth_superior and all_guardrails:
        verdict = DEPTH_CONFIRMED
        recommendation = "confirm_d10_against_f2m_then_scale"
    elif depth_directional and all_guardrails:
        verdict = DIRECTIONAL
        recommendation = "independent_d10_confirmation"
    else:
        verdict = PLATEAU
        recommendation = "stop_d10_and_prepare_d12_or_d10_d12_mix"

    return {
        "schema": 1,
        "verdict": verdict,
        "protocol": {
            "candidate": "D10",
            "causal_control": "M2_D8",
            "incumbent": "F2M",
            "historical_guardrail": "GEN2_MMTO",
            "games_per_force_view_and_opponent": 1_000,
            "openings": 500,
            "paired_colors": True,
            "force_views": ["q00_depth9", "native_movetime_0.1"],
            "changed_training_factor": "play_depth_8_to_10",
        },
        "force": force,
        "conversion": conversion,
        "coverage": coverage,
        "coverage_delta_d10_minus_m2": {
            "visited_buckets": (
                coverage["D10"]["visited_buckets"] - coverage["M2"]["visited_buckets"]
            ),
            "ge_100": coverage["D10"]["ge_100"] - coverage["M2"]["ge_100"],
        },
        "d10_minus_m2_gen2_independent_delta": gen2_delta,
        "primary_depth_checks": primary,
        "versus_f2m_checks": versus_f2m,
        "guardrails": guardrails,
        "all_guardrails_pass": all_guardrails,
        "recommendation": recommendation,
        "training_summary": training,
        "d8_training_summary": d8_training,
        "m2_plateau_certificate": m2_evaluation,
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
    parser.add_argument("--d8-training-summary", required=True, type=Path)
    parser.add_argument("--m2-evaluation", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=971_001)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()
    payload = build_evaluation(
        force_dir=args.force_dir,
        conversion_dir=args.conversion_dir,
        coverage_dir=args.coverage_dir,
        training_summary_path=args.training_summary,
        d8_training_summary_path=args.d8_training_summary,
        m2_evaluation_path=args.m2_evaluation,
        opening_manifest_path=args.opening_manifest,
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
