#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only cross-pool screen for error-specific action-margin corrections.

The state-trigger stable6 and 20-bucket routes are closed by 1532/1535.  This
screen asks a narrower causal question: can a bounded linear correction rank
the exact better action above CURRICULUM's action on error states while being
explicitly anchored to zero action-margin movement on paired controls?

Every candidate is trained on one opening/game-disjoint 1524 pool and tested
on the other.  Selection uses the minimum held-out paired gain across pools and
is compared with the maximum over the complete finite family for 1,000 aligned
sign shams.  A PASS is discovery-only and can authorize only two entirely new
confirmation pools, never a PatternEval refit or a strength gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_bucket_treatment_atlas as bucket
from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as fresh
from jobs.tools import l3_curriculum_error_target_specificity_autopsy as target


SCHEMA = "jass.l3_curriculum_error_action_margin_contrastive_screen.v1"
READY = "JASS_CURRICULUM_ERROR_ACTION_MARGIN_CONTRASTIVE_SCREEN_READY"
BUCKET_SOURCE_SCHEMA = bucket.SCHEMA
ALPHAS = (30.0, 300.0, 3000.0)
CONTROL_ANCHOR_PENALTIES = (1.0, 10.0, 100.0)
THRESHOLDS_CP = (5.0, 10.0)
CAP_CP = 25.0
MODE = "strict_both_change"
SHAM_REPLICATES = 1000
SHAM_SEED = 2026082318
BOOTSTRAP_SAMPLES = 200_000
BOOTSTRAP_SEED = 2026082319
MIN_COEFFICIENT_COSINE = 0.50
MIN_ERROR_INTERVENTIONS = 24
MIN_ERROR_INTERVENTIONS_PER_POOL = 8
MIN_POSITIVE_REALIZATION_RATE = 0.60
MIN_CONTROL_MEAN_CP = -2.0
EPS = 1e-10


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _same(left: object, right: object) -> bool:
    return _canonical(left) == _canonical(right)


def _require_negative_atlas(report: dict[str, Any], target_report: dict[str, Any]) -> None:
    screen = report.get("bucket_treatment_screen", {})
    if (
        report.get("schema") != BUCKET_SOURCE_SCHEMA
        or report.get("verdict") != bucket.READY
        or report.get("passed") is not True
        or screen.get("passed") is not False
        or screen.get("status") != "bucket_treatment_rule_not_established"
        or report.get("bucket_treatment_rule_candidate_established") is not False
        or report.get("new_fresh_pool_preregistration_recommended") is not False
    ):
        raise ValueError("action-margin screen requires certified negative 1535 atlas")
    if report.get("scientific_source", {}).get("target_specificity_report_sha256") != _digest(target_report):
        raise ValueError("1535/1532 report identity drift")
    for key in (
        "anchored_local_refit_authorized", "production_model_authorized",
        "strength_gate_authorized", "promotion_authorized", "automatic_continuation",
    ):
        if report.get(key) is not False:
            raise ValueError(f"1535 forbidden authorization drift: {key}")


