#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Diagnose why the confirmed residual helps controls as much as errors.

The 1524 labels are used for descriptive, cross-pool discovery only.  The
underlying alpha=300 residual is always re-fitted on immutable 1508 rows.  A
six-dimensional uplift screen is then trained pool1->pool2 and pool2->pool1
on the independently established 1525 support.  Nothing produced here is a
production model: any candidate must be preregistered and confirmed on new
opening/game-disjoint pools before an anchored refit can be authorized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from jobs.tools import l3_curriculum_error_endgame_abstention_confirmation as confirmation
from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as fresh
from jobs.tools import l3_curriculum_error_fresh_tail_autopsy as tail
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge
from jobs.tools import l3_curriculum_error_residual_stable_subspace_screen as subspace
from jobs.tools import l3_curriculum_error_trace_residual_training as historical
from jobs.tools import l3_curriculum_search_error_atlas as atlas


SCHEMA = "jass.l3_curriculum_error_target_specificity_autopsy.v1"
READY = "JASS_CURRICULUM_ERROR_TARGET_SPECIFICITY_AUTOPSY_READY"
SOURCE_SCHEMA = "jass.curriculum_error_endgame_abstention_confirmation_terminal.v1"
FRESH_PAIRS = 600
UPLIFT_RIDGE = 10.0
SHAM_REPLICATES = 1000
SHAM_SEED = 2026082314
BOOTSTRAP_SAMPLES = 200_000
BOOTSTRAP_SEED = 2026082315
MIN_SUPPORT_RANK = 3
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


def _require_source(summary: dict[str, Any], report: dict[str, Any]) -> None:
    if (
        summary.get("schema") != SOURCE_SCHEMA
        or summary.get("verdict") != confirmation.NOT_ESTABLISHED
        or summary.get("passed") is not False
        or report.get("schema") != confirmation.SCHEMA_REPORT
        or report.get("verdict") != confirmation.NOT_ESTABLISHED
        or report.get("passed") is not False
    ):
        raise ValueError("target-specificity autopsy requires certified negative 1524")
    for key in (
        "verdict", "passed", "selected_hypothesis", "fresh_pairs",
        "fresh_pairs_by_pool", "metrics", "metrics_by_pool", "rule_proof",
        "symmetry_drop", "sham", "gates", "failed_gates", "identities",
        "new_target_states", "fresh_confirmation_target_states",
        "discarded_labelled_states", "exact_target_batches",
        "exact_action_value_reads", "residual_fits", "diagnostic_fits",
    ):
        if not tail._same(summary.get(key), report.get(key)):
            raise ValueError(f"1524 terminal/report drift: {key}")
    if int(report.get("fresh_pairs", -1)) != FRESH_PAIRS:
        raise ValueError("1524 fresh pair cardinality drift")
    if report.get("fresh_labels_used_for_fit") is not False:
        raise ValueError("1524 reports fresh-label fitting")
    expected = {"alpha": 300.0, "cap_cp": 100.0, "mode": "strict_both_change", "threshold_cp": 10.0}
    selected = report.get("selected_hypothesis", {})
    if any(not tail._same(selected.get(key), value) for key, value in expected.items()):
        raise ValueError(f"1524 frozen hypothesis drift: {selected}")
    for key in ("pattern_eval_fits", "production_model_fits", "strength_games", "new_selfplay_games", "frozen_reads"):
        if int(report.get(key, -1)) != 0:
            raise ValueError(f"1524 forbidden counter drift: {key}")


def _require_subspace(report: dict[str, Any]) -> tuple[list[int], list[str]]:
    if (
        report.get("schema") != subspace.SCHEMA
        or report.get("verdict") != subspace.READY
        or report.get("passed") is not True
        or report.get("stable_subspace_candidate_established") is not True
    ):
        raise ValueError("target-specificity autopsy requires passed 1525 subspace")
    analysis = report.get("analysis", {})
    indices = [int(value) for value in analysis.get("selected_feature_indices", [])]
    names = [str(value) for value in analysis.get("selected_feature_names", [])]
    if len(indices) != 6 or len(names) != 6:
        raise ValueError("1525 support must contain exactly six features")
    return indices, names


