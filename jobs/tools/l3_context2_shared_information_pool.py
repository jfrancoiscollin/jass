#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Select one deterministic, shared, information-balanced CTX2 seed pool.

This is the deliberately less constrained successor to the infeasible 1414
six-pool construction.  It keeps the causal hygiene that matters (one source,
zeroed labels, canonical de-duplication, at most two states per source game and
an exact phase/WDL/material quota), but does not partition openings between six
competing pools.  The fixed certified mapper is replayed without refit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any

import numpy as np

try:
    from l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _game_equal_weights,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        _splitmix64,
        game_folds,
    )
    from l3_context2_contribution_seed_miner import (
        TARGET_COMPONENTS,
        _strata,
        allocate_capped_proportional,
        canonical_position,
        zero_targets,
    )
except ModuleNotFoundError:
    from jobs.tools.l3_conditional_targets import (
        CTX2_BASE_COMPONENTS,
        CTX2_CONTEXT_COMPONENTS,
        JNNW_DTYPE,
        _game_equal_weights,
        _open_counted,
        _open_feat,
        _open_meta,
        _sha256,
        _splitmix64,
        game_folds,
    )
    from jobs.tools.l3_context2_contribution_seed_miner import (
        TARGET_COMPONENTS,
        _strata,
        allocate_capped_proportional,
        canonical_position,
        zero_targets,
    )


HEADER = struct.Struct("<4sI")
WEAK_INDICES = np.asarray(
    [CTX2_BASE_COMPONENTS.index(name) for name in TARGET_COMPONENTS], dtype=np.int64
)
LEVERAGE_WEIGHTS = (0.00, 0.10, 0.25, 0.50, 0.75, 1.00, 0.50, 0.25)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _mapper_table(
    report: dict[str, Any], metadata: np.ndarray
) -> tuple[np.ndarray, np.ndarray, int]:
    if report.get("schema") != "jass.l3_conditional_targets.v2":
        raise ValueError("conditional mapper schema drift")
    if report.get("context_schema") != "ctx2-phase-tactical-30":
        raise ValueError("conditional context schema drift")
    mapping = report.get("mapping") or {}
    if tuple(mapping.get("components") or ()) != CTX2_CONTEXT_COMPONENTS:
        raise ValueError("conditional component order drift")
    if (
        mapping.get("fold_group") != "opening_id"
        or mapping.get("row_weighting") != "game_equal"
        or not mapping.get("fold_local_rms")
        or not mapping.get("all_groups_fold_disjoint")
    ):
        raise ValueError("conditional mapper contract drift")
    train_count = int(report.get("train_records", -1))
    if report.get("records") != len(metadata) or not 0 < train_count < len(metadata):
        raise ValueError("conditional mapper sizing drift")
    fold_count = int(mapping.get("fold_count", 0))
    fold_seed = int(mapping.get("fold_seed", -1))
    fold_rows = sorted(mapping.get("folds") or [], key=lambda row: int(row["fold"]))
    if fold_count != 5 or [int(row["fold"]) for row in fold_rows] != list(range(5)):
        raise ValueError("conditional mapper fold drift")
    fits = [row["fit"] for row in fold_rows] + [mapping["final_train_fit"]["fit"]]
    if not all(bool(row.get("converged")) for row in fits):
        raise ValueError("all mapper fits must have converged")
    theta = np.asarray(
        [row["theta_raw"] for row in fold_rows]
        + [mapping["final_train_fit"]["theta_raw"]],
        dtype=np.float64,
    )
    if theta.shape != (6, len(CTX2_CONTEXT_COMPONENTS)) or not np.all(np.isfinite(theta)):
        raise ValueError("mapper coefficient table drift")
    folds = game_folds(
        np.asarray(metadata["opening_id"], dtype=np.uint64), fold_count, fold_seed
    )
    folds[train_count:] = fold_count
    return theta, folds, train_count


