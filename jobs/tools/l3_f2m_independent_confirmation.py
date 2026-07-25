#!/usr/bin/env python3
"""Aggregate the preregistered independent confirmation of M1 F2M."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXPECTED_REVIEW = "M1_REPAIRED_FORCE_COVERAGE_REVIEW_READY"
EXPECTED_MATRIX = "M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW"
CONFIRMED = "F2M_CONFIRMED_FOR_HUMAN_PROMOTION_REVIEW"
NOT_CONFIRMED = "F2M_NOT_CONFIRMED_RETAIN_C0"
VIEWS = ("q00_vs_C0", "native_vs_C0", "q00_vs_R2M", "native_vs_R2M")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


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
    if int(row["n"]) != 1_000:
        raise ValueError(f"{path}: confirmation gate must contain 1000 games")
    return row


def build_confirmation(
    *,
    review_path: Path,
    matrix_path: Path,
    force_dir: Path,
    opening_manifest_path: Path,
) -> dict[str, Any]:
    review = load(review_path)
    matrix = load(matrix_path)
    openings = load(opening_manifest_path)
    if review.get("verdict") != EXPECTED_REVIEW:
        raise ValueError("unexpected repaired force/coverage review")
    if review.get("selected_m1_arm_for_confirmation") != "F2M":
        raise ValueError("F2M was not selected by the preregistered review")
    if review.get("eligible_arms", [None])[0] != "F2M":
        raise ValueError("F2M was not the top eligible arm")
    if matrix.get("verdict") != EXPECTED_MATRIX:
        raise ValueError("unexpected repaired conversion matrix")
    if "F2M" not in matrix.get("m1_arms_passing_floor", []):
        raise ValueError("F2M did not pass the repaired conversion floor")
    if (
        openings.get("records") != 500
        or openings.get("unique_records") != 500
        or openings.get("overlap_records") != 0
    ):
        raise ValueError("independent opening-pool contract mismatch")

    force = {
        "q00_vs_C0": force_row(force_dir / "force-q00-F2M-vs-C0.json"),
        "native_vs_C0": force_row(force_dir / "force-native-F2M-vs-C0.json"),
        "q00_vs_R2M": force_row(force_dir / "force-q00-F2M-vs-R2M.json"),
        "native_vs_R2M": force_row(
            force_dir / "force-native-F2M-vs-R2M.json"
        ),
    }
    checks = {
        "independent_q00_superiority_vs_c0": (
            force["q00_vs_C0"]["ci_low"] > 0.5
        ),
        "independent_native_superiority_vs_c0": (
            force["native_vs_C0"]["ci_low"] > 0.5
        ),
        "q00_regression_vs_r2m_not_established": (
            force["q00_vs_R2M"]["ci_high"] >= 0.5
        ),
        "native_regression_vs_r2m_not_established": (
            force["native_vs_R2M"]["ci_high"] >= 0.5
        ),
        "repaired_conversion_floor_passed": True,
        "independent_pool_verified": True,
    }
    passed = all(checks.values())
    verdict = CONFIRMED if passed else NOT_CONFIRMED
    return {
        "schema": 1,
        "verdict": verdict,
        "protocol": {
            "candidate": "F2M",
            "immutable_parent": "C0_A_G3",
            "challenger_control": "R2M",
            "games_per_view": 1_000,
            "openings": 500,
            "paired_colors": True,
            "views": list(VIEWS),
            "primary_rule": (
                "95% lower bound above 50% against C0 in Q00 and native"
            ),
            "guardrail_rule": (
                "no established F2M regression against R2M in either view"
            ),
        },
        "force": force,
        "checks": checks,
        "confirmed": passed,
        "selected_generalist_candidate": "F2M" if passed else None,
        "generalist_parent_remains": "C0_A_G3",
        "opening_manifest": openings,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_confirmation(
        review_path=args.review,
        matrix_path=args.matrix,
        force_dir=args.force_dir,
        opening_manifest_path=args.opening_manifest,
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
