#!/usr/bin/env python3
"""Compare the repaired-engine M1 matrix with the immutable 0955 baseline."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from l3_corrected_conversion_matrix import (
    SUMMARY_KEYS,
    load_document,
    paired_conversion,
)


EXPECTED_REPAIR_VERDICT = "LEGALITY_REPAIR_RECOVERS_CONVERSION"
EXPECTED_BASELINE_VERDICT = "M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW"
VERDICT = "M1_REPAIRED_ENGINE_MATRIX_READY_HUMAN_REVIEW"


def wilson_interval(wins: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("Wilson interval requires a positive sample size")
    rate = wins / total
    denominator = 1.0 + z * z / total
    centre = rate + z * z / (2.0 * total)
    radius = z * math.sqrt(
        rate * (1.0 - rate) / total + z * z / (4.0 * total * total)
    )
    return (centre - radius) / denominator, (centre + radius) / denominator


def conversion_summary(document: dict[str, Any]) -> dict[str, Any]:
    summary = {key: document[key] for key in SUMMARY_KEYS}
    low, high = wilson_interval(int(document["n_win"]), int(document["n_pos"]))
    summary["ci_low"] = low
    summary["ci_high"] = high
    summary["n_errors"] = int(document.get("n_errors", 0))
    return summary


def build_report(
    *,
    new_dir: Path,
    baseline_dir: Path,
    new_matrix_path: Path,
    repair_summary_path: Path,
    models: list[str],
    strata: list[str],
    m1_arms: list[str],
    bootstrap_samples: int,
    seed: int,
    conversion_floor: float = 0.80,
) -> dict[str, Any]:
    if len(models) != len(set(models)) or len(strata) != len(set(strata)):
        raise ValueError("models and strata must be unique")
    if not set(m1_arms).issubset(models):
        raise ValueError("every M1 arm must be present in models")

    repair = load_document(repair_summary_path)
    if repair.get("verdict") != EXPECTED_REPAIR_VERDICT:
        raise ValueError("unexpected legality-repair certificate")
    if repair.get("promotion_authorized") is not False:
        raise ValueError("repair certificate must remain non-promotable")

    baseline_matrix = load_document(baseline_dir / "baseline-matrix.json")
    if baseline_matrix.get("verdict") != EXPECTED_BASELINE_VERDICT:
        raise ValueError("unexpected baseline matrix verdict")
    new_matrix = load_document(new_matrix_path)
    if new_matrix.get("verdict") != EXPECTED_BASELINE_VERDICT:
        raise ValueError("unexpected repaired matrix input verdict")

    effects: dict[str, dict[str, Any]] = {}
    repaired_conversion: dict[str, dict[str, Any]] = {}
    for model_index, model in enumerate(models):
        effects[model] = {}
        repaired_conversion[model] = {}
        for stratum_index, stratum in enumerate(strata):
            before = load_document(
                baseline_dir / f"baseline-{model}-{stratum}.json"
            )
            after = load_document(new_dir / f"{model}-{stratum}.json")
            comparison = paired_conversion(
                after,
                before,
                seed=seed + model_index * 100 + stratum_index,
                bootstrap_samples=bootstrap_samples,
            )
            effects[model][stratum] = {
                "before": conversion_summary(before),
                "after": conversion_summary(after),
                "paired_repair_effect": comparison,
            }
            repaired_conversion[model][stratum] = conversion_summary(after)

    floor_audit: dict[str, Any] = {}
    passing_arms: list[str] = []
    for arm in m1_arms:
        by_stratum = {
            stratum: {
                "ci_low": repaired_conversion[arm][stratum]["ci_low"],
                "passes": (
                    repaired_conversion[arm][stratum]["ci_low"]
                    >= conversion_floor
                ),
            }
            for stratum in strata
        }
        passes_all = all(item["passes"] for item in by_stratum.values())
        floor_audit[arm] = {
            "by_stratum": by_stratum,
            "passes_all_strata": passes_all,
        }
        if passes_all:
            passing_arms.append(arm)

    next_branch = (
        "human_review_repaired_m1_force_and_training_provenance"
        if passing_arms
        else "scan_faithful_retraining_required"
    )
    return {
        "schema": 1,
        "verdict": VERDICT,
        "question": (
            "What do the existing M1 weights convert when only the attacker "
            "engine receives the certified legality repair?"
        ),
        "protocol": {
            "baseline_matrix": "home-0955",
            "same_models": True,
            "same_positions": True,
            "same_historical_gen2_defender": True,
            "attacker_change_only": "certified legality repair",
            "paired_unit": "position_index",
            "draw_treatment": "valid_nonconversion",
            "conversion_floor_wilson_low": conversion_floor,
            "bootstrap_samples": bootstrap_samples,
        },
        "repair_certificate": {
            "verdict": repair["verdict"],
            "conversion": repair.get("conversion"),
        },
        "repaired_conversion": repaired_conversion,
        "paired_repair_effect": effects,
        "m1_floor_audit": floor_audit,
        "m1_arms_passing_floor": passing_arms,
        "repaired_model_ranking_vs_c0": new_matrix.get("ranking_vs_baseline"),
        "selected_challenger_for_force_review": new_matrix.get(
            "selected_challenger_for_force_review"
        ),
        "force": new_matrix.get("force"),
        "next_branch": next_branch,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new-dir", type=Path, required=True)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--new-matrix", type=Path, required=True)
    parser.add_argument("--repair-summary", type=Path, required=True)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--strata", nargs="+", required=True)
    parser.add_argument("--m1-arms", nargs="+", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=962_001)
    parser.add_argument("--conversion-floor", type=float, default=0.80)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_report(
        new_dir=args.new_dir,
        baseline_dir=args.baseline_dir,
        new_matrix_path=args.new_matrix,
        repair_summary_path=args.repair_summary,
        models=args.models,
        strata=args.strata,
        m1_arms=args.m1_arms,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
        conversion_floor=args.conversion_floor,
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