def _reconstruct(
    training_report: dict[str, Any], failed_model: dict[str, Any],
    training_pairs: dict[str, Any], training_shards: list[dict[str, Any]],
    fresh_summary: dict[str, Any], fresh_report: dict[str, Any],
    fresh_pairs: dict[str, Any], fresh_shards: list[dict[str, Any]],
    target_cache: dict[str, Any], subspace_report: dict[str, Any],
    target_report: dict[str, Any], bucket_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[int], dict[str, Any], dict[str, Any]]:
    bucket._require_negative_target_report(target_report)
    _require_negative_atlas(bucket_report, target_report)
    source_hashes = target_report.get("source_hashes", {})
    expected_hashes = {
        "training_pairs_sha256": _digest(training_pairs),
        "fresh_pairs_sha256": _digest(fresh_pairs),
        "fresh_target_cache_sha256": _digest(target_cache),
        "fresh_report_sha256": _digest(fresh_report),
        "stable_subspace_sha256": _digest(subspace_report),
    }
    for key, value in expected_hashes.items():
        if source_hashes.get(key) != value:
            raise ValueError(f"1532/source digest drift: {key}")

    _atlas_rows, split, reproduction, stable_indices = bucket._reconstruct(
        training_report, failed_model, training_pairs, training_shards,
        fresh_summary, fresh_report, fresh_pairs, fresh_shards,
        target_cache, subspace_report,
    )
    if not _same(bucket_report.get("split_integrity"), split):
        raise ValueError("1535 split reproduction drift")
    if not _same(bucket_report.get("reproduction"), reproduction):
        raise ValueError("1535 decision reproduction drift")
    rows, identities = fresh._load_fresh_rows(
        fresh_pairs, fresh_shards, pair_count=target.FRESH_PAIRS
    )
    if identities != reproduction.get("identities"):
        raise ValueError("fresh action rows identity drift")
    return rows, stable_indices, split, {
        **reproduction,
        "target_report_sha256": _digest(target_report),
        "bucket_report_sha256": _digest(bucket_report),
    }


def _configurations(stable_indices: list[int]) -> list[dict[str, Any]]:
    supports = (
        ("stable6", list(stable_indices)),
        ("full20", list(range(len(ranker.FEATURE_NAMES)))),
    )
    output = []
    for support_name, indices in supports:
        for alpha in ALPHAS:
            for control_penalty in CONTROL_ANCHOR_PENALTIES:
                for threshold in THRESHOLDS_CP:
                    output.append({
                        "name": (
                            f"{support_name}__alpha_{alpha:g}"
                            f"__control_{control_penalty:g}__threshold_{threshold:g}"
                        ),
                        "support_name": support_name,
                        "indices": indices,
                        "feature_names": [ranker.FEATURE_NAMES[index] for index in indices],
                        "dimension": len(indices),
                        "alpha": alpha,
                        "control_anchor_penalty": control_penalty,
                        "threshold_cp": threshold,
                        "cap_cp": CAP_CP,
                        "mode": MODE,
                    })
    return output


def _best(scores: dict[str, float]) -> str:
    return max(scores, key=lambda action: (scores[action], action))


def _normalization(rows: list[dict[str, Any]], indices: list[int]) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.vstack([
        np.asarray(vector, dtype=float)[indices]
        for row in rows for role in ("error", "control")
        for vector in row[role]["features"].values()
    ])
    mean = matrix.mean(axis=0)
    rms = np.sqrt(np.mean((matrix - mean) ** 2, axis=0))
    rms[rms < 1e-6] = 1.0
    return mean, rms


