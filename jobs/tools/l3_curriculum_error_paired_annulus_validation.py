#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One-shot OOS validation of the fixed paired-image annular correction.

The architecture is immutable before this tool reads the 31 inner-validation
pairs.  It fits a single strongly-regularised diagnostic residual on the 103
authorised discovery-fit pairs, evaluates aligned, shuffled and zero-residual
arms at identical paired-trace cost, and leaves the outer confirm split sealed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    from jobs.tools import l3_curriculum_error_action_ranker as ranker
    from jobs.tools import l3_curriculum_error_annulus_preregistration as prereg
except ModuleNotFoundError:  # pragma: no cover - direct CPX script execution
    import l3_curriculum_error_action_ranker as ranker  # type: ignore
    import l3_curriculum_error_annulus_preregistration as prereg  # type: ignore


SCHEMA = "jass.l3_curriculum_error_paired_annulus_validation.v1"
MODEL_SCHEMA = "jass.l3_curriculum_error_paired_annulus_residual.v1"
READY = "JASS_CURRICULUM_ERROR_PAIRED_ANNULUS_VALIDATION_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_PAIRED_ANNULUS_VALIDATION_NOT_ESTABLISHED"
SHAM_REPLICATES = 100


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _paired_features(
    profile: dict[str, Any],
) -> tuple[dict[str, np.ndarray], dict[str, float], dict[str, float], dict[str, float]]:
    original_features, original_scores = ranker._raw_features(profile, image=False)
    image_features, image_scores = ranker._raw_features(profile, image=True)
    if set(original_features) != set(image_features) or set(original_scores) != set(image_scores):
        raise ValueError("paired exact-image legal feature set drift")
    actions = sorted(original_features)
    features = {
        action: (original_features[action] + image_features[action]) / 2.0
        for action in actions
    }
    scores = {
        action: (original_scores[action] + image_scores[action]) / 2.0
        for action in actions
    }
    return features, scores, original_scores, image_scores


