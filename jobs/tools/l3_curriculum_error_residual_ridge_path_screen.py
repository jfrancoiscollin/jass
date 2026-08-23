#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Training-only stability screen for the failed 1508 residual family."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_trace_proxy_preregistration as prereg
from jobs.tools import l3_curriculum_error_trace_residual_training as source
from jobs.tools import l3_curriculum_error_trace_variability_screen as variability


SCHEMA = "jass.l3_curriculum_error_residual_ridge_path_screen.v1"
READY = "JASS_CURRICULUM_ERROR_RESIDUAL_RIDGE_PATH_SCREEN_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_RESIDUAL_RIDGE_PATH_SCREEN_NOT_ESTABLISHED"
ALPHAS = (0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0)
CAPS_CP = (25.0, 50.0, 75.0, 100.0, 150.0)
MODES = ("strict_both_change", "at_least_one_change")
THRESHOLDS_CP = prereg.THRESHOLDS_CP
BOOTSTRAP_SAMPLES = 5_000
BOOTSTRAP_SEED = 2026082256
SHAM_REPLICATES = 100
SHAM_SEED = 2026082257
MIN_COEF_COSINE = 0.75
MIN_TOP5_JACCARD = 0.40
MIN_DECISION_JACCARD = 0.50
MIN_PLATEAU_JACCARD = 0.60


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _check_source(report: dict[str, Any], model: dict[str, Any]) -> None:
    if report.get("schema") != source.SCHEMA or report.get("verdict") != source.NOT_ESTABLISHED or report.get("passed") is not False:
        raise ValueError("ridge path requires the certified failed 1508 training report")
    if report.get("selected_threshold") is not None or report.get("sham") is not None:
        raise ValueError("ridge path source selection/sham drift")
    if model.get("schema") != source.MODEL_SCHEMA or model.get("authorized_for_feature_audit") is not False:
        raise ValueError("ridge path failed model authorization drift")
    if model.get("aligned_model") is not None or model.get("shuffled_model") is not None:
        raise ValueError("ridge path source unexpectedly published weights")
    for key in (
        "feature_audit_action_value_reads",
        "outer_confirm_action_value_reads",
        "pattern_eval_fits",
        "strength_games",
        "new_selfplay_games",
        "frozen_reads",
    ):
        if int(report.get(key, -1)) != 0:
            raise ValueError(f"ridge path sealed/forbidden source counter drift: {key}")


def _fit(
    rows: list[dict[str, Any]], *, alpha: float, sham_seed: int | None = None
) -> dict[str, Any]:
    matrix = np.vstack(
        [
            vector
            for row in rows
            for role in ("error", "control")
            for vector in row[role]["features"].values()
        ]
    )
    mean = matrix.mean(axis=0)
    rms = np.sqrt(np.mean((matrix - mean) ** 2, axis=0))
    rms[rms < 1e-6] = 1.0
    width = len(ranker.FEATURE_NAMES)
    gram = np.zeros((width, width))
    target = np.zeros(width)
    total = 0.0
    comparisons = 0
    for row in rows:
        for role in ("error", "control"):
            state = row[role]
            values = (
                state["values"]
                if sham_seed is None
                else ranker._permuted_values(
                    state["values"],
                    seed=sham_seed,
                    state_key=f"{row['pair_id']}|{role}",
                )
            )
            teacher = max(values, key=lambda action: (values[action], action))
            others = [action for action in sorted(values) if action != teacher]
            if not others:
                continue
            weight = 0.5 / len(rows) / len(others)
            baseline = {
                action: (
                    state["original_scores"][action]
                    + state["image_scores"][action]
                )
                / 2.0
                for action in values
            }
            for other in others:
                x = (state["features"][teacher] - state["features"][other]) / rms
                y = (values[teacher] - values[other]) - (
                    baseline[teacher] - baseline[other]
                )
                gram += weight * np.outer(x, x)
                target += weight * x * y
                total += weight
                comparisons += 1
    if total <= 0.0:
        raise ValueError("ridge path fit has zero comparisons")
    coefficient = np.linalg.solve(
        gram / total + alpha * np.eye(width), target / total
    )
    return {
        "mean": mean,
        "rms": rms,
        "coef": coefficient,
        "alpha": alpha,
        "comparisons": comparisons,
        "sham_seed": sham_seed,
    }