def _fit(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    indices = list(config["indices"])
    mean, rms = _normalization(rows, indices)
    width = len(indices)
    error_grams = []
    error_targets = []
    error_design = []
    control_grams = []
    control_design = []
    error_comparisons = 0
    control_comparisons = 0

    for row in rows:
        state = row["error"]
        values = state["values"]
        teacher = max(values, key=lambda action: (values[action], action))
        others = [action for action in sorted(values) if action != teacher]
        if not others:
            error_grams.append(np.zeros((width, width), dtype=float))
            error_targets.append(np.zeros(width, dtype=float))
        else:
            baseline = {
                action: (state["original_scores"][action] + state["image_scores"][action]) / 2.0
                for action in values
            }
            xs = []
            ys = []
            for other in others:
                x = (
                    np.asarray(state["features"][teacher], dtype=float)[indices]
                    - np.asarray(state["features"][other], dtype=float)[indices]
                ) / rms
                y = (values[teacher] - values[other]) - (baseline[teacher] - baseline[other])
                xs.append(x)
                ys.append(float(y))
            design = np.asarray(xs, dtype=float)
            targets = np.asarray(ys, dtype=float)
            error_grams.append(np.mean(np.einsum("ni,nj->nij", design, design), axis=0))
            error_targets.append(np.mean(design * targets[:, None], axis=0))
            error_design.extend(xs)
            error_comparisons += len(xs)

        state = row["control"]
        xs = []
        for score_key in ("original_scores", "image_scores"):
            anchor = _best(state[score_key])
            for other in sorted(state[score_key]):
                if other == anchor:
                    continue
                x = (
                    np.asarray(state["features"][anchor], dtype=float)[indices]
                    - np.asarray(state["features"][other], dtype=float)[indices]
                ) / rms
                xs.append(x)
        if xs:
            design = np.asarray(xs, dtype=float)
            control_grams.append(np.mean(np.einsum("ni,nj->nij", design, design), axis=0))
            control_design.extend(xs)
            control_comparisons += len(xs)
        else:
            control_grams.append(np.zeros((width, width), dtype=float))

    if not error_comparisons or not control_comparisons:
        raise ValueError("action-margin fit has zero error/control comparisons")
    error_gram = np.mean(np.asarray(error_grams), axis=0)
    control_gram = np.mean(np.asarray(control_grams), axis=0)
    contributions = np.asarray(error_targets, dtype=float) / len(rows)
    system = (
        error_gram
        + float(config["control_anchor_penalty"]) * control_gram
        + float(config["alpha"]) * np.eye(width)
    )
    inverse = np.linalg.inv(system)
    coefficient = inverse @ np.sum(contributions, axis=0)
    return {
        "mean": mean,
        "rms": rms,
        "coefficient": coefficient,
        "inverse": inverse,
        "target_contributions": contributions,
        "error_rank": int(np.linalg.matrix_rank(np.asarray(error_design, dtype=float))),
        "control_rank": int(np.linalg.matrix_rank(np.asarray(control_design, dtype=float))),
        "condition_number": float(np.linalg.cond(system)),
        "error_comparisons": error_comparisons,
        "control_anchor_comparisons": control_comparisons,
        "states": len(rows),
    }


def _corrections(state: dict[str, Any], model: dict[str, Any], config: dict[str, Any]) -> dict[str, float]:
    indices = list(config["indices"])
    output = {}
    for action, vector in state["features"].items():
        selected = np.asarray(vector, dtype=float)[indices]
        value = float(((selected - model["mean"]) / model["rms"]) @ model["coefficient"])
        output[action] = max(-CAP_CP, min(CAP_CP, value))
    return output


def _decision(state: dict[str, Any], model: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    original_anchor = _best(state["original_scores"])
    image_anchor = _best(state["image_scores"])
    corrections = _corrections(state, model, config)
    original_corrected = {
        action: state["original_scores"][action] + corrections[action]
        for action in corrections
    }
    image_corrected = {
        action: state["image_scores"][action] + corrections[action]
        for action in corrections
    }
    original_proposed = _best(original_corrected)
    image_proposed = _best(image_corrected)
    original_advantage = original_corrected[original_proposed] - original_corrected[original_anchor]
    image_advantage = image_corrected[image_proposed] - image_corrected[image_anchor]
    intervention = bool(
        original_proposed == image_proposed
        and original_proposed not in {original_anchor, image_anchor}
        and min(original_advantage, image_advantage) >= float(config["threshold_cp"])
    )
    chosen_original = original_proposed if intervention else original_anchor
    chosen_image = image_proposed if intervention else image_anchor
    values = state["values"]
    anchor_value = (values[original_anchor] + values[image_anchor]) / 2.0
    chosen_value = (values[chosen_original] + values[chosen_image]) / 2.0
    return {
        "intervention": intervention,
        "improvement_cp": float(chosen_value - anchor_value),
        "predicted_advantage_cp": (
            float((original_advantage + image_advantage) / 2.0) if intervention else None
        ),
        "realized_gain_cp": float(chosen_value - anchor_value) if intervention else None,
        "original_anchor": original_anchor,
        "image_anchor": image_anchor,
        "action": original_proposed if intervention else None,
        "anchor_symmetry": original_anchor == image_anchor,
        "aligned_symmetry": chosen_original == chosen_image,
        "abstention_bit_identical": (
            intervention or (chosen_original == original_anchor and chosen_image == image_anchor)
        ),
        "outside_support_bit_identical": True,
    }


def _quick(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    errors = np.asarray([row["error"]["improvement_cp"] for row in decisions], dtype=float)
    controls = np.asarray([row["control"]["improvement_cp"] for row in decisions], dtype=float)
    paired = errors - controls
    changed = [row["error"] for row in decisions if row["error"]["intervention"]]
    return {
        "pairs": len(decisions),
        "error_mean_cp": float(np.mean(errors)),
        "control_mean_cp": float(np.mean(controls)),
        "paired_mean_cp": float(np.mean(paired)),
        "error_interventions": len(changed),
        "control_interventions": sum(row["control"]["intervention"] for row in decisions),
        "error_positive_realization_rate": (
            float(np.mean([float(row["realized_gain_cp"]) > 0.0 for row in changed]))
            if changed else None
        ),
        "abstentions_bit_identical": all(
            row[role]["abstention_bit_identical"]
            for row in decisions for role in ("error", "control")
        ),
        "aligned_intervention_symmetry": all(
            row[role]["aligned_symmetry"]
            for row in decisions for role in ("error", "control")
            if row[role]["intervention"]
        ),
    }


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(left @ right / denominator) if denominator > 0.0 else 0.0


def _evaluate(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    pools = {
        pool: [row for row in rows if str(row["source_pool"]) == pool]
        for pool in ("pool1", "pool2")
    }
    fits = {pool: _fit(pool_rows, config) for pool, pool_rows in pools.items()}
    decisions = []
    for heldout_pool in ("pool1", "pool2"):
        training_pool = "pool2" if heldout_pool == "pool1" else "pool1"
        model = fits[training_pool]
        for row in pools[heldout_pool]:
            decisions.append({
                "pair_id": int(row["pair_id"]),
                "source_pool": heldout_pool,
                "error": _decision(row["error"], model, config),
                "control": _decision(row["control"], model, config),
            })
    by_pool = {
        pool: _quick([row for row in decisions if row["source_pool"] == pool])
        for pool in ("pool1", "pool2")
    }
    combined = _quick(decisions)
    cosine = _cosine(fits["pool1"]["coefficient"], fits["pool2"]["coefficient"])
    minimum_rank = min(fit["error_rank"] for fit in fits.values())
    rank_requirement = min(3, int(config["dimension"]))
    gates = {
        "error_support_ranks_sufficient": minimum_rank >= rank_requirement,
        "coefficient_cosine_at_least_0_50": cosine >= MIN_COEFFICIENT_COSINE,
        "error_interventions_at_least_24": combined["error_interventions"] >= MIN_ERROR_INTERVENTIONS,
        "error_positive_realization_rate_at_least_0_60": (
            combined["error_positive_realization_rate"] is not None
            and combined["error_positive_realization_rate"] >= MIN_POSITIVE_REALIZATION_RATE
        ),
        "abstentions_bit_identical": combined["abstentions_bit_identical"],
        "aligned_intervention_symmetry": combined["aligned_intervention_symmetry"],
    }
    for pool, metrics in by_pool.items():
        gates[f"{pool}_error_interventions_at_least_8"] = (
            metrics["error_interventions"] >= MIN_ERROR_INTERVENTIONS_PER_POOL
        )
        gates[f"{pool}_error_mean_gt_0cp"] = metrics["error_mean_cp"] > 0.0
        gates[f"{pool}_paired_mean_gt_0cp"] = metrics["paired_mean_cp"] > 0.0
        gates[f"{pool}_control_mean_at_least_minus_2cp"] = (
            metrics["control_mean_cp"] >= MIN_CONTROL_MEAN_CP
        )
    eligible = all(gates.values())
    return {
        "config": config,
        "fits": {
            pool: {
                "coefficient": fit["coefficient"].tolist(),
                "coefficient_sha256": _digest(fit["coefficient"].tolist()),
                "error_rank": fit["error_rank"],
                "control_rank": fit["control_rank"],
                "condition_number": fit["condition_number"],
                "error_comparisons": fit["error_comparisons"],
                "control_anchor_comparisons": fit["control_anchor_comparisons"],
                "states": fit["states"],
            }
            for pool, fit in fits.items()
        },
        "coefficient_cosine": cosine,
        "combined": combined,
        "by_pool": by_pool,
        "structural_gates": gates,
        "eligible": eligible,
        "selection_score_min_pool_paired_mean_cp": min(
            metrics["paired_mean_cp"] for metrics in by_pool.values()
        ),
        "decisions": decisions,
        "fits_internal": fits,
        "rows_by_pool": pools,
    }


def _batched_pool(
    rows: list[dict[str, Any]], coefficients: np.ndarray,
    model: dict[str, Any], config: dict[str, Any],
) -> dict[str, np.ndarray]:
    replicates = coefficients.shape[1]
    gains: dict[str, list[np.ndarray]] = {"error": [], "control": []}
    interventions: dict[str, list[np.ndarray]] = {"error": [], "control": []}
    indices = list(config["indices"])
    for row in rows:
        for role in ("error", "control"):
            state = row[role]
            actions = sorted(state["features"], reverse=True)
            feature_matrix = np.asarray([
                (np.asarray(state["features"][action], dtype=float)[indices] - model["mean"])
                / model["rms"]
                for action in actions
            ])
            correction = np.clip(feature_matrix @ coefficients, -CAP_CP, CAP_CP)
            original_base = np.asarray([state["original_scores"][action] for action in actions])
            image_base = np.asarray([state["image_scores"][action] for action in actions])
            original_anchor = int(np.argmax(original_base))
            image_anchor = int(np.argmax(image_base))
            original_corrected = original_base[:, None] + correction
            image_corrected = image_base[:, None] + correction
            original_proposed = np.argmax(original_corrected, axis=0)
            image_proposed = np.argmax(image_corrected, axis=0)
            columns = np.arange(replicates)
            original_advantage = (
                original_corrected[original_proposed, columns]
                - original_corrected[original_anchor, columns]
            )
            image_advantage = (
                image_corrected[image_proposed, columns]
                - image_corrected[image_anchor, columns]
            )
            intervene = (
                (original_proposed == image_proposed)
                & (original_proposed != original_anchor)
                & (original_proposed != image_anchor)
                & (np.minimum(original_advantage, image_advantage) >= float(config["threshold_cp"]))
            )
            values = np.asarray([state["values"][action] for action in actions], dtype=float)
            anchor_value = (values[original_anchor] + values[image_anchor]) / 2.0
            improvement = values[original_proposed] - anchor_value
            gains[role].append(np.where(intervene, improvement, 0.0))
            interventions[role].append(intervene)
    error_gain = np.asarray(gains["error"], dtype=float)
    control_gain = np.asarray(gains["control"], dtype=float)
    error_intervene = np.asarray(interventions["error"], dtype=bool)
    control_intervene = np.asarray(interventions["control"], dtype=bool)
    error_count = np.sum(error_intervene, axis=0)
    positive_count = np.sum(error_intervene & (error_gain > 0.0), axis=0)
    return {
        "error_mean": np.mean(error_gain, axis=0),
        "control_mean": np.mean(control_gain, axis=0),
        "paired_mean": np.mean(error_gain - control_gain, axis=0),
        "error_count": error_count,
        "control_count": np.sum(control_intervene, axis=0),
        "error_positive_count": positive_count,
    }


def _sham_maxima(evaluations: list[dict[str, Any]]) -> list[float]:
    rng = np.random.default_rng(SHAM_SEED)
    reference = evaluations[0]
    signs = {
        pool: rng.choice(
            np.asarray([-1.0, 1.0]),
            size=(len(reference["rows_by_pool"][pool]), SHAM_REPLICATES),
        )
        for pool in ("pool1", "pool2")
    }
    maxima = np.zeros(SHAM_REPLICATES, dtype=float)
    for evaluation in evaluations:
        coefficients = {}
        for pool in ("pool1", "pool2"):
            fit = evaluation["fits_internal"][pool]
            coefficients[pool] = fit["inverse"] @ (
                fit["target_contributions"].T @ signs[pool]
            )
        left = coefficients["pool1"]
        right = coefficients["pool2"]
        denominator = np.linalg.norm(left, axis=0) * np.linalg.norm(right, axis=0)
        cosine = np.divide(
            np.sum(left * right, axis=0), denominator,
            out=np.zeros(SHAM_REPLICATES, dtype=float), where=denominator > 0.0,
        )
        heldout = {
            "pool1": _batched_pool(
                evaluation["rows_by_pool"]["pool1"], coefficients["pool2"],
                evaluation["fits_internal"]["pool2"], evaluation["config"],
            ),
            "pool2": _batched_pool(
                evaluation["rows_by_pool"]["pool2"], coefficients["pool1"],
                evaluation["fits_internal"]["pool1"], evaluation["config"],
            ),
        }
        total_error_count = heldout["pool1"]["error_count"] + heldout["pool2"]["error_count"]
        total_positive = (
            heldout["pool1"]["error_positive_count"]
            + heldout["pool2"]["error_positive_count"]
        )
        positive_rate = np.divide(
            total_positive, total_error_count,
            out=np.zeros(SHAM_REPLICATES, dtype=float), where=total_error_count > 0,
        )
        eligible = (
            (cosine >= MIN_COEFFICIENT_COSINE)
            & (total_error_count >= MIN_ERROR_INTERVENTIONS)
            & (positive_rate >= MIN_POSITIVE_REALIZATION_RATE)
        )
        for pool in ("pool1", "pool2"):
            metrics = heldout[pool]
            eligible &= metrics["error_count"] >= MIN_ERROR_INTERVENTIONS_PER_POOL
            eligible &= metrics["error_mean"] > 0.0
            eligible &= metrics["paired_mean"] > 0.0
            eligible &= metrics["control_mean"] >= MIN_CONTROL_MEAN_CP
        selection = np.minimum(
            heldout["pool1"]["paired_mean"], heldout["pool2"]["paired_mean"]
        )
        maxima = np.maximum(maxima, np.where(eligible, selection, 0.0))
    if not np.all(np.isfinite(maxima)):
        raise ValueError("non-finite action-margin familywise sham maximum")
    return maxima.tolist()


def _bootstrap_metrics(decisions: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    errors = [float(row["error"]["improvement_cp"]) for row in decisions]
    controls = [float(row["control"]["improvement_cp"]) for row in decisions]
    paired = [left - right for left, right in zip(errors, controls, strict=True)]
    quick = _quick(decisions)
    return {
        **quick,
        "error": ranker._bootstrap(errors, samples=BOOTSTRAP_SAMPLES, seed=seed),
        "control": ranker._bootstrap(controls, samples=BOOTSTRAP_SAMPLES, seed=seed + 1),
        "paired": ranker._bootstrap(paired, samples=BOOTSTRAP_SAMPLES, seed=seed + 2),
    }


def _compact(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in evaluation.items()
        if key not in {"decisions", "fits_internal", "rows_by_pool"}
    }


def screen(rows: list[dict[str, Any]], stable_indices: list[int]) -> dict[str, Any]:
    configurations = _configurations(stable_indices)
    evaluations = [_evaluate(rows, config) for config in configurations]
    eligible = [row for row in evaluations if row["eligible"]]
    best = max(
        eligible or evaluations,
        key=lambda row: (
            row["selection_score_min_pool_paired_mean_cp"],
            row["combined"]["paired_mean_cp"],
            -row["config"]["dimension"],
            -row["config"]["alpha"],
            -row["config"]["control_anchor_penalty"],
            -row["config"]["threshold_cp"],
        ),
    )
    sham_maxima = _sham_maxima(evaluations)
    sham_q99 = float(np.quantile(np.asarray(sham_maxima), 0.99))
    metrics = _bootstrap_metrics(best["decisions"], BOOTSTRAP_SEED)
    by_pool = {
        pool: _bootstrap_metrics(
            [row for row in best["decisions"] if row["source_pool"] == pool],
            BOOTSTRAP_SEED + 100 * index,
        )
        for index, pool in enumerate(("pool1", "pool2"), start=1)
    }
    selection_score = float(best["selection_score_min_pool_paired_mean_cp"])
    gates = {
        "best_candidate_structurally_eligible": best["eligible"],
        "oof_error_ci95_lower_gt_0cp": float(metrics["error"]["ci95"][0]) > 0.0,
        "oof_paired_ci95_lower_gt_0cp": float(metrics["paired"]["ci95"][0]) > 0.0,
        "oof_control_mean_at_least_minus_2cp": float(metrics["control"]["mean"]) >= MIN_CONTROL_MEAN_CP,
        "oof_error_positive_realization_rate_at_least_0_60": (
            metrics["error_positive_realization_rate"] is not None
            and metrics["error_positive_realization_rate"] >= MIN_POSITIVE_REALIZATION_RATE
        ),
        "selected_min_pool_paired_mean_exceeds_familywise_1000_sham_q99": selection_score > sham_q99,
    }
    for pool, pool_metrics in by_pool.items():
        gates[f"{pool}_error_mean_gt_0cp"] = float(pool_metrics["error"]["mean"]) > 0.0
        gates[f"{pool}_paired_mean_gt_0cp"] = float(pool_metrics["paired"]["mean"]) > 0.0
        gates[f"{pool}_control_mean_at_least_minus_2cp"] = (
            float(pool_metrics["control"]["mean"]) >= MIN_CONTROL_MEAN_CP
        )
    passed = all(gates.values())
    leaderboard = sorted(
        (_compact(row) for row in evaluations),
        key=lambda row: (
            row["selection_score_min_pool_paired_mean_cp"],
            row["combined"]["paired_mean_cp"],
        ),
        reverse=True,
    )
    return {
        "status": (
            "candidate_for_two_new_pool_confirmation"
            if passed else "action_margin_correction_not_established"
        ),
        "passed": passed,
        "candidate_family": {
            "supports": ["stable6", "full20"],
            "alphas": list(ALPHAS),
            "control_anchor_penalties": list(CONTROL_ANCHOR_PENALTIES),
            "thresholds_cp": list(THRESHOLDS_CP),
            "cap_cp": CAP_CP,
            "mode": MODE,
            "configurations": len(configurations),
            "selection_metric": "minimum_pool_oof_paired_error_minus_control_mean_cp",
            "heldout_direction": {"pool1": "fit_on_pool2", "pool2": "fit_on_pool1"},
            "control_objective": "zero_action_margin_movement_on_paired_controls",
        },
        "best_candidate": _compact(best),
        "oof_metrics": metrics,
        "oof_metrics_by_pool": by_pool,
        "familywise_sham": {
            "replicates": SHAM_REPLICATES,
            "seed": SHAM_SEED,
            "maximum_selection_score_q99_cp": sham_q99,
            "real_selection_score_cp": selection_score,
            "real_exceeds_q99": selection_score > sham_q99,
            "maxima_sha256": _digest(sham_maxima),
        },
        "leaderboard": leaderboard,
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "fresh_1524_reuse_for_confirmation_forbidden": True,
        "production_authorized": False,
    }


def run(
    training_report: dict[str, Any], failed_model: dict[str, Any],
    training_pairs: dict[str, Any], training_shards: list[dict[str, Any]],
    fresh_summary: dict[str, Any], fresh_report: dict[str, Any],
    fresh_pairs: dict[str, Any], fresh_shards: list[dict[str, Any]],
    target_cache: dict[str, Any], subspace_report: dict[str, Any],
    target_report: dict[str, Any], bucket_report: dict[str, Any],
) -> dict[str, Any]:
    rows, stable_indices, split, reproduction = _reconstruct(
        training_report, failed_model, training_pairs, training_shards,
        fresh_summary, fresh_report, fresh_pairs, fresh_shards,
        target_cache, subspace_report, target_report, bucket_report,
    )
    result = screen(rows, stable_indices)
    configurations = int(result["candidate_family"]["configurations"])
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "scientific_sources": {
            "target_specificity_status": "target_specificity_not_established",
            "bucket_treatment_status": "bucket_treatment_rule_not_established",
            "target_report_sha256": _digest(target_report),
            "bucket_report_sha256": _digest(bucket_report),
        },
        "purpose": "read_only_cross_pool_error_specific_action_margin_discovery",
        "feature_names": list(ranker.FEATURE_NAMES),
        "stable_support_indices": stable_indices,
        "stable_support_names": [ranker.FEATURE_NAMES[index] for index in stable_indices],
        "split_integrity": split,
        "reproduction": reproduction,
        "action_margin_screen": result,
        "accounting": {
            "authenticated_fresh_pairs_read": len(rows),
            "new_exact_target_computations": 0,
            "diagnostic_base_residual_fits_on_immutable_1508": 1,
            "diagnostic_action_margin_fit_equivalents": 2 * configurations * (1 + SHAM_REPLICATES),
            "fresh_label_pattern_eval_fits": 0,
            "production_model_fits": 0,
            "strength_games": 0,
            "new_selfplay_games": 0,
            "frozen_reads": 0,
        },
        "action_margin_candidate_established": result["passed"],
        "new_fresh_pool_preregistration_recommended": result["passed"],
        "anchored_local_refit_authorized": False,
        "production_model_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": (
            "freeze_action_margin_rule_then_confirm_on_two_entirely_new_pools"
            if result["passed"] else None
        ),
    }


def parser() -> argparse.ArgumentParser:
    out = argparse.ArgumentParser(description=__doc__)
    out.add_argument("--training-report", type=Path, required=True)
    out.add_argument("--failed-model", type=Path, required=True)
    out.add_argument("--training-pairs", type=Path, required=True)
    out.add_argument("--training-shard", type=Path, action="append", required=True)
    out.add_argument("--fresh-summary", type=Path, required=True)
    out.add_argument("--fresh-report", type=Path, required=True)
    out.add_argument("--fresh-pairs", type=Path, required=True)
    out.add_argument("--fresh-shard", type=Path, action="append", required=True)
    out.add_argument("--target-cache", type=Path, required=True)
    out.add_argument("--subspace-report", type=Path, required=True)
    out.add_argument("--target-report", type=Path, required=True)
    out.add_argument("--bucket-report", type=Path, required=True)
    out.add_argument("--report", type=Path, required=True)
    return out


def main() -> int:
    args = parser().parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    report = run(
        load(args.training_report), load(args.failed_model), load(args.training_pairs),
        [load(path) for path in args.training_shard],
        load(args.fresh_summary), load(args.fresh_report), load(args.fresh_pairs),
        [load(path) for path in args.fresh_shard], load(args.target_cache),
        load(args.subspace_report), load(args.target_report), load(args.bucket_report),
    )
    _publish(args.report, report)
    print(json.dumps({
        "verdict": report["verdict"],
        "status": report["action_margin_screen"]["status"],
        "best_candidate": report["action_margin_screen"]["best_candidate"]["config"]["name"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