def _states(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for pair in rows:
        for role in ("error", "control"):
            entry = pair[role]
            features, scores, _, _ = _paired_features(entry["profile"])
            values = ranker._true_values(entry["judged"])
            if set(features) != set(values):
                raise ValueError("paired feature/judge legal action set drift")
            states.append(
                {
                    "pair_id": int(pair["pair_id"]),
                    "role": role,
                    "state_key": f"{pair['pair_id']}|{role}|paired",
                    "features": features,
                    "scores": scores,
                    "values": values,
                }
            )
    return states


def _source_ids(rows: list[dict[str, Any]], key: str) -> set[str]:
    values: set[str] = set()
    for pair in rows:
        for role in ("error", "control"):
            source = pair[role]["profile"]["source"]
            value = source.get(key)
            if value in (None, ""):
                raise ValueError(f"source row lacks {key}")
            values.add(str(value))
    return values


def _fit(
    rows: list[dict[str, Any]], *, sham_seed: int | None = None
) -> dict[str, Any]:
    states = _states(rows)
    all_features = np.vstack(
        [vector for state in states for vector in state["features"].values()]
    )
    mean = all_features.mean(axis=0)
    scale = all_features.std(axis=0)
    scale[scale < 1e-6] = 1.0
    gram = np.zeros((len(ranker.FEATURE_NAMES), len(ranker.FEATURE_NAMES)))
    target = np.zeros(len(ranker.FEATURE_NAMES))
    total = 0.0
    comparisons = 0
    for state in states:
        values = (
            state["values"]
            if sham_seed is None
            else ranker._permuted_values(
                state["values"], seed=sham_seed, state_key=state["state_key"]
            )
        )
        teacher = max(values, key=lambda action: (values[action], action))
        others = [action for action in sorted(values) if action != teacher]
        if not others:
            continue
        weight = 1.0 / len(others)
        for other in others:
            x = (state["features"][teacher] - state["features"][other]) / scale
            judge_delta = values[teacher] - values[other]
            q00_delta = state["scores"][teacher] - state["scores"][other]
            y = judge_delta - q00_delta
            gram += weight * np.outer(x, x)
            target += weight * x * y
            total += weight
            comparisons += 1
    if total <= 0.0:
        raise ValueError("paired annulus fit has zero comparisons")
    gram = gram / total + prereg.FIXED_ALPHA * np.eye(len(ranker.FEATURE_NAMES))
    coef = np.linalg.solve(gram, target / total)
    return {
        "schema": MODEL_SCHEMA,
        "feature_names": list(ranker.FEATURE_NAMES),
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "coef": coef.tolist(),
        "alpha": prereg.FIXED_ALPHA,
        "correction_cap_cp": ranker.CORRECTION_CAP_CP,
        "states": len(states),
        "comparisons": comparisons,
        "coefficient_l2": float(np.linalg.norm(coef)),
        "sham_seed": sham_seed,
    }


def _correction(model: dict[str, Any], vector: np.ndarray) -> float:
    mean = np.asarray(model["mean"])
    scale = np.asarray(model["scale"])
    coef = np.asarray(model["coef"])
    value = float(((vector - mean) / scale) @ coef)
    cap = float(model["correction_cap_cp"])
    return max(-cap, min(cap, value))


def _best(scores: dict[str, float]) -> str:
    return max(scores, key=lambda action: (scores[action], action))


def _margin(scores: dict[str, float]) -> float:
    ordered = sorted(scores.values(), reverse=True)
    return ordered[0] - ordered[1] if len(ordered) > 1 else float("inf")


def _decision(entry: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    features, paired_scores, original_scores, image_scores = _paired_features(entry["profile"])
    values = ranker._true_values(entry["judged"])
    anchor_original, anchor_image = _best(original_scores), _best(image_scores)
    original_margin, image_margin = _margin(original_scores), _margin(image_scores)
    eligible = (
        prereg.FIXED_MARGIN_LOWER_OPEN_CP < original_margin <= prereg.FIXED_MARGIN_UPPER_CLOSED_CP
        and prereg.FIXED_MARGIN_LOWER_OPEN_CP < image_margin <= prereg.FIXED_MARGIN_UPPER_CLOSED_CP
    )
    paired_zero = _best(paired_scores)
    zero_original = paired_zero if eligible else anchor_original
    zero_image = paired_zero if eligible else anchor_image
    corrected = {
        action: paired_scores[action] + _correction(model, features[action])
        for action in paired_scores
    }
    proposed = _best(corrected)
    predicted_advantage = corrected[proposed] - corrected[paired_zero]
    residual_intervention = (
        eligible
        and proposed != paired_zero
        and predicted_advantage >= prereg.FIXED_ADVANTAGE_THRESHOLD_CP
    )
    aligned_original = proposed if residual_intervention else zero_original
    aligned_image = proposed if residual_intervention else zero_image
    anchor_value = (values[anchor_original] + values[anchor_image]) / 2.0
    zero_value = (values[zero_original] + values[zero_image]) / 2.0
    aligned_value = (values[aligned_original] + values[aligned_image]) / 2.0
    outside_identity = eligible or (
        aligned_original == anchor_original
        and aligned_image == anchor_image
        and zero_original == anchor_original
        and zero_image == anchor_image
    )
    return {
        "eligible": eligible,
        "original_margin_cp": original_margin,
        "exact_image_margin_cp": image_margin,
        "anchor_original": anchor_original,
        "anchor_image": anchor_image,
        "zero_action_original": zero_original,
        "zero_action_image": zero_image,
        "aligned_action_original": aligned_original,
        "aligned_action_image": aligned_image,
        "residual_intervention": residual_intervention,
        "predicted_advantage_cp": predicted_advantage if residual_intervention else None,
        "realized_residual_gain_cp": aligned_value - zero_value if residual_intervention else None,
        "aligned_vs_anchor_cp": aligned_value - anchor_value,
        "zero_vs_anchor_cp": zero_value - anchor_value,
        "aligned_vs_zero_cp": aligned_value - zero_value,
        "anchor_symmetry": anchor_original == anchor_image,
        "zero_symmetry": zero_original == zero_image,
        "aligned_symmetry": aligned_original == aligned_image,
        "outside_annulus_bit_identical": outside_identity,
    }


def _calibration(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in decisions if row["residual_intervention"]]
    if not rows:
        return {
            "n": 0,
            "mean_predicted_advantage_cp": None,
            "mean_realized_gain_cp": None,
            "mean_bias_realized_minus_predicted_cp": None,
            "mean_absolute_error_cp": None,
            "positive_realization_rate": None,
        }
    predicted = np.asarray([row["predicted_advantage_cp"] for row in rows], dtype=float)
    realized = np.asarray([row["realized_residual_gain_cp"] for row in rows], dtype=float)
    return {
        "n": len(rows),
        "mean_predicted_advantage_cp": float(predicted.mean()),
        "mean_realized_gain_cp": float(realized.mean()),
        "mean_bias_realized_minus_predicted_cp": float((realized - predicted).mean()),
        "mean_absolute_error_cp": float(np.abs(realized - predicted).mean()),
        "positive_realization_rate": float(np.mean(realized > 0.0)),
    }


def _evaluate(
    rows: list[dict[str, Any]],
    model: dict[str, Any],
    *,
    bootstrap_samples: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    decisions = []
    for pair in rows:
        decisions.append(
            {
                "pair_id": int(pair["pair_id"]),
                "error": _decision(pair["error"], model),
                "control": _decision(pair["control"], model),
            }
        )

    def values(role: str, key: str) -> list[float]:
        return [float(row[role][key]) for row in decisions]

    def paired(key: str) -> list[float]:
        return [
            float(row["error"][key]) - float(row["control"][key])
            for row in decisions
        ]

    def rate(role: str, key: str) -> float:
        return float(np.mean([bool(row[role][key]) for row in decisions])) if decisions else 0.0

    error_calibration = _calibration([row["error"] for row in decisions])
    control_calibration = _calibration([row["control"] for row in decisions])
    return {
        "pairs": len(rows),
        "error_aligned_vs_anchor": ranker._bootstrap(
            values("error", "aligned_vs_anchor_cp"), samples=bootstrap_samples, seed=bootstrap_seed
        ),
        "control_aligned_vs_anchor": ranker._bootstrap(
            values("control", "aligned_vs_anchor_cp"), samples=bootstrap_samples, seed=bootstrap_seed + 1
        ),
        "paired_error_minus_control_vs_anchor": ranker._bootstrap(
            paired("aligned_vs_anchor_cp"), samples=bootstrap_samples, seed=bootstrap_seed + 2
        ),
        "error_aligned_vs_zero": ranker._bootstrap(
            values("error", "aligned_vs_zero_cp"), samples=bootstrap_samples, seed=bootstrap_seed + 3
        ),
        "control_aligned_vs_zero": ranker._bootstrap(
            values("control", "aligned_vs_zero_cp"), samples=bootstrap_samples, seed=bootstrap_seed + 4
        ),
        "paired_error_minus_control_vs_zero": ranker._bootstrap(
            paired("aligned_vs_zero_cp"), samples=bootstrap_samples, seed=bootstrap_seed + 5
        ),
        "error_zero_vs_anchor": ranker._bootstrap(
            values("error", "zero_vs_anchor_cp"), samples=bootstrap_samples, seed=bootstrap_seed + 6
        ),
        "error_annulus_pairs": sum(bool(row["error"]["eligible"]) for row in decisions),
        "control_annulus_pairs": sum(bool(row["control"]["eligible"]) for row in decisions),
        "error_residual_interventions": sum(bool(row["error"]["residual_intervention"]) for row in decisions),
        "control_residual_interventions": sum(bool(row["control"]["residual_intervention"]) for row in decisions),
        "error_anchor_symmetry": rate("error", "anchor_symmetry"),
        "error_zero_symmetry": rate("error", "zero_symmetry"),
        "error_aligned_symmetry": rate("error", "aligned_symmetry"),
        "control_anchor_symmetry": rate("control", "anchor_symmetry"),
        "control_zero_symmetry": rate("control", "zero_symmetry"),
        "control_aligned_symmetry": rate("control", "aligned_symmetry"),
        "outside_annulus_bit_identical": all(
            row[role]["outside_annulus_bit_identical"]
            for row in decisions
            for role in ("error", "control")
        ),
        "error_calibration": error_calibration,
        "control_calibration": control_calibration,
        "paired_sign_flip_pvalue_vs_anchor": ranker._sign_flip(
            paired("aligned_vs_anchor_cp"), samples=min(bootstrap_samples, 10000), seed=bootstrap_seed + 7
        ),
        "paired_sign_flip_pvalue_vs_zero": ranker._sign_flip(
            paired("aligned_vs_zero_cp"), samples=min(bootstrap_samples, 10000), seed=bootstrap_seed + 8
        ),
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    preregistration = json.loads(args.preregistration.read_text())
    if preregistration.get("schema") != prereg.SCHEMA or preregistration.get("verdict") != prereg.READY:
        raise ValueError("paired annulus validation requires a passed immutable pre-registration")
    architecture = preregistration.get("fixed_architecture")
    if not architecture or architecture.get("family") != "paired_exact_image_canonical_equivariant_pairwise_ridge_root_trace_residual_with_annular_risk_gate":
        raise ValueError("pre-registered paired-image architecture drift")
    if architecture.get("required_validation_controls") != [
        "same_cost_shuffled_residual",
        "same_cost_zero_residual",
        "unaltered_CURRICULUM_secondary",
    ]:
        raise ValueError("pre-registered causal controls drift")

    source_report = json.loads(args.ranker_report.read_text())
    if source_report.get("schema") != ranker.SCHEMA or source_report.get("verdict") != preregistration.get("source_verdict"):
        raise ValueError("source ranker report identity drift")
    if source_report.get("inner_validation") is not None or source_report.get("outer_confirm") is not None:
        raise ValueError("source holdout was evaluated before fixed validation")
    if int(source_report.get("outer_confirm_pairs_read", -1)) != 0:
        raise ValueError("source outer confirm read count drift")
    pairs = json.loads(args.pairs.read_text())
    shards = [json.loads(path.read_text()) for path in args.atlas_shard]
    matched, judged, identities, counts = ranker._load_source(pairs, shards)
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        if identities[key] != preregistration[key] or identities[key] != source_report[key]:
            raise ValueError(f"validation {key} identity drift")
    discovery, reclassified = ranker._join_split(matched, judged, split="discovery")
    fit, validation, inner = ranker._inner_split(discovery, seed=2026082235)
    if inner != source_report["inner_split"] or inner != preregistration["inner_split"]:
        raise ValueError("sealed inner split reproduction drift")
    if len(fit) != 103 or len(validation) != 31:
        raise ValueError("sealed 103/31 support drift")
    split_overlap = {
        "opening_id": len(_source_ids(fit, "opening_id") & _source_ids(validation, "opening_id")),
        "game_uid": len(_source_ids(fit, "game_uid") & _source_ids(validation, "game_uid")),
        "exact_state_key": len(
            _source_ids(fit, "exact_state_key") & _source_ids(validation, "exact_state_key")
        ),
    }
    if any(split_overlap.values()):
        raise ValueError(f"fit/validation leakage detected: {split_overlap}")
    counts["informative_errors_by_split"]["discovery"] = len(discovery)
    counts["reclassified_by_split"]["discovery"] = reclassified

    model = _fit(fit)
    metrics = _evaluate(
        validation,
        model,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    sham_means = []
    for index in range(SHAM_REPLICATES):
        sham_model = _fit(fit, sham_seed=args.sham_seed + index)
        sham_metrics = _evaluate(
            validation,
            sham_model,
            bootstrap_samples=200,
            bootstrap_seed=args.sham_seed + 1000 + index,
        )
        sham_means.append(float(sham_metrics["paired_error_minus_control_vs_zero"]["mean"]))
    real = float(metrics["paired_error_minus_control_vs_zero"]["mean"])
    sham_q95 = float(np.quantile(sham_means, 0.95))
    calibration = metrics["error_calibration"]
    gates = {
        "exact_31_pair_holdout": len(validation) == 31,
        "error_vs_anchor_ci95_positive": metrics["error_aligned_vs_anchor"]["ci95"][0] > 0.0,
        "paired_vs_anchor_ci95_positive": metrics["paired_error_minus_control_vs_anchor"]["ci95"][0] > 0.0,
        "controls_vs_anchor_not_harmed_ci95": metrics["control_aligned_vs_anchor"]["ci95"][0] >= -2.0,
        "error_residual_vs_zero_ci95_positive": metrics["error_aligned_vs_zero"]["ci95"][0] > 0.0,
        "paired_residual_vs_zero_ci95_positive": metrics["paired_error_minus_control_vs_zero"]["ci95"][0] > 0.0,
        "paired_sign_flip_vs_zero_p_le_0_025": metrics["paired_sign_flip_pvalue_vs_zero"] <= 0.025,
        "real_residual_exceeds_100_shams_q95": real > sham_q95,
        "at_least_6_error_residual_interventions": metrics["error_residual_interventions"] >= 6,
        "calibration_support_at_least_6": calibration["n"] >= 6,
        "calibration_positive_realization_rate_ge_0_60": (
            calibration["positive_realization_rate"] is not None
            and calibration["positive_realization_rate"] >= 0.60
        ),
        "calibration_abs_mean_bias_le_75cp": (
            calibration["mean_bias_realized_minus_predicted_cp"] is not None
            and abs(calibration["mean_bias_realized_minus_predicted_cp"]) <= 75.0
        ),
        "aligned_symmetry_ge_0_70": metrics["error_aligned_symmetry"] >= 0.70,
        "aligned_symmetry_not_worse": metrics["error_aligned_symmetry"] >= metrics["error_anchor_symmetry"] - 0.02,
        "control_aligned_symmetry_ge_0_70": metrics["control_aligned_symmetry"] >= 0.70,
        "control_aligned_symmetry_not_worse": metrics["control_aligned_symmetry"] >= metrics["control_anchor_symmetry"] - 0.02,
        "outside_annulus_bit_identical": metrics["outside_annulus_bit_identical"],
        "opening_game_state_split_overlap_zero": not any(split_overlap.values()),
    }
    passed = all(gates.values())
    report = {
        "schema": SCHEMA,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        **identities,
        "source_counts": counts,
        "support": {"discovery": len(discovery), "fit": len(fit), "inner_validation": len(validation), "outer_confirm": None},
        "inner_split": inner,
        "fit_validation_overlap": split_overlap,
        "weighting": "pair_equal_and_game_equal_by_one_selected_decision_per_opening_role",
        "fixed_architecture": architecture,
        "validation_metrics": metrics,
        "validation_gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "sham": {
            "replicates": SHAM_REPLICATES,
            "seed": args.sham_seed,
            "real_paired_residual_vs_zero_mean_cp": real,
            "sham_paired_residual_vs_zero_q95_cp": sham_q95,
            "real_exceeds_sham_q95": real > sham_q95,
        },
        "ranker_report_sha256": _sha256(args.ranker_report),
        "preregistration_sha256": _sha256(args.preregistration),
        "pairs_sha256": _sha256(args.pairs),
        "atlas_shards": [{"path": str(path), "sha256": _sha256(path)} for path in args.atlas_shard],
        "inner_validation_decision_payload_reads": len(validation),
        "outer_confirm_decision_payload_reads": 0,
        "diagnostic_residual_fits": 1 + SHAM_REPLICATES,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "production_rule_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "one_shot_outer_confirm" if passed else None,
    }
    envelope = {
        "schema": MODEL_SCHEMA,
        "authorized_for_outer_confirm": passed,
        "authorized_for_production": False,
        "fixed_architecture": architecture,
        "diagnostic_fit_model": model if passed else None,
        "champion_sha256": identities["champion_sha256"],
        "outer_confirm_decision_payload_reads": 0,
        "promotion_authorized": False,
    }
    return report, envelope


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--ranker-report", type=Path, required=True)
    root.add_argument("--preregistration", type=Path, required=True)
    root.add_argument("--pairs", type=Path, required=True)
    root.add_argument("--atlas-shard", action="append", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    root.add_argument("--model", type=Path, required=True)
    root.add_argument("--bootstrap-samples", type=int, default=10000)
    root.add_argument("--bootstrap-seed", type=int, default=2026082243)
    root.add_argument("--sham-seed", type=int, default=2026082244)
    return root


def main() -> int:
    args = parser().parse_args()
    report, model = run(args)
    _publish(args.report, report)
    _publish(args.model, model)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "failed_gates": report["failed_gates"],
                "validation_reads": report["inner_validation_decision_payload_reads"],
                "confirm_reads": report["outer_confirm_decision_payload_reads"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
