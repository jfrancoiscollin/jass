#!/usr/bin/env python3
"""Calibrate the corrected L3 conversion gauge with pinned Scan d10/d12."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

try:
    from l3_corrected_conversion_matrix import load_document, paired_conversion
except ModuleNotFoundError:
    from jobs.tools.l3_corrected_conversion_matrix import (
        load_document,
        paired_conversion,
    )


SUMMARY_KEYS = ("n_pos", "n_win", "n_draw", "n_loss", "conversion")


def wilson_interval(wins: int, total: int) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("Wilson interval requires a positive total")
    z = 1.959963984540054
    rate = wins / total
    denominator = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total))
        / denominator
    )
    return centre - margin, centre + margin


def target_status(rate: float, low: float, threshold: float) -> str:
    if low >= threshold:
        return "supported"
    if rate >= threshold:
        return "point_estimate_only"
    return "not_observed"


def build_calibration(
    *,
    conversion_dir: Path,
    learned_models: list[str],
    scan_models: list[str],
    strata: list[str],
    source_summary: Path,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    if scan_models != ["SCAN_D10", "SCAN_D12"]:
        raise ValueError("scan_models must be SCAN_D10 SCAN_D12")
    source_raw = source_summary.read_bytes()
    source = json.loads(source_raw)
    if source.get("verdict") != "M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW":
        raise ValueError("source matrix verdict mismatch")
    if source.get("promotion_authorized") is not False:
        raise ValueError("source matrix promotion guard mismatch")

    documents: dict[str, dict[str, dict[str, Any]]] = {}
    conversion: dict[str, dict[str, dict[str, Any]]] = {}
    for model in learned_models + scan_models:
        documents[model] = {}
        conversion[model] = {}
        for stratum in strata:
            document = load_document(conversion_dir / f"{model}-{stratum}.json")
            documents[model][stratum] = document
            low, high = wilson_interval(
                int(document["n_win"]), int(document["n_pos"])
            )
            conversion[model][stratum] = {
                **{key: document[key] for key in SUMMARY_KEYS},
                "conversion_ci_low": low,
                "conversion_ci_high": high,
            }

    best_learned = source.get("selected_challenger_for_force_review")
    if best_learned is None:
        ranking = source.get("ranking_vs_baseline", [])
        if not ranking:
            raise ValueError("source matrix has no learned-model ranking")
        best_learned = ranking[0]
    if best_learned not in learned_models:
        raise ValueError(f"source selected unknown model {best_learned!r}")

    comparisons: dict[str, Any] = {}
    for stratum_index, stratum in enumerate(strata):
        comparisons[stratum] = {
            "SCAN_D12_vs_SCAN_D10": paired_conversion(
                documents["SCAN_D12"][stratum],
                documents["SCAN_D10"][stratum],
                seed=seed + stratum_index,
                bootstrap_samples=bootstrap_samples,
            ),
            f"{best_learned}_vs_SCAN_D10": paired_conversion(
                documents[best_learned][stratum],
                documents["SCAN_D10"][stratum],
                seed=seed + 100 + stratum_index,
                bootstrap_samples=bootstrap_samples,
            ),
            f"{best_learned}_vs_SCAN_D12": paired_conversion(
                documents[best_learned][stratum],
                documents["SCAN_D12"][stratum],
                seed=seed + 200 + stratum_index,
                bootstrap_samples=bootstrap_samples,
            ),
        }
        comparisons[stratum]["SCAN_vs_each_learned"] = {}
        for model_index, model in enumerate(learned_models):
            comparisons[stratum]["SCAN_vs_each_learned"][model] = {
                "d10": paired_conversion(
                    documents["SCAN_D10"][stratum],
                    documents[model][stratum],
                    seed=seed + 1000 + stratum_index * 100 + model_index,
                    bootstrap_samples=bootstrap_samples,
                ),
                "d12": paired_conversion(
                    documents["SCAN_D12"][stratum],
                    documents[model][stratum],
                    seed=seed + 2000 + stratum_index * 100 + model_index,
                    bootstrap_samples=bootstrap_samples,
                ),
            }

    thresholds: dict[str, Any] = {}
    for stratum in strata:
        row = conversion["SCAN_D12"][stratum]
        thresholds[stratum] = {}
        for threshold in (0.70, 0.80):
            thresholds[stratum][f"{int(threshold * 100)}pct"] = {
                "threshold": threshold,
                "status": target_status(
                    float(row["conversion"]),
                    float(row["conversion_ci_low"]),
                    threshold,
                ),
            }

    return {
        "schema": 1,
        "verdict": "SCAN_D10_D12_CORRECTED_GAUGE_CALIBRATION_READY",
        "protocol": {
            "shared_corrected_stable_gauge": True,
            "fixed_defender": "GEN2_Q00_D10",
            "scan_runtime": "pinned_no_book_threads1_tt24_bb0",
            "scan_depths": [10, 12],
            "paired_unit": "position_index",
            "draw_treatment": "valid_nonconversion",
            "bootstrap_samples": bootstrap_samples,
        },
        "source_0955_summary_sha256": hashlib.sha256(source_raw).hexdigest(),
        "best_learned_from_0955": best_learned,
        "conversion": conversion,
        "paired_comparisons": comparisons,
        "scan_d12_target_calibration": thresholds,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversion-dir", type=Path, required=True)
    parser.add_argument("--learned-models", nargs="+", required=True)
    parser.add_argument(
        "--scan-models",
        nargs="+",
        default=["SCAN_D10", "SCAN_D12"],
    )
    parser.add_argument("--strata", nargs="+", required=True)
    parser.add_argument("--source-summary", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=956_001)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_calibration(
        conversion_dir=args.conversion_dir,
        learned_models=args.learned_models,
        scan_models=args.scan_models,
        strata=args.strata,
        source_summary=args.source_summary,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
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
