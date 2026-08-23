#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only causal atlas of error-specific treatment buckets.

The stable six-feature screen was not target-specific on 1524.  This follow-up
does not refit PatternEval.  It replays the certified 1524 decisions exactly,
then searches a preregistered finite family over all 20 single buckets,
joint-bucket and
phase-conditional treatment gates.  Every coefficient is evaluated on the
opposite opening/game-disjoint pool.  The selected discovery score is compared
against the maximum over the entire family for 1,000 stratified sign shams.

Any positive result is discovery-only and must be frozen and confirmed on two
entirely new pools before it can authorize an anchored local refit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_endgame_abstention_confirmation as confirmation
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge
from jobs.tools import l3_curriculum_error_target_specificity_autopsy as target
from jobs.tools import l3_curriculum_error_trace_residual_training as historical


SCHEMA = "jass.l3_curriculum_error_bucket_treatment_atlas.v1"
READY = "JASS_CURRICULUM_ERROR_BUCKET_TREATMENT_ATLAS_READY"
TARGET_SOURCE_SCHEMA = "jass.l3_curriculum_error_target_specificity_autopsy.v1"
RIDGES = (0.1, 1.0, 10.0, 100.0, 1000.0)
SHAM_REPLICATES = 1000
SHAM_SEED = 2026082316
BOOTSTRAP_SAMPLES = 200_000
BOOTSTRAP_SEED = 2026082317
MIN_COEFFICIENT_COSINE = 0.50
MIN_ERROR_INTERVENTIONS = 24
MIN_CONTROL_INTERVENTIONS = 18
MIN_ERROR_INTERVENTIONS_PER_POOL = 8
MIN_CONTROL_INTERVENTIONS_PER_POOL = 6
MIN_POSITIVE_REALIZATION_RATE = 0.60
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


def _require_negative_target_report(report: dict[str, Any]) -> None:
    screen = report.get("cross_pool_uplift_screen", {})
    if (
        report.get("schema") != TARGET_SOURCE_SCHEMA
        or report.get("verdict") != target.READY
        or report.get("passed") is not True
        or screen.get("passed") is not False
        or screen.get("status") != "target_specificity_not_established"
        or report.get("new_fresh_pool_preregistration_recommended") is not False
        or report.get("production_model_authorized") is not False
    ):
        raise ValueError("bucket atlas requires certified negative target-specificity source")


