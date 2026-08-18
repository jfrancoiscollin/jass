#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Localize the CTX2 intervention mapper concentration failure by generator cell.

The tool never fits a mapper.  It replays the six certified OOF/final mapper
coefficient vectors from the 1411 report on the exact split corpus, recovers
the source generator cell of every row, and attributes the 15 collapsed CTX2
base-component contributions to those cells.  A preregistered lattice then
tests whether changing only the six record quotas could have satisfied the
1411 concentration gates with this fixed mapper.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import struct
from typing import Any, Iterable

import numpy as np

try:
    from l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        _game_equal_weights,
        _open_feat,
        _open_meta,
        _sha256,
        game_folds,
    )
except ModuleNotFoundError:
    from jobs.tools.l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        _game_equal_weights,
        _open_feat,
        _open_meta,
        _sha256,
        game_folds,
    )


GENERATOR_CELLS = (
    "BASE",
    "ROP16",
    "EPS16",
    "DECAY120",
    "TOPK3M30",
    "DEPTH10",
)
CELL_KNOBS = {
    "ROP16": "random_open_plies_8_to_16",
    "EPS16": "explore_epsilon_8_to_16_percent",
    "DECAY120": "explore_decay_60_to_120_plies",
    "TOPK3M30": "topk_0_to_3_with_margin_30",
    "DEPTH10": "play_depth_8_to_10",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _opening_is_holdout(opening_id: int, seed: int, mod: int) -> bool:
    payload = struct.pack("<QQ", int(opening_id), seed & ((1 << 64) - 1))
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "little") % mod == 0


def recover_split_cell_ids(
    *,
    original_meta_path: Path,
    split_meta_path: Path,
    quotas: dict[str, int],
    split_seed: int,
    holdout_mod: int,
) -> np.ndarray:
    """Reproduce selfplay_frontier split ordering and attach source cell IDs."""
    if tuple(quotas) != GENERATOR_CELLS or any(int(quotas[name]) <= 0 for name in quotas):
        raise ValueError("source cell quota/order drift")
    total = sum(int(quotas[name]) for name in GENERATOR_CELLS)
    original, original_schema = _open_meta(original_meta_path, total)
    split, split_schema = _open_meta(split_meta_path, total)
    if original_schema != split_schema:
        raise ValueError("source/split metadata schema drift")

    source_ids = np.empty(total, dtype=np.uint8)
    start = 0
    for cell_id, name in enumerate(GENERATOR_CELLS):
        stop = start + int(quotas[name])
        source_ids[start:stop] = cell_id
        start = stop

    openings = np.asarray(original["opening_id"], dtype=np.uint64)
    unique, inverse = np.unique(openings, return_inverse=True)
    hold_unique = np.fromiter(
        (_opening_is_holdout(int(value), split_seed, holdout_mod) for value in unique),
        dtype=np.bool_,
        count=len(unique),
    )
    hold = hold_unique[inverse]
    order = np.concatenate((np.flatnonzero(~hold), np.flatnonzero(hold)))
    if not np.array_equal(
        np.asarray(split["opening_id"], dtype=np.uint64), openings[order]
    ):
        raise ValueError("split opening order cannot be reproduced")
    if not np.array_equal(
        np.asarray(split["game_id"], dtype=np.uint64),
        np.asarray(original["game_id"], dtype=np.uint64)[order],
    ):
        raise ValueError("split game order cannot be reproduced")
    return source_ids[order]


def _new_accumulator() -> dict[str, Any]:
    width = len(CTX2_BASE_COMPONENTS)
    return {
        "rows": 0,
        "weight_sum": 0.0,
        "base_abs_sum": np.zeros(width, dtype=np.float64),
        "base_local_abs_sum": np.zeros(width, dtype=np.float64),
        "dominant_weight": np.zeros(width, dtype=np.float64),
        "prediction_abs_sum": 0.0,
        "prediction_sq_sum": 0.0,
    }