def _oof_models(
    rows: list[dict[str, Any]],
    folds: dict[int, int],
    *,
    alpha: float,
    sham_seed: int | None = None,
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    by_pair: dict[int, dict[str, Any]] = {}
    by_fold: list[dict[str, Any]] = []
    for fold in range(prereg.FOLDS):
        model = _fit(
            [row for row in rows if folds[row["pair_id"]] != fold],
            alpha=alpha,
            sham_seed=sham_seed,
        )
        by_fold.append(model)
        for row in rows:
            if folds[row["pair_id"]] == fold:
                by_pair[row["pair_id"]] = model
    return by_pair, by_fold


def _correction(model: dict[str, Any], vector: np.ndarray, cap_cp: float) -> float:
    value = float(
        ((vector - model["mean"]) / model["rms"]) @ model["coef"]
    )
    return max(-cap_cp, min(cap_cp, value))


def _best(scores: dict[str, float]) -> str:
    return max(scores, key=lambda action: (scores[action], action))


def _decision(
    state: dict[str, Any],
    model: dict[str, Any],
    *,
    cap_cp: float,
    threshold_cp: float,
    mode: str,
) -> dict[str, Any]:
    if mode not in MODES:
        raise ValueError(f"unknown ridge path decision mode: {mode}")
    proxy = variability._profile_values(state["profile"])[prereg.SELECTED_PROXY]
    eligible = prereg.LOWER_OPEN < proxy <= prereg.UPPER_CLOSED
    original_anchor = _best(state["original_scores"])
    image_anchor = _best(state["image_scores"])
    correction = {
        action: _correction(model, vector, cap_cp)
        for action, vector in state["features"].items()
    }
    original_corrected = {
        action: state["original_scores"][action] + correction[action]
        for action in correction
    }
    image_corrected = {
        action: state["image_scores"][action] + correction[action]
        for action in correction
    }
    original_proposed = _best(original_corrected)
    image_proposed = _best(image_corrected)
    original_advantage = (
        original_corrected[original_proposed] - original_corrected[original_anchor]
    )
    image_advantage = image_corrected[image_proposed] - image_corrected[image_anchor]
    changed = (
        original_proposed not in {original_anchor, image_anchor}
        if mode == "strict_both_change"
        else not (
            original_proposed == original_anchor
            and original_proposed == image_anchor
        )
    )
    intervention = (
        eligible
        and original_proposed == image_proposed
        and changed
        and min(original_advantage, image_advantage) >= threshold_cp
    )
    chosen_original = original_proposed if intervention else original_anchor
    chosen_image = image_proposed if intervention else image_anchor
    values = state["values"]
    anchor_value = (values[original_anchor] + values[image_anchor]) / 2.0
    chosen_value = (values[chosen_original] + values[chosen_image]) / 2.0
    return {
        "eligible": eligible,
        "intervention": intervention,
        "improvement_cp": chosen_value - anchor_value,
        "predicted_advantage_cp": (
            (original_advantage + image_advantage) / 2.0
            if intervention
            else None
        ),
        "realized_gain_cp": chosen_value - anchor_value if intervention else None,
        "anchor_symmetry": original_anchor == image_anchor,
        "aligned_symmetry": chosen_original == chosen_image,
        "outside_gate_bit_identical": eligible
        or (chosen_original == original_anchor and chosen_image == image_anchor),
        "action": original_proposed if intervention else None,
    }


def _decisions(
    rows: list[dict[str, Any]],
    models: dict[int, dict[str, Any]],
    *,
    cap_cp: float,
    threshold_cp: float,
    mode: str,
) -> list[dict[str, Any]]:
    return [
        {
            "pair_id": row["pair_id"],
            "error": _decision(
                row["error"],
                models[row["pair_id"]],
                cap_cp=cap_cp,
                threshold_cp=threshold_cp,
                mode=mode,
            ),
            "control": _decision(
                row["control"],
                models[row["pair_id"]],
                cap_cp=cap_cp,
                threshold_cp=threshold_cp,
                mode=mode,
            ),
        }
        for row in rows
    ]


def _bootstrap(values: list[float], *, seed: int) -> dict[str, Any]:
    return ranker._bootstrap(values, samples=BOOTSTRAP_SAMPLES, seed=seed)


def _metrics(decisions: list[dict[str, Any]], *, seed: int) -> dict[str, Any]:
    errors = [row["error"]["improvement_cp"] for row in decisions]
    controls = [row["control"]["improvement_cp"] for row in decisions]
    paired = [left - right for left, right in zip(errors, controls, strict=True)]
    changed = [row["error"] for row in decisions if row["error"]["intervention"]]
    realized = np.asarray([row["realized_gain_cp"] for row in changed], dtype=float)
    predicted = np.asarray([row["predicted_advantage_cp"] for row in changed], dtype=float)
    return {
        "error_improvement": _bootstrap(errors, seed=seed),
        "control_improvement": _bootstrap(controls, seed=seed + 1),
        "paired_error_minus_control": _bootstrap(paired, seed=seed + 2),
        "error_interventions": sum(row["error"]["intervention"] for row in decisions),
        "control_interventions": sum(row["control"]["intervention"] for row in decisions),
        "error_eligible": sum(row["error"]["eligible"] for row in decisions),
        "control_eligible": sum(row["control"]["eligible"] for row in decisions),
        "error_positive_realization_rate": (
            float(np.mean(realized > 0.0)) if realized.size else None
        ),
        "error_calibration_bias_cp": (
            float(np.mean(realized - predicted)) if realized.size else None
        ),
        "outside_gate_bit_identical": all(
            row[role]["outside_gate_bit_identical"]
            for row in decisions
            for role in ("error", "control")
        ),
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _model_stability(models: list[dict[str, Any]]) -> dict[str, Any]:
    cosines = []
    top_jaccards = []
    for left, right in itertools.combinations(models, 2):
        a, b = left["coef"], right["coef"]
        denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
        cosines.append(float(a @ b / denominator) if denominator else 1.0)
        atop = set(np.argsort(np.abs(a))[-5:].tolist())
        btop = set(np.argsort(np.abs(b))[-5:].tolist())
        top_jaccards.append(_jaccard({str(x) for x in atop}, {str(x) for x in btop}))
    return {
        "minimum_coefficient_cosine": min(cosines),
        "mean_coefficient_cosine": float(np.mean(cosines)),
        "minimum_top5_feature_jaccard": min(top_jaccards),
        "mean_top5_feature_jaccard": float(np.mean(top_jaccards)),
    }


def _intervention_tokens(decisions: list[dict[str, Any]]) -> set[str]:
    return {
        f"{row['pair_id']}|{role}|{row[role]['action']}"
        for row in decisions
        for role in ("error", "control")
        if row[role]["intervention"]
    }


def _fold_decision_stability(
    rows: list[dict[str, Any]],
    models: list[dict[str, Any]],
    *,
    cap_cp: float,
    threshold_cp: float,
    mode: str,
) -> float:
    sets = []
    for model in models:
        replicated = {row["pair_id"]: model for row in rows}
        sets.append(
            _intervention_tokens(
                _decisions(
                    rows,
                    replicated,
                    cap_cp=cap_cp,
                    threshold_cp=threshold_cp,
                    mode=mode,
                )
            )
        )
    return min(_jaccard(left, right) for left, right in itertools.combinations(sets, 2))


def screen(
    registration: dict[str, Any],
    training_report: dict[str, Any],
    failed_model: dict[str, Any],
    pairs: dict[str, Any],
    shards: list[dict[str, Any]],
) -> dict[str, Any]:
    source._check_preregistration(registration)
    _check_source(training_report, failed_model)
    rows, identities = source._load_rows(pairs, shards)
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        if identities[key] != training_report.get(key) or identities[key] != failed_model.get(key):
            raise ValueError(f"ridge path source {key} drift")
    folds, fold_manifest = source._components_folds(rows)

    cached: dict[float, tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]] = {}
    model_stability: dict[float, dict[str, Any]] = {}
    for alpha in ALPHAS:
        cached[alpha] = _oof_models(rows, folds, alpha=alpha)
        model_stability[alpha] = _model_stability(cached[alpha][1])

    candidates: list[dict[str, Any]] = []
    internal_sets: dict[tuple[float, float, str, float], set[str]] = {}
    for index, (alpha, cap_cp, mode, threshold_cp) in enumerate(
        itertools.product(ALPHAS, CAPS_CP, MODES, THRESHOLDS_CP)
    ):
        oof, by_fold = cached[alpha]
        decisions = _decisions(
            rows,
            oof,
            cap_cp=cap_cp,
            threshold_cp=threshold_cp,
            mode=mode,
        )
        metrics = _metrics(decisions, seed=BOOTSTRAP_SEED + index * 3)
        stability = {
            **model_stability[alpha],
            "minimum_fold_decision_jaccard": _fold_decision_stability(
                rows,
                by_fold,
                cap_cp=cap_cp,
                threshold_cp=threshold_cp,
                mode=mode,
            ),
        }
        gates = {
            "error_interventions_at_least_12": metrics["error_interventions"] >= 12,
            "control_interventions_at_least_8": metrics["control_interventions"] >= 8,
            "total_interventions_at_least_20": metrics["error_interventions"]
            + metrics["control_interventions"]
            >= 20,
            "error_positive_realization_rate_ge_0_60": metrics[
                "error_positive_realization_rate"
            ]
            is not None
            and metrics["error_positive_realization_rate"] >= 0.60,
            "control_mean_gain_ge_minus_2cp": metrics["control_improvement"]["mean"]
            >= -2.0,
            "paired_ci95_lower_gt_0cp": metrics["paired_error_minus_control"]["ci95"][0]
            > 0.0,
            "minimum_coefficient_cosine_ge_0_75": stability[
                "minimum_coefficient_cosine"
            ]
            >= MIN_COEF_COSINE,
            "minimum_top5_jaccard_ge_0_40": stability[
                "minimum_top5_feature_jaccard"
            ]
            >= MIN_TOP5_JACCARD,
            "minimum_fold_decision_jaccard_ge_0_50": stability[
                "minimum_fold_decision_jaccard"
            ]
            >= MIN_DECISION_JACCARD,
            "outside_gate_bit_identical": metrics["outside_gate_bit_identical"],
        }
        key = (alpha, cap_cp, mode, threshold_cp)
        internal_sets[key] = _intervention_tokens(decisions)
        candidates.append(
            {
                "alpha": alpha,
                "cap_cp": cap_cp,
                "mode": mode,
                "threshold_cp": threshold_cp,
                "metrics": metrics,
                "stability": stability,
                "base_gates": gates,
                "base_passed": all(gates.values()),
                "intervention_set_sha256": hashlib.sha256(
                    "\n".join(sorted(internal_sets[key])).encode()
                ).hexdigest(),
            }
        )

    for row in candidates:
        ai, ci = ALPHAS.index(row["alpha"]), CAPS_CP.index(row["cap_cp"])
        neighbor_keys = []
        for da, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            na, nc = ai + da, ci + dc
            if 0 <= na < len(ALPHAS) and 0 <= nc < len(CAPS_CP):
                neighbor_keys.append(
                    (ALPHAS[na], CAPS_CP[nc], row["mode"], row["threshold_cp"])
                )
        key = (row["alpha"], row["cap_cp"], row["mode"], row["threshold_cp"])
        jaccards = [
            _jaccard(internal_sets[key], internal_sets[neighbor])
            for neighbor in neighbor_keys
        ]
        row["plateau"] = {
            "neighbors": len(jaccards),
            "minimum_neighbor_intervention_jaccard": min(jaccards),
            "mean_neighbor_intervention_jaccard": float(np.mean(jaccards)),
        }
        row["plateau_gate"] = (
            len(jaccards) >= 2 and min(jaccards) >= MIN_PLATEAU_JACCARD
        )
        row["passed"] = row["base_passed"] and row["plateau_gate"]
        row["failed_gates"] = sorted(
            [key for key, value in row["base_gates"].items() if not value]
            + ([] if row["plateau_gate"] else ["stable_neighbor_plateau"])
        )

    passing = [row for row in candidates if row["passed"]]
    passing.sort(
        key=lambda row: (
            -float(row["metrics"]["paired_error_minus_control"]["ci95"][0]),
            -float(row["metrics"]["error_improvement"]["mean"]),
            -float(row["alpha"]),
            float(row["cap_cp"]),
            -float(row["threshold_cp"]),
            MODES.index(row["mode"]),
        )
    )
    selected = passing[0] if passing else None
    sham = None
    if selected is not None:
        sham_means = []
        for replicate in range(SHAM_REPLICATES):
            oof, _ = _oof_models(
                rows,
                folds,
                alpha=float(selected["alpha"]),
                sham_seed=SHAM_SEED + replicate,
            )
            decisions = _decisions(
                rows,
                oof,
                cap_cp=float(selected["cap_cp"]),
                threshold_cp=float(selected["threshold_cp"]),
                mode=str(selected["mode"]),
            )
            errors = [row["error"]["improvement_cp"] for row in decisions]
            controls = [row["control"]["improvement_cp"] for row in decisions]
            sham_means.append(float(np.mean(np.asarray(errors) - np.asarray(controls))))
        q95 = float(np.quantile(sham_means, 0.95))
        real = float(selected["metrics"]["paired_error_minus_control"]["mean"])
        sham = {
            "replicates": SHAM_REPLICATES,
            "seed": SHAM_SEED,
            "real_paired_mean_cp": real,
            "sham_q95_cp": q95,
            "real_exceeds_sham_q95": real > q95,
        }

    passed = selected is not None and sham is not None and sham["real_exceeds_sham_q95"]
    return {
        "schema": SCHEMA,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        **identities,
        "source_verdict": training_report["verdict"],
        "grid": {
            "alphas": list(ALPHAS),
            "caps_cp": list(CAPS_CP),
            "modes": list(MODES),
            "thresholds_cp": list(THRESHOLDS_CP),
            "candidates": len(candidates),
            "selection_rule": "max_paired_ci95_lower_then_error_mean_then_stronger_anchor_then_smaller_cap_then_higher_threshold_then_strict_mode",
        },
        "fold_manifest": fold_manifest,
        "candidates": candidates,
        "passing_candidates": len(passing),
        "selected": selected,
        "sham": sham,
        "diagnostic_fits": len(ALPHAS) * prereg.FOLDS
        + (SHAM_REPLICATES * prereg.FOLDS if selected else 0),
        "feature_audit_profile_rows_examined": 0,
        "feature_audit_action_value_reads": 0,
        "outer_confirm_profile_rows_examined": 0,
        "outer_confirm_action_value_reads": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "preregistration_authorized": passed,
        "feature_audit_authorized": False,
        "production_rule_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "immutable_ridge_plateau_preregistration" if passed else None,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--preregistration", type=Path, required=True)
    root.add_argument("--training-report", type=Path, required=True)
    root.add_argument("--failed-model", type=Path, required=True)
    root.add_argument("--pairs", type=Path, required=True)
    root.add_argument("--atlas-shard", action="append", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    report = screen(
        json.loads(args.preregistration.read_text()),
        json.loads(args.training_report.read_text()),
        json.loads(args.failed_model.read_text()),
        json.loads(args.pairs.read_text()),
        [json.loads(path.read_text()) for path in args.atlas_shard],
    )
    report["preregistration_sha256"] = hashlib.sha256(
        args.preregistration.read_bytes()
    ).hexdigest()
    report["training_report_sha256"] = hashlib.sha256(
        args.training_report.read_bytes()
    ).hexdigest()
    report["failed_model_sha256"] = hashlib.sha256(
        args.failed_model.read_bytes()
    ).hexdigest()
    report["pairs_sha256"] = hashlib.sha256(args.pairs.read_bytes()).hexdigest()
    _publish(args.report, report)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "passing_candidates": report["passing_candidates"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