def _state_vector(
    state: dict[str, Any], decision: dict[str, Any], model: dict[str, Any], support: list[int]
) -> np.ndarray:
    vector = np.zeros(len(support), dtype=float)
    if not bool(decision["intervention"]):
        return vector
    proposed = str(decision["action"])
    original_anchor = ridge._best(state["original_scores"])
    image_anchor = ridge._best(state["image_scores"])
    rms = np.asarray(model["rms"], dtype=float)
    delta = (
        (np.asarray(state["features"][proposed]) - np.asarray(state["features"][original_anchor]))
        + (np.asarray(state["features"][proposed]) - np.asarray(state["features"][image_anchor]))
    ) / (2.0 * rms)
    vector[:] = delta[support]
    if not np.all(np.isfinite(vector)):
        raise ValueError("non-finite uplift state vector")
    return vector


def _split_identity(
    training_rows: list[dict[str, Any]], fresh_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    def values(rows: list[dict[str, Any]], field: str) -> set[str]:
        return {
            str(row[role]["profile"]["source"][field])
            for row in rows for role in ("error", "control")
        }

    pools = {
        pool: [row for row in fresh_rows if str(row["source_pool"]) == pool]
        for pool in ("pool1", "pool2")
    }
    pool_openings = {pool: values(rows, "opening_id") for pool, rows in pools.items()}
    pool_games = {pool: values(rows, "game_uid") for pool, rows in pools.items()}
    training_openings = values(training_rows, "opening_id")
    training_games = values(training_rows, "game_uid")
    return {
        "pool_pair_counts": {pool: len(rows) for pool, rows in pools.items()},
        "pool_opening_counts": {pool: len(rows) for pool, rows in pool_openings.items()},
        "pool_game_counts": {pool: len(rows) for pool, rows in pool_games.items()},
        "pool_opening_overlap": len(pool_openings["pool1"] & pool_openings["pool2"]),
        "pool_game_overlap": len(pool_games["pool1"] & pool_games["pool2"]),
        "training_fresh_opening_overlap": len(training_openings & set().union(*pool_openings.values())),
        "training_fresh_game_overlap": len(training_games & set().union(*pool_games.values())),
    }


def _fit_uplift(rows: list[dict[str, Any]], *, target_signs: np.ndarray | None = None) -> dict[str, Any]:
    x = np.asarray([row["pair_vector"] for row in rows], dtype=float)
    y = np.asarray([row["paired_gain_cp"] for row in rows], dtype=float)
    if target_signs is not None:
        if target_signs.shape != y.shape:
            raise ValueError("uplift sham sign shape drift")
        y = y * target_signs
    active = np.any(np.abs(x) > EPS, axis=1)
    x = x[active]
    y = y[active]
    if not len(x):
        raise ValueError("uplift fit has zero active pairs")
    gram = x.T @ x / len(x)
    target = x.T @ y / len(x)
    coefficient = np.linalg.solve(gram + UPLIFT_RIDGE * np.eye(x.shape[1]), target)
    return {
        "coefficient": coefficient,
        "active_pairs": int(len(x)),
        "rank": int(np.linalg.matrix_rank(x)),
        "condition_number": float(np.linalg.cond(gram + UPLIFT_RIDGE * np.eye(x.shape[1]))),
    }


def _apply_gate(rows: list[dict[str, Any]], coefficient_by_pool: dict[str, np.ndarray]) -> tuple[list[dict[str, Any]], list[float]]:
    adjusted = []
    scores = []
    for row in rows:
        coefficient = coefficient_by_pool[str(row["source_pool"])]
        output = {"pair_id": row["pair_id"], "source_pool": row["source_pool"]}
        for role in ("error", "control"):
            state = row[role]
            score = float(np.asarray(state["vector"]) @ coefficient)
            retain = bool(state["intervention"] and score > 0.0)
            output[role] = {
                **state,
                "uplift_score": score,
                "retained": retain,
                "adjusted_gain_cp": float(state["gain_cp"]) if retain else 0.0,
            }
            if state["intervention"]:
                scores.append(score)
        adjusted.append(output)
    return adjusted, scores


def _gate_metrics(rows: list[dict[str, Any]], *, seed: int) -> dict[str, Any]:
    errors = [float(row["error"]["adjusted_gain_cp"]) for row in rows]
    controls = [float(row["control"]["adjusted_gain_cp"]) for row in rows]
    paired = [left - right for left, right in zip(errors, controls, strict=True)]
    retained_error = [row["error"] for row in rows if row["error"]["retained"]]
    retained_control = [row["control"] for row in rows if row["control"]["retained"]]
    return {
        "pairs": len(rows),
        "error": atlas._bootstrap(errors, samples=BOOTSTRAP_SAMPLES, seed=seed),
        "control": atlas._bootstrap(controls, samples=BOOTSTRAP_SAMPLES, seed=seed + 1),
        "paired": atlas._bootstrap(paired, samples=BOOTSTRAP_SAMPLES, seed=seed + 2),
        "error_interventions": len(retained_error),
        "control_interventions": len(retained_control),
        "error_positive_realization_rate": (
            float(np.mean([float(row["gain_cp"]) > 0.0 for row in retained_error]))
            if retained_error else None
        ),
        "paired_values_cp": paired,
    }


def _coefficient_cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(left @ right / denominator) if denominator > 0.0 else 0.0


def _cross_pool_screen(pair_rows: list[dict[str, Any]], support_names: list[str]) -> dict[str, Any]:
    pools = {pool: [row for row in pair_rows if row["source_pool"] == pool] for pool in ("pool1", "pool2")}
    fits = {pool: _fit_uplift(rows) for pool, rows in pools.items()}
    coefficients = {pool: fits[pool]["coefficient"] for pool in pools}
    # Held-out pool1 uses the model trained on pool2 and vice versa.
    heldout_coefficients = {"pool1": coefficients["pool2"], "pool2": coefficients["pool1"]}
    adjusted, scores = _apply_gate(pair_rows, heldout_coefficients)
    metrics = _gate_metrics(adjusted, seed=BOOTSTRAP_SEED)
    by_pool = {
        pool: _gate_metrics([row for row in adjusted if row["source_pool"] == pool], seed=BOOTSTRAP_SEED + 100 * index)
        for index, pool in enumerate(("pool1", "pool2"), start=1)
    }

    rng = np.random.default_rng(SHAM_SEED)
    sham_means = []
    for _replicate in range(SHAM_REPLICATES):
        sham_fits = {}
        for pool, rows in pools.items():
            signs = rng.choice(np.asarray([-1.0, 1.0]), size=len(rows))
            sham_fits[pool] = _fit_uplift(rows, target_signs=signs)["coefficient"]
        sham_adjusted, _ = _apply_gate(
            pair_rows, {"pool1": sham_fits["pool2"], "pool2": sham_fits["pool1"]}
        )
        sham_means.append(float(np.mean([
            row["error"]["adjusted_gain_cp"] - row["control"]["adjusted_gain_cp"]
            for row in sham_adjusted
        ])))
    sham_q99 = float(np.quantile(np.asarray(sham_means), 0.99))
    real_mean = float(metrics["paired"]["mean"])
    cosine = _coefficient_cosine(coefficients["pool1"], coefficients["pool2"])
    gates = {
        "both_training_pool_support_ranks_at_least_3": all(fits[pool]["rank"] >= MIN_SUPPORT_RANK for pool in pools),
        "coefficient_cosine_at_least_0_50": cosine >= MIN_COEFFICIENT_COSINE,
        "oof_error_interventions_at_least_24": metrics["error_interventions"] >= MIN_ERROR_INTERVENTIONS,
        "oof_control_interventions_at_least_18": metrics["control_interventions"] >= MIN_CONTROL_INTERVENTIONS,
        "oof_error_ci95_lower_gt_0cp": float(metrics["error"]["ci95"][0]) > 0.0,
        "oof_paired_ci95_lower_gt_0cp": float(metrics["paired"]["ci95"][0]) > 0.0,
        "oof_control_mean_at_least_minus_2cp": float(metrics["control"]["mean"]) >= -2.0,
        "oof_error_positive_realization_rate_at_least_0_60": metrics["error_positive_realization_rate"] is not None and metrics["error_positive_realization_rate"] >= MIN_POSITIVE_REALIZATION_RATE,
        "oof_real_paired_mean_exceeds_1000_sham_q99": real_mean > sham_q99,
    }
    for pool, row in by_pool.items():
        gates[f"{pool}_error_interventions_at_least_8"] = row["error_interventions"] >= MIN_ERROR_INTERVENTIONS_PER_POOL
        gates[f"{pool}_control_interventions_at_least_6"] = row["control_interventions"] >= MIN_CONTROL_INTERVENTIONS_PER_POOL
        gates[f"{pool}_error_mean_gt_0cp"] = float(row["error"]["mean"]) > 0.0
        gates[f"{pool}_paired_mean_gt_0cp"] = float(row["paired"]["mean"]) > 0.0
        gates[f"{pool}_control_mean_at_least_minus_2cp"] = float(row["control"]["mean"]) >= -2.0
    passed = all(gates.values())
    compact = lambda row: {key: value for key, value in row.items() if key != "paired_values_cp"}
    full_fit = _fit_uplift(pair_rows)
    return {
        "status": "candidate_for_preregistration_on_new_fresh_pools" if passed else "target_specificity_not_established",
        "passed": passed,
        "support_feature_names": support_names,
        "ridge": UPLIFT_RIDGE,
        "decision_rule": "retain_base_intervention_iff_cross_pool_uplift_score_gt_0",
        "training_direction": {"pool1": "tests_model_fit_on_pool2", "pool2": "tests_model_fit_on_pool1"},
        "pool_fits": {
            pool: {
                "coefficient": coefficients[pool].tolist(),
                "active_pairs": fits[pool]["active_pairs"],
                "rank": fits[pool]["rank"],
                "condition_number": fits[pool]["condition_number"],
            }
            for pool in pools
        },
        "coefficient_cosine": cosine,
        "full_discovery_fit": {
            "coefficient": full_fit["coefficient"].tolist(),
            "coefficient_sha256": _digest(full_fit["coefficient"].tolist()),
            "active_pairs": full_fit["active_pairs"],
            "rank": full_fit["rank"],
        },
        "oof_score_distribution": tail._distribution(scores),
        "oof_metrics": compact(metrics),
        "oof_metrics_by_pool": {pool: compact(row) for pool, row in by_pool.items()},
        "sham": {
            "replicates": SHAM_REPLICATES,
            "seed": SHAM_SEED,
            "paired_mean_q99_cp": sham_q99,
            "real_paired_mean_cp": real_mean,
            "real_exceeds_sham_q99": real_mean > sham_q99,
            "means_sha256": _digest(sham_means),
        },
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "fresh_1524_reuse_for_confirmation_forbidden": True,
        "production_authorized": False,
    }


def autopsy(
    training_report: dict[str, Any], failed_model: dict[str, Any],
    training_pairs: dict[str, Any], training_shards: list[dict[str, Any]],
    fresh_summary: dict[str, Any], fresh_report: dict[str, Any],
    fresh_pairs: dict[str, Any], fresh_shards: list[dict[str, Any]],
    target_cache: dict[str, Any], subspace_report: dict[str, Any],
) -> dict[str, Any]:
    _require_source(fresh_summary, fresh_report)
    support_indices, support_names = _require_subspace(subspace_report)
    ridge._check_source(training_report, failed_model)
    training_rows, training_identities = historical._load_rows(training_pairs, training_shards)
    fresh_rows, fresh_identities = fresh._load_fresh_rows(fresh_pairs, fresh_shards, pair_count=FRESH_PAIRS)
    if training_identities != fresh_identities or fresh_report.get("identities") != fresh_identities:
        raise ValueError("1508/1524 engine, champion or search identity drift")
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        if subspace_report.get(key) != training_identities[key]:
            raise ValueError(f"1525 stable support identity drift: {key}")
    if target_cache.get("schema") != fresh.SCHEMA_CACHE:
        raise ValueError("1524 target-cache schema drift")

    model = ridge._fit(training_rows, alpha=300.0)
    base_decisions = ridge._decisions(
        fresh_rows, {row["pair_id"]: model for row in fresh_rows},
        cap_cp=100.0, threshold_cp=10.0, mode="strict_both_change",
    )
    decisions, rule_proof = confirmation._apply_endgame_abstention(fresh_rows, base_decisions)
    reproduced = confirmation._metrics(decisions, seed=2026082307)
    reproduced_compact = {key: value for key, value in reproduced.items() if key != "paired_values_cp"}
    if not tail._same(reproduced_compact, fresh_report.get("metrics")):
        raise ValueError("1524 endgame-abstention metric reproduction drift")
    if not tail._same(rule_proof, fresh_report.get("rule_proof")):
        raise ValueError("1524 endgame rule proof drift")

    pair_rows = []
    for row, decision in zip(fresh_rows, decisions, strict=True):
        output: dict[str, Any] = {
            "pair_id": int(row["pair_id"]),
            "source_pool": str(row["source_pool"]),
        }
        for role in ("error", "control"):
            output[role] = {
                "intervention": bool(decision[role]["intervention"]),
                "gain_cp": float(decision[role]["improvement_cp"]),
                "vector": _state_vector(row[role], decision[role], model, support_indices).tolist(),
                "phase": confirmation._phase(row[role]),
                "opening_id": str(row[role]["profile"]["source"]["opening_id"]),
                "game_uid": str(row[role]["profile"]["source"]["game_uid"]),
            }
        output["pair_vector"] = (
            np.asarray(output["error"]["vector"]) - np.asarray(output["control"]["vector"])
        ).tolist()
        output["paired_gain_cp"] = output["error"]["gain_cp"] - output["control"]["gain_cp"]
        pair_rows.append(output)

    split = _split_identity(training_rows, fresh_rows)
    split_gates = {
        "fresh_pairs_exactly_600": len(pair_rows) == FRESH_PAIRS,
        "pool_pair_counts_sum_to_600": sum(split["pool_pair_counts"].values()) == FRESH_PAIRS,
        "pool_opening_overlap_zero": split["pool_opening_overlap"] == 0,
        "pool_game_overlap_zero": split["pool_game_overlap"] == 0,
        "training_fresh_opening_overlap_zero": split["training_fresh_opening_overlap"] == 0,
        "training_fresh_game_overlap_zero": split["training_fresh_game_overlap"] == 0,
    }
    if not all(split_gates.values()):
        raise ValueError(f"target-specificity split leakage: {split_gates}")
    screen = _cross_pool_screen(pair_rows, support_names)
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "scientific_source_verdict": confirmation.NOT_ESTABLISHED,
        "purpose": "read_only_cross_pool_target_specificity_discovery_after_1524_failure",
        "identities": fresh_identities,
        "source_hashes": {
            "training_pairs_sha256": _digest(training_pairs),
            "fresh_pairs_sha256": _digest(fresh_pairs),
            "fresh_target_cache_sha256": _digest(target_cache),
            "fresh_report_sha256": _digest(fresh_report),
            "stable_subspace_sha256": _digest(subspace_report),
            "base_model_coef_sha256": _digest(np.asarray(model["coef"]).tolist()),
        },
        "reproduction": reproduced_compact,
        "rule_proof": rule_proof,
        "stable_support": {
            "indices": support_indices,
            "names": support_names,
            "support_sha256": subspace_report["analysis"]["support_sha256"],
        },
        "split_integrity": {**split, "gates": split_gates},
        "cross_pool_uplift_screen": screen,
        "accounting": {
            "authenticated_fresh_pairs_read": len(pair_rows),
            "authenticated_fresh_states_read": 2 * len(pair_rows),
            "new_exact_target_computations": 0,
            "diagnostic_base_residual_fits_on_immutable_1508": 1,
            "diagnostic_uplift_fits": 3 + 2 * SHAM_REPLICATES,
            "fresh_label_pattern_eval_fits": 0,
            "production_model_fits": 0,
            "strength_games": 0,
            "new_selfplay_games": 0,
            "frozen_reads": 0,
        },
        "fresh_1524_reuse_for_confirmation_forbidden": True,
        "new_fresh_pool_preregistration_recommended": bool(screen["passed"]),
        "anchored_local_refit_authorized": False,
        "production_model_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "preregister_then_confirm_uplift_gate_on_entirely_new_fresh_pools" if screen["passed"] else None,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--training-report", type=Path, required=True)
    root.add_argument("--failed-model", type=Path, required=True)
    root.add_argument("--training-pairs", type=Path, required=True)
    root.add_argument("--training-shard", action="append", type=Path, required=True)
    root.add_argument("--fresh-summary", type=Path, required=True)
    root.add_argument("--fresh-report", type=Path, required=True)
    root.add_argument("--fresh-pairs", type=Path, required=True)
    root.add_argument("--fresh-shard", action="append", type=Path, required=True)
    root.add_argument("--target-cache", type=Path, required=True)
    root.add_argument("--subspace-report", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    report = autopsy(
        load(args.training_report), load(args.failed_model), load(args.training_pairs),
        [load(path) for path in args.training_shard], load(args.fresh_summary),
        load(args.fresh_report), load(args.fresh_pairs),
        [load(path) for path in args.fresh_shard], load(args.target_cache),
        load(args.subspace_report),
    )
    _publish(args.report, report)
    screen = report["cross_pool_uplift_screen"]
    print(json.dumps({
        "verdict": report["verdict"], "screen_status": screen["status"],
        "paired_mean_cp": screen["oof_metrics"]["paired"]["mean"],
        "coefficient_cosine": screen["coefficient_cosine"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