def _update_accumulator(
    acc: dict[str, Any],
    base_linear: np.ndarray,
    base_local: np.ndarray,
    predictions: np.ndarray,
    weights: np.ndarray,
) -> None:
    if not len(weights):
        return
    acc["rows"] += int(len(weights))
    acc["weight_sum"] += float(weights.sum())
    acc["base_abs_sum"] += np.abs(base_linear).T @ weights
    acc["base_local_abs_sum"] += np.abs(base_local).T @ weights
    acc["dominant_weight"] += np.bincount(
        np.argmax(np.abs(base_linear), axis=1),
        weights=weights,
        minlength=len(CTX2_BASE_COMPONENTS),
    )
    acc["prediction_abs_sum"] += float(np.abs(predictions) @ weights)
    acc["prediction_sq_sum"] += float((predictions * predictions) @ weights)


def _concentration(abs_values: np.ndarray) -> dict[str, float]:
    values = np.asarray(abs_values, dtype=np.float64)
    if values.shape != (len(CTX2_BASE_COMPONENTS),) or np.any(values < 0):
        raise ValueError("invalid base contribution vector")
    total = float(values.sum())
    if not total > 0:
        raise ValueError("zero base contribution vector")
    shares = values / total
    return {
        "largest_share": float(shares.max()),
        "top3_share": float(np.sort(shares)[-3:].sum()),
        "effective_component_count": float(1.0 / np.sum(shares * shares)),
    }


def _finalize_cell(acc: dict[str, Any], source_records: int) -> dict[str, Any]:
    weight = float(acc["weight_sum"])
    if acc["rows"] <= 0 or weight <= 0 or source_records <= 0:
        raise ValueError("empty cell contribution accumulator")
    abs_sum = np.asarray(acc["base_abs_sum"], dtype=np.float64)
    local_abs_sum = np.asarray(acc["base_local_abs_sum"], dtype=np.float64)
    shares = abs_sum / abs_sum.sum()
    local_shares = local_abs_sum / local_abs_sum.sum()
    return {
        "source_records": int(source_records),
        "train_oof_rows": int(acc["rows"]),
        "effective_game_equal_weight_sum": weight,
        "game_equal_weight_per_source_record": weight / source_records,
        "mean_absolute_prediction": acc["prediction_abs_sum"] / weight,
        "rms_prediction": math.sqrt(acc["prediction_sq_sum"] / weight),
        "base_components": [
            {
                "component": name,
                "mean_absolute_logit_contribution": float(abs_sum[index] / weight),
                "absolute_logit_share": float(shares[index]),
                "mean_absolute_alpha_target_probability_effect": float(
                    local_abs_sum[index] / weight
                ),
                "absolute_alpha_target_probability_effect_share": float(
                    local_shares[index]
                ),
                "dominant_position_rate": float(acc["dominant_weight"][index] / weight),
            }
            for index, name in enumerate(CTX2_BASE_COMPONENTS)
        ],
        "base_15_concentration": _concentration(abs_sum),
    }


