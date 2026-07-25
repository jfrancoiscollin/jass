#!/usr/bin/env python3
"""Aggregate the exact-Scan-eval × Jass-depth causal conversion test."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from l3_corrected_conversion_matrix import (
        SUMMARY_KEYS,
        load_document,
        paired_conversion,
    )
    from l3_scan_conversion_calibration import wilson_interval
except ModuleNotFoundError:  # pragma: no cover
    from jobs.tools.l3_corrected_conversion_matrix import (
        SUMMARY_KEYS,
        load_document,
        paired_conversion,
    )
    from jobs.tools.l3_scan_conversion_calibration import wilson_interval


MODELS = (
    "AB_EXTRAS_D10",
    "AB_EXTRAS_D12",
    "SCAN_EXACT_D10",
    "SCAN_EXACT_D12",
    "SCAN_NATIVE_D10",
    "SCAN_NATIVE_D12",
)


def classify(
    conversion: dict[str, dict[str, dict[str, Any]]],
    comparisons: dict[str, dict[str, dict[str, Any]]],
    strata: list[str],
) -> dict[str, Any]:
    exact_d10 = [conversion["SCAN_EXACT_D10"][s] for s in strata]
    exact_d12 = [conversion["SCAN_EXACT_D12"][s] for s in strata]
    depth = [comparisons[s]["SCAN_EXACT_D12_vs_D10"] for s in strata]

    if all(float(row["ci_low"]) >= 0.80 for row in exact_d10):
        verdict = "EVAL_WEIGHTS_DOMINANT"
        reason = (
            "Jass search at d10 reaches the preregistered conversion floor "
            "with Scan's exact static evaluation on both strata."
        )
        next_branch = "replicate_scan_training_and_fold"
    elif (
        all(float(row["ci_low"]) >= 0.80 for row in exact_d12)
        and any(float(row["ci_low"]) > 0.0 for row in depth)
    ):
        verdict = "SEARCH_DEPTH_DOMINANT"
        reason = (
            "The exact evaluation crosses the conversion floor only after "
            "deepening Jass search, with a positive paired depth effect."
        )
        next_branch = "audit_depth_and_forcing_schedule"
    elif all(float(row["ci_high"]) < 0.80 for row in exact_d12):
        verdict = "SEARCH_IMPLEMENTATION_DOMINANT"
        reason = (
            "Even Jass d12 with Scan's exact evaluation remains below the "
            "conversion floor on both strata."
        )
        next_branch = "compare_scan_and_jass_tree_expansion"
    else:
        verdict = "MIXED_OR_UNRESOLVED"
        reason = (
            "The two strata or confidence intervals do not support one "
            "preregistered causal branch."
        )
        next_branch = "targeted_replication_or_depth14"

    return {
        "verdict": verdict,
        "reason": reason,
        "next_branch_requiring_human_review": next_branch,
        "threshold": {
            "conversion_floor": 0.80,
            "uses_wilson_95pct_lower_for_success": True,
            "uses_wilson_95pct_upper_for_failure": True,
        },
    }


def build_readout(
    *,
    conversion_dir: Path,
    strata: list[str],
    source_0955: Path,
    source_0956: Path,
    static_parity: Path,
    port_manifest: Path,
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    src55_raw = source_0955.read_bytes()
    src56_raw = source_0956.read_bytes()
    src55 = json.loads(src55_raw)
    src56 = json.loads(src56_raw)
    parity_raw = static_parity.read_bytes()
    parity = json.loads(parity_raw)
    port_raw = port_manifest.read_bytes()
    port = json.loads(port_raw)

    if src55.get("verdict") != "M1_CORRECTED_CONVERSION_MATRIX_READY_HUMAN_REVIEW":
        raise ValueError("0955 source verdict mismatch")
    if src56.get("verdict") != "SCAN_D10_D12_CORRECTED_GAUGE_CALIBRATION_READY":
        raise ValueError("0956 source verdict mismatch")
    if parity.get("verdict") != "SCAN_STATIC_PORT_EXACT":
        raise ValueError("static port parity is not exact")
    if parity.get("comparison", {}).get("max_abs_delta") != 0:
        raise ValueError("static port has a non-zero score delta")
    if port.get("distillation") is not False:
        raise ValueError("port manifest does not certify an algebraic port")

    documents: dict[str, dict[str, dict[str, Any]]] = {}
    conversion: dict[str, dict[str, dict[str, Any]]] = {}
    for model in MODELS:
        documents[model] = {}
        conversion[model] = {}
        for stratum in strata:
            doc = load_document(conversion_dir / f"{model}-{stratum}.json")
            documents[model][stratum] = doc
            low, high = wilson_interval(int(doc["n_win"]), int(doc["n_pos"]))
            conversion[model][stratum] = {
                **{key: doc[key] for key in SUMMARY_KEYS},
                "ci_low": low,
                "ci_high": high,
            }

    comparisons: dict[str, dict[str, dict[str, Any]]] = {}
    for stratum_index, stratum in enumerate(strata):
        pairs = (
            ("SCAN_EXACT_D10_vs_AB_EXTRAS_D10", "SCAN_EXACT_D10", "AB_EXTRAS_D10"),
            ("SCAN_EXACT_D12_vs_AB_EXTRAS_D12", "SCAN_EXACT_D12", "AB_EXTRAS_D12"),
            ("AB_EXTRAS_D12_vs_D10", "AB_EXTRAS_D12", "AB_EXTRAS_D10"),
            ("SCAN_EXACT_D12_vs_D10", "SCAN_EXACT_D12", "SCAN_EXACT_D10"),
            ("SCAN_NATIVE_D10_vs_SCAN_EXACT_D10", "SCAN_NATIVE_D10", "SCAN_EXACT_D10"),
            ("SCAN_NATIVE_D12_vs_SCAN_EXACT_D12", "SCAN_NATIVE_D12", "SCAN_EXACT_D12"),
        )
        comparisons[stratum] = {}
        for pair_index, (name, candidate, baseline) in enumerate(pairs):
            comparisons[stratum][name] = paired_conversion(
                documents[candidate][stratum],
                documents[baseline][stratum],
                seed=seed + stratum_index * 100 + pair_index,
                bootstrap_samples=bootstrap_samples,
            )

    localization = classify(conversion, comparisons, strata)
    return {
        "schema": 1,
        "verdict": "SCAN_GAP_CAUSAL_READOUT_READY_HUMAN_REVIEW",
        "localization": localization,
        "protocol": {
            "design": "2x2_eval_weights_x_jass_depth",
            "evals": ["AB_EXTRAS_LEARNED", "SCAN_3_1_EXACT_RAW_PORT"],
            "jass_depths": [10, 12],
            "fixed_defender": "GEN2_Q00_D10",
            "shared_corrected_stable_gauge": True,
            "strata": strata,
            "paired_unit": "position_index",
            "draws_are_nonconversion": True,
            "static_parity_required": True,
            "bootstrap_samples": bootstrap_samples,
        },
        "source_sha256": {
            "0955": hashlib.sha256(src55_raw).hexdigest(),
            "0956": hashlib.sha256(src56_raw).hexdigest(),
            "static_parity": hashlib.sha256(parity_raw).hexdigest(),
            "port_manifest": hashlib.sha256(port_raw).hexdigest(),
        },
        "static_parity": parity["comparison"],
        "conversion": conversion,
        "paired_comparisons": comparisons,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversion-dir", type=Path, required=True)
    parser.add_argument("--strata", nargs="+", required=True)
    parser.add_argument("--source-0955", type=Path, required=True)
    parser.add_argument("--source-0956", type=Path, required=True)
    parser.add_argument("--static-parity", type=Path, required=True)
    parser.add_argument("--port-manifest", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=957_001)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    payload = build_readout(
        conversion_dir=args.conversion_dir,
        strata=args.strata,
        source_0955=args.source_0955,
        source_0956=args.source_0956,
        static_parity=args.static_parity,
        port_manifest=args.port_manifest,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialized, encoding="utf-8")
    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(serialized, encoding="utf-8")
    print(payload["localization"]["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
