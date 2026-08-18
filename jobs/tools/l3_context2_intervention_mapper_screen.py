#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gate an intervention mapper against preregistered CURRENT concentration ratios."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _concentration(report: dict[str, Any], label: str) -> dict[str, float]:
    if report.get("schema") != "jass.l3_context2_fixed_contribution_audit.v1":
        raise ValueError(f"{label} contribution schema drift")
    if report.get("verdict") != "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY":
        raise ValueError(f"{label} contribution verdict drift")
    train = ((report.get("cohorts") or {}).get("train_oof") or {})
    concentration = train.get("base_15_concentration") or {}
    required = ("largest_share", "top3_share", "effective_component_count")
    if not all(key in concentration for key in required):
        raise ValueError(f"{label} concentration fields drift")
    result = {key: float(concentration[key]) for key in required}
    if not (0.0 < result["largest_share"] <= result["top3_share"] <= 1.0):
        raise ValueError(f"{label} concentration share range drift")
    if result["effective_component_count"] <= 0.0:
        raise ValueError(f"{label} effective count drift")
    return result


def screen(
    *,
    intervention: dict[str, Any],
    current: dict[str, Any],
    activation: dict[str, Any],
    top1_ratio: float = 0.90,
    top3_ratio: float = 0.95,
    effective_ratio: float = 1.25,
) -> dict[str, Any]:
    if not (0.0 < top1_ratio <= 1.0 and 0.0 < top3_ratio <= 1.0):
        raise ValueError("share ratios must be in (0,1]")
    if effective_ratio <= 1.0:
        raise ValueError("effective ratio must exceed one")
    if activation.get("schema") != "jass.l3_context2_intervention_activation_audit.v1":
        raise ValueError("activation screen schema drift")
    if not activation.get("screen_passed"):
        raise ValueError("activation screen did not pass")
    candidate = _concentration(intervention, "intervention")
    reference = _concentration(current, "CURRENT")
    thresholds = {
        "maximum_largest_share": top1_ratio * reference["largest_share"],
        "maximum_top3_share": top3_ratio * reference["top3_share"],
        "minimum_effective_component_count": (
            effective_ratio * reference["effective_component_count"]
        ),
    }
    guards = {
        "largest_share_at_most_90pct_current": (
            candidate["largest_share"] <= thresholds["maximum_largest_share"]
        ),
        "top3_share_at_most_95pct_current": (
            candidate["top3_share"] <= thresholds["maximum_top3_share"]
        ),
        "effective_count_at_least_125pct_current": (
            candidate["effective_component_count"]
            >= thresholds["minimum_effective_component_count"]
        ),
    }
    passed = all(guards.values())
    return {
        "schema": "jass.l3_context2_intervention_mapper_screen.v1",
        "verdict": (
            "JASS_CONTEXT2_INTERVENTION_MAPPER_SCREEN_PASSED"
            if passed
            else "JASS_CONTEXT2_INTERVENTION_MAPPER_SCREEN_FAILED"
        ),
        "screen_passed": passed,
        "preregistered_ratios": {
            "largest_share": top1_ratio,
            "top3_share": top3_ratio,
            "effective_component_count": effective_ratio,
        },
        "current_reference": reference,
        "thresholds": thresholds,
        "intervention": candidate,
        "relative_to_current": {
            "largest_share_ratio": candidate["largest_share"] / reference["largest_share"],
            "top3_share_ratio": candidate["top3_share"] / reference["top3_share"],
            "effective_component_count_ratio": (
                candidate["effective_component_count"]
                / reference["effective_component_count"]
            ),
        },
        "guards": guards,
        "patterneval_fit_authorized": passed,
        "next_required_stage": (
            "paired aligned-vs-shuffled PatternEval fit on intervention corpus"
            if passed
            else "intervention corpus closed for PatternEval fit"
        ),
        "patterneval_fits_run": 0,
        "force_games_played": 0,
        "frozen_read": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intervention", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--activation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = screen(
        intervention=json.loads(args.intervention.read_text(encoding="utf-8")),
        current=json.loads(args.current.read_text(encoding="utf-8")),
        activation=json.loads(args.activation.read_text(encoding="utf-8")),
    )
    if args.out.exists():
        raise ValueError(f"{args.out}: output exists (no-clobber)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
