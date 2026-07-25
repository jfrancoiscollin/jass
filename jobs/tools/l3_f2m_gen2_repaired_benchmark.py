#!/usr/bin/env python3
"""Classify the symmetric repaired-engine F2M versus Gen2 benchmark."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EXPECTED_CONFIRMATION = "F2M_CONFIRMED_FOR_HUMAN_PROMOTION_REVIEW"
NEW_CHAMPION = "F2M_NEW_GENERAL_CHAMPION_HUMAN_REVIEW"
INCONCLUSIVE = "F2M_GEN2_REPAIRED_BENCH_INCONCLUSIVE"
GEN2_RETAINS = "GEN2_RETAINS_GENERAL_CHAMPION"


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
        raise ValueError(f"{path}: benchmark gate must contain 1000 games")
    return row


def build_benchmark(
    *,
    confirmation_path: Path,
    force_dir: Path,
    opening_manifest_path: Path,
    engine_code_sha: str,
) -> dict[str, Any]:
    confirmation = load(confirmation_path)
    openings = load(opening_manifest_path)
    if confirmation.get("verdict") != EXPECTED_CONFIRMATION:
        raise ValueError("unexpected F2M confirmation verdict")
    if confirmation.get("selected_generalist_candidate") != "F2M":
        raise ValueError("F2M is not the confirmed L3-PURE candidate")
    if (
        openings.get("records") != 500
        or openings.get("unique_records") != 500
        or openings.get("overlap_records") != 0
    ):
        raise ValueError("independent opening-pool contract mismatch")
    if len(engine_code_sha) != 40:
        raise ValueError("engine code SHA must be fully pinned")

    force = {
        "q00": force_row(force_dir / "force-q00-F2M-vs-GEN2.json"),
        "native": force_row(force_dir / "force-native-F2M-vs-GEN2.json"),
    }
    checks = {
        view: {
            "superiority_established": row["ci_low"] > 0.5,
            "regression_established": row["ci_high"] < 0.5,
        }
        for view, row in force.items()
    }
    both_superior = all(
        check["superiority_established"] for check in checks.values()
    )
    any_regression = any(
        check["regression_established"] for check in checks.values()
    )
    if both_superior:
        verdict = NEW_CHAMPION
        recommended = "F2M"
    elif any_regression:
        verdict = GEN2_RETAINS
        recommended = "GEN2_MMTO"
    else:
        verdict = INCONCLUSIVE
        recommended = "GEN2_MMTO"

    return {
        "schema": 1,
        "verdict": verdict,
        "protocol": {
            "candidate": "F2M",
            "incumbent": "GEN2_MMTO",
            "candidate_geometry": "8cf",
            "incumbent_geometry": "32cf",
            "engine_code_sha_both_sides": engine_code_sha,
            "same_repaired_engine_semantics": True,
            "games_per_view": 1_000,
            "openings": 500,
            "paired_colors": True,
            "views": ["q00_depth9", "native_movetime_0.1"],
            "champion_rule": (
                "95% lower bound above 50% in both Q00 and native"
            ),
            "incumbency_rule": (
                "Gen2 remains general champion if either view loses or "
                "the two-view superiority criterion is inconclusive"
            ),
        },
        "force": force,
        "checks": checks,
        "recommended_general_champion": recommended,
        "l3_pure_champion": "F2M",
        "m2_parent": "F2M",
        "opening_manifest": openings,
        "general_champion_promotion_authorized": False,
        "m2_launch_authorized": False,
        "automatic_next_job": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirmation", required=True, type=Path)
    parser.add_argument("--force-dir", required=True, type=Path)
    parser.add_argument("--opening-manifest", required=True, type=Path)
    parser.add_argument("--engine-code-sha", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_benchmark(
        confirmation_path=args.confirmation,
        force_dir=args.force_dir,
        opening_manifest_path=args.opening_manifest,
        engine_code_sha=args.engine_code_sha,
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
