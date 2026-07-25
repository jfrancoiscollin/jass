#!/usr/bin/env python3
"""Aggregate the 0961 Scan-root-order causal replay and conversion gate."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:
    from l3_corrected_conversion_matrix import load_document, paired_conversion
    from l3_internal_root_trace_report import (
        compare_attempts,
        final_attempt,
        load_rows,
    )
    from l3_scan_conversion_calibration import wilson_interval
except ModuleNotFoundError:  # pragma: no cover
    from jobs.tools.l3_corrected_conversion_matrix import (
        load_document,
        paired_conversion,
    )
    from jobs.tools.l3_internal_root_trace_report import (
        compare_attempts,
        final_attempt,
        load_rows,
    )
    from jobs.tools.l3_scan_conversion_calibration import wilson_interval


DEPTHS = tuple(range(1, 13))


def load_replays(
    paths: Iterable[Path],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    rows: dict[str, dict[str, Any]] = {}
    totals: Counter[str] = Counter()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("protocol") != "l3-pure-m1-root-order-causal-replay-v1":
            raise ValueError(f"{path}: unexpected replay protocol")
        totals.update(
            {key: int(value) for key, value in payload["oracle_totals"].items()}
        )
        for row in payload.get("rows", []):
            sid = str(row["sentinel_id"])
            if sid in rows:
                raise ValueError(f"{path}: duplicate sentinel {sid}")
            if "error" in row:
                raise ValueError(f"{path}: replay error {sid}: {row['error']}")
            analysis = row.get("analysis", {})
            if int(analysis.get("root_order_failures", -1)) != 0:
                raise ValueError(f"{path}: root order failure at {sid}")
            rows[sid] = row
    return rows, dict(totals)


def paired_boolean(
    candidate: list[bool],
    baseline: list[bool],
    *,
    seed: int,
    samples: int,
) -> dict[str, Any]:
    if len(candidate) != len(baseline) or not candidate:
        raise ValueError("paired boolean vectors must be non-empty and equal")
    cand = np.asarray(candidate, dtype=np.int8)
    base = np.asarray(baseline, dtype=np.int8)
    diff = cand - base
    counts = np.asarray(
        [
            np.count_nonzero(diff == -1),
            np.count_nonzero(diff == 0),
            np.count_nonzero(diff == 1),
        ],
        dtype=np.int64,
    )
    rng = np.random.default_rng(seed)
    draws = rng.multinomial(
        len(diff), counts / counts.sum(), size=samples
    )
    deltas = (draws[:, 2] - draws[:, 0]) / len(diff)
    return {
        "n": len(diff),
        "candidate_rate": float(cand.mean()),
        "baseline_rate": float(base.mean()),
        "delta": float(diff.mean()),
        "ci_low": float(np.quantile(deltas, 0.025)),
        "ci_high": float(np.quantile(deltas, 0.975)),
        "baseline_only": int(counts[0]),
        "same": int(counts[1]),
        "candidate_only": int(counts[2]),
    }


def classify(
    *,
    order_contract: bool,
    root_paired: dict[str, Any],
    conversion: dict[str, dict[str, Any]],
) -> str:
    if not order_contract:
        return "ROOT_ORDER_REPLAY_CONTRACT_FAILED"
    if all(
        row["native_repaired"]["ci_low"] >= 0.80
        for row in conversion.values()
    ):
        return "LEGALITY_REPAIR_RECOVERS_CONVERSION"
    if all(
        row["root_order"]["ci_low"] >= 0.80
        for row in conversion.values()
    ):
        return "ROOT_ORDER_REPLAY_RECOVERS_CONVERSION"
    if all(
        row["root_order_paired"]["delta"] >= 0.10
        and row["root_order_paired"]["ci_low"] > 0
        for row in conversion.values()
    ):
        return "ROOT_ORDER_CAUSAL_PARTIAL_RECOVERY"
    if all(
        row["repair_paired"]["delta"] >= 0.10
        and row["repair_paired"]["ci_low"] > 0
        for row in conversion.values()
    ):
        return "LEGALITY_REPAIR_CAUSAL_PARTIAL_RECOVERY"
    if root_paired["delta"] >= 0.10 and root_paired["ci_low"] > 0:
        return "ROOT_ORDER_EXPLAINS_ROOT_CHOICE_NOT_CONVERSION"
    return "ROOT_ORDER_NOT_DOMINANT_RECURSIVE_TRACE_REQUIRED"


def build_report(
    *,
    sentinels: list[dict[str, Any]],
    source_rows: dict[tuple[str, str], dict[str, Any]],
    replay_rows: dict[str, dict[str, Any]],
    oracle_totals: dict[str, int],
    conversion_dir: Path,
    strata: list[str],
    bootstrap_samples: int,
    seed: int,
) -> dict[str, Any]:
    if set(replay_rows) != {str(row["sentinel_id"]) for row in sentinels}:
        raise ValueError("0961 replay matrix does not cover all sentinels")

    per_depth: dict[str, Any] = {}
    cases: list[dict[str, Any]] = []
    all_order_equal = True
    d12_baseline: list[bool] = []
    d12_forced: list[bool] = []
    for depth in DEPTHS:
        baseline_best: list[bool] = []
        forced_best: list[bool] = []
        forced_kinds: Counter[str | None] = Counter()
        order_equal = 0
        score_equal = 0
        for sentinel in sentinels:
            sid = str(sentinel["sentinel_id"])
            scan_events = source_rows[
                (sid, "SCAN_NATIVE_INSTRUMENTED")
            ]["analysis"]["events"]
            baseline_events = source_rows[
                (sid, "JASS_EXACT")
            ]["analysis"]["events"]
            forced_events = replay_rows[sid]["analysis"]["events"]
            scan = final_attempt(scan_events, depth)
            baseline = compare_attempts(
                final_attempt(baseline_events, depth), scan
            )
            forced = compare_attempts(
                final_attempt(forced_events, depth), scan
            )
            baseline_best.append(bool(baseline["bestmove_equal"]))
            forced_best.append(bool(forced["bestmove_equal"]))
            forced_kinds[forced["first_divergence"]] += 1
            order_equal += int(bool(forced["order_equal"]))
            score_equal += int(bool(forced.get("scores_equal", False)))
            if depth == 12:
                cases.append(
                    {
                        "sentinel_id": sid,
                        "stratum": sentinel["stratum"],
                        "baseline": baseline,
                        "root_order_replay": forced,
                    }
                )
        all_order_equal &= order_equal == len(sentinels)
        paired = paired_boolean(
            forced_best,
            baseline_best,
            seed=seed + depth,
            samples=bootstrap_samples,
        )
        per_depth[str(depth)] = {
            "order_matches": order_equal,
            "score_matches": score_equal,
            "sentinel_count": len(sentinels),
            "baseline_best_matches": sum(baseline_best),
            "root_order_best_matches": sum(forced_best),
            "paired_best_match": paired,
            "remaining_first_divergence": {
                str(key): value for key, value in sorted(
                    forced_kinds.items(), key=lambda item: str(item[0])
                )
            },
        }
        if depth == 12:
            d12_baseline = baseline_best
            d12_forced = forced_best

    conversion: dict[str, dict[str, Any]] = {}
    for index, stratum in enumerate(strata):
        baseline = load_document(
            conversion_dir / f"BASE-{stratum}.json"
        )
        native = load_document(
            conversion_dir / f"NATIVE_REPAIRED-{stratum}.json"
        )
        forced = load_document(
            conversion_dir / f"ROOT_ORDER-{stratum}.json"
        )
        native_low, native_high = wilson_interval(
            int(native["n_win"]), int(native["n_pos"])
        )
        low, high = wilson_interval(
            int(forced["n_win"]), int(forced["n_pos"])
        )
        conversion[stratum] = {
            "old_baseline": {
                key: baseline[key]
                for key in ("n_pos", "n_win", "n_draw", "n_loss", "conversion")
            },
            "native_repaired": {
                **{
                    key: native[key]
                    for key in (
                        "n_pos",
                        "n_win",
                        "n_draw",
                        "n_loss",
                        "conversion",
                    )
                },
                "ci_low": native_low,
                "ci_high": native_high,
            },
            "root_order": {
                **{
                    key: forced[key]
                    for key in (
                        "n_pos",
                        "n_win",
                        "n_draw",
                        "n_loss",
                        "conversion",
                    )
                },
                "ci_low": low,
                "ci_high": high,
                "schedule_queries": forced.get(
                    "root_order_schedule_queries", 0
                ),
                "schedule_failures": forced.get("root_order_failures", 0),
            },
            "repair_paired": paired_conversion(
                native,
                baseline,
                seed=seed + 1000 + index,
                bootstrap_samples=bootstrap_samples,
            ),
            "root_order_paired": paired_conversion(
                forced,
                native,
                seed=seed + 1100 + index,
                bootstrap_samples=bootstrap_samples,
            ),
        }

    root_paired = paired_boolean(
        d12_forced,
        d12_baseline,
        seed=seed + 1200,
        samples=bootstrap_samples,
    )
    order_contract = (
        all_order_equal
        and oracle_totals.get("failures", -1) == 0
        and all(
            row["root_order"]["schedule_failures"] == 0
            for row in conversion.values()
        )
    )
    verdict = classify(
        order_contract=order_contract,
        root_paired=root_paired,
        conversion=conversion,
    )
    next_branch = {
        "LEGALITY_REPAIR_RECOVERS_CONVERSION": "certify_legality_repair_then_resume_m1",
        "ROOT_ORDER_REPLAY_RECOVERS_CONVERSION": "port_scan_root_ordering_without_oracle",
        "ROOT_ORDER_CAUSAL_PARTIAL_RECOVERY": "port_scan_root_ordering_then_trace_recursive_residual",
        "LEGALITY_REPAIR_CAUSAL_PARTIAL_RECOVERY": "certify_legality_repair_then_trace_residual",
        "ROOT_ORDER_EXPLAINS_ROOT_CHOICE_NOT_CONVERSION": "instrument_first_recursive_child",
        "ROOT_ORDER_NOT_DOMINANT_RECURSIVE_TRACE_REQUIRED": "instrument_first_recursive_child",
        "ROOT_ORDER_REPLAY_CONTRACT_FAILED": "repair_root_order_replay_contract",
    }[verdict]
    return {
        "schema": 1,
        "protocol": "l3-pure-m1-root-order-causal-audit-v2",
        "diagnostic_only": True,
        "order_contract_valid": order_contract,
        "oracle_totals": oracle_totals,
        "per_depth": per_depth,
        "d12_paired_best_match": root_paired,
        "conversion": conversion,
        "localization": {
            "verdict": verdict,
            "next_branch": next_branch,
        },
        "cases": cases,
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentinels", type=Path, required=True)
    parser.add_argument("--source-traces", type=Path, nargs="+", required=True)
    parser.add_argument("--replay-inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--conversion-dir", type=Path, required=True)
    parser.add_argument("--strata", nargs="+", required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=200000)
    parser.add_argument("--seed", type=int, default=961101)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    args = parser.parse_args()

    sentinels = json.loads(
        args.sentinels.read_text(encoding="utf-8")
    ).get("sentinels", [])
    if len(sentinels) != 48:
        raise ValueError("expected 48 sentinels")
    replay_rows, oracle_totals = load_replays(args.replay_inputs)
    report = build_report(
        sentinels=sentinels,
        source_rows=load_rows(args.source_traces),
        replay_rows=replay_rows,
        oracle_totals=oracle_totals,
        conversion_dir=args.conversion_dir,
        strata=args.strata,
        bootstrap_samples=args.bootstrap_samples,
        seed=args.seed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        "job": "0961bis",
        "verdict": report["localization"]["verdict"],
        "next_branch": report["localization"]["next_branch"],
        "d12_paired_best_match": report["d12_paired_best_match"],
        "conversion": report["conversion"],
        "training_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    args.summary_out.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