def _reconstruct(
    training_report: dict[str, Any],
    failed_model: dict[str, Any],
    training_pairs: dict[str, Any],
    training_shards: list[dict[str, Any]],
    fresh_summary: dict[str, Any],
    fresh_report: dict[str, Any],
    fresh_pairs: dict[str, Any],
    fresh_shards: list[dict[str, Any]],
    target_cache: dict[str, Any],
    subspace_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], list[int]]:
    target._require_source(fresh_summary, fresh_report)
    stable_indices, _stable_names = target._require_subspace(subspace_report)
    ridge._check_source(training_report, failed_model)
    training_rows, training_identities = historical._load_rows(training_pairs, training_shards)
    fresh_rows, fresh_identities = target.fresh._load_fresh_rows(
        fresh_pairs, fresh_shards, pair_count=target.FRESH_PAIRS
    )
    if training_identities != fresh_identities or fresh_report.get("identities") != fresh_identities:
        raise ValueError("1508/1524 identity drift")
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        if subspace_report.get(key) != fresh_identities[key]:
            raise ValueError(f"1525 stable support identity drift: {key}")
    if target_cache.get("schema") != target.fresh.SCHEMA_CACHE:
        raise ValueError("1524 target-cache schema drift")
    model = ridge._fit(training_rows, alpha=300.0)
    base_decisions = ridge._decisions(
        fresh_rows,
        {row["pair_id"]: model for row in fresh_rows},
        cap_cp=100.0,
        threshold_cp=10.0,
        mode="strict_both_change",
    )
    decisions, rule_proof = confirmation._apply_endgame_abstention(fresh_rows, base_decisions)
    reproduced = confirmation._metrics(decisions, seed=target.SOURCE_BOOTSTRAP_SEED)
    reproduced_compact = {key: value for key, value in reproduced.items() if key != "paired_values_cp"}
    if not target.tail._same(reproduced_compact, fresh_report.get("metrics")):
        raise ValueError("1524 metric reproduction drift")
    if not target.tail._same(rule_proof, fresh_report.get("rule_proof")):
        raise ValueError("1524 rule proof drift")

    all_indices = list(range(len(ranker.FEATURE_NAMES)))
    rows: list[dict[str, Any]] = []
    for source, decision in zip(fresh_rows, decisions, strict=True):
        row: dict[str, Any] = {
            "pair_id": int(source["pair_id"]),
            "source_pool": str(source["source_pool"]),
        }
        for role in ("error", "control"):
            phase = confirmation._phase(source[role])
            row[role] = {
                "intervention": bool(decision[role]["intervention"]),
                "gain_cp": float(decision[role]["improvement_cp"]),
                "full_vector": target._state_vector(
                    source[role], decision[role], model, all_indices
                ).tolist(),
                "phase": phase,
                "opening_id": str(source[role]["profile"]["source"]["opening_id"]),
                "game_uid": str(source[role]["profile"]["source"]["game_uid"]),
            }
        row["paired_gain_cp"] = row["error"]["gain_cp"] - row["control"]["gain_cp"]
        rows.append(row)

    split = target._split_identity(training_rows, fresh_rows)
    split_gates = {
        "fresh_pairs_exactly_600": len(rows) == target.FRESH_PAIRS,
        "pool_pair_counts_sum_to_600": sum(split["pool_pair_counts"].values()) == target.FRESH_PAIRS,
        "pool_opening_overlap_zero": split["pool_opening_overlap"] == 0,
        "pool_game_overlap_zero": split["pool_game_overlap"] == 0,
        "training_fresh_opening_overlap_zero": split["training_fresh_opening_overlap"] == 0,
        "training_fresh_game_overlap_zero": split["training_fresh_game_overlap"] == 0,
    }
    if not all(split_gates.values()):
        raise ValueError(f"bucket atlas split leakage: {split_gates}")
    return rows, {**split, "gates": split_gates}, {
        "metrics": reproduced_compact,
        "rule_proof": rule_proof,
        "identities": fresh_identities,
        "base_model_coef_sha256": _digest(np.asarray(model["coef"]).tolist()),
    }, stable_indices


def _configurations(stable_indices: list[int], phases: list[str]) -> list[dict[str, Any]]:
    supports: list[tuple[str, list[int], bool]] = [
        (f"singleton_{name}", [index], False)
        for index, name in enumerate(ranker.FEATURE_NAMES)
    ]
    supports.extend([
        ("stable6", list(stable_indices), False),
        ("full20", list(range(len(ranker.FEATURE_NAMES))), False),
        ("stable6_phase", list(stable_indices), True),
        ("full20_phase", list(range(len(ranker.FEATURE_NAMES))), True),
    ])
    configs = []
    for support_name, indices, phase_interaction in supports:
        names = [ranker.FEATURE_NAMES[index] for index in indices]
        if phase_interaction:
            names = [f"{phase}::{name}" for phase in phases for name in names]
        for penalty in RIDGES:
            configs.append({
                "name": f"{support_name}__ridge_{penalty:g}",
                "support_name": support_name,
                "indices": indices,
                "phase_interaction": phase_interaction,
                "phases": phases,
                "feature_names": names,
                "ridge": penalty,
                "dimension": len(names),
            })
    return configs


def _vector(state: dict[str, Any], config: dict[str, Any]) -> np.ndarray:
    base = np.asarray(state["full_vector"], dtype=float)[config["indices"]]
    if not config["phase_interaction"]:
        return base
    return np.concatenate([
        base if state["phase"] == phase else np.zeros_like(base)
        for phase in config["phases"]
    ])


