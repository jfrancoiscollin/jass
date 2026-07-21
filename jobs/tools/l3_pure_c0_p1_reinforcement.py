#!/usr/bin/env python3
"""Aggregate strengthened direct C0-vs-P1 matches for L3-PURE parent review."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def load_report(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"wins_a", "draws", "wins_b", "n", "rate", "ci_low", "ci_high", "elo", "complete"}
    missing = required - set(payload)
    if missing:
        raise ValueError(f"{path}: missing keys {sorted(missing)}")
    if payload.get("complete") is not True:
        raise ValueError(f"{path}: incomplete report")
    if int(payload["n"]) != int(payload["wins_a"]) + int(payload["draws"]) + int(payload["wins_b"]):
        raise ValueError(f"{path}: inconsistent counts")
    return payload


def aggregate(reports: list[dict[str, Any]]) -> dict[str, float | int]:
    wins = sum(int(item["wins_a"]) for item in reports)
    draws = sum(int(item["draws"]) for item in reports)
    losses = sum(int(item["wins_b"]) for item in reports)
    n = wins + draws + losses
    if n <= 0:
        raise ValueError("empty aggregate")
    rate = (wins + 0.5 * draws) / n
    variance = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(variance / n)
    ci_low = max(0.0, rate - 1.96 * se)
    ci_high = min(1.0, rate + 1.96 * se)
    elo = -400 * math.log10(1 / rate - 1) if 0 < rate < 1 else 0.0
    return {
        "wins_p1": wins,
        "draws": draws,
        "wins_c0": losses,
        "n": n,
        "p1_score_rate": round(rate, 6),
        "ci_low": round(ci_low, 6),
        "ci_high": round(ci_high, 6),
        "p1_elo_vs_c0": round(elo, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--q00-depth", required=True)
    parser.add_argument("--q00-movetime", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary-out", required=True)
    parser.add_argument("--practical-margin", type=float, default=0.005)
    args = parser.parse_args()
    if not 0 <= args.practical_margin < 0.05:
        parser.error("invalid practical margin")

    try:
        depth = load_report(args.q00_depth)
        movetime = load_report(args.q00_movetime)
        for label, report, budget in (
            ("q00_depth9", depth, "depth"),
            ("q00_movetime_0_3", movetime, "movetime"),
        ):
            if int(report["n"]) < 1000:
                raise ValueError(f"{label}: requires at least 1000 games")
            if report.get("search_params_a") != report.get("search_params_b"):
                raise ValueError(f"{label}: search fingerprints differ")
            if budget == "depth" and int(report.get("depth") or -1) != 9:
                raise ValueError(f"{label}: expected depth 9")
            if budget == "movetime" and float(report.get("movetime") or 0.0) != 0.3:
                raise ValueError(f"{label}: expected movetime 0.3")

        combined = aggregate([depth, movetime])
        margin = args.practical_margin
        rates = [float(depth["rate"]), float(movetime["rate"])]
        p1_supported = (
            all(rate >= 0.5 for rate in rates)
            and float(combined["ci_low"]) > 0.5 + margin
        )
        c0_supported = (
            all(rate <= 0.5 for rate in rates)
            and float(combined["ci_high"]) < 0.5 - margin
        )
        if p1_supported:
            decision = "M0_DIRECT_REINFORCEMENT_P1_PARENT_SUPPORTED"
            parent = "P1_0842_G4"
        elif c0_supported:
            decision = "M0_DIRECT_REINFORCEMENT_C0_PARENT_SUPPORTED"
            parent = "C0_A_G3"
        else:
            decision = "M0_DIRECT_REINFORCEMENT_PARENT_UNRESOLVED"
            parent = "UNRESOLVED"

        payload = {
            "schema": 1,
            "protocol": "l3-pure-m0-c0-p1-direct-reinforcement",
            "decision": decision,
            "recommended_parent": parent,
            "primary_views": {
                "q00_depth9": depth,
                "q00_movetime_0_3": movetime,
            },
            "combined": combined,
            "guards": {
                "same_q00_fingerprint_both_sides": True,
                "minimum_games_per_view": 1000,
                "practical_margin": margin,
                "both_view_point_estimates_same_side_required": True,
                "combined_interval_must_clear_50pct_plus_margin": True,
            },
            "m1_authorized": False,
            "promotion_authorized": False,
            "automatic_next_job": None,
        }
        summary = {
            "decision": decision,
            "recommended_parent": parent,
            "combined_p1_score_rate": combined["p1_score_rate"],
            "combined_ci95": [combined["ci_low"], combined["ci_high"]],
            "combined_p1_elo_vs_c0": combined["p1_elo_vs_c0"],
            "m1_authorized": False,
            "promotion_authorized": False,
            "automatic_next_job": None,
        }
        Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        Path(args.summary_out).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(decision)
        print(f"recommended_parent={parent}")
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