def mapper_base_contributions(
    *,
    metadata: np.ndarray,
    features: np.ndarray,
    report: dict[str, Any],
    chunk_size: int = 100_000,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Replay signed base-15 contributions and retain train OOF rows only."""
    theta, folds, train_count = _mapper_table(report, metadata)
    signed = np.empty((train_count, len(CTX2_BASE_COMPONENTS)), dtype=np.float32)
    for start in range(0, train_count, chunk_size):
        stop = min(start + chunk_size, train_count)
        x = np.asarray(features[start:stop], dtype=np.float64)
        linear = x * theta[np.asarray(folds[start:stop], dtype=np.int64)]
        signed[start:stop] = linear[:, :15] + linear[:, 15:]
    return signed, folds[:train_count], train_count


def concentration(absolute_sums: np.ndarray) -> dict[str, Any]:
    values = np.asarray(absolute_sums, dtype=np.float64)
    if values.shape != (len(CTX2_BASE_COMPONENTS),) or np.any(values < 0):
        raise ValueError("invalid base contribution vector")
    total = float(values.sum())
    if total <= 0:
        raise ValueError("zero base contribution mass")
    shares = values / total
    order = np.argsort(-shares)
    return {
        "largest_share": float(shares[order[0]]),
        "top3_share": float(shares[order[:3]].sum()),
        "effective_component_count": float(1.0 / np.sum(shares * shares)),
        "component_shares": {
            CTX2_BASE_COMPONENTS[int(index)]: float(shares[index]) for index in order
        },
    }


def gate_ratios(metrics: dict[str, Any], thresholds: dict[str, float]) -> dict[str, float]:
    ratios = {
        "largest_share_to_maximum": metrics["largest_share"] / thresholds["maximum_largest_share"],
        "top3_share_to_maximum": metrics["top3_share"] / thresholds["maximum_top3_share"],
        "minimum_effective_to_count": thresholds["minimum_effective_component_count"]
        / metrics["effective_component_count"],
    }
    ratios["worst"] = max(ratios.values())
    return ratios


def _current_thresholds(current_audit: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    if current_audit.get("schema") != "jass.l3_context2_fixed_contribution_audit.v1":
        raise ValueError("CURRENT audit schema drift")
    if current_audit.get("verdict") != "JASS_CONTEXT2_FIXED_CONTRIBUTION_AUDIT_READY":
        raise ValueError("CURRENT audit verdict drift")
    current = current_audit["cohorts"]["train_oof"]["base_15_concentration"]
    reference = {
        "largest_share": float(current["largest_share"]),
        "top3_share": float(current["top3_share"]),
        "effective_component_count": float(current["effective_component_count"]),
    }
    thresholds = {
        "maximum_largest_share": 0.90 * reference["largest_share"],
        "maximum_top3_share": 0.95 * reference["top3_share"],
        "minimum_effective_component_count": 1.25 * reference["effective_component_count"],
    }
    return reference, thresholds


def _weighted_feature_moments(
    features: np.ndarray,
    weights: np.ndarray,
    indices: np.ndarray,
    *,
    chunk_size: int = 100_000,
) -> tuple[np.ndarray, np.ndarray]:
    width = features.shape[1]
    total_weight = 0.0
    total = np.zeros(width, dtype=np.float64)
    cross = np.zeros((width, width), dtype=np.float64)
    for start in range(0, len(indices), chunk_size):
        rows = indices[start : start + chunk_size]
        x = np.asarray(features[rows], dtype=np.float64)
        w = np.asarray(weights[rows], dtype=np.float64)
        total_weight += float(w.sum())
        total += x.T @ w
        cross += x.T @ (x * w[:, None])
    if total_weight <= 0:
        raise ValueError("zero feature weight")
    mean = total / total_weight
    covariance = cross / total_weight - np.outer(mean, mean)
    covariance = 0.5 * (covariance + covariance.T)
    return mean, covariance


def covariance_metrics(covariance: np.ndarray, ridge: float = 1e-6) -> dict[str, float]:
    variance = np.maximum(np.diag(covariance), 0.0)
    scale = np.sqrt(np.where(variance > 1e-18, variance, 1.0))
    correlation = covariance / np.outer(scale, scale)
    correlation = 0.5 * (correlation + correlation.T)
    np.fill_diagonal(correlation, np.where(variance > 1e-18, 1.0, 0.0))
    eig = np.maximum(np.linalg.eigvalsh(correlation), 0.0)
    regularized = eig + ridge
    off = correlation - np.diag(np.diag(correlation))
    return {
        "logdet_correlation_ridge_1e_6": float(np.log(regularized).sum()),
        "effective_covariance_dimension": float(eig.sum() ** 2 / np.sum(eig * eig)),
        "maximum_absolute_offdiagonal_correlation": float(np.max(np.abs(off))),
    }


def leverage_scores(
    features: np.ndarray,
    weights: np.ndarray,
    train_count: int,
    *,
    chunk_size: int = 100_000,
) -> tuple[np.ndarray, dict[str, float], np.ndarray, np.ndarray]:
    indices = np.arange(train_count, dtype=np.int64)
    mean, covariance = _weighted_feature_moments(features, weights, indices, chunk_size=chunk_size)
    scale = np.sqrt(np.maximum(np.diag(covariance), 1e-12))
    correlation = covariance / np.outer(scale, scale)
    correlation = 0.5 * (correlation + correlation.T)
    inverse = np.linalg.pinv(correlation + 1e-5 * np.eye(correlation.shape[0]))
    result = np.empty(train_count, dtype=np.float32)
    for start in range(0, train_count, chunk_size):
        stop = min(start + chunk_size, train_count)
        z = (np.asarray(features[start:stop], dtype=np.float64) - mean) / scale
        result[start:stop] = np.einsum("ij,jk,ik->i", z, inverse, z, optimize=True)
    normalizer = max(float(np.median(result)), 1e-12)
    result /= normalizer
    cap = float(np.quantile(result, 0.995))
    np.minimum(result, cap, out=result)
    return result, covariance_metrics(covariance), mean, scale


def _scaled_contributions(signed: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    absolute = np.abs(np.asarray(signed, dtype=np.float32))
    base_scale = np.maximum(np.quantile(absolute, 0.90, axis=0), 1e-8)
    base = np.minimum(absolute / base_scale, 4.0).astype(np.float32)
    directional = np.zeros((len(signed), len(TARGET_COMPONENTS) * 2), dtype=np.float32)
    for component, base_index in enumerate(WEAK_INDICES):
        values = absolute[:, base_index]
        signs = signed[:, base_index]
        for sign_index, mask in enumerate((signs < 0, signs > 0)):
            scale = max(float(np.mean(values[mask])) if np.any(mask) else 0.0, 1e-8)
            directional[mask, component * 2 + sign_index] = np.minimum(
                values[mask] / scale, 4.0
            )
    return base, directional


def _ranked_window(
    candidates: np.ndarray,
    utility: np.ndarray,
    hashes: np.ndarray,
    target: int,
) -> np.ndarray:
    if target <= 0:
        return np.empty(0, dtype=np.int64)
    width = min(len(candidates), max(target * 8, target + 2048))
    if width < len(candidates):
        local = utility[candidates]
        selected = candidates[np.argpartition(local, len(local) - width)[-width:]]
    else:
        selected = candidates
    order = np.lexsort((selected, hashes[selected], -utility[selected]))
    return selected[order]


def select_with_guards(
    *,
    records: np.ndarray,
    metadata: np.ndarray,
    strata: np.ndarray,
    quotas: np.ndarray,
    utility: np.ndarray,
    seed: int,
    max_per_game: int = 2,
) -> np.ndarray:
    hashes = _splitmix64(np.arange(len(records), dtype=np.uint64) ^ np.uint64(seed))
    used: set[bytes] = set()
    game_counts: Counter[int] = Counter()
    selected: list[int] = []
    # Serve the tightest strata first.  A single shared pool leaves ample slack;
    # the full-stratum fallback below is nevertheless deterministic and exact.
    rows_by_stratum = [np.flatnonzero(strata == value) for value in range(60)]
    order = sorted(
        range(60),
        key=lambda value: (
            -(int(quotas[value]) / max(len(rows_by_stratum[value]), 1)),
            value,
        ),
    )
    canonical_cache: dict[int, bytes] = {}
    for stratum in order:
        required = int(quotas[stratum])
        if not required:
            continue
        candidates = rows_by_stratum[stratum]
        ranked = _ranked_window(candidates, utility, hashes, required)
        chosen: list[int] = []

        def visit(rows: np.ndarray) -> None:
            for raw_index in rows:
                if len(chosen) == required:
                    return
                index = int(raw_index)
                game = int(metadata["game_id"][index])
                if game_counts[game] >= max_per_game:
                    continue
                canonical = canonical_cache.get(index)
                if canonical is None:
                    canonical = canonical_position(records[index].tobytes())
                    canonical_cache[index] = canonical
                if canonical in used:
                    continue
                used.add(canonical)
                game_counts[game] += 1
                chosen.append(index)

        visit(ranked)
        if len(chosen) < required and len(ranked) < len(candidates):
            ranked_set = set(map(int, ranked))
            remainder = np.asarray(
                [int(index) for index in candidates if int(index) not in ranked_set],
                dtype=np.int64,
            )
            remainder = remainder[
                np.lexsort((remainder, hashes[remainder], -utility[remainder]))
            ]
            visit(remainder)
        if len(chosen) != required:
            raise ValueError(
                f"shared pool guard capacity shortfall stratum={stratum} "
                f"selected={len(chosen)} required={required}"
            )
        selected.extend(chosen)
    if len(selected) != int(quotas.sum()):
        raise ValueError("shared pool exact size drift")
    return np.asarray(selected, dtype=np.int64)


def _selected_metrics(
    signed: np.ndarray,
    source_weights: np.ndarray,
    selected: np.ndarray,
    thresholds: dict[str, float],
) -> tuple[dict[str, Any], dict[str, float], np.ndarray]:
    absolute_sums = np.abs(signed[selected]).T @ source_weights[selected]
    metrics = concentration(absolute_sums)
    return metrics, gate_ratios(metrics, thresholds), absolute_sums


def _distribution_report(
    records: np.ndarray,
    strata: np.ndarray,
    selected: np.ndarray,
) -> dict[str, Any]:
    source_counts = np.bincount(strata, minlength=60).astype(np.float64)
    selected_counts = np.bincount(strata[selected], minlength=60).astype(np.float64)
    source_rates = source_counts / source_counts.sum()
    selected_rates = selected_counts / selected_counts.sum()
    source_wdl = {str(value): float(np.mean(records["wdl"] == value)) for value in (-1, 0, 1)}
    selected_wdl = {
        str(value): float(np.mean(records["wdl"][selected] == value)) for value in (-1, 0, 1)
    }
    draw_shift = (
        abs(selected_wdl["0"] - source_wdl["0"]) / source_wdl["0"]
        if source_wdl["0"]
        else math.inf
    )
    return {
        "stratum_total_variation": float(0.5 * np.abs(selected_rates - source_rates).sum()),
        "source_wdl_rates": source_wdl,
        "selected_wdl_rates": selected_wdl,
        "selected_wdl_side_skew": abs(selected_wdl["1"] - selected_wdl["-1"]),
        "relative_draw_shift_vs_source": draw_shift,
        "selected_stratum_counts": {
            str(index): int(value) for index, value in enumerate(selected_counts) if value
        },
    }


def stratified_null_screen(
    *,
    signed: np.ndarray,
    source_weights: np.ndarray,
    strata: np.ndarray,
    quotas: np.ndarray,
    thresholds: dict[str, float],
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    if replicates <= 0:
        raise ValueError("null replicate count must be positive")
    rng = np.random.default_rng(seed)
    groups = [np.flatnonzero(strata == value) for value in range(60)]
    weighted = np.abs(signed) * source_weights[:, None]
    worst = np.empty(replicates, dtype=np.float64)
    top1 = np.empty(replicates, dtype=np.float64)
    top3 = np.empty(replicates, dtype=np.float64)
    effective = np.empty(replicates, dtype=np.float64)
    for replicate in range(replicates):
        total = np.zeros(len(CTX2_BASE_COMPONENTS), dtype=np.float64)
        for stratum, count in enumerate(quotas):
            if count:
                donors = rng.choice(groups[stratum], size=int(count), replace=False)
                total += weighted[donors].sum(axis=0)
        metrics = concentration(total)
        ratios = gate_ratios(metrics, thresholds)
        worst[replicate] = ratios["worst"]
        top1[replicate] = metrics["largest_share"]
        top3[replicate] = metrics["top3_share"]
        effective[replicate] = metrics["effective_component_count"]
    return {
        "replicates": replicates,
        "seed": seed,
        "method": "exact_without_replacement_within_phase_wdl_material_stratum",
        "worst_gate_ratio_quantiles": {
            str(q): float(np.quantile(worst, q)) for q in (0.01, 0.025, 0.05, 0.5, 0.95)
        },
        "largest_share_quantiles": {
            str(q): float(np.quantile(top1, q)) for q in (0.025, 0.5, 0.975)
        },
        "top3_share_quantiles": {
            str(q): float(np.quantile(top3, q)) for q in (0.025, 0.5, 0.975)
        },
        "effective_component_count_quantiles": {
            str(q): float(np.quantile(effective, q)) for q in (0.025, 0.5, 0.975)
        },
        "_worst": worst,
    }


def _write_pool(path: Path, records: np.ndarray, indices: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("wb") as handle:
        header = HEADER.pack(b"JNNW", len(indices))
        handle.write(header)
        digest.update(header)
        for index in indices:
            row = zero_targets(records[int(index)].tobytes())
            handle.write(row)
            digest.update(row)
    return digest.hexdigest()


def build(args: argparse.Namespace) -> dict[str, Any]:
    paths = {
        "data": Path(args.data),
        "meta": Path(args.meta),
        "features": Path(args.features),
        "conditional": Path(args.conditional_report),
        "current": Path(args.current_audit),
        "output": Path(args.output),
        "manifest": Path(args.manifest),
    }
    if paths["output"].exists() or paths["manifest"].exists():
        raise ValueError("outputs are no-clobber")
    if args.pool_size <= 0:
        raise ValueError("pool size must be positive")
    conditional = _load(paths["conditional"])
    current_audit = _load(paths["current"])
    records = _open_counted(paths["data"], b"JNNW", JNNW_DTYPE)
    metadata, meta_schema = _open_meta(paths["meta"], len(records))
    features, width = _open_feat(paths["features"], len(records))
    if meta_schema != "JSM2" or width != len(CTX2_CONTEXT_COMPONENTS):
        raise ValueError("source schema drift")
    source = conditional.get("source") or {}
    for name in ("data", "meta", "feat"):
        path = paths["features" if name == "feat" else name]
        if source.get(f"{name}_sha256") != _sha256(path):
            raise ValueError(f"conditional source {name} hash drift")

    signed, _folds, train_count = mapper_base_contributions(
        metadata=metadata, features=features, report=conditional
    )
    train_records = records[:train_count]
    train_metadata = metadata[:train_count]
    train_features = features[:train_count]
    source_weights = _game_equal_weights(
        np.asarray(train_metadata["game_id"], dtype=np.uint64)
    )
    strata, stratum_definition = _strata(train_records)
    capacities = np.bincount(strata, minlength=60).astype(np.int64)
    quotas = allocate_capped_proportional(capacities, capacities, args.pool_size)
    reference, thresholds = _current_thresholds(current_audit)
    base_scaled, directional = _scaled_contributions(signed)
    leverage, source_covariance, feature_mean, feature_scale = leverage_scores(
        train_features, source_weights, train_count
    )

    source_metrics = concentration(np.abs(signed).T @ source_weights)
    base_weights = np.clip(
        (1.0 / len(CTX2_BASE_COMPONENTS))
        / np.asarray(
            [source_metrics["component_shares"][name] for name in CTX2_BASE_COMPONENTS]
        ),
        0.15,
        8.0,
    )
    direction_weights = np.ones(directional.shape[1], dtype=np.float64)
    iterations: list[dict[str, Any]] = []
    selections: list[np.ndarray] = []
    for iteration, leverage_weight in enumerate(LEVERAGE_WEIGHTS):
        utility = (
            base_scaled @ base_weights
            + 0.50 * (directional @ direction_weights)
            + leverage_weight * leverage
        ).astype(np.float64)
        selected = select_with_guards(
            records=train_records,
            metadata=train_metadata,
            strata=strata,
            quotas=quotas,
            utility=utility,
            seed=args.seed + iteration * 1009,
        )
        metrics, ratios, _sums = _selected_metrics(
            signed, source_weights, selected, thresholds
        )
        selected_mean, selected_cov = _weighted_feature_moments(
            train_features, source_weights, selected
        )
        cov = covariance_metrics(selected_cov)
        direction_totals = directional[selected].T @ source_weights[selected]
        nonzero = direction_totals[direction_totals > 0]
        direction_cv = float(np.std(nonzero) / np.mean(nonzero)) if len(nonzero) else math.inf
        iterations.append({
            "iteration": iteration,
            "leverage_weight": leverage_weight,
            "concentration": metrics,
            "gate_ratios": ratios,
            "direction_coefficient_of_variation": direction_cv,
            "context_covariance": cov,
            "context_mean_shift_l2_source_std": float(
                np.linalg.norm((selected_mean - feature_mean) / feature_scale)
            ),
        })
        selections.append(selected)
        shares = np.asarray(
            [metrics["component_shares"][name] for name in CTX2_BASE_COMPONENTS]
        )
        base_weights = np.clip((1.0 / len(shares)) / np.maximum(shares, 1e-12), 0.15, 8.0)
        normalized_direction = direction_totals / max(float(np.mean(direction_totals)), 1e-12)
        direction_weights = np.clip(1.0 / np.maximum(normalized_direction, 1e-6), 0.20, 5.0)

    def iteration_key(row: dict[str, Any]) -> tuple[int, float, float, float, int]:
        context = row["context_covariance"]
        logdet_deficit = max(
            source_covariance["logdet_correlation_ridge_1e_6"]
            - context["logdet_correlation_ridge_1e_6"], 0.0
        )
        effective_deficit = max(
            source_covariance["effective_covariance_dimension"]
            - context["effective_covariance_dimension"], 0.0
        )
        failed_screen_parts = sum((
            row["gate_ratios"]["worst"] > 1.0,
            logdet_deficit > 0.0,
            effective_deficit > 0.0,
        ))
        return (
            failed_screen_parts,
            row["gate_ratios"]["worst"],
            logdet_deficit + effective_deficit,
            row["direction_coefficient_of_variation"],
            row["iteration"],
        )

    chosen_row = min(iterations, key=iteration_key)
    chosen_iteration = int(chosen_row["iteration"])
    selected = selections[chosen_iteration]
    # Stable but mixed output order, independent of optimization traversal.
    output_hashes = _splitmix64(selected.astype(np.uint64) ^ np.uint64(args.seed ^ 0x534841524544))
    selected = selected[np.argsort(output_hashes, kind="stable")]
    selected_metrics, selected_ratios, _selected_sums = _selected_metrics(
        signed, source_weights, selected, thresholds
    )
    distribution = _distribution_report(train_records, strata, selected)
    null = stratified_null_screen(
        signed=signed,
        source_weights=source_weights,
        strata=strata,
        quotas=quotas,
        thresholds=thresholds,
        replicates=args.shuffles,
        seed=args.shuffle_seed,
    )
    null_worst = null.pop("_worst")
    superiority = float((1 + np.sum(null_worst > selected_ratios["worst"])) / (args.shuffles + 1))
    selected_cov = chosen_row["context_covariance"]
    guards = {
        "exact_pool_size": len(selected) == args.pool_size,
        "canonical_duplicates_zero": len({canonical_position(train_records[int(i)].tobytes()) for i in selected}) == len(selected),
        "maximum_two_positions_per_source_game": max(Counter(map(int, train_metadata["game_id"][selected])).values()) <= 2,
        "stratum_total_variation_at_most_0_03": distribution["stratum_total_variation"] <= 0.03,
        "wdl_side_skew_at_most_0_02": distribution["selected_wdl_side_skew"] <= 0.02,
        "relative_draw_shift_at_most_0_15": distribution["relative_draw_shift_vs_source"] <= 0.15,
        "largest_share_at_most_90pct_current": selected_metrics["largest_share"] <= thresholds["maximum_largest_share"],
        "top3_share_at_most_95pct_current": selected_metrics["top3_share"] <= thresholds["maximum_top3_share"],
        "effective_count_at_least_125pct_current": selected_metrics["effective_component_count"] >= thresholds["minimum_effective_component_count"],
        "context_logdet_strictly_above_source": selected_cov["logdet_correlation_ridge_1e_6"] > source_covariance["logdet_correlation_ridge_1e_6"],
        "context_effective_dimension_at_least_source": selected_cov["effective_covariance_dimension"] >= source_covariance["effective_covariance_dimension"],
        "aligned_beats_10000_stratified_shuffles_p_ge_0_975": args.shuffles >= 10_000 and superiority >= 0.975,
    }
    passed = all(guards.values())
    digest = _write_pool(paths["output"], train_records, selected)
    payload = {
        "schema": "jass.l3_context2_shared_information_pool.v1",
        "verdict": (
            "JASS_CONTEXT2_SHARED_INFORMATION_POOL_SCREEN_PASSED"
            if passed
            else "JASS_CONTEXT2_SHARED_INFORMATION_POOL_SCREEN_FAILED"
        ),
        "screen_passed": passed,
        "protocol": {
            "single_shared_pool": True,
            "pool_size": args.pool_size,
            "seed": args.seed,
            "shuffle_seed": args.shuffle_seed,
            "stratified_shuffles": args.shuffles,
            "fixed_mapper_replayed_without_refit": True,
            "train_oof_rows_only": True,
            "target_components": list(TARGET_COMPONENTS),
            "hard_guards": ["canonical_unique", "max_two_positions_per_source_game", "zero_targets"],
            "distribution_control": "phase_x_wdl_x_material_source_proportional_quota",
            "mapper_fit": False,
            "patterneval_fit": False,
            "selfplay_generated": False,
            "force_games_played": 0,
            "frozen_read": False,
            "promotion_authorized": False,
        },
        "source": {
            "records": len(records),
            "train_records": train_count,
            "data_sha256": _sha256(paths["data"]),
            "meta_sha256": _sha256(paths["meta"]),
            "feat_sha256": _sha256(paths["features"]),
            "conditional_report_sha256": _sha256(paths["conditional"]),
            "current_audit_sha256": _sha256(paths["current"]),
        },
        "output": {
            "file": paths["output"].name,
            "records": len(selected),
            "sha256": digest,
            "source_index_sha256": hashlib.sha256(selected.astype("<u8").tobytes()).hexdigest(),
            "unique_games": len(set(map(int, train_metadata["game_id"][selected]))),
            "unique_openings": len(set(map(int, train_metadata["opening_id"][selected]))),
            "targets_zeroed": True,
        },
        "stratum_definition": stratum_definition,
        "distribution": distribution,
        "current_reference": reference,
        "thresholds": thresholds,
        "source_concentration": source_metrics,
        "selected_concentration": selected_metrics,
        "selected_gate_ratios": selected_ratios,
        "source_context_covariance": source_covariance,
        "selected_context_covariance": selected_cov,
        "iterations": iterations,
        "selected_iteration": chosen_iteration,
        "stratified_null": null,
        "aligned_superiority_probability": superiority,
        "guards": guards,
        "next_stage_authorized": passed,
        "next_required_stage": (
            "generate 600k shared-pool self-play positions then fit aligned-vs-shuffled"
            if passed
            else "close CTX2 corpus engineering and revisit mapper/context representation"
        ),
    }
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)
    paths["manifest"].write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--meta", required=True)
    parser.add_argument("--features", required=True)
    parser.add_argument("--conditional-report", required=True)
    parser.add_argument("--current-audit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pool-size", type=int, default=24_576)
    parser.add_argument("--seed", type=int, default=2026081901)
    parser.add_argument("--shuffles", type=int, default=10_000)
    parser.add_argument("--shuffle-seed", type=int, default=2026081902)
    args = parser.parse_args(argv)
    payload = build(args)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