def _matrices(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, np.ndarray]:
    error = np.asarray([_vector(row["error"], config) for row in rows], dtype=float)
    control = np.asarray([_vector(row["control"], config) for row in rows], dtype=float)
    return {
        "error": error,
        "control": control,
        "pair": error - control,
        "target": np.asarray([row["paired_gain_cp"] for row in rows], dtype=float),
        "error_gain": np.asarray([row["error"]["gain_cp"] for row in rows], dtype=float),
        "control_gain": np.asarray([row["control"]["gain_cp"] for row in rows], dtype=float),
        "error_active": np.asarray([row["error"]["intervention"] for row in rows], dtype=bool),
        "control_active": np.asarray([row["control"]["intervention"] for row in rows], dtype=bool),
    }


def _fit(matrix: np.ndarray, target_values: np.ndarray, penalty: float) -> dict[str, Any]:
    active = np.any(np.abs(matrix) > EPS, axis=1)
    x = matrix[active]
    y = target_values[active]
    if not len(x):
        raise ValueError("bucket treatment fit has zero active pairs")
    gram = x.T @ x / len(x)
    coefficient = np.linalg.solve(
        gram + penalty * np.eye(x.shape[1]), x.T @ y / len(x)
    )
    return {
        "coefficient": coefficient,
        "active_pairs": int(len(x)),
        "rank": int(np.linalg.matrix_rank(x)),
        "condition_number": float(np.linalg.cond(gram + penalty * np.eye(x.shape[1]))),
        "active_mask": active,
        "inverse": np.linalg.inv(gram + penalty * np.eye(x.shape[1])),
        "x": x,
    }


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(left @ right / denominator) if denominator > 0.0 else 0.0


