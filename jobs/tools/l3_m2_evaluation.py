#!/usr/bin/env python3
"""Aggregate the preregistered L3-PURE M2 evaluation screen."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

try:
    from l3_corrected_conversion_matrix import paired_conversion
except ModuleNotFoundError:  # imported as jobs.tools.* by the unit suite
    from jobs.tools.l3_corrected_conversion_matrix import paired_conversion


PROMOTION = "M2_PROMOTION_REVIEW_READY"
DIRECTIONAL = "M2_DIRECTIONAL_CONFIRMATION_REVIEW"
PLATEAU = "M2_PLATEAU_OR_REGRESSION_REVIEW"


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
    champion_benchmark_path: Path,
    opening_manifest_path: Path,
    bootstrap_samples: int = 200_000,
    seed: int = 967_001,
) -> dict[str, Any]:
    training = load(training_summary_path)
    champion = load(champion_benchmark_path)
    openings = load(opening_manifest_path)
    if training.get("verdict") != "M2_TRAINING_SCREEN_READY":
        raise ValueError("unexpected M2 training verdict")
    if training.get("parent") != "F2M" or training.get("fresh_only") is not True:
        raise ValueError("M2 training contract mismatch")
    if champion.get("verdict") != "F2M_NEW_GENERAL_CHAMPION_HUMAN_REVIEW":
        raise ValueError("F2M champion certificate mismatch")
    if champion.get("recommended_general_champion") != "F2M":
        raise ValueError("F2M is not the champion baseline")
    if (
        openings.get("records") != 500
        or openings.get("unique_records") != 500
        or openings.get("overlap_records") != 0
    ):
        raise ValueError("independent opening-pool contract mismatch")

    force = {
        "q00_vs_F2M": force_row(force_dir / "force-q00-M2-vs-F2M.json"),
        "native_vs_F2M": force_row(force_dir / "force-native-M2-vs-F2M.json"),
        "q00_vs_GEN2": force_row(force_dir / "force-q00-M2-vs-GEN2.json"),
        "native_vs_GEN2": force_row(force_dir / "force-native-M2-vs-GEN2.json"),
    }
    champion_force = champion["force"]
    gen2_delta = {
        "q00": independent_delta(force["q00_vs_GEN2"], champion_force["q00"]),
        "native": independent_delta(
            force["native_vs_GEN2"], champion_force["native"]
        ),
    }

    conversion: dict[str, Any] = {}
    for index, stratum in enumerate(("p3_mince", "p4_egal")):
        m2 = load(conversion_dir / f"M2-{stratum}.json")
        f2m = load(conversion_dir / f"F2M-{stratum}.json")
        comparison = paired_conversion(
            m2,
            f2m,
            seed=seed + index,
            bootstrap_samples=bootstrap_samples,
        )
        conversion[stratum] = {
            "M2": {
                key: m2[key]
                for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
            },
            "F2M": {
                key: f2m[key]
                for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
            },
            "paired_delta_m2_minus_f2m": comparison,
        }

    coverage = {
        name: compact_coverage(coverage_dir / f"{name}-coverage.json")
        for name in ("F2M", "M2")
    }
    f2m_cov, m2_cov = coverage["F2M"], coverage["M2"]
    coverage_delta = {
        "visited_buckets": m2_cov["visited_buckets"] - f2m_cov["visited_buckets"],
        "ge_100": m2_cov["ge_100"] - f2m_cov["ge_100"],
    }

    primary = {
        view: {
            "positive_point_estimate": force[f"{view}_vs_F2M"]["rate"] > 0.5,
            "superiority_established": force[f"{view}_vs_F2M"]["ci_low"] > 0.5,
            "regression_not_established": force[f"{view}_vs_F2M"]["ci_high"] >= 0.5,
        }
        for view in ("q00", "native")
    }
    guardrails = {
        "gen2_q00_gross_regression_not_observed": (
            force["q00_vs_GEN2"]["ci_high"] >= 0.5
            and gen2_delta["q00"]["delta"] >= -0.03
        ),
        "gen2_native_gross_regression_not_observed": (
            force["native_vs_GEN2"]["ci_high"] >= 0.5
            and gen2_delta["native"]["delta"] >= -0.03
        ),
        "p3_absolute_conversion_floor": (
            float(conversion["p3_mince"]["M2"]["conversion"]) >= 0.95
        ),
        "p4_absolute_conversion_floor": (
            float(conversion["p4_egal"]["M2"]["conversion"]) >= 0.95
        ),
        "p3_regression_over_3pp_not_established": (
            conversion["p3_mince"]["paired_delta_m2_minus_f2m"]["ci_high"]
            >= -0.03
        ),
        "p4_regression_over_3pp_not_established": (
            conversion["p4_egal"]["paired_delta_m2_minus_f2m"]["ci_high"]
            >= -0.03
        ),
        "visited_coverage_no_5pct_collapse": (
            m2_cov["visited_buckets"] >= 0.95 * f2m_cov["visited_buckets"]
        ),
        "ge100_coverage_no_5pct_collapse": (
            m2_cov["ge_100"] >= 0.95 * f2m_cov["ge_100"]
        ),
    }
    all_guardrails = all(guardrails.values())
    both_superior = all(row["superiority_established"] for row in primary.values())
    both_directional = all(
        row["positive_point_estimate"] and row["regression_not_established"]
        for row in primary.values()
    )
    if both_superior and all_guardrails:
        verdict = PROMOTION
        recommendation = "human_review_m2_promotion"
    elif both_directional and all_guardrails:
        verdict = DIRECTIONAL
        recommendation = "independent_m2_confirmation"
    else:
        verdict = PLATEAU
        recommendation = "stop_same_recipe_and_prepare_d10_causal_arm"

    return {
        "schema": 1,
        "verdict": verdict,
        "protocol": {
            "candidate": "M2",
            "incumbent": "F2M",
            "historical_guardrail": "GEN2_MMTO",
            "games_per_force_view": 1_000,
            "openings": 500,
            "paired_colors": True,
            "force_views": ["q00_depth9", "native_movetime_0.1"],
            "conversion_positions_per_stratum": 300,
            "promotion_rule": (
                "95% lower bound above 50% vs F2M in both force views "
                "and all guardrails pass"
            ),
            "directional_rule": (
                "positive point estimate in both force views, no established "
                "regression, and all guardrails pass"
            ),
        },
        "force": force,
        "f2m_champion_force_vs_gen2": champion_force,
        "m2_minus_f2m_gen2_independent_delta": gen2_delta,
        "conversion": conversion,
        "coverage": coverage,
        "coverage_delta_m2_minus_f2m": coverage_delta,
        "primary_checks": primary,
        "guardrails": guardrails,
        "all_guardrails_pass": all_guardrails,
        "recommendation": recommendation,
        "training_summary": training,
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
    parser.add_argument("--champion-benchmark", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=967_001)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()
    payload = build_evaluation(
        force_dir=args.force_dir,
        conversion_dir=args.conversion_dir,
        coverage_dir=args.coverage_dir,
        training_summary_path=args.training_summary,
        champion_benchmark_path=args.champion_benchmark,
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
