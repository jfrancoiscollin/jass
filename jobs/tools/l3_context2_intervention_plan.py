#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build a deterministic D-optimal CTX2 self-play intervention mixture.

The planner consumes the paired-seed activation reports produced by the CTX2
knob-attribution experiment.  It reconstructs a covariance matrix for each
admissible self-play cell from its reported moments and correlation matrix,
then enumerates a preregistered weight lattice.  The selected mixture maximizes
the regularized log determinant of the pooled 15-dimensional covariance while
respecting WDL, phase and per-cell exposure guards.

This is a design-stage tool.  It does not generate self-play, fit a mapper or a
PatternEval, read frozen data, play force games, or authorize promotion.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

try:
    from l3_conditional_targets import CTX2_BASE_COMPONENTS
except ModuleNotFoundError:
    from jobs.tools.l3_conditional_targets import CTX2_BASE_COMPONENTS


GENERATOR_CELLS = (
    "BASE",
    "ROP16",
    "EPS16",
    "DECAY120",
    "TOPK3M30",
    "DEPTH10",
)
NON_GENERATOR_CONTROLS = ("BASEBIS", "NODECAY")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_cells(items: list[str]) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for item in items:
        if "=" not in item:
            raise ValueError("--cell must use NAME=report.json")
        name, raw_path = item.split("=", 1)
        if not name or name in reports:
            raise ValueError(f"invalid or duplicate cell {name!r}")
        reports[name] = _load(Path(raw_path))
    expected = set(GENERATOR_CELLS) | set(NON_GENERATOR_CONTROLS)
    if set(reports) != expected:
        raise ValueError(
            f"cell set drift: got {sorted(reports)}, expected {sorted(expected)}"
        )
    return reports


