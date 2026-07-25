#!/usr/bin/env python3
"""Aggregate the 0959 Scan verification/threat-semantics diagnostic."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import statistics
from typing import Any, Iterable

try:
    from l3_corrected_conversion_matrix import (
        SUMMARY_KEYS,
        load_document,
        paired_conversion,
    )
    from l3_scan_conversion_calibration import wilson_interval
    from l3_scan_semantics_replay import DEPTHS, ENGINES
    from l3_scan_semantics_variants import VARIANT_ORDER
except ModuleNotFoundError:  # pragma: no cover
    from jobs.tools.l3_corrected_conversion_matrix import (
        SUMMARY_KEYS,
        load_document,
        paired_conversion,
    )
    from jobs.tools.l3_scan_conversion_calibration import wilson_interval
    from jobs.tools.l3_scan_semantics_replay import DEPTHS, ENGINES
    from jobs.tools.l3_scan_semantics_variants import VARIANT_ORDER


CONVERSION_DEPTHS = (10, 12)
COUNTERS = (
    "scan_verify_probes",
    "scan_verify_cutoffs",
    "scan_threat_reentries",
)


def load_replays(
    paths: Iterable[Path],
) -> dict[tuple[str, str, int], dict[str, Any]]:
    rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("protocol") != "l3-pure-m1-scan-node-semantics-replay-v1":
            raise ValueError(f"{path}: unexpected replay protocol")
        if tuple(payload.get("depths", [])) != DEPTHS:
            raise ValueError(f"{path}: depth ladder mismatch")
        if tuple(payload.get("engines", [])) != ENGINES:
            raise ValueError(f"{path}: engine ladder mismatch")
        for row in payload.get("rows", []):
            key = (
                str(row["sentinel_id"]),
                str(row["engine"]),
                int(row["requested_depth"]),
            )
            if key in rows:
                raise ValueError(f"{path}: duplicate replay key {key}")
            if "error" in row:
                raise ValueError(f"{path}: engine error at {key}: {row['error']}")
            analysis = row.get("analysis")
            if not isinstance(analysis, dict) or not analysis.get("best_move"):
                raise ValueError(f"{path}: incomplete analysis at {key}")
            rows[key] = row
    return rows


def trace_readout(
    sentinels: list[dict[str, Any]],
    rows: dict[tuple[str, str, int], dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    expected = {
        (str(s["sentinel_id"]), engine, depth)
        for s in sentinels
        for engine in ENGINES
        for depth in DEPTHS
    }
    if set(rows) != expected:
        raise ValueError(
            f"replay matrix mismatch missing={len(expected-set(rows))} "
            f"extra={len(set(rows)-expected)}"
        )

    buckets: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    cases: list[dict[str, Any]] = []
    for sentinel in sentinels:
        sid = str(sentinel["sentinel_id"])
        case = {
            key: sentinel[key]
            for key in (
                "sentinel_id",
                "stratum",
                "source_index",
                "advantaged_side",
                "family",
            )
        }
        case["depths"] = {}
        for depth in DEPTHS:
            scan = dict(rows[(sid, "SCAN_NATIVE", depth)]["analysis"])
            depth_row: dict[str, Any] = {
                "scan_best_move": scan["best_move"],
                "scan_score": scan.get("score"),
                "jass": {},
            }
            for engine in VARIANT_ORDER:
                analysis = dict(rows[(sid, engine, depth)]["analysis"])
                compact = {
                    key: analysis.get(key)
                    for key in (
                        "best_move",
                        "score",
                        "reported_depth",
                        "nodes",
                        "cutoffs",
                        "first_move_cutoffs",
                        "pvs_researches",
                        "moves_searched",
                        *COUNTERS,
                        "elapsed_seconds",
                        "pv",
                        "raw_trace_sha256",
                    )
                }
                compact["matches_scan_move"] = (
                    str(compact["best_move"]) == str(scan["best_move"])
                )
                depth_row["jass"][engine] = compact
                buckets[(engine, depth, "all")].append(compact)
                buckets[(engine, depth, str(sentinel["family"]))].append(compact)
                buckets[
                    (engine, depth, f"stratum:{sentinel['stratum']}")
                ].append(compact)
            case["depths"][str(depth)] = depth_row
        cases.append(case)

    summary: dict[str, Any] = {}
    labels = (
        "all",
        "jass_failure",
        "shared_win_control",
        *sorted({f"stratum:{s['stratum']}" for s in sentinels}),
    )
    for engine in VARIANT_ORDER:
        summary[engine] = {}
        for depth in DEPTHS:
            summary[engine][str(depth)] = {}
            for label in labels:
                values = buckets[(engine, depth, label)]
                matches = sum(bool(row["matches_scan_move"]) for row in values)
                nodes = [
                    int(row["nodes"]) for row in values if row.get("nodes") is not None
                ]
                entry: dict[str, Any] = {
                    "n": len(values),
                    "scan_move_matches": matches,
                    "scan_move_match_rate": matches / len(values) if values else None,
                    "median_nodes": statistics.median(nodes) if nodes else None,
                }
                for counter in COUNTERS:
                    counts = [
                        int(row[counter])
                        for row in values
                        if row.get(counter) is not None
                    ]
                    entry[f"total_{counter}"] = sum(counts)
                    entry[f"median_{counter}"] = (
                        statistics.median(counts) if counts else None
                    )
                summary[engine][str(depth)][label] = entry
    return summary, cases


def classify(
    conversion: dict[str, dict[str, dict[str, dict[str, Any]]]],
    paired: dict[str, dict[str, dict[str, dict[str, Any]]]],
    strata: list[str],
) -> dict[str, Any]:
    for depth in CONVERSION_DEPTHS:
        ds = str(depth)
        for arm in ("SCAN_VERIFY", "SCAN_VERIFY_THREAT"):
            if all(float(conversion[ds][arm][s]["ci_low"]) >= 0.80 for s in strata):
                return {
                    "verdict": "SCAN_NODE_SEMANTICS_RECOVERS_CONVERSION",
                    "localized_arm": arm,
                    "localized_depth": depth,
                    "reason": (
                        f"{arm} d{depth} crosses the preregistered 80% "
                        "Wilson lower bound on both strata."
                    ),
                    "next_branch_requiring_human_review": (
                        "confirm_minimal_patch_and_general_strength"
                    ),
                }

    labels = {
        "SCAN_VERIFY": "SCAN_VERIFICATION_PRUNING_DOMINANT",
        "SCAN_VERIFY_THREAT": "SCAN_THREAT_NODE_SEMANTICS_DOMINANT",
    }
    for depth in CONVERSION_DEPTHS:
        ds = str(depth)
        for arm in ("SCAN_VERIFY", "SCAN_VERIFY_THREAT"):
            rows = [paired[ds][s][f"{arm}_vs_SCAN_CORE"] for s in strata]
            if all(
                float(row["delta"]) >= 0.10 and float(row["ci_low"]) > 0.0
                for row in rows
            ):
                return {
                    "verdict": labels[arm],
                    "localized_arm": arm,
                    "localized_depth": depth,
                    "reason": (
                        f"{arm} d{depth} improves paired conversion by at "
                        "least 10 points with positive 95% intervals on both strata."
                    ),
                    "next_branch_requiring_human_review": (
                        "confirm_minimal_patch_and_general_strength"
                    ),
                }

    means = {
        (depth, arm): sum(
            float(conversion[str(depth)][arm][s]["conversion"]) for s in strata
        )
        / len(strata)
        for depth in CONVERSION_DEPTHS
        for arm in VARIANT_ORDER
    }
    best_depth, best_arm = max(means, key=means.get)
    return {
        "verdict": "SCAN_INTERNAL_NODE_SEMANTICS_REQUIRED",
        "localized_arm": None,
        "best_diagnostic_arm": best_arm,
        "best_diagnostic_depth": best_depth,
        "reason": (
            "Neither exact verification pruning nor exact threat re-entry "
            "produces a robust paired conversion gain on both strata."
        ),
        "next_branch_requiring_human_review": (
            "instrument_native_scan_internal_nodes_tt_bounds_and_terminal_returns"
        ),
    }


def build_report(
    *,
    sentinels_path: Path,
    replay_paths: list[Path],
    conversion_dir: Path,
    strata: list[str],
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    sentinels_payload = json.loads(sentinels_path.read_text(encoding="utf-8"))
    if sentinels_payload.get("protocol") != (
        "l3-pure-m1-search-tree-audit-sentinels-v1"
    ):
        raise ValueError("unexpected sentinel protocol")
    sentinels = list(sentinels_payload.get("sentinels", []))
    if len(sentinels) != 48:
        raise ValueError("0959 requires 48 sentinels")
    traces, cases = trace_readout(sentinels, load_replays(replay_paths))

    documents: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    conversion: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for depth in CONVERSION_DEPTHS:
        ds = str(depth)
        documents[ds] = {}
        conversion[ds] = {}
        for model in VARIANT_ORDER:
            documents[ds][model] = {}
            conversion[ds][model] = {}
            for stratum in strata:
                document = load_document(
                    conversion_dir / f"{model}-D{depth}-{stratum}.json"
                )
                documents[ds][model][stratum] = document
                low, high = wilson_interval(
                    int(document["n_win"]), int(document["n_pos"])
                )
                conversion[ds][model][stratum] = {
                    **{key: document[key] for key in SUMMARY_KEYS},
                    "ci_low": low,
                    "ci_high": high,
                }

    comparisons: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for depth_index, depth in enumerate(CONVERSION_DEPTHS):
        ds = str(depth)
        comparisons[ds] = {}
        for stratum_index, stratum in enumerate(strata):
            comparisons[ds][stratum] = {}
            for arm_index, arm in enumerate(("SCAN_VERIFY", "SCAN_VERIFY_THREAT")):
                comparisons[ds][stratum][f"{arm}_vs_SCAN_CORE"] = (
                    paired_conversion(
                        documents[ds][arm][stratum],
                        documents[ds]["SCAN_CORE"][stratum],
                        seed=(
                            seed
                            + depth_index * 1000
                            + stratum_index * 100
                            + arm_index
                        ),
                        bootstrap_samples=bootstrap_samples,
                    )
                )

    localization = classify(conversion, comparisons, strata)
    return {
        "schema": 1,
        "verdict": "SCAN_NODE_SEMANTICS_AUDIT_READY_HUMAN_REVIEW",
        "localization": localization,
        "protocol": {
            "design": "paired_full_gauge_plus_root_trace",
            "fixed_eval": "SCAN_3_1_EXACT_RAW_PORT",
            "fixed_defender": "GEN2_Q00_D10",
            "conversion_depths": list(CONVERSION_DEPTHS),
            "trace_depths": list(DEPTHS),
            "sentinel_count": len(sentinels),
            "paired_unit": "source_position_index",
            "bootstrap_samples": bootstrap_samples,
        },
        "conversion": conversion,
        "paired_conversion": comparisons,
        "trace_summary": traces,
        "cases": cases,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinels", type=Path, required=True)
    parser.add_argument("--replay-inputs", nargs="+", type=Path, required=True)
    parser.add_argument("--conversion-dir", type=Path, required=True)
    parser.add_argument("--strata", nargs="+", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=959_101)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path)
    args = parser.parse_args()

    payload = build_report(
        sentinels_path=args.sentinels,
        replay_paths=args.replay_inputs,
        conversion_dir=args.conversion_dir,
        strata=args.strata,
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