def _quick(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = np.asarray([row["error"]["adjusted_gain_cp"] for row in rows], dtype=float)
    controls = np.asarray([row["control"]["adjusted_gain_cp"] for row in rows], dtype=float)
    paired = errors - controls
    retained_error = [row["error"] for row in rows if row["error"]["retained"]]
    retained_control = [row["control"] for row in rows if row["control"]["retained"]]
    return {
        "pairs": len(rows),
        "error_mean_cp": float(np.mean(errors)),
        "control_mean_cp": float(np.mean(controls)),
        "paired_mean_cp": float(np.mean(paired)),
        "error_interventions": len(retained_error),
        "control_interventions": len(retained_control),
        "error_positive_realization_rate": (
            float(np.mean([float(row["gain_cp"]) > 0.0 for row in retained_error]))
            if retained_error else None
        ),
    }


def _evaluate(rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    pools = {pool: [row for row in rows if row["source_pool"] == pool] for pool in ("pool1", "pool2")}
    matrices = {pool: _matrices(pool_rows, config) for pool, pool_rows in pools.items()}
    fits = {
        pool: _fit(matrix["pair"], matrix["target"], float(config["ridge"]))
        for pool, matrix in matrices.items()
    }
    coefficients = {pool: fit["coefficient"] for pool, fit in fits.items()}
    adjusted: list[dict[str, Any]] = []
    for heldout_pool in ("pool1", "pool2"):
        training_pool = "pool2" if heldout_pool == "pool1" else "pool1"
        coefficient = coefficients[training_pool]
        for source in pools[heldout_pool]:
            output = {"pair_id": source["pair_id"], "source_pool": heldout_pool}
            for role in ("error", "control"):
                score = float(_vector(source[role], config) @ coefficient)
                retained = bool(source[role]["intervention"] and score > 0.0)
                output[role] = {
                    **source[role],
                    "treatment_score": score,
                    "retained": retained,
                    "adjusted_gain_cp": source[role]["gain_cp"] if retained else 0.0,
                }
            adjusted.append(output)
    by_pool = {
        pool: _quick([row for row in adjusted if row["source_pool"] == pool])
        for pool in ("pool1", "pool2")
    }
    combined = _quick(adjusted)
    cosine = _cosine(coefficients["pool1"], coefficients["pool2"])
    minimum_rank = min(fit["rank"] for fit in fits.values())
    rank_requirement = min(3, int(config["dimension"]))
    structural = {
        "ranks_sufficient": minimum_rank >= rank_requirement,
        "coefficient_cosine_at_least_0_50": cosine >= MIN_COEFFICIENT_COSINE,
        "error_interventions_at_least_24": combined["error_interventions"] >= MIN_ERROR_INTERVENTIONS,
        "control_interventions_at_least_18": combined["control_interventions"] >= MIN_CONTROL_INTERVENTIONS,
    }
    for pool, metric in by_pool.items():
        structural[f"{pool}_error_interventions_at_least_8"] = metric["error_interventions"] >= MIN_ERROR_INTERVENTIONS_PER_POOL
        structural[f"{pool}_control_interventions_at_least_6"] = metric["control_interventions"] >= MIN_CONTROL_INTERVENTIONS_PER_POOL
        structural[f"{pool}_error_mean_gt_0cp"] = metric["error_mean_cp"] > 0.0
        structural[f"{pool}_paired_mean_gt_0cp"] = metric["paired_mean_cp"] > 0.0
        structural[f"{pool}_control_mean_at_least_minus_2cp"] = metric["control_mean_cp"] >= -2.0
    eligible = all(structural.values())
    selection_score = min(metric["paired_mean_cp"] for metric in by_pool.values())
    return {
        "config": config,
        "coefficients": {pool: value.tolist() for pool, value in coefficients.items()},
        "coefficient_sha256": _digest({pool: value.tolist() for pool, value in coefficients.items()}),
        "coefficient_cosine": cosine,
        "fits": {
            pool: {key: value for key, value in fit.items() if key not in {"coefficient", "active_mask", "inverse", "x"}}
            for pool, fit in fits.items()
        },
        "combined": combined,
        "by_pool": by_pool,
        "structural_gates": structural,
        "eligible": eligible,
        "selection_score_min_pool_paired_mean_cp": selection_score,
        "adjusted": adjusted,
        "matrices": matrices,
        "fits_internal": fits,
    }


def _sham_maxima(evaluations: list[dict[str, Any]]) -> list[float]:
    rng = np.random.default_rng(SHAM_SEED)
    # The always-abstain rule is the zero-score baseline for every replicate.
    # It keeps a degenerate sham draw finite without granting it interventions.
    maxima = np.zeros(SHAM_REPLICATES, dtype=float)
    reference = evaluations[0]
    signs_by_pool = {
        pool: rng.choice(
            np.asarray([-1.0, 1.0]),
            size=(len(reference["matrices"][pool]["target"]), SHAM_REPLICATES),
        )
        for pool in ("pool1", "pool2")
    }
    for evaluation in evaluations:
        pool_scores: dict[str, np.ndarray] = {}
        pool_counts: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for heldout_pool in ("pool1", "pool2"):
            training_pool = "pool2" if heldout_pool == "pool1" else "pool1"
            train_matrix = evaluation["matrices"][training_pool]
            train_fit = evaluation["fits_internal"][training_pool]
            signs = signs_by_pool[training_pool]
            active = train_fit["active_mask"]
            x = train_fit["x"]
            y = train_matrix["target"][active, None] * signs[active]
            coefficients = train_fit["inverse"] @ (x.T @ y / len(x))
            heldout = evaluation["matrices"][heldout_pool]
            error_retained = heldout["error_active"][:, None] & ((heldout["error"] @ coefficients) > 0.0)
            control_retained = heldout["control_active"][:, None] & ((heldout["control"] @ coefficients) > 0.0)
            paired = np.mean(
                heldout["error_gain"][:, None] * error_retained
                - heldout["control_gain"][:, None] * control_retained,
                axis=0,
            )
            pool_scores[heldout_pool] = paired
            pool_counts[heldout_pool] = (
                np.sum(error_retained, axis=0), np.sum(control_retained, axis=0)
            )
        score = np.minimum(pool_scores["pool1"], pool_scores["pool2"])
        count_guard = np.ones(SHAM_REPLICATES, dtype=bool)
        for pool in ("pool1", "pool2"):
            errors, controls = pool_counts[pool]
            count_guard &= errors >= MIN_ERROR_INTERVENTIONS_PER_POOL
            count_guard &= controls >= MIN_CONTROL_INTERVENTIONS_PER_POOL
        maxima = np.maximum(maxima, np.where(count_guard, score, -np.inf))
    if not np.all(np.isfinite(maxima)):
        raise ValueError("non-finite familywise sham maximum")
    return maxima.tolist()


def _compact_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in evaluation.items() if key not in {
        "adjusted", "matrices", "fits_internal"
    }}


def screen(rows: list[dict[str, Any]], stable_indices: list[int]) -> dict[str, Any]:
    phases = sorted({row[role]["phase"] for row in rows for role in ("error", "control")})
    configs = _configurations(stable_indices, phases)
    evaluations = [_evaluate(rows, config) for config in configs]
    eligible = [row for row in evaluations if row["eligible"]]
    best = max(
        eligible or evaluations,
        key=lambda row: (
            row["selection_score_min_pool_paired_mean_cp"],
            row["combined"]["paired_mean_cp"],
            -row["config"]["dimension"],
            -float(row["config"]["ridge"]),
        ),
    )
    sham_maxima = _sham_maxima(evaluations)
    sham_q99 = float(np.quantile(np.asarray(sham_maxima), 0.99))
    adjusted = best["adjusted"]
    metrics = target._gate_metrics(adjusted, seed=BOOTSTRAP_SEED)
    by_pool = {
        pool: target._gate_metrics(
            [row for row in adjusted if row["source_pool"] == pool],
            seed=BOOTSTRAP_SEED + 100 * index,
        )
        for index, pool in enumerate(("pool1", "pool2"), start=1)
    }
    compact = lambda row: {key: value for key, value in row.items() if key != "paired_values_cp"}
    selection_score = float(best["selection_score_min_pool_paired_mean_cp"])
    gates = {
        "best_candidate_structurally_eligible": best["eligible"],
        "oof_error_ci95_lower_gt_0cp": float(metrics["error"]["ci95"][0]) > 0.0,
        "oof_paired_ci95_lower_gt_0cp": float(metrics["paired"]["ci95"][0]) > 0.0,
        "oof_control_mean_at_least_minus_2cp": float(metrics["control"]["mean"]) >= -2.0,
        "oof_error_positive_realization_rate_at_least_0_60": metrics["error_positive_realization_rate"] is not None and metrics["error_positive_realization_rate"] >= MIN_POSITIVE_REALIZATION_RATE,
        "selected_min_pool_paired_mean_exceeds_familywise_1000_sham_q99": selection_score > sham_q99,
    }
    for pool, row in by_pool.items():
        gates[f"{pool}_error_mean_gt_0cp"] = float(row["error"]["mean"]) > 0.0
        gates[f"{pool}_paired_mean_gt_0cp"] = float(row["paired"]["mean"]) > 0.0
        gates[f"{pool}_control_mean_at_least_minus_2cp"] = float(row["control"]["mean"]) >= -2.0
    passed = all(gates.values())
    feature_atlas = [
        _compact_evaluation(row)
        for row in evaluations
        if row["config"]["support_name"].startswith("singleton_")
        and float(row["config"]["ridge"]) == 10.0
    ]
    leaderboard = sorted(
        (_compact_evaluation(row) for row in evaluations),
        key=lambda row: (
            row["selection_score_min_pool_paired_mean_cp"],
            row["combined"]["paired_mean_cp"],
        ),
        reverse=True,
    )[:20]
    return {
        "status": "candidate_for_new_pool_preregistration" if passed else "bucket_treatment_rule_not_established",
        "passed": passed,
        "phases": phases,
        "candidate_family": {
            "supports": 24,
            "ridges": list(RIDGES),
            "configurations": len(configs),
            "selection_metric": "minimum_pool_oof_paired_mean_cp",
            "heldout_direction": {"pool1": "fit_on_pool2", "pool2": "fit_on_pool1"},
        },
        "best_candidate": _compact_evaluation(best),
        "oof_metrics": compact(metrics),
        "oof_metrics_by_pool": {pool: compact(row) for pool, row in by_pool.items()},
        "familywise_sham": {
            "replicates": SHAM_REPLICATES,
            "seed": SHAM_SEED,
            "maximum_selection_score_q99_cp": sham_q99,
            "real_selection_score_cp": selection_score,
            "real_exceeds_q99": selection_score > sham_q99,
            "maxima_sha256": _digest(sham_maxima),
        },
        "feature_atlas_ridge10": feature_atlas,
        "leaderboard_top20": leaderboard,
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "fresh_1524_reuse_for_confirmation_forbidden": True,
        "production_authorized": False,
    }


def atlas(
    training_report: dict[str, Any], failed_model: dict[str, Any],
    training_pairs: dict[str, Any], training_shards: list[dict[str, Any]],
    fresh_summary: dict[str, Any], fresh_report: dict[str, Any],
    fresh_pairs: dict[str, Any], fresh_shards: list[dict[str, Any]],
    target_cache: dict[str, Any], subspace_report: dict[str, Any],
    target_report: dict[str, Any],
) -> dict[str, Any]:
    _require_negative_target_report(target_report)
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
    rows, split, reproduction, stable_indices = _reconstruct(
        training_report, failed_model, training_pairs, training_shards,
        fresh_summary, fresh_report, fresh_pairs, fresh_shards,
        target_cache, subspace_report,
    )
    result = screen(rows, stable_indices)
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "scientific_source": {
            "target_specificity_status": "target_specificity_not_established",
            "target_specificity_report_sha256": _digest(target_report),
        },
        "purpose": "read_only_familywise_cross_pool_error_bucket_treatment_discovery",
        "feature_names": list(ranker.FEATURE_NAMES),
        "stable_support_indices": stable_indices,
        "stable_support_names": [ranker.FEATURE_NAMES[index] for index in stable_indices],
        "split_integrity": split,
        "reproduction": reproduction,
        "bucket_treatment_screen": result,
        "accounting": {
            "authenticated_fresh_pairs_read": len(rows),
            "new_exact_target_computations": 0,
            "diagnostic_base_residual_fits_on_immutable_1508": 1,
            "diagnostic_bucket_fit_equivalents": 2 * result["candidate_family"]["configurations"] * (1 + SHAM_REPLICATES),
            "fresh_label_pattern_eval_fits": 0,
            "production_model_fits": 0,
            "strength_games": 0,
            "new_selfplay_games": 0,
            "frozen_reads": 0,
        },
        "bucket_treatment_rule_candidate_established": result["passed"],
        "new_fresh_pool_preregistration_recommended": result["passed"],
        "anchored_local_refit_authorized": False,
        "production_model_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "freeze_best_rule_then_confirm_on_two_entirely_new_pools" if result["passed"] else None,
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
    out.add_argument("--report", type=Path, required=True)
    return out


def main() -> int:
    args = parser().parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    report = atlas(
        load(args.training_report), load(args.failed_model), load(args.training_pairs),
        [load(path) for path in args.training_shard],
        load(args.fresh_summary), load(args.fresh_report), load(args.fresh_pairs),
        [load(path) for path in args.fresh_shard], load(args.target_cache),
        load(args.subspace_report), load(args.target_report),
    )
    _publish(args.report, report)
    print(json.dumps({
        "verdict": report["verdict"],
        "status": report["bucket_treatment_screen"]["status"],
        "best_candidate": report["bucket_treatment_screen"]["best_candidate"]["config"]["name"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