def _cell_statistics(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema") != "jass.l3_context2_activation_census.v1":
        raise ValueError("activation report schema drift")
    rows = report.get("base_15_signals") or {}
    if set(rows) != set(CTX2_BASE_COMPONENTS):
        raise ValueError("base component set drift")
    matrix = ((report.get("diagnostics") or {}).get("base_matrix") or {})
    correlation = np.asarray(matrix.get("correlation"), dtype=np.float64)
    width = len(CTX2_BASE_COMPONENTS)
    if correlation.shape != (width, width) or not np.all(np.isfinite(correlation)):
        raise ValueError("base correlation matrix drift")
    correlation = 0.5 * (correlation + correlation.T)
    means = np.asarray([float(rows[name]["mean"]) for name in CTX2_BASE_COMPONENTS])
    rms = np.asarray([float(rows[name]["rms"]) for name in CTX2_BASE_COMPONENTS])
    variance = np.maximum(rms * rms - means * means, 0.0)
    standard = np.sqrt(variance)
    covariance = correlation * np.outer(standard, standard)
    covariance = 0.5 * (covariance + covariance.T)
    second = covariance + np.outer(means, means)
    active = np.asarray(
        [float(rows[name]["active_position_rate_material"]) for name in CTX2_BASE_COMPONENTS]
    )
    positive = np.asarray(
        [float(rows[name]["positive_position_rate"]) for name in CTX2_BASE_COMPONENTS]
    )
    negative = np.asarray(
        [float(rows[name]["negative_position_rate"]) for name in CTX2_BASE_COMPONENTS]
    )
    population = report.get("population") or {}
    wdl = population.get("wdl_stm_rates") or {}
    if set(wdl) != {"-1", "0", "1"}:
        raise ValueError("WDL rates drift")
    phase = report.get("phase") or {}
    strata = phase.get("strata") or []
    if len(strata) != 5:
        raise ValueError("phase strata drift")
    phase_rates = np.asarray([float(row["position_rate"]) for row in strata])
    if not math.isclose(float(phase_rates.sum()), 1.0, abs_tol=1e-9):
        raise ValueError("phase strata do not sum to one")
    return {
        "positions": int(population["positions"]),
        "mean": means,
        "second": second,
        "active": active,
        "positive": positive,
        "negative": negative,
        "wdl": np.asarray([float(wdl["-1"]), float(wdl["0"]), float(wdl["1"])]),
        "tempo_mid": float(phase["tempo_mid_weight_mean"]),
        "phase_rates": phase_rates,
    }


def _mixture(weights: np.ndarray, cells: list[dict[str, Any]], ridge: float) -> dict[str, Any]:
    mean = sum((weight * cell["mean"] for weight, cell in zip(weights, cells)), np.zeros(15))
    second = sum((weight * cell["second"] for weight, cell in zip(weights, cells)), np.zeros((15, 15)))
    covariance = 0.5 * ((second - np.outer(mean, mean)) + (second - np.outer(mean, mean)).T)
    diagonal = np.maximum(np.diag(covariance), 0.0)
    standard = np.sqrt(diagonal)
    denominator = np.outer(standard, standard)
    correlation = np.divide(
        covariance,
        denominator,
        out=np.zeros_like(covariance),
        where=denominator > 1e-18,
    )
    np.fill_diagonal(correlation, np.where(diagonal > 1e-18, 1.0, 0.0))
    eigenvalues = np.maximum(np.linalg.eigvalsh(covariance), 0.0)
    regularized = covariance + ridge * np.eye(len(covariance))
    sign, logdet = np.linalg.slogdet(regularized)
    if sign <= 0 or not np.isfinite(logdet):
        logdet = -math.inf
    total = float(eigenvalues.sum())
    effective = (
        float(total * total / np.sum(eigenvalues * eigenvalues))
        if total > 0 and np.any(eigenvalues > 0)
        else 0.0
    )
    upper = np.abs(correlation[np.triu_indices(len(correlation), 1)])
    active = sum((weight * cell["active"] for weight, cell in zip(weights, cells)), np.zeros(15))
    positive = sum((weight * cell["positive"] for weight, cell in zip(weights, cells)), np.zeros(15))
    negative = sum((weight * cell["negative"] for weight, cell in zip(weights, cells)), np.zeros(15))
    wdl = sum((weight * cell["wdl"] for weight, cell in zip(weights, cells)), np.zeros(3))
    phase_rates = sum(
        (weight * cell["phase_rates"] for weight, cell in zip(weights, cells)), np.zeros(5)
    )
    return {
        "logdet": float(logdet),
        "effective_covariance_dimension": effective,
        "maximum_absolute_pair_correlation": float(upper.max()) if len(upper) else 0.0,
        "minimum_component_variance": float(diagonal.min()),
        "component_variances": diagonal,
        "active_rates": active,
        "positive_rates": positive,
        "negative_rates": negative,
        "wdl_rates": wdl,
        "tempo_mid_weight_mean": float(
            sum(weight * cell["tempo_mid"] for weight, cell in zip(weights, cells))
        ),
        "phase_strata_rates": phase_rates,
    }


def _integer_bounds(value: float, step: float, *, ceil: bool) -> int:
    scaled = value / step
    return int(math.ceil(scaled - 1e-12) if ceil else math.floor(scaled + 1e-12))


def build_plan(
    *,
    attribution_summary: dict[str, Any],
    contribution_audit: dict[str, Any],
    cell_reports: dict[str, dict[str, Any]],
    total_records: int,
    step: float,
    min_base_weight: float,
    min_intervention_weight: float,
    max_cell_weight: float,
    max_relative_draw_shift: float,
    max_wdl_side_skew: float,
    tempo_mid_min: float,
    tempo_mid_max: float,
) -> dict[str, Any]:
    if attribution_summary.get("schema") != "jass.l3_context2_knob_attribution_job.v1":
        raise ValueError("attribution summary schema drift")
    if attribution_summary.get("verdict") != "JASS_CONTEXT2_KNOB_ATTRIBUTION_READY":
        raise ValueError("attribution verdict drift")
    if int(attribution_summary.get("records_per_cell", -1)) != 250_000:
        raise ValueError("attribution cell size drift")
    guards = attribution_summary.get("guards") or {}
    if set(guards) != set(cell_reports):
        raise ValueError("guard cell set drift")
    for name in GENERATOR_CELLS:
        if not bool((guards.get(name) or {}).get("passed")):
            raise ValueError(f"admissible cell {name} failed its WDL guard")
    if bool((guards.get("NODECAY") or {}).get("passed")):
        raise ValueError("NODECAY unexpectedly passed; exclusion rationale drift")

    if contribution_audit.get("schema") != "jass.l3_context2_fixed_contribution_audit.v1":
        raise ValueError("contribution audit schema drift")
    if contribution_audit.get("verdict") != "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY":
        raise ValueError("contribution audit verdict drift")
    current = ((contribution_audit.get("cohorts") or {}).get("train_oof") or {})
    concentration = current.get("base_15_concentration") or {}
    if not concentration:
        raise ValueError("current contribution concentration missing")

    if total_records <= 0 or total_records % 100_000:
        raise ValueError("total records must be a positive multiple of 100,000")
    reciprocal = round(1.0 / step)
    if reciprocal <= 0 or not math.isclose(reciprocal * step, 1.0, abs_tol=1e-12):
        raise ValueError("weight step must divide one exactly")
    if not math.isclose(total_records * step, round(total_records * step), abs_tol=1e-9):
        raise ValueError("weight step does not yield integral record quotas")

    statistics = {name: _cell_statistics(cell_reports[name]) for name in cell_reports}
    if {statistics[name]["positions"] for name in cell_reports} != {250_000}:
        raise ValueError("cell report population drift")
    ordered = [statistics[name] for name in GENERATOR_CELLS]
    base = statistics["BASE"]
    base_variance = np.maximum(np.diag(base["second"] - np.outer(base["mean"], base["mean"])), 0.0)
    ridge = max(float(base_variance.mean()) * 1e-9, 1e-12)

    units_total = reciprocal
    minimum = [
        _integer_bounds(min_base_weight, step, ceil=True),
        *[_integer_bounds(min_intervention_weight, step, ceil=True)] * 5,
    ]
    maximum = [_integer_bounds(max_cell_weight, step, ceil=False)] * 6
    if sum(minimum) > units_total or sum(maximum) < units_total:
        raise ValueError("infeasible lattice weight bounds")
    ranges = [range(lo, hi + 1) for lo, hi in zip(minimum, maximum)]
    base_draw = float(base["wdl"][1])
    feasible: list[tuple[float, float, tuple[int, ...], dict[str, Any]]] = []
    evaluated = 0
    for units in itertools.product(*ranges):
        if sum(units) != units_total:
            continue
        weights = np.asarray(units, dtype=np.float64) * step
        wdl = sum((weight * cell["wdl"] for weight, cell in zip(weights, ordered)), np.zeros(3))
        draw_shift = abs(float(wdl[1]) - base_draw) / base_draw if base_draw else math.inf
        side_skew = abs(float(wdl[2]) - float(wdl[0]))
        tempo_mid = float(sum(weight * cell["tempo_mid"] for weight, cell in zip(weights, ordered)))
        if (
            draw_shift > max_relative_draw_shift + 1e-12
            or side_skew > max_wdl_side_skew + 1e-12
            or not tempo_mid_min - 1e-12 <= tempo_mid <= tempo_mid_max + 1e-12
        ):
            continue
        evaluated += 1
        metrics = _mixture(weights, ordered, ridge)
        entropy = -float(np.sum(weights * np.log(weights))) / math.log(len(weights))
        feasible.append((metrics["logdet"], entropy, units, metrics))
    if not feasible:
        raise ValueError("no feasible intervention mixture")
    feasible.sort(key=lambda row: (-row[0], -row[1], row[2]))
    _, entropy, selected_units, selected = feasible[0]
    selected_weights = np.asarray(selected_units, dtype=np.float64) * step
    base_metrics = _mixture(np.asarray([1.0]), [base], ridge)
    equal_metrics = _mixture(np.full(6, 1.0 / 6.0), ordered, ridge)
    logdet_gain_base = selected["logdet"] - base_metrics["logdet"]
    logdet_gain_equal = selected["logdet"] - equal_metrics["logdet"]
    draw_shift = abs(float(selected["wdl_rates"][1]) - base_draw) / base_draw
    side_skew = abs(float(selected["wdl_rates"][2]) - float(selected["wdl_rates"][0]))
    weights = {name: float(weight) for name, weight in zip(GENERATOR_CELLS, selected_weights)}
    quotas = {name: int(round(total_records * weight)) for name, weight in weights.items()}
    if sum(quotas.values()) != total_records:
        raise RuntimeError("record quota rounding drift")

    current_top1 = float(concentration["largest_share"])
    current_top3 = float(concentration["top3_share"])
    current_effective = float(concentration["effective_component_count"])
    generation_authorized = logdet_gain_base > 0.0 and evaluated > 0
    return {
        "schema": "jass.l3_context2_intervention_plan.v1",
        "verdict": (
            "JASS_CONTEXT2_INTERVENTION_PLAN_READY"
            if generation_authorized
            else "JASS_CONTEXT2_INTERVENTION_PLAN_NO_GAIN"
        ),
        "method": {
            "name": "lattice_D_optimal_pooled_base15_covariance",
            "criterion": "maximize_regularized_log_determinant",
            "weight_step": step,
            "lattice_candidates_feasible": evaluated,
            "regularization": ridge,
            "tie_breaker": "maximum_normalized_cell_entropy_then_lexicographic_units",
        },
        "constraints": {
            "minimum_base_weight": min_base_weight,
            "minimum_each_intervention_weight": min_intervention_weight,
            "maximum_each_cell_weight": max_cell_weight,
            "maximum_relative_draw_shift_vs_base": max_relative_draw_shift,
            "maximum_wdl_side_skew": max_wdl_side_skew,
            "tempo_mid_weight_range": [tempo_mid_min, tempo_mid_max],
            "same_parent_and_paired_generation_required": True,
            "excluded_cells": {
                "BASEBIS": "independent-seed noise control, not an intervention",
                "NODECAY": "failed preregistered WDL distribution guard",
            },
        },
        "corpus": {
            "target_records": total_records,
            "weights": weights,
            "record_quotas": quotas,
            "generator_cells": list(GENERATOR_CELLS),
            "cell_entropy_normalized": entropy,
        },
        "predicted_design": {
            "logdet": selected["logdet"],
            "logdet_gain_vs_base": logdet_gain_base,
            "logdet_gain_vs_equal_mixture": logdet_gain_equal,
            "effective_covariance_dimension": selected["effective_covariance_dimension"],
            "maximum_absolute_pair_correlation": selected["maximum_absolute_pair_correlation"],
            "minimum_component_variance": selected["minimum_component_variance"],
            "base_component_active_rates": {
                name: float(value)
                for name, value in zip(CTX2_BASE_COMPONENTS, selected["active_rates"])
            },
            "base_component_positive_rates": {
                name: float(value)
                for name, value in zip(CTX2_BASE_COMPONENTS, selected["positive_rates"])
            },
            "base_component_negative_rates": {
                name: float(value)
                for name, value in zip(CTX2_BASE_COMPONENTS, selected["negative_rates"])
            },
            "wdl_stm_rates": {
                "-1": float(selected["wdl_rates"][0]),
                "0": float(selected["wdl_rates"][1]),
                "1": float(selected["wdl_rates"][2]),
            },
            "relative_draw_shift_vs_base": draw_shift,
            "wdl_side_skew": side_skew,
            "tempo_mid_weight_mean": selected["tempo_mid_weight_mean"],
            "phase_strata_rates": [float(value) for value in selected["phase_strata_rates"]],
        },
        "current_corpus_diagnosis": {
            "largest_base_logit_share": current_top1,
            "top3_base_logit_share": current_top3,
            "effective_base_component_count": current_effective,
        },
        "downstream_preregistered_screens": {
            "before_fit": {
                "all_15_base_signals_materially_active": True,
                "relative_draw_shift_vs_BASE_at_most": max_relative_draw_shift,
                "wdl_side_skew_at_most": max_wdl_side_skew,
                "tempo_mid_weight_range": [tempo_mid_min, tempo_mid_max],
                "actual_logdet_gain_vs_BASE_strictly_positive": True,
            },
            "after_aligned_mapper_before_patterneval_fit": {
                "largest_base_logit_share_at_most": 0.90 * current_top1,
                "top3_base_logit_share_at_most": 0.95 * current_top3,
                "effective_base_component_count_at_least": 1.25 * current_effective,
                "thresholds_are_relative_to_authenticated_CURRENT_2M_audit": True,
            },
            "force": {
                "primary": "INTERVENTION_ALIGNED_CTX2_A30_vs_INTERVENTION_SHUFFLED_CTX2_A30",
                "primary_view": "native_movetime_0.1_two_fresh_disjoint_pools",
                "diagnostic_view": "Q00_depth9",
                "secondary_if_primary_passes": "INTERVENTION_ALIGNED_CTX2_A30_vs_CURRICULUM",
            },
        },
        "generation_authorized_by_design": generation_authorized,
        "fits_run": 0,
        "force_games_played": 0,
        "selfplay_generated": False,
        "frozen_read": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attribution-summary", type=Path, required=True)
    parser.add_argument("--contribution-audit", type=Path, required=True)
    parser.add_argument("--cell", action="append", required=True)
    parser.add_argument("--total-records", type=int, default=2_000_000)
    parser.add_argument("--weight-step", type=float, default=0.05)
    parser.add_argument("--min-base-weight", type=float, default=0.15)
    parser.add_argument("--min-intervention-weight", type=float, default=0.05)
    parser.add_argument("--max-cell-weight", type=float, default=0.30)
    parser.add_argument("--max-relative-draw-shift", type=float, default=0.15)
    parser.add_argument("--max-wdl-side-skew", type=float, default=0.02)
    parser.add_argument("--tempo-mid-min", type=float, default=0.45)
    parser.add_argument("--tempo-mid-max", type=float, default=0.55)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    plan = build_plan(
        attribution_summary=_load(args.attribution_summary),
        contribution_audit=_load(args.contribution_audit),
        cell_reports=_parse_cells(args.cell),
        total_records=args.total_records,
        step=args.weight_step,
        min_base_weight=args.min_base_weight,
        min_intervention_weight=args.min_intervention_weight,
        max_cell_weight=args.max_cell_weight,
        max_relative_draw_shift=args.max_relative_draw_shift,
        max_wdl_side_skew=args.max_wdl_side_skew,
        tempo_mid_min=args.tempo_mid_min,
        tempo_mid_max=args.tempo_mid_max,
    )
    if args.output.exists():
        raise ValueError(f"{args.output}: output exists (no-clobber)")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
