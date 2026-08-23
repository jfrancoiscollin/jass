#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Identify a fold-stable residual coefficient subspace on sealed 1508 data."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge
from jobs.tools import l3_curriculum_error_trace_proxy_preregistration as prereg
from jobs.tools import l3_curriculum_error_trace_residual_training as source


SCHEMA = "jass.l3_curriculum_error_residual_stable_subspace_screen.v1"
READY = "JASS_CURRICULUM_ERROR_RESIDUAL_STABLE_SUBSPACE_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_RESIDUAL_STABLE_SUBSPACE_NOT_ESTABLISHED"
ALPHA = 300.0
TOP_K = 6
MIN_TOP_K_FOLDS = 4
MAX_ABS_COEFFICIENT_CV = 0.75
MIN_COEFFICIENT_COSINE = 0.75
MIN_TOP_K_JACCARD = 0.40
MIN_SELECTED_FEATURES = 2
MAX_SELECTED_FEATURES = 8


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _top_indices(coefficient: np.ndarray) -> set[int]:
    order = sorted(
        range(coefficient.size),
        key=lambda index: (-abs(float(coefficient[index])), index),
    )
    return set(order[:TOP_K])


def _jaccard(left: set[int], right: set[int]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _analyze_models(
    fold_models: list[dict[str, Any]], full_model: dict[str, Any]
) -> dict[str, Any]:
    if len(fold_models) != prereg.FOLDS:
        raise ValueError("stable subspace requires exactly five fold models")
    coefficients = [np.asarray(model["coef"], dtype=float) for model in fold_models]
    full = np.asarray(full_model["coef"], dtype=float)
    width = len(ranker.FEATURE_NAMES)
    if full.size != width or any(row.size != width for row in coefficients):
        raise ValueError("stable subspace coefficient width drift")
    if any(not np.all(np.isfinite(row)) for row in [*coefficients, full]):
        raise ValueError("stable subspace non-finite coefficient")

    top_sets = [_top_indices(row) for row in coefficients]
    full_top = _top_indices(full)
    cosines = []
    jaccards = []
    for left_index, right_index in itertools.combinations(range(len(coefficients)), 2):
        left, right = coefficients[left_index], coefficients[right_index]
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        cosines.append(float(left @ right / denominator) if denominator else 1.0)
        jaccards.append(_jaccard(top_sets[left_index], top_sets[right_index]))

    features = []
    selected_indices = []
    for index, name in enumerate(ranker.FEATURE_NAMES):
        fold_values = np.asarray([row[index] for row in coefficients], dtype=float)
        absolute = np.abs(fold_values)
        mean_absolute = float(np.mean(absolute))
        coefficient_cv = (
            float(np.std(absolute) / mean_absolute) if mean_absolute > 0.0 else None
        )
        signs = np.sign(np.append(fold_values, full[index])).astype(int)
        same_nonzero_sign = bool(np.all(signs == signs[0]) and signs[0] != 0)
        top_fold_count = sum(index in row for row in top_sets)
        gates = {
            "same_nonzero_sign_all_folds_and_full": same_nonzero_sign,
            "top6_in_at_least_4_of_5_folds": top_fold_count >= MIN_TOP_K_FOLDS,
            "top6_in_full_fit": index in full_top,
            "absolute_coefficient_cv_le_0_75": coefficient_cv is not None
            and coefficient_cv <= MAX_ABS_COEFFICIENT_CV,
        }
        selected = all(gates.values())
        if selected:
            selected_indices.append(index)
        features.append(
            {
                "index": index,
                "name": name,
                "fold_coefficients": fold_values.tolist(),
                "full_coefficient": float(full[index]),
                "sign": int(signs[0]) if same_nonzero_sign else None,
                "mean_absolute_fold_coefficient": mean_absolute,
                "absolute_coefficient_cv": coefficient_cv,
                "top6_fold_count": top_fold_count,
                "full_top6": index in full_top,
                "gates": gates,
                "selected": selected,
            }
        )

    selected_names = [ranker.FEATURE_NAMES[index] for index in selected_indices]
    support_payload = {
        "alpha": ALPHA,
        "feature_names": selected_names,
        "feature_indices": selected_indices,
        "signs": [features[index]["sign"] for index in selected_indices],
    }
    return {
        "features": features,
        "selected_feature_indices": selected_indices,
        "selected_feature_names": selected_names,
        "selected_feature_count": len(selected_indices),
        "support_sha256": hashlib.sha256(_canonical(support_payload)).hexdigest(),
        "fold_stability": {
            "minimum_coefficient_cosine": min(cosines),
            "mean_coefficient_cosine": float(np.mean(cosines)),
            "minimum_top6_jaccard": min(jaccards),
            "mean_top6_jaccard": float(np.mean(jaccards)),
        },
    }


def screen(
    registration: dict[str, Any],
    training_report: dict[str, Any],
    failed_model: dict[str, Any],
    pairs: dict[str, Any],
    shards: list[dict[str, Any]],
) -> dict[str, Any]:
    source._check_preregistration(registration)
    ridge._check_source(training_report, failed_model)
    rows, identities = source._load_rows(pairs, shards)
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        if (
            identities[key] != training_report.get(key)
            or identities[key] != failed_model.get(key)
            or identities[key] != registration.get(key)
        ):
            raise ValueError(f"stable subspace source {key} drift")

    folds, fold_manifest = source._components_folds(rows)
    _, fold_models = ridge._oof_models(rows, folds, alpha=ALPHA)
    full_model = ridge._fit(rows, alpha=ALPHA)
    analysis = _analyze_models(fold_models, full_model)
    stability = analysis["fold_stability"]
    gates = {
        "immutable_gate_fit_pairs_at_least_64": len(rows) >= 64,
        "five_nonempty_component_folds": all(
            int(value) > 0 for value in fold_manifest["counts"].values()
        ),
        "minimum_coefficient_cosine_ge_0_75": stability[
            "minimum_coefficient_cosine"
        ]
        >= MIN_COEFFICIENT_COSINE,
        "minimum_top6_jaccard_ge_0_40": stability["minimum_top6_jaccard"]
        >= MIN_TOP_K_JACCARD,
        "selected_feature_count_between_2_and_8": MIN_SELECTED_FEATURES
        <= analysis["selected_feature_count"]
        <= MAX_SELECTED_FEATURES,
    }
    passed = all(gates.values())
    return {
        "schema": SCHEMA,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        **identities,
        "source_verdict": training_report["verdict"],
        "population": "immutable_1508_gate_fit_pairs_only",
        "alpha": ALPHA,
        "selection_rule": {
            "top_k": TOP_K,
            "minimum_top_k_folds": MIN_TOP_K_FOLDS,
            "same_nonzero_sign": "all_5_fold_fits_and_full_fit",
            "maximum_absolute_coefficient_cv": MAX_ABS_COEFFICIENT_CV,
            "full_fit_top_k_required": True,
            "minimum_selected_features": MIN_SELECTED_FEATURES,
            "maximum_selected_features": MAX_SELECTED_FEATURES,
        },
        "fold_manifest": fold_manifest,
        "analysis": analysis,
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "diagnostic_residual_fits": prereg.FOLDS + 1,
        "new_exact_target_computations": 0,
        "fresh_label_reads": 0,
        "feature_audit_action_value_reads": 0,
        "outer_confirm_action_value_reads": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "stable_subspace_candidate_established": passed,
        "anchored_refit_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": (
            "joint_preregistration_after_independent_fresh_confirmation_pass"
            if passed
            else None
        ),
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
    report["gate_fit_pairs_sha256"] = hashlib.sha256(
        args.pairs.read_bytes()
    ).hexdigest()
    _publish(args.report, report)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "selected_feature_count": report["analysis"][
                    "selected_feature_count"
                ],
                "support_sha256": report["analysis"]["support_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
