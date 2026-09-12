#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mechanistic screen for learning move decisions instead of scalar value.

The frozen CURRICULUM search first nominates its top two legal moves at a
shallow/common choice depth.  A deeper CURRICULUM search supplies a direct
pairwise target: the centipawn delta of top2 versus top1.  A small ridge ranker
is cross-fitted out of fold on child-context feature differences and may only
recommend top2 inside the preregistered uncertainty band.

The primary causal control cyclically permutes the *same OOF ranker scores*
within pool and fold.  This preserves score/intervention marginals exactly while
breaking position alignment.  No PatternEval weights, self-play, strength game,
frozen cohort, Scan label or promotion path is used here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "jobs" / "tools"))

import calibrate_vs_scan as cv  # type: ignore  # noqa: E402
import l3_context4_uncertainty_screen as ctx4  # type: ignore  # noqa: E402
from l3_conditional_targets import _open_counted, _open_feat, JNNW_DTYPE  # type: ignore  # noqa: E402

CONTEXT_WIDTH = 30
PAIR_FEATURE_NAMES = tuple(
    [f"parent_pov_ctx2_delta_{index:02d}" for index in range(CONTEXT_WIDTH)]
    + [
        "choice_top2_minus_top1_cp_div100",
        "piece_count_div40",
        "legal_children_div20",
        "capture_top2_minus_top1",
        "both_moves_capture",
    ]
)


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path: str | Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    if target.exists():
        raise ValueError(f"refusing to overwrite {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _deadband_sign(value: float, deadband: float) -> int:
    if value > deadband:
        return 1
    if value < -deadband:
        return -1
    return 0


def pair_feature_vector(
    top1_context: np.ndarray,
    top2_context: np.ndarray,
    *,
    root_side: str,
    choice_top1_cp: int,
    choice_top2_cp: int,
    piece_count: int,
    legal_children: int,
    top1_capture: bool,
    top2_capture: bool,
) -> np.ndarray:
    """Return the fixed pair feature vector in the parent side-to-move POV."""

    left = np.asarray(top1_context, dtype=np.float64)
    right = np.asarray(top2_context, dtype=np.float64)
    if left.shape != (CONTEXT_WIDTH,) or right.shape != (CONTEXT_WIDTH,):
        raise ValueError("decision ranker requires two 30-wide context rows")
    if root_side not in ("B", "W"):
        raise ValueError(f"unknown root side {root_side!r}")
    if choice_top2_cp > choice_top1_cp:
        raise ValueError("top2 choice score exceeds top1")
    if not 0 < piece_count <= 40 or legal_children < 2:
        raise ValueError("invalid pair descriptors")

    # The dedicated CTX2 context dump is black-POV.  top2-top1 is converted to
    # the parent mover's POV so the exact colour-swap meaning is shared across
    # black and white roots.
    parent_sign = 1.0 if root_side == "B" else -1.0
    context_delta = parent_sign * (right - left)
    descriptors = np.asarray(
        [
            (choice_top2_cp - choice_top1_cp) / 100.0,
            piece_count / 40.0,
            min(legal_children, 20) / 20.0,
            float(int(top2_capture) - int(top1_capture)),
            float(top1_capture and top2_capture),
        ],
        dtype=np.float64,
    )
    result = np.concatenate((context_delta, descriptors))
    if result.shape != (len(PAIR_FEATURE_NAMES),) or not np.all(np.isfinite(result)):
        raise RuntimeError("invalid decision-ranker feature vector")
    return result


def _child_rows(children: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    if children.get("schema") != "jass.l3_context4_children.v1":
        raise ValueError("children schema drift")
    parents = {int(row["ordinal"]): row for row in children.get("parents", [])}
    flat = {int(row["child_id"]): row for row in children.get("children", [])}
    if len(flat) != int(children.get("child_count", -1)):
        raise ValueError("children cardinality drift")
    return parents, flat


def analyse_shard(args: argparse.Namespace) -> dict[str, Any]:
    selection = _load(args.selection)
    children = _load(args.children)
    if selection.get("schema") != "jass.l3_context4_uncertainty_selection.v1":
        raise ValueError("selection schema drift")
    by_parent, flat = _child_rows(children)

    child_records = _open_counted(Path(args.child_jnnw), b"JNNW", JNNW_DTYPE)
    context, width = _open_feat(Path(args.context_features), len(child_records))
    if width != CONTEXT_WIDTH or len(child_records) != len(flat):
        raise ValueError("child context alignment drift")

    engine = cv.JassEngine(
        args.jass,
        label=f"decision-ranker-s{args.shard}",
        pattern_path=args.curriculum,
        search_params=args.search_params,
    )
    rows: list[dict[str, Any]] = []
    try:
        for source in selection.get("rows", []):
            ordinal = int(source["ordinal"])
            if ordinal % int(args.nshards) != int(args.shard):
                continue
            parent = by_parent[ordinal]
            count = int(parent["child_count"])
            if count < 2:
                continue
            children_here = [
                flat[index]
                for index in range(int(parent["child_start"]), int(parent["child_start"]) + count)
            ]
            ranked: list[dict[str, Any]] = []
            for child in children_here:
                result = ctx4._search(engine, str(child["fen"]), int(args.choice_depth))
                ranked.append(
                    {
                        **child,
                        "choice_parent_score_cp": -int(result["child_stm_score_cp"]),
                        "choice_depth_reached": int(result["depth"]),
                        "choice_nodes": int(result["nodes"]),
                    }
                )
            ranked.sort(key=lambda row: (-int(row["choice_parent_score_cp"]), str(row["move"])))
            top1, top2 = ranked[:2]
            margin = int(top1["choice_parent_score_cp"]) - int(top2["choice_parent_score_cp"])
            if margin < 0:
                raise RuntimeError("negative top-two choice margin")
            if margin > int(args.uncertainty_cp):
                continue

            audit1 = ctx4._search(engine, str(top1["fen"]), int(args.audit_depth))
            audit2 = ctx4._search(engine, str(top2["fen"]), int(args.audit_depth))
            judge1 = ctx4._search(engine, str(top1["fen"]), int(args.judge_depth))
            judge2 = ctx4._search(engine, str(top2["fen"]), int(args.judge_depth))
            audit_delta = -int(audit2["child_stm_score_cp"]) + int(audit1["child_stm_score_cp"])
            judge_delta = -int(judge2["child_stm_score_cp"]) + int(judge1["child_stm_score_cp"])
            audit_class = _deadband_sign(audit_delta, float(args.judge_deadband_cp))
            judge_class = _deadband_sign(judge_delta, float(args.judge_deadband_cp))

            side, wm, wk, bm, bk = cv.parse_jass_fen(str(source["fen"]))
            piece_count = sum(map(len, (wm, wk, bm, bk)))
            top1_id = int(top1["child_id"])
            top2_id = int(top2["child_id"])
            vector = pair_feature_vector(
                np.asarray(context[top1_id], dtype=np.float64),
                np.asarray(context[top2_id], dtype=np.float64),
                root_side=side,
                choice_top1_cp=int(top1["choice_parent_score_cp"]),
                choice_top2_cp=int(top2["choice_parent_score_cp"]),
                piece_count=piece_count,
                legal_children=count,
                top1_capture=bool(top1.get("capture", False)),
                top2_capture=bool(top2.get("capture", False)),
            )
            rows.append(
                {
                    "ordinal": ordinal,
                    "pool_index": int(source["pool_index"]),
                    "pool_label": str(source["pool_label"]),
                    "fen": str(source["fen"]),
                    "root_side": side,
                    "piece_count": int(piece_count),
                    "legal_children": count,
                    "baseline_top1_move": str(top1["move"]),
                    "baseline_top2_move": str(top2["move"]),
                    "baseline_top1_cp": int(top1["choice_parent_score_cp"]),
                    "baseline_top2_cp": int(top2["choice_parent_score_cp"]),
                    "baseline_margin_cp": margin,
                    "top1_capture": bool(top1.get("capture", False)),
                    "top2_capture": bool(top2.get("capture", False)),
                    "audit_top2_minus_top1_cp": audit_delta,
                    "judge_top2_minus_top1_cp": judge_delta,
                    "audit_class": audit_class,
                    "judge_class": judge_class,
                    "stable_non_tie": audit_class == judge_class and judge_class != 0,
                    "pair_features": [float(value) for value in vector],
                }
            )
    finally:
        engine.close()

    return {
        "schema": "jass.l3_decision_ranker_shard.v1",
        "shard": int(args.shard),
        "nshards": int(args.nshards),
        "choice_depth": int(args.choice_depth),
        "audit_depth": int(args.audit_depth),
        "judge_depth": int(args.judge_depth),
        "uncertainty_cp": int(args.uncertainty_cp),
        "judge_deadband_cp": int(args.judge_deadband_cp),
        "feature_names": list(PAIR_FEATURE_NAMES),
        "rows": rows,
    }


def _fold_for(row: dict[str, Any], *, folds: int, seed: int) -> int:
    material = f"{seed}|{row['pool_index']}|{row['ordinal']}|{row['fen']}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "little") % folds


def _pool_equal_weights(rows: list[dict[str, Any]]) -> np.ndarray:
    pools = sorted({int(row["pool_index"]) for row in rows})
    if len(pools) != 2:
        raise ValueError("decision screen requires exactly two source pools")
    weights = np.zeros(len(rows), dtype=np.float64)
    for pool in pools:
        indices = [index for index, row in enumerate(rows) if int(row["pool_index"]) == pool]
        if not indices:
            raise ValueError(f"empty pool {pool}")
        weights[indices] = 0.5 / len(indices)
    return weights / weights.mean()


def _ridge_fit(
    x: np.ndarray,
    y_cp: np.ndarray,
    weights: np.ndarray,
    *,
    ridge: float,
    target_clip_cp: float,
) -> dict[str, Any]:
    if x.ndim != 2 or y_cp.shape != (len(x),) or weights.shape != (len(x),):
        raise ValueError("ridge arrays are not aligned")
    if len(x) < 2 or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y_cp)):
        raise ValueError("ridge input is empty/non-finite")
    if ridge <= 0.0 or target_clip_cp <= 0.0 or np.any(weights <= 0.0):
        raise ValueError("invalid ridge contract")

    mean = np.average(x, axis=0, weights=weights)
    variance = np.average((x - mean) ** 2, axis=0, weights=weights)
    scale = np.sqrt(np.maximum(variance, 1e-12))
    z = (x - mean) / scale
    design = np.column_stack((np.ones(len(z), dtype=np.float64), z))
    target = np.clip(y_cp, -target_clip_cp, target_clip_cp) / 100.0
    weighted = design * np.sqrt(weights)[:, None]
    response = target * np.sqrt(weights)
    penalty = np.eye(design.shape[1], dtype=np.float64) * ridge
    penalty[0, 0] = 0.0
    lhs = weighted.T @ weighted + penalty
    rhs = weighted.T @ response
    coefficients = np.linalg.solve(lhs, rhs)
    if not np.all(np.isfinite(coefficients)):
        raise RuntimeError("ridge fit produced non-finite coefficients")
    return {
        "mean": mean,
        "scale": scale,
        "coefficients": coefficients,
        "ridge": float(ridge),
        "target_clip_cp": float(target_clip_cp),
    }


