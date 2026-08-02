#!/usr/bin/env python3
"""Apply the preregistered HIER-alone decision to a generic model-gate summary."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


EXPECTED_VIEWS = ("q00", "native")
EXPECTED_PER_VIEW = 6000
EXPECTED_TOTAL = 12000


def _counts(payload: dict, label: str) -> tuple[int, int, int, int, float]:
    keys = ("wins_a", "draws", "wins_b", "n")
    try:
        raw = [payload[key] for key in keys]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{label}: missing/invalid raw count key") from exc
    if any(isinstance(value, bool) or not isinstance(value, int) for value in raw):
        raise ValueError(f"{label}: raw counts must be JSON integers")
    wins, draws, losses, n = raw
    if min(wins, draws, losses) < 0 or wins + draws + losses != n:
        raise ValueError(f"{label}: inconsistent raw counts")
    rate = (wins + 0.5 * draws) / n if n else math.nan
    return wins, draws, losses, n, rate


def decide(summary: dict) -> dict:
    if summary.get("arms") != {"a": "HIER", "b": "CONTROL"}:
        raise ValueError("arms must be exactly A=HIER, B=CONTROL")
    per_view = summary.get("per_view")
    if not isinstance(per_view, dict) or set(per_view) != set(EXPECTED_VIEWS):
        raise ValueError("per_view must contain exactly q00 and native")

    views: dict[str, dict] = {}
    for name in EXPECTED_VIEWS:
        wins, draws, losses, n, rate = _counts(per_view[name], f"view {name}")
        if n != EXPECTED_PER_VIEW:
            raise ValueError(f"view {name}: n={n}, expected {EXPECTED_PER_VIEW}")
        views[name] = {
            "wins_a": wins,
            "draws": draws,
            "wins_b": losses,
            "n": n,
            "rate": rate,
        }

    wins = sum(v["wins_a"] for v in views.values())
    draws = sum(v["draws"] for v in views.values())
    losses = sum(v["wins_b"] for v in views.values())
    n = wins + draws + losses
    if n != EXPECTED_TOTAL:
        raise ValueError(f"combined n={n}, expected {EXPECTED_TOTAL}")

    rate = (wins + 0.5 * draws) / n
    variance = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(variance / n)
    lo = max(0.0, rate - 1.96 * se)
    hi = min(1.0, rate + 1.96 * se)
    same_positive_direction = all(v["rate"] > 0.5 for v in views.values())

    if lo > 0.5 and same_positive_direction:
        verdict = "HIER_L2_REOPEN_FOR_PRIOR_COMBINATION"
        combination_authorized = True
    elif hi < 0.5:
        verdict = "HIER_L2_REGRESSION_ESTABLISHED"
        combination_authorized = False
    else:
        verdict = "HIER_L2_NO_ESTABLISHED_GAIN_CLOSE"
        combination_authorized = False

    gate_summed = summary.get("views_summed")
    if not isinstance(gate_summed, dict):
        raise ValueError("views_summed is missing")
    gate_counts = _counts(gate_summed, "views_summed")[:4]
    if gate_counts != (wins, draws, losses, n):
        raise ValueError("views_summed does not round-trip the per-view raw counts")

    return {
        "schema": 1,
        "verdict": verdict,
        "preregistration": "docs/experiments/L3_HIER_L2_PREREGISTRATION_20260802.md",
        "combined": {
            "wins_a": wins,
            "draws": draws,
            "wins_b": losses,
            "n": n,
            "rate": round(rate, 8),
            "ci95": [round(lo, 8), round(hi, 8)],
        },
        "per_view": {
            name: {**view, "rate": round(view["rate"], 8)}
            for name, view in views.items()
        },
        "same_positive_direction": same_positive_direction,
        "prior_hier_experiment_authorized": combination_authorized,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate-summary", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = decide(json.loads(args.gate_summary.read_text(encoding="utf-8")))
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