def replay_cells(
    *,
    split_meta_path: Path,
    feature_path: Path,
    conditional_report_path: Path,
    cell_ids: np.ndarray,
    quotas: dict[str, int],
    chunk_size: int = 20_000,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    report = _load(conditional_report_path)
    if report.get("schema") != "jass.l3_conditional_targets.v2":
        raise ValueError("conditional report schema drift")
    if report.get("context_schema") != "ctx2-phase-tactical-30":
        raise ValueError("conditional context schema drift")
    mapping = report.get("mapping") or {}
    if (
        mapping.get("fold_group") != "opening_id"
        or mapping.get("row_weighting") != "game_equal"
        or not mapping.get("fold_local_rms")
        or not mapping.get("each_game_total_weight_equal")
        or not mapping.get("all_groups_fold_disjoint")
        or int(mapping.get("train_holdout_group_overlap", -1)) != 0
    ):
        raise ValueError("strict mapper contract drift")
    components = tuple(mapping.get("components") or ())
    if components != CTX2_CONTEXT_COMPONENTS:
        raise ValueError("CTX2 component order drift")
    fits = [row["fit"] for row in mapping.get("folds") or []]
    fits.append((mapping.get("final_train_fit") or {}).get("fit") or {})
    if len(fits) != 6 or not all(bool(row.get("converged")) for row in fits):
        raise ValueError("six converged mapper fits required")

    records = int(report.get("records", -1))
    train_count = int(report.get("train_records", -1))
    if records != len(cell_ids) or not 0 < train_count < records:
        raise ValueError("conditional sizing drift")
    metadata, _ = _open_meta(split_meta_path, records)
    features, width = _open_feat(feature_path, records)
    if width != len(CTX2_CONTEXT_COMPONENTS):
        raise ValueError("feature width drift")
    source = report.get("source") or {}
    if source.get("meta_sha256") != _sha256(split_meta_path):
        raise ValueError("split metadata hash drift")
    if source.get("feat_sha256") != _sha256(feature_path):
        raise ValueError("feature hash drift")

    fold_count = int(mapping.get("fold_count", 0))
    fold_seed = int(mapping.get("fold_seed", -1))
    fold_rows = sorted(mapping.get("folds") or [], key=lambda row: int(row["fold"]))
    if fold_count != 5 or [int(row["fold"]) for row in fold_rows] != list(range(5)):
        raise ValueError("fold report drift")
    coefficient_table = np.asarray(
        [row["theta_raw"] for row in fold_rows]
        + [mapping["final_train_fit"]["theta_raw"]],
        dtype=np.float64,
    )
    if coefficient_table.shape != (6, len(CTX2_CONTEXT_COMPONENTS)):
        raise ValueError("coefficient table drift")
    folds = game_folds(
        np.asarray(metadata["opening_id"], dtype=np.uint64), fold_count, fold_seed
    )
    folds[train_count:] = fold_count
    weights = _game_equal_weights(np.asarray(metadata["game_id"], dtype=np.uint64))
    alpha = float((report.get("target") or {}).get("alpha", 0.0))
    if not math.isclose(alpha, 0.30, abs_tol=1e-15):
        raise ValueError("alpha drift")

    accs = {name: _new_accumulator() for name in GENERATOR_CELLS}
    overall = _new_accumulator()
    for start in range(0, train_count, chunk_size):
        stop = min(start + chunk_size, train_count)
        x = np.asarray(features[start:stop], dtype=np.float64)
        theta = coefficient_table[np.asarray(folds[start:stop], dtype=np.int64)]
        linear = x * theta
        logits = linear.sum(axis=1)
        predictions = np.tanh(logits)
        base_linear = linear[:, :15] + linear[:, 15:]
        base_local = 0.5 * alpha * (
            predictions[:, None] - np.tanh(logits[:, None] - base_linear)
        )
        chunk_weights = weights[start:stop]
        _update_accumulator(overall, base_linear, base_local, predictions, chunk_weights)
        chunk_cells = cell_ids[start:stop]
        for cell_id, name in enumerate(GENERATOR_CELLS):
            selection = chunk_cells == cell_id
            _update_accumulator(
                accs[name],
                base_linear[selection],
                base_local[selection],
                predictions[selection],
                chunk_weights[selection],
            )
    cells = {
        name: _finalize_cell(accs[name], int(quotas[name]))
        for name in GENERATOR_CELLS
    }
    return cells, _finalize_cell(overall, sum(int(value) for value in quotas.values()))


def _cell_abs_vector(profile: dict[str, Any]) -> np.ndarray:
    rows = profile.get("base_components") or []
    if [row.get("component") for row in rows] != list(CTX2_BASE_COMPONENTS):
        raise ValueError("cell base component order drift")
    weight = float(profile["effective_game_equal_weight_sum"])
    return np.asarray(
        [float(row["mean_absolute_logit_contribution"]) * weight for row in rows],
        dtype=np.float64,
    )


def _compositions(total: int, lower: int, upper: int, width: int) -> Iterable[tuple[int, ...]]:
    def visit(prefix: tuple[int, ...], remaining: int) -> Iterable[tuple[int, ...]]:
        missing = width - len(prefix)
        if missing == 1:
            if lower <= remaining <= upper:
                yield prefix + (remaining,)
            return
        lo = max(lower, remaining - upper * (missing - 1))
        hi = min(upper, remaining - lower * (missing - 1))
        for value in range(lo, hi + 1):
            yield from visit(prefix + (value,), remaining - value)

    yield from visit((), total)


def _project(
    record_weights: np.ndarray,
    cell_profiles: dict[str, dict[str, Any]],
    cell_wdl: dict[str, dict[str, float]],
) -> dict[str, Any]:
    weight_per_record = np.asarray(
        [
            float(cell_profiles[name]["game_equal_weight_per_source_record"])
            for name in GENERATOR_CELLS
        ]
    )
    effective = record_weights * weight_per_record
    effective /= effective.sum()
    means = np.asarray(
        [
            _cell_abs_vector(cell_profiles[name])
            / float(cell_profiles[name]["effective_game_equal_weight_sum"])
            for name in GENERATOR_CELLS
        ]
    )
    absolute = effective @ means
    concentration = _concentration(absolute)
    wdl_matrix = np.asarray(
        [[float(cell_wdl[name][str(value)]) for value in (-1, 0, 1)] for name in GENERATOR_CELLS]
    )
    wdl = record_weights @ wdl_matrix
    return {
        "record_weights": {
            name: float(value) for name, value in zip(GENERATOR_CELLS, record_weights)
        },
        "projected_game_equal_weights": {
            name: float(value) for name, value in zip(GENERATOR_CELLS, effective)
        },
        "base_component_absolute_logit_shares": {
            name: float(value) for name, value in zip(CTX2_BASE_COMPONENTS, absolute / absolute.sum())
        },
        "base_15_concentration": concentration,
        "wdl_stm_rates": {str(value): float(rate) for value, rate in zip((-1, 0, 1), wdl)},
    }


def analyse(
    *,
    cell_profiles: dict[str, dict[str, Any]],
    reproduced_overall: dict[str, Any],
    intervention_audit: dict[str, Any],
    current_audit: dict[str, Any],
    corpus_summary: dict[str, Any],
    weight_step: float = 0.05,
    minimum_cell_weight: float = 0.05,
    maximum_cell_weight: float = 0.50,
    max_relative_draw_shift: float = 0.15,
    max_wdl_side_skew: float = 0.02,
) -> dict[str, Any]:
    if set(cell_profiles) != set(GENERATOR_CELLS):
        raise ValueError("cell profile set drift")
    for report, label in ((intervention_audit, "intervention"), (current_audit, "CURRENT")):
        if report.get("schema") != "jass.l3_context2_fixed_contribution_audit.v1":
            raise ValueError(f"{label} contribution schema drift")
        if report.get("verdict") != "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY":
            raise ValueError(f"{label} contribution verdict drift")
    observed = intervention_audit["cohorts"]["train_oof"]["base_15_concentration"]
    reproduced = reproduced_overall["base_15_concentration"]
    reproduction_error = max(abs(float(observed[key]) - float(reproduced[key])) for key in observed)
    if reproduction_error > 2e-10:
        raise ValueError(f"overall contribution reproduction drift {reproduction_error}")
    current = current_audit["cohorts"]["train_oof"]["base_15_concentration"]
    thresholds = {
        "maximum_largest_share": 0.90 * float(current["largest_share"]),
        "maximum_top3_share": 0.95 * float(current["top3_share"]),
        "minimum_effective_component_count": 1.25 * float(current["effective_component_count"]),
    }
    quotas = {name: int(corpus_summary["cell_quotas"][name]) for name in GENERATOR_CELLS}
    cell_wdl = {
        name: corpus_summary["cells"][name]["wdl_stm_rates"] for name in GENERATOR_CELLS
    }
    base_draw = float(cell_wdl["BASE"]["0"])

    actual_abs = sum((_cell_abs_vector(cell_profiles[name]) for name in GENERATOR_CELLS), np.zeros(15))
    actual_shares = actual_abs / actual_abs.sum()
    ranked_indices = np.argsort(-actual_shares)
    component_attribution = []
    actual_cell_weight = np.asarray(
        [float(cell_profiles[name]["effective_game_equal_weight_sum"]) for name in GENERATOR_CELLS]
    )
    actual_cell_weight /= actual_cell_weight.sum()
    for index in ranked_indices:
        contributions = np.asarray(
            [_cell_abs_vector(cell_profiles[name])[index] for name in GENERATOR_CELLS]
        )
        cell_fraction = contributions / contributions.sum()
        component_attribution.append({
            "component": CTX2_BASE_COMPONENTS[int(index)],
            "absolute_logit_share": float(actual_shares[index]),
            "cell_fraction_of_component": {
                name: float(value) for name, value in zip(GENERATOR_CELLS, cell_fraction)
            },
            "cell_enrichment_vs_game_equal_weight": {
                name: float(value / weight) if weight > 0 else None
                for name, value, weight in zip(GENERATOR_CELLS, cell_fraction, actual_cell_weight)
            },
        })

    base_metrics = cell_profiles["BASE"]["base_15_concentration"]
    knob_effects = []
    for name in GENERATOR_CELLS[1:]:
        metrics = cell_profiles[name]["base_15_concentration"]
        knob_effects.append({
            "cell": name,
            "single_factor_knob": CELL_KNOBS[name],
            "largest_share_delta_vs_BASE": float(metrics["largest_share"] - base_metrics["largest_share"]),
            "top3_share_delta_vs_BASE": float(metrics["top3_share"] - base_metrics["top3_share"]),
            "effective_component_count_delta_vs_BASE": float(
                metrics["effective_component_count"] - base_metrics["effective_component_count"]
            ),
            "base_15_concentration": metrics,
        })
    knob_effects.sort(
        key=lambda row: (
            row["largest_share_delta_vs_BASE"],
            row["top3_share_delta_vs_BASE"],
            -row["effective_component_count_delta_vs_BASE"],
        )
    )

    leave_one_out = []
    for omitted in GENERATOR_CELLS:
        vector = sum(
            (_cell_abs_vector(cell_profiles[name]) for name in GENERATOR_CELLS if name != omitted),
            np.zeros(15),
        )
        metrics = _concentration(vector)
        leave_one_out.append({
            "omitted_cell": omitted,
            "largest_share_delta_vs_observed": metrics["largest_share"] - observed["largest_share"],
            "top3_share_delta_vs_observed": metrics["top3_share"] - observed["top3_share"],
            "effective_component_count_delta_vs_observed": (
                metrics["effective_component_count"] - observed["effective_component_count"]
            ),
            "base_15_concentration": metrics,
        })
    leave_one_out.sort(
        key=lambda row: (
            row["largest_share_delta_vs_observed"],
            row["top3_share_delta_vs_observed"],
            -row["effective_component_count_delta_vs_observed"],
        )
    )

    reciprocal = round(1.0 / weight_step)
    if not math.isclose(reciprocal * weight_step, 1.0, abs_tol=1e-12):
        raise ValueError("weight step must divide one")
    lower = math.ceil(minimum_cell_weight / weight_step - 1e-12)
    upper = math.floor(maximum_cell_weight / weight_step + 1e-12)
    candidates = []
    rejected_distribution = 0
    passed = []
    for units in _compositions(reciprocal, lower, upper, len(GENERATOR_CELLS)):
        weights = np.asarray(units, dtype=np.float64) * weight_step
        projection = _project(weights, cell_profiles, cell_wdl)
        wdl = projection["wdl_stm_rates"]
        draw_shift = abs(float(wdl["0"]) - base_draw) / base_draw if base_draw else math.inf
        skew = abs(float(wdl["1"]) - float(wdl["-1"]))
        if draw_shift > max_relative_draw_shift + 1e-12 or skew > max_wdl_side_skew + 1e-12:
            rejected_distribution += 1
            continue
        metrics = projection["base_15_concentration"]
        guards = {
            "largest_share_at_most_90pct_current": metrics["largest_share"] <= thresholds["maximum_largest_share"],
            "top3_share_at_most_95pct_current": metrics["top3_share"] <= thresholds["maximum_top3_share"],
            "effective_count_at_least_125pct_current": metrics["effective_component_count"] >= thresholds["minimum_effective_component_count"],
        }
        ratios = {
            "largest_share_to_gate": metrics["largest_share"] / thresholds["maximum_largest_share"],
            "top3_share_to_gate": metrics["top3_share"] / thresholds["maximum_top3_share"],
            "effective_gate_to_count": thresholds["minimum_effective_component_count"] / metrics["effective_component_count"],
        }
        projection.update({
            "relative_draw_shift_vs_BASE": draw_shift,
            "wdl_side_skew": skew,
            "guards": guards,
            "worst_normalized_gate_ratio": max(ratios.values()),
            "normalized_gate_ratios": ratios,
        })
        candidates.append(projection)
        if all(guards.values()):
            passed.append(projection)
    if not candidates:
        raise ValueError("no WDL-admissible quota candidate")
    candidates.sort(
        key=lambda row: (
            row["worst_normalized_gate_ratio"],
            row["normalized_gate_ratios"]["largest_share_to_gate"],
            row["normalized_gate_ratios"]["top3_share_to_gate"],
            tuple(row["record_weights"][name] for name in GENERATOR_CELLS),
        )
    )
    best = candidates[0]
    quota_rescue = bool(passed)
    top = component_attribution[0]
    weakest = sorted(component_attribution, key=lambda row: row["absolute_logit_share"])[:5]
    return {
        "schema": "jass.l3_context2_intervention_contribution_autopsy.v1",
        "verdict": "JASS_CONTEXT2_INTERVENTION_CONTRIBUTION_AUTOPSY_READY",
        "overall_reproduction": {
            "maximum_concentration_absolute_error": reproduction_error,
            "observed": observed,
            "replayed": reproduced,
        },
        "dominant_component": top,
        "five_weakest_components": weakest,
        "component_attribution": component_attribution,
        "cell_profiles": cell_profiles,
        "single_factor_knob_effects_ranked": knob_effects,
        "leave_one_cell_out_ranked": leave_one_out,
        "fixed_mapper_quota_lattice": {
            "weight_step": weight_step,
            "minimum_each_cell_weight": minimum_cell_weight,
            "maximum_each_cell_weight": maximum_cell_weight,
            "wdl_admissible_candidates": len(candidates),
            "distribution_rejected_candidates": rejected_distribution,
            "full_gate_candidates": len(passed),
            "thresholds": thresholds,
            "best_candidate": best,
            "quota_only_rescue_predicted": quota_rescue,
        },
        "mechanism": {
            "activation_covariance_improvement_preserved": True,
            "conditional_contribution_spread_improved": False,
            "diagnosis": (
                "quota_only_rescue_exists_under_fixed_mapper"
                if quota_rescue
                else "existing_generation_knobs_do_not_span_the_required_conditional_contribution_directions"
            ),
            "next_design_axis": (
                "generate_and_remap_the_best_preregistered_quota_candidate"
                if quota_rescue
                else "contribution_balanced_pilot_with_new_state_targeting_cells"
            ),
            "dominant_component_to_deconcentrate": top["component"],
            "components_to_enrich": [row["component"] for row in weakest],
        },
        "protocol": {
            "mapper_refit": False,
            "patterneval_fit": False,
            "force_games_played": 0,
            "new_selfplay_generated": False,
            "frozen_read": False,
            "promotion_authorized": False,
            "automatic_next_job": None,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-meta", type=Path, required=True)
    parser.add_argument("--split-meta", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--conditional-report", type=Path, required=True)
    parser.add_argument("--intervention-audit", type=Path, required=True)
    parser.add_argument("--current-audit", type=Path, required=True)
    parser.add_argument("--corpus-summary", type=Path, required=True)
    parser.add_argument("--split-seed", type=int, default=577215)
    parser.add_argument("--holdout-mod", type=int, default=10)
    parser.add_argument("--chunk-size", type=int, default=20_000)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    corpus = _load(args.corpus_summary)
    if corpus.get("schema") != "jass.l3_context2_intervention_corpus.v1":
        raise ValueError("corpus summary schema drift")
    quotas = {name: int(corpus["cell_quotas"][name]) for name in GENERATOR_CELLS}
    cell_ids = recover_split_cell_ids(
        original_meta_path=args.original_meta,
        split_meta_path=args.split_meta,
        quotas=quotas,
        split_seed=args.split_seed,
        holdout_mod=args.holdout_mod,
    )
    profiles, overall = replay_cells(
        split_meta_path=args.split_meta,
        feature_path=args.features,
        conditional_report_path=args.conditional_report,
        cell_ids=cell_ids,
        quotas=quotas,
        chunk_size=args.chunk_size,
    )
    payload = analyse(
        cell_profiles=profiles,
        reproduced_overall=overall,
        intervention_audit=_load(args.intervention_audit),
        current_audit=_load(args.current_audit),
        corpus_summary=corpus,
    )
    payload["source"] = {
        "original_meta_sha256": _sha256(args.original_meta),
        "split_meta_sha256": _sha256(args.split_meta),
        "features_sha256": _sha256(args.features),
        "conditional_report_sha256": _sha256(args.conditional_report),
        "intervention_audit_sha256": _sha256(args.intervention_audit),
        "current_audit_sha256": _sha256(args.current_audit),
        "corpus_summary_sha256": _sha256(args.corpus_summary),
        "split_seed": args.split_seed,
        "holdout_mod": args.holdout_mod,
    }
    if args.out.exists():
        raise ValueError(f"{args.out}: output exists (no-clobber)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
