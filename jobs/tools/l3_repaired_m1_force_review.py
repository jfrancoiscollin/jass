#!/usr/bin/env python3
"""Select an M1 continuation candidate after repaired-engine force gates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ARMS = ("F500", "F2M", "R2M")
FORCE_KEYS = ("q00_vs_C0", "native_vs_C0", "q00_vs_GEN2")
EXPECTED_MATRIX_VERDICT = "M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW"
VERDICT = "M1_REPAIRED_FORCE_COVERAGE_REVIEW_READY"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def compact_coverage(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("stage") != "l3_bucket_visits":
        raise ValueError("unexpected coverage report")
    geometry = report.get("geometry", {})
    if int(geometry.get("trained_buckets_total", 0)) != 2_125_768:
        raise ValueError("coverage geometry is not 8cf color-fold")
    coverage = report["coverage"]
    concentration = report["concentration"]
    return {
        "records": int(report["corpus"]["total_records"]),
        "visited_buckets": int(coverage["visited_buckets"]),
        "coverage_fraction": float(coverage["coverage_fraction"]),
        "ge_10": int(coverage["buckets_with_at_least"]["ge_10"]),
        "ge_100": int(coverage["buckets_with_at_least"]["ge_100"]),
        "frac_ge_100": float(coverage["frac_buckets_ge_100"]),
        "gini": float(concentration["gini"]),
    }


def force_row(path: Path) -> dict[str, Any]:
    value = load(path)
    fields = (
        "n",
        "wins_a",
        "draws",
        "wins_b",
        "rate",
        "elo",
        "ci_low",
        "ci_high",
    )
    row = {field: value[field] for field in fields}
    if int(row["n"]) != 400:
        raise ValueError(f"{path}: force gate must contain 400 games")
    return row


def build_review(
    *,
    matrix_path: Path,
    force_dir: Path,
    coverage_dir: Path,
    training_summary_path: Path,
) -> dict[str, Any]:
    matrix = load(matrix_path)
    if matrix.get("verdict") != EXPECTED_MATRIX_VERDICT:
        raise ValueError("unexpected repaired conversion matrix")
    passing = set(matrix.get("m1_arms_passing_floor", []))
    training = load(training_summary_path)
    if training.get("verdict") != "M1_TRAINING_SCREEN_READY":
        raise ValueError("unexpected M1 training summary")

    force: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        force[arm] = {
            "q00_vs_C0": force_row(force_dir / f"force-q00-{arm}-vs-C0.json"),
            "native_vs_C0": force_row(
                force_dir / f"force-native-{arm}-vs-C0.json"
            ),
            "q00_vs_GEN2": force_row(
                force_dir / f"force-q00-{arm}-vs-GEN2.json"
            ),
        }

    coverage = {
        name: compact_coverage(load(coverage_dir / f"{name}-coverage.json"))
        for name in ("C0",) + ARMS
    }
    parent = coverage["C0"]
    eligibility: dict[str, dict[str, Any]] = {}
    eligible: list[str] = []
    for arm in ARMS:
        arm_coverage = coverage[arm]
        checks = {
            "conversion_floor_passed": arm in passing,
            "q00_slope_positive_vs_c0": force[arm]["q00_vs_C0"]["rate"] > 0.5,
            "native_slope_positive_vs_c0": (
                force[arm]["native_vs_C0"]["rate"] > 0.5
            ),
            "gen2_regression_not_established": (
                force[arm]["q00_vs_GEN2"]["ci_high"] >= 0.5
            ),
            "visited_coverage_above_parent": (
                arm_coverage["visited_buckets"] > parent["visited_buckets"]
            ),
            "ge100_coverage_above_parent": (
                arm_coverage["ge_100"] > parent["ge_100"]
            ),
        }
        qualifies = all(checks.values())
        eligibility[arm] = {
            **checks,
            "eligible_for_confirmation": qualifies,
            "coverage_delta_vs_parent": {
                "visited_buckets": (
                    arm_coverage["visited_buckets"] - parent["visited_buckets"]
                ),
                "ge_100": arm_coverage["ge_100"] - parent["ge_100"],
            },
        }
        if qualifies:
            eligible.append(arm)

    ranked = sorted(
        eligible,
        key=lambda arm: (
            -min(
                force[arm]["q00_vs_C0"]["rate"],
                force[arm]["native_vs_C0"]["rate"],
            ),
            -force[arm]["q00_vs_GEN2"]["rate"],
            -eligibility[arm]["coverage_delta_vs_parent"]["ge_100"],
            arm,
        ),
    )
    selected = ranked[0] if ranked else None
    next_branch = (
        "independent_powered_confirmation_of_selected_m1_arm"
        if selected
        else "retain_c0_and_stop_mechanical_m1_continuation"
    )
    return {
        "schema": 1,
        "verdict": VERDICT,
        "protocol": {
            "models": list(ARMS),
            "force_games_per_view": 400,
            "force_views": list(FORCE_KEYS),
            "conversion_source": "home-0962",
            "coverage_space": "8cf color-fold",
            "selection_rule": (
                "conversion floor + positive Q00/native slopes vs C0 + "
                "no established Gen2 regression + visited/ge100 coverage "
                "above immutable C0 parent"
            ),
            "ranking_rule": (
                "maximise the weaker C0 force view, then Gen2 rate, then "
                "ge100 coverage delta"
            ),
        },
        "force": force,
        "coverage": coverage,
        "eligibility": eligibility,
        "eligible_arms": ranked,
        "selected_m1_arm_for_confirmation": selected,
        "next_branch": next_branch,
        "training_summary": training,
        "confirmation_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--coverage-dir", required=True, type=Path)
    parser.add_argument("--training-summary", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_review(
        matrix_path=args.matrix,
        force_dir=args.force_dir,
        coverage_dir=args.coverage_dir,
        training_summary_path=args.training_summary,
    )
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialized, encoding="utf-8")
    if args.summary_out is not None:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(serialized, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