def _ridge_predict(model: dict[str, Any], x: np.ndarray) -> np.ndarray:
    mean = np.asarray(model["mean"], dtype=np.float64)
    scale = np.asarray(model["scale"], dtype=np.float64)
    coefficients = np.asarray(model["coefficients"], dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != len(mean) or coefficients.shape != (len(mean) + 1,):
        raise ValueError("ridge model/input shape drift")
    z = (x - mean) / scale
    return 100.0 * (coefficients[0] + z @ coefficients[1:])


def cross_fitted_scores(
    rows: list[dict[str, Any]],
    *,
    folds: int,
    fold_seed: int,
    ridge: float,
    target_clip_cp: float,
) -> tuple[np.ndarray, list[int], dict[str, Any]]:
    if folds < 3:
        raise ValueError("at least three OOF folds required")
    x = np.asarray([row["pair_features"] for row in rows], dtype=np.float64)
    y = np.asarray([row["judge_top2_minus_top1_cp"] for row in rows], dtype=np.float64)
    fold_ids = [_fold_for(row, folds=folds, seed=fold_seed) for row in rows]
    oof = np.full(len(rows), np.nan, dtype=np.float64)
    reports = []
    for fold in range(folds):
        test = np.asarray([value == fold for value in fold_ids], dtype=bool)
        train = ~test
        if int(test.sum()) < 2 or int(train.sum()) < 2:
            raise ValueError(f"fold {fold}: empty/tiny train or test")
        train_classes = {int(row["judge_class"]) for row, keep in zip(rows, train) if keep}
        if train_classes != {-1, 1}:
            raise ValueError(f"fold {fold}: training classes are {sorted(train_classes)}")
        train_rows = [row for row, keep in zip(rows, train) if keep]
        model = _ridge_fit(
            x[train], y[train], _pool_equal_weights(train_rows),
            ridge=ridge, target_clip_cp=target_clip_cp,
        )
        oof[test] = _ridge_predict(model, x[test])
        reports.append(
            {
                "fold": fold,
                "train_rows": int(train.sum()),
                "test_rows": int(test.sum()),
                "train_pools": sorted({int(row["pool_index"]) for row in train_rows}),
                "train_classes": sorted(train_classes),
            }
        )
    if not np.all(np.isfinite(oof)):
        raise RuntimeError("OOF ranker left missing/non-finite scores")
    final = _ridge_fit(
        x, y, _pool_equal_weights(rows), ridge=ridge, target_clip_cp=target_clip_cp
    )
    serial_final = {
        "feature_names": list(PAIR_FEATURE_NAMES),
        "mean": [float(value) for value in final["mean"]],
        "scale": [float(value) for value in final["scale"]],
        "coefficients": [float(value) for value in final["coefficients"]],
        "ridge": float(ridge),
        "target_clip_cp": float(target_clip_cp),
        "output": "predicted_judge_top2_minus_top1_cp",
    }
    return oof, fold_ids, {"folds": reports, "final_model": serial_final}


def _shuffle_scores(
    rows: list[dict[str, Any]], scores: np.ndarray, fold_ids: list[int], *, seed: int
) -> tuple[np.ndarray, dict[str, Any]]:
    if scores.shape != (len(rows),) or len(fold_ids) != len(rows):
        raise ValueError("shuffle arrays are not aligned")
    shuffled = np.empty_like(scores)
    donors = np.empty(len(rows), dtype=np.int64)
    cells: dict[str, Any] = {}
    for pool in sorted({int(row["pool_index"]) for row in rows}):
        for fold in sorted(set(fold_ids)):
            members = [
                index
                for index, row in enumerate(rows)
                if int(row["pool_index"]) == pool and fold_ids[index] == fold
            ]
            if len(members) < 2:
                raise ValueError(f"pool {pool} fold {fold}: fewer than two rows")
            ordered = sorted(
                members,
                key=lambda index: hashlib.sha256(
                    f"{seed}|{pool}|{fold}|{rows[index]['ordinal']}".encode()
                ).digest(),
            )
            rotated = ordered[-1:] + ordered[:-1]
            for target, donor in zip(ordered, rotated):
                shuffled[target] = scores[donor]
                donors[target] = donor
            key = f"pool{pool}_fold{fold}"
            cells[key] = {"rows": len(members), "score_multiset_preserved": True}
    fixed = int(np.sum(donors == np.arange(len(rows), dtype=np.int64)))
    if fixed or not np.array_equal(np.sort(shuffled), np.sort(scores)):
        raise RuntimeError("score shuffle failed fixed-point/marginal contract")
    return shuffled, {
        "seed": int(seed),
        "fixed_points": fixed,
        "all_sources_within_same_pool": True,
        "all_sources_within_same_fold": True,
        "global_score_multiset_preserved": True,
        "cells": cells,
        "donor_hash": hashlib.sha256(donors.tobytes(order="C")).hexdigest(),
    }


def _bootstrap_mean(values: np.ndarray, *, samples: int, seed: int) -> dict[str, Any]:
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 1 or len(x) == 0:
        raise ValueError("bootstrap requires a non-empty vector")
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    batch = max(1, min(1024, 2_000_000 // len(x)))
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        indices = rng.integers(0, len(x), size=(stop - start, len(x)))
        draws[start:stop] = x[indices].mean(axis=1)
    low, high = np.quantile(draws, (0.025, 0.975))
    return {
        "n": int(len(x)),
        "mean_cp": float(x.mean()),
        "median_cp": float(np.median(x)),
        "ci95_cp": [float(low), float(high)],
        "probability_positive": float(np.mean(draws > 0.0)),
        "bootstrap_samples": int(samples),
        "seed": int(seed),
    }


def _two_pool_bootstrap(
    rows: list[dict[str, Any]], values: np.ndarray, *, samples: int, seed: int
) -> dict[str, Any]:
    pools = sorted({int(row["pool_index"]) for row in rows})
    if pools != [1, 2] or values.shape != (len(rows),):
        raise ValueError("two-pool bootstrap contract drift")
    arrays = [
        np.asarray([value for row, value in zip(rows, values) if int(row["pool_index"]) == pool])
        for pool in pools
    ]
    if any(len(array) == 0 for array in arrays):
        raise ValueError("empty pool in bootstrap")
    rng = np.random.default_rng(seed)
    draws = np.empty(samples, dtype=np.float64)
    batch = max(1, min(512, 2_000_000 // max(len(array) for array in arrays)))
    for start in range(0, samples, batch):
        stop = min(start + batch, samples)
        pool_draws = []
        for array in arrays:
            indices = rng.integers(0, len(array), size=(stop - start, len(array)))
            pool_draws.append(array[indices].mean(axis=1))
        draws[start:stop] = 0.5 * (pool_draws[0] + pool_draws[1])
    low, high = np.quantile(draws, (0.025, 0.975))
    means = [float(array.mean()) for array in arrays]
    return {
        "pool_means_cp": means,
        "mean_cp": 0.5 * (means[0] + means[1]),
        "ci95_cp": [float(low), float(high)],
        "probability_positive": float(np.mean(draws > 0.0)),
        "bootstrap_samples": int(samples),
        "seed": int(seed),
        "pool_mass": {"1": 0.5, "2": 0.5},
    }


def _balanced_accuracy(scores: np.ndarray, classes: np.ndarray) -> dict[str, float]:
    prediction = np.where(scores > 0.0, 1, -1)
    positive = classes == 1
    negative = classes == -1
    tpr = float(np.mean(prediction[positive] == 1)) if np.any(positive) else float("nan")
    tnr = float(np.mean(prediction[negative] == -1)) if np.any(negative) else float("nan")
    return {"positive_recall": tpr, "negative_recall": tnr, "balanced_accuracy": 0.5 * (tpr + tnr)}


def aggregate_rows(
    raw_rows: list[dict[str, Any]],
    *,
    folds: int,
    fold_seed: int,
    ridge: float,
    target_clip_cp: float,
    shuffle_seed: int,
    bootstrap_samples: int,
    bootstrap_seed: int,
    min_total: int,
    min_per_pool: int,
    min_positive: int,
    min_negative: int,
    min_stable_fraction: float,
    min_interventions: int,
    max_intervention_rate: float,
) -> dict[str, Any]:
    ordered = sorted(raw_rows, key=lambda row: int(row["ordinal"]))
    if len({int(row["ordinal"]) for row in ordered}) != len(ordered):
        raise ValueError("duplicate decision ordinal")
    if any(len(row.get("pair_features", [])) != len(PAIR_FEATURE_NAMES) for row in ordered):
        raise ValueError("pair feature width drift")
    stable = [row for row in ordered if bool(row.get("stable_non_tie"))]
    if not stable:
        raise ValueError("no stable non-tie decision pairs")

    oof, fold_ids, fit = cross_fitted_scores(
        stable,
        folds=folds,
        fold_seed=fold_seed,
        ridge=ridge,
        target_clip_cp=target_clip_cp,
    )
    shuffled, shuffle = _shuffle_scores(stable, oof, fold_ids, seed=shuffle_seed)
    judge = np.asarray([row["judge_top2_minus_top1_cp"] for row in stable], dtype=np.float64)
    classes = np.asarray([row["judge_class"] for row in stable], dtype=np.int8)
    aligned_flip = oof > 0.0
    shuffled_flip = shuffled > 0.0
    if int(aligned_flip.sum()) != int(shuffled_flip.sum()):
        raise RuntimeError("shuffle changed total intervention count")
    aligned_gain = np.where(aligned_flip, judge, 0.0)
    shuffled_gain = np.where(shuffled_flip, judge, 0.0)
    contrast = aligned_gain - shuffled_gain

    combined = _two_pool_bootstrap(
        stable, contrast, samples=bootstrap_samples, seed=bootstrap_seed
    )
    flip_gain = (
        _bootstrap_mean(
            judge[aligned_flip], samples=bootstrap_samples, seed=bootstrap_seed + 1
        )
        if np.any(aligned_flip)
        else None
    )
    per_pool: dict[str, Any] = {}
    for pool in (1, 2):
        mask = np.asarray([int(row["pool_index"]) == pool for row in stable], dtype=bool)
        per_pool[str(pool)] = {
            "stable_pairs": int(mask.sum()),
            "positive_labels": int(np.sum(classes[mask] == 1)),
            "negative_labels": int(np.sum(classes[mask] == -1)),
            "aligned_interventions": int(np.sum(aligned_flip[mask])),
            "shuffled_interventions": int(np.sum(shuffled_flip[mask])),
            "aligned_minus_shuffled_mean_cp": float(np.mean(contrast[mask])),
        }

    counts = [row["stable_pairs"] for row in per_pool.values()]
    positives = int(np.sum(classes == 1))
    negatives = int(np.sum(classes == -1))
    intervention_count = int(aligned_flip.sum())
    intervention_rate = intervention_count / len(stable)
    stable_fraction = len(stable) / max(1, len(ordered))
    accuracy = _balanced_accuracy(oof, classes)
    baseline_accuracy = _balanced_accuracy(
        np.full(len(stable), -1.0, dtype=np.float64), classes
    )

    guards = {
        "enough_stable_pairs": len(stable) >= min_total,
        "enough_stable_pairs_each_pool": min(counts) >= min_per_pool,
        "enough_positive_labels": positives >= min_positive,
        "enough_negative_labels": negatives >= min_negative,
        "judge_stable_fraction": stable_fraction >= min_stable_fraction,
        "shuffle_fixed_points_zero": int(shuffle["fixed_points"]) == 0,
        "enough_aligned_interventions": intervention_count >= min_interventions,
        "bounded_intervention_rate": 0.0 < intervention_rate <= max_intervention_rate,
        "aligned_vs_shuffled_ci95_positive": combined["ci95_cp"][0] > 0.0,
        "aligned_vs_shuffled_probability_positive": combined["probability_positive"] >= 0.975,
        "both_pool_point_estimates_positive": min(combined["pool_means_cp"]) > 0.0,
        "aligned_intervention_gain_ci95_positive": (
            flip_gain is not None and flip_gain["ci95_cp"][0] > 0.0
        ),
        "oof_balanced_accuracy_above_chance": accuracy["balanced_accuracy"] > 0.5,
    }
    passed = all(guards.values())

    enriched = []
    for index, row in enumerate(stable):
        enriched.append(
            {
                **row,
                "oof_fold": int(fold_ids[index]),
                "oof_predicted_top2_minus_top1_cp": float(oof[index]),
                "shuffled_predicted_top2_minus_top1_cp": float(shuffled[index]),
                "aligned_flip": bool(aligned_flip[index]),
                "shuffled_flip": bool(shuffled_flip[index]),
                "aligned_gain_vs_baseline_cp": float(aligned_gain[index]),
                "shuffled_gain_vs_baseline_cp": float(shuffled_gain[index]),
                "aligned_minus_shuffled_gain_cp": float(contrast[index]),
            }
        )

    return {
        "schema": "jass.l3_decision_ranker_mechanism_screen.v1",
        "verdict": (
            "JASS_DECISION_RANKER_MECHANISM_SCREEN_PASSED"
            if passed
            else "JASS_DECISION_RANKER_MECHANISM_SCREEN_FAILED"
        ),
        "screen_passed": passed,
        "next_stage_authorized": passed,
        "protocol": {
            "learning_object": "direct_top2_vs_top1_deep_judge_delta",
            "scalar_value": "CURRICULUM_unchanged",
            "ranker": "linear_ridge_pairwise_residual_OOF",
            "features": list(PAIR_FEATURE_NAMES),
            "intervention": "inside_uncertainty_band_flip_to_top2_only_when_OOF_predicted_delta_cp_gt_zero",
            "control": "same_OOF_score_multiset_cyclically_permuted_within_pool_and_fold",
            "teacher": "deeper_CURRICULUM_only_no_Scan",
            "pattern_eval_refit": False,
            "selfplay": False,
            "strength_games": False,
            "frozen_read": False,
            "promotion_authorized": False,
        },
        "sample": {
            "uncertainty_pairs": len(ordered),
            "stable_non_tie_pairs": len(stable),
            "stable_fraction": stable_fraction,
            "positive_labels": positives,
            "negative_labels": negatives,
            "aligned_interventions": intervention_count,
            "intervention_rate": intervention_rate,
            "per_pool": per_pool,
        },
        "oof_diagnostics": {
            "balanced_accuracy": accuracy,
            "always_top1_baseline": baseline_accuracy,
            "fit": fit,
        },
        "shuffle_control": shuffle,
        "aligned_vs_shuffled_gain": combined,
        "aligned_intervention_judge_gain": flip_gain,
        "guards": guards,
        "rows": enriched,
    }


def aggregate_shards(args: argparse.Namespace) -> dict[str, Any]:
    shards = [_load(path) for path in args.shards]
    indices = {int(row.get("shard", -1)) for row in shards}
    expected = set(range(len(shards)))
    if indices != expected:
        raise ValueError(f"shard indices {sorted(indices)} != {sorted(expected)}")
    for shard in shards:
        if shard.get("schema") != "jass.l3_decision_ranker_shard.v1":
            raise ValueError("ranker shard schema drift")
        if shard.get("feature_names") != list(PAIR_FEATURE_NAMES):
            raise ValueError("ranker feature-name drift")
    rows = [row for shard in shards for row in shard.get("rows", [])]
    payload = aggregate_rows(
        rows,
        folds=int(args.folds),
        fold_seed=int(args.fold_seed),
        ridge=float(args.ridge),
        target_clip_cp=float(args.target_clip_cp),
        shuffle_seed=int(args.shuffle_seed),
        bootstrap_samples=int(args.bootstrap_samples),
        bootstrap_seed=int(args.bootstrap_seed),
        min_total=int(args.min_total),
        min_per_pool=int(args.min_per_pool),
        min_positive=int(args.min_positive),
        min_negative=int(args.min_negative),
        min_stable_fraction=float(args.min_stable_fraction),
        min_interventions=int(args.min_interventions),
        max_intervention_rate=float(args.max_intervention_rate),
    )
    payload["source"] = {
        "selection_sha256": _sha256(args.selection),
        "children_sha256": _sha256(args.children),
        "child_jnnw_sha256": _sha256(args.child_jnnw),
        "context_features_sha256": _sha256(args.context_features),
        "shard_sha256": [_sha256(path) for path in args.shards],
    }
    _write(args.out, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    worker = sub.add_parser("worker")
    worker.add_argument("--selection", required=True)
    worker.add_argument("--children", required=True)
    worker.add_argument("--child-jnnw", required=True)
    worker.add_argument("--context-features", required=True)
    worker.add_argument("--jass", required=True)
    worker.add_argument("--curriculum", required=True)
    worker.add_argument("--search-params", default="")
    worker.add_argument("--choice-depth", type=int, default=9)
    worker.add_argument("--audit-depth", type=int, default=12)
    worker.add_argument("--judge-depth", type=int, default=14)
    worker.add_argument("--uncertainty-cp", type=int, default=40)
    worker.add_argument("--judge-deadband-cp", type=int, default=8)
    worker.add_argument("--shard", type=int, required=True)
    worker.add_argument("--nshards", type=int, required=True)
    worker.add_argument("--out", required=True)

    aggregate = sub.add_parser("aggregate")
    aggregate.add_argument("--selection", required=True)
    aggregate.add_argument("--children", required=True)
    aggregate.add_argument("--child-jnnw", required=True)
    aggregate.add_argument("--context-features", required=True)
    aggregate.add_argument("--shard", dest="shards", action="append", required=True)
    aggregate.add_argument("--folds", type=int, default=5)
    aggregate.add_argument("--fold-seed", type=int, default=2026082311)
    aggregate.add_argument("--ridge", type=float, default=0.1)
    aggregate.add_argument("--target-clip-cp", type=float, default=200.0)
    aggregate.add_argument("--shuffle-seed", type=int, default=2026082312)
    aggregate.add_argument("--bootstrap-samples", type=int, default=100000)
    aggregate.add_argument("--bootstrap-seed", type=int, default=2026082313)
    aggregate.add_argument("--min-total", type=int, default=240)
    aggregate.add_argument("--min-per-pool", type=int, default=80)
    aggregate.add_argument("--min-positive", type=int, default=30)
    aggregate.add_argument("--min-negative", type=int, default=120)
    aggregate.add_argument("--min-stable-fraction", type=float, default=0.65)
    aggregate.add_argument("--min-interventions", type=int, default=20)
    aggregate.add_argument("--max-intervention-rate", type=float, default=0.35)
    aggregate.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    if args.command == "worker":
        if not int(args.choice_depth) < int(args.audit_depth) < int(args.judge_depth):
            raise SystemExit("require choice_depth < audit_depth < judge_depth")
        payload = analyse_shard(args)
        _write(args.out, payload)
    else:
        payload = aggregate_shards(args)
    print(json.dumps({key: value for key, value in payload.items() if key != "rows"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
