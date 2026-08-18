#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit realized CTX2 activation/covariance before any intervention fit."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    from l3_conditional_targets import CTX2_BASE_COMPONENTS
    from l3_context2_intervention_plan import _cell_statistics, _mixture
except ModuleNotFoundError:
    from jobs.tools.l3_conditional_targets import CTX2_BASE_COMPONENTS
    from jobs.tools.l3_context2_intervention_plan import _cell_statistics, _mixture


def _single_report_statistics(report: dict[str, Any], ridge: float) -> dict[str, Any]:
    return _mixture(
        np.asarray([1.0], dtype=np.float64),
        [_cell_statistics(report)],
        ridge,
    )


def audit(
    *,
    intervention: dict[str, Any],
    baseline: dict[str, Any],
    corpus: dict[str, Any],
    plan: dict[str, Any],
    current_contribution: dict[str, Any],
    ridge: float = 1e-8,
) -> dict[str, Any]:
    if ridge <= 0:
        raise ValueError("ridge must be positive")
    if intervention.get("schema") != "jass.l3_context2_activation_census.v1":
        raise ValueError("intervention activation schema drift")
    if baseline.get("schema") != "jass.l3_context2_activation_census.v1":
        raise ValueError("baseline activation schema drift")
    if corpus.get("schema") != "jass.l3_context2_intervention_corpus.v1":
        raise ValueError("corpus summary schema drift")
    if corpus.get("verdict") != "JASS_CONTEXT2_INTERVENTION_CORPUS_READY":
        raise ValueError("corpus is not certified")
    if corpus.get("records") != 2_000_000:
        raise ValueError("intervention corpus cardinality drift")
    if plan.get("schema") != "jass.l3_context2_intervention_plan.v1":
        raise ValueError("plan schema drift")
    if plan.get("verdict") != "JASS_CONTEXT2_INTERVENTION_PLAN_READY":
        raise ValueError("plan is not certified")
    if current_contribution.get("schema") != "jass.l3_context2_fixed_contribution_audit.v1":
        raise ValueError("CURRENT contribution schema drift")

    intervention_stats = _single_report_statistics(intervention, ridge)
    baseline_stats = _single_report_statistics(baseline, ridge)
    realized_logdet_gain = intervention_stats["logdet"] - baseline_stats["logdet"]
    diagnostics = intervention.get("diagnostics") or {}
    constraints = plan.get("constraints") or {}
    max_draw_shift = float(constraints["maximum_relative_draw_shift_vs_base"])
    max_side_skew = float(constraints["maximum_wdl_side_skew"])
    guards = {
        "all_30_channels_materially_active": bool(
            diagnostics.get("all_30_channels_materially_active")
        ),
        "all_15_base_signals_materially_active": bool(
            diagnostics.get("all_15_base_signals_materially_active")
        ),
        "strict_realized_logdet_gain_vs_base": realized_logdet_gain > 0.0,
        "corpus_relative_draw_shift": (
            float(corpus["relative_draw_shift_vs_base"]) <= max_draw_shift
        ),
        "corpus_wdl_side_skew": float(corpus["wdl_side_skew"]) <= max_side_skew,
        "phase_recomposition": (
            float((intervention.get("phase") or {})["recomposition_max_absolute_error"])
            <= 1e-5
        ),
    }
    passed = all(guards.values())

    activation_delta = {}
    new_rows = intervention.get("base_15_signals") or {}
    base_rows = baseline.get("base_15_signals") or {}
    if set(new_rows) != set(CTX2_BASE_COMPONENTS) or set(base_rows) != set(CTX2_BASE_COMPONENTS):
        raise ValueError("base component set drift")
    for name in CTX2_BASE_COMPONENTS:
        activation_delta[name] = {
            "intervention_rate": float(new_rows[name]["active_position_rate_material"]),
            "baseline_rate": float(base_rows[name]["active_position_rate_material"]),
            "delta_percentage_points": 100.0 * (
                float(new_rows[name]["active_position_rate_material"])
                - float(base_rows[name]["active_position_rate_material"])
            ),
        }

    current_train = ((current_contribution.get("cohorts") or {}).get("train_oof") or {})
    current_concentration = current_train.get("base_15_concentration") or {}
    required = {"largest_share", "top3_share", "effective_component_count"}
    if not required.issubset(current_concentration):
        raise ValueError("CURRENT concentration reference drift")

    return {
        "schema": "jass.l3_context2_intervention_activation_audit.v1",
        "verdict": (
            "JASS_CONTEXT2_INTERVENTION_ACTIVATION_SCREEN_PASSED"
            if passed
            else "JASS_CONTEXT2_INTERVENTION_ACTIVATION_SCREEN_FAILED"
        ),
        "screen_passed": passed,
        "guards": guards,
        "population": intervention["population"],
        "realized": {
            "ridge": ridge,
            "logdet": intervention_stats["logdet"],
            "logdet_gain_vs_base": realized_logdet_gain,
            "effective_covariance_dimension": intervention_stats[
                "effective_covariance_dimension"
            ],
            "maximum_absolute_pair_correlation": intervention_stats[
                "maximum_absolute_pair_correlation"
            ],
            "minimum_component_variance": intervention_stats[
                "minimum_component_variance"
            ],
        },
        "baseline": {
            "logdet": baseline_stats["logdet"],
            "effective_covariance_dimension": baseline_stats[
                "effective_covariance_dimension"
            ],
            "maximum_absolute_pair_correlation": baseline_stats[
                "maximum_absolute_pair_correlation"
            ],
        },
        "predicted_design": plan["predicted_design"],
        "base_activation_delta": activation_delta,
        "rare_raw_channels": diagnostics.get("rare_raw_channels") or [],
        "rare_base_signals": diagnostics.get("rare_base_signals") or [],
        "current_mapper_concentration_reference": {
            key: float(current_concentration[key]) for key in sorted(required)
        },
        "next_required_stage": (
            "aligned mapper contribution/concentration screen on intervention corpus"
            if passed
            else "redesign intervention corpus; fit remains forbidden"
        ),
        "patterneval_fit_authorized": False,
        "fits_run": 0,
        "force_games_played": 0,
        "frozen_read": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intervention", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--corpus-summary", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--current-contribution", type=Path, required=True)
    parser.add_argument("--ridge", type=float, default=1e-8)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = audit(
        intervention=json.loads(args.intervention.read_text(encoding="utf-8")),
        baseline=json.loads(args.baseline.read_text(encoding="utf-8")),
        corpus=json.loads(args.corpus_summary.read_text(encoding="utf-8")),
        plan=json.loads(args.plan.read_text(encoding="utf-8")),
        current_contribution=json.loads(
            args.current_contribution.read_text(encoding="utf-8")
        ),
        ridge=args.ridge,
    )
    if args.out.exists():
        raise ValueError(f"{args.out}: output exists (no-clobber)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
