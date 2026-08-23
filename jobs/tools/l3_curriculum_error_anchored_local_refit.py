#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fit the single preregistered support-limited residual delta."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_anchored_local_refit_preregistration as prereg
from jobs.tools import l3_curriculum_error_endgame_abstention_confirmation as confirmation
from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as fresh
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge
from jobs.tools import l3_curriculum_error_trace_residual_training as historical


SCHEMA = "jass.l3_curriculum_error_anchored_local_refit.v1"
MODEL_SCHEMA = "jass.l3_curriculum_error_anchored_local_residual_model.v1"
READY = "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_NOT_ESTABLISHED"
PREREG_TERMINAL_SCHEMA = "jass.curriculum_error_anchored_local_refit_preregistration_terminal.v1"


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


def _check_preregistration(report: dict[str, Any]) -> dict[str, Any]:
    if (
        report.get("schema") != PREREG_TERMINAL_SCHEMA
        or report.get("verdict") != prereg.READY
        or report.get("passed") is not True
        or report.get("anchored_local_refit_authorized") is not True
        or report.get("oos_campaign_authorized") is not False
        or report.get("strength_gate_authorized") is not False
        or report.get("automatic_continuation") is not False
    ):
        raise ValueError("anchored fit requires its passed no-OOS preregistration")
    protocol = report.get("protocol") or {}
    fit = protocol.get("fit") or {}
    population = protocol.get("training_population") or {}
    if (
        fit.get("family")
        != "support_limited_pairwise_residual_delta_around_alpha300_full_1508_model"
        or float(fit.get("delta_ridge", -1.0)) != prereg.DELTA_RIDGE
        or float(fit.get("maximum_delta_l2_fraction_of_base_support_norm", -1.0))
        != prereg.MAX_DELTA_L2_FRACTION
        or float(fit.get("maximum_per_coefficient_delta_fraction_of_base_absolute_value", -1.0))
        != prereg.MAX_PER_COEFFICIENT_DELTA_FRACTION
        or int(fit.get("candidate_models", -1)) != 1
        or fit.get("hyperparameter_search") is not False
        or float(population.get("historical_weight", -1.0))
        != prereg.HISTORICAL_CORPUS_WEIGHT
        or float(population.get("confirmed_fresh_weight", -1.0))
        != prereg.CONFIRMED_FRESH_CORPUS_WEIGHT
    ):
        raise ValueError("anchored fit protocol drift")
    support = report.get("support") or {}
    if (
        fit.get("mutable_feature_indices") != support.get("feature_indices")
        or fit.get("mutable_feature_names") != support.get("feature_names")
        or fit.get("signed_support_sha256") != support.get("support_sha256")
    ):
        raise ValueError("anchored fit support/protocol drift")
    return support


def _state_comparisons(
    rows: list[dict[str, Any]],
    base_model: dict[str, Any],
    support_indices: list[int],
    *,
    corpus_weight: float,
) -> tuple[np.ndarray, np.ndarray, float, int, int, int]:
    width = len(support_indices)
    gram = np.zeros((width, width), dtype=float)
    target = np.zeros(width, dtype=float)
    total_weight = 0.0
    comparisons = 0
    non_endgame_states = 0
    endgame_states = 0
    rms = np.asarray(base_model["rms"], dtype=float)
    base_coefficient = np.asarray(base_model["coef"], dtype=float)
    eligible_rows: list[tuple[dict[str, Any], list[str]]] = []
    for row in rows:
        roles = []
        for role in ("error", "control"):
            if confirmation._phase(row[role]) == "endgame":
                endgame_states += 1
            else:
                roles.append(role)
                non_endgame_states += 1
        if roles:
            eligible_rows.append((row, roles))
    for row, roles in eligible_rows:
        role_weight = corpus_weight / len(eligible_rows) / len(roles)
        for role in roles:
            state = row[role]
            values = state["values"]
            teacher = max(values, key=lambda action: (values[action], action))
            others = [action for action in sorted(values) if action != teacher]
            if not others:
                continue
            baseline = {
                action: (
                    state["original_scores"][action]
                    + state["image_scores"][action]
                )
                / 2.0
                for action in values
            }
            comparison_weight = role_weight / len(others)
            for other in others:
                standardized = (
                    state["features"][teacher] - state["features"][other]
                ) / rms
                desired_residual = (values[teacher] - values[other]) - (
                    baseline[teacher] - baseline[other]
                )
                remaining = desired_residual - float(standardized @ base_coefficient)
                vector = standardized[support_indices]
                gram += comparison_weight * np.outer(vector, vector)
                target += comparison_weight * vector * remaining
                total_weight += comparison_weight
                comparisons += 1
    return gram, target, total_weight, comparisons, non_endgame_states, endgame_states


def _fit_anchored_delta(
    historical_rows: list[dict[str, Any]],
    confirmed_rows: list[dict[str, Any]],
    support: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    support_indices = [int(index) for index in support["feature_indices"]]
    support_names = [str(name) for name in support["feature_names"]]
    if support_names != [ranker.FEATURE_NAMES[index] for index in support_indices]:
        raise ValueError("anchored fit support feature identity drift")
    base_model = ridge._fit(historical_rows, alpha=300.0)
    base_coefficient = np.asarray(base_model["coef"], dtype=float)
    signed_support = {
        int(row["index"]): int(row["sign"])
        for row in support.get("signed_features", [])
    }
    if set(signed_support) != set(support_indices) or any(
        signed_support[index] != int(np.sign(base_coefficient[index]))
        for index in support_indices
    ):
        raise ValueError("anchored fit signed support/base coefficient drift")
    parts = [
        _state_comparisons(
            historical_rows,
            base_model,
            support_indices,
            corpus_weight=prereg.HISTORICAL_CORPUS_WEIGHT,
        ),
        _state_comparisons(
            confirmed_rows,
            base_model,
            support_indices,
            corpus_weight=prereg.CONFIRMED_FRESH_CORPUS_WEIGHT,
        ),
    ]
    gram = sum((row[0] for row in parts), np.zeros((len(support_indices), len(support_indices))))
    target = sum((row[1] for row in parts), np.zeros(len(support_indices)))
    total_weight = sum(row[2] for row in parts)
    if total_weight <= 0.0:
        raise ValueError("anchored fit has zero non-endgame comparison weight")
    raw_delta = np.linalg.solve(
        gram / total_weight + prereg.DELTA_RIDGE * np.eye(len(support_indices)),
        target / total_weight,
    )
    base_support = base_coefficient[support_indices]
    per_coefficient_cap = (
        np.abs(base_support) * prereg.MAX_PER_COEFFICIENT_DELTA_FRACTION
    )
    clipped_delta = np.clip(raw_delta, -per_coefficient_cap, per_coefficient_cap)
    global_cap = float(np.linalg.norm(base_support) * prereg.MAX_DELTA_L2_FRACTION)
    clipped_norm = float(np.linalg.norm(clipped_delta))
    global_scale = min(1.0, global_cap / clipped_norm) if clipped_norm > 0.0 else 1.0
    delta = clipped_delta * global_scale
    coefficient = base_coefficient.copy()
    coefficient[support_indices] += delta

    outside = sorted(set(range(base_coefficient.size)) - set(support_indices))
    signs_preserved = bool(
        np.all(np.sign(coefficient[support_indices]) == np.sign(base_support))
    )
    gates = {
        "exactly_one_delta_fit": True,
        "support_size_between_2_and_8": 2 <= len(support_indices) <= 8,
        "mean_bit_identical_to_base": list(base_model["mean"]) == list(base_model["mean"]),
        "rms_bit_identical_to_base": list(base_model["rms"]) == list(base_model["rms"]),
        "coefficients_outside_support_bit_identical": bool(
            np.array_equal(coefficient[outside], base_coefficient[outside])
        ),
        "coefficient_signs_preserved": signs_preserved,
        "per_coefficient_delta_fraction_le_0_25": bool(
            np.all(np.abs(delta) <= per_coefficient_cap + 1e-12)
        ),
        "global_delta_l2_fraction_le_0_20": float(np.linalg.norm(delta))
        <= global_cap + 1e-12,
        "both_corpora_have_non_endgame_states": all(row[4] > 0 for row in parts),
        "both_corpora_contribute_positive_weight": all(row[2] > 0.0 for row in parts),
    }
    model = {
        "schema": MODEL_SCHEMA,
        "feature_names": list(ranker.FEATURE_NAMES),
        "mean": np.asarray(base_model["mean"], dtype=float).tolist(),
        "rms": np.asarray(base_model["rms"], dtype=float).tolist(),
        "base_coef": base_coefficient.tolist(),
        "coef": coefficient.tolist(),
        "support_indices": support_indices,
        "support_names": support_names,
        "support_sha256": support["support_sha256"],
        "delta": delta.tolist(),
        "raw_delta": raw_delta.tolist(),
        "base_alpha": 300.0,
        "delta_ridge": prereg.DELTA_RIDGE,
        "correction_cap_cp": 100.0,
        "mode": "strict_both_change",
        "threshold_cp": 10.0,
        "endgame_rule": "exact_CURRICULUM_anchor_action",
        "authorized_for_oos_audit": all(gates.values()),
        "authorized_for_strength": False,
        "authorized_for_promotion": False,
    }
    diagnostics = {
        "historical_pairs": len(historical_rows),
        "confirmed_fresh_pairs": len(confirmed_rows),
        "historical_non_endgame_states": parts[0][4],
        "confirmed_non_endgame_states": parts[1][4],
        "historical_endgame_states_excluded": parts[0][5],
        "confirmed_endgame_states_excluded": parts[1][5],
        "historical_comparisons": parts[0][3],
        "confirmed_comparisons": parts[1][3],
        "historical_weight": parts[0][2],
        "confirmed_weight": parts[1][2],
        "raw_delta_l2": float(np.linalg.norm(raw_delta)),
        "projected_delta_l2": float(np.linalg.norm(delta)),
        "base_support_l2": float(np.linalg.norm(base_support)),
        "global_cap_l2": global_cap,
        "global_projection_scale": global_scale,
        "per_coefficient_caps": per_coefficient_cap.tolist(),
        "gates": gates,
    }
    return model, diagnostics


def fit(
    preregistration: dict[str, Any],
    historical_pairs: dict[str, Any],
    historical_shards: list[dict[str, Any]],
    confirmed_pairs: dict[str, Any],
    confirmed_shards: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    support = _check_preregistration(preregistration)
    historical_rows, historical_identities = historical._load_rows(
        historical_pairs, historical_shards
    )
    confirmed_rows, confirmed_identities = fresh._load_fresh_rows(
        confirmed_pairs, confirmed_shards, pair_count=600
    )
    if historical_identities != confirmed_identities:
        raise ValueError("anchored fit historical/confirmed scientific identity drift")
    if preregistration.get("identities") != historical_identities:
        raise ValueError("anchored fit preregistration scientific identity drift")
    model, diagnostics = _fit_anchored_delta(
        historical_rows, confirmed_rows, support
    )
    gates = {
        **diagnostics["gates"],
        "historical_gate_fit_pairs_at_least_64": len(historical_rows) >= 64,
        "confirmed_fresh_pairs_exactly_600": len(confirmed_rows) == 600,
        "model_authorized_for_oos_audit": model["authorized_for_oos_audit"],
    }
    passed = all(gates.values())
    model["identities"] = historical_identities
    model["authorized_for_oos_audit"] = passed
    report = {
        "schema": SCHEMA,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        "identities": historical_identities,
        "support": support,
        "model_sha256": _digest(model),
        "base_coefficient_sha256": _digest(model["base_coef"]),
        "anchored_coefficient_sha256": _digest(model["coef"]),
        "diagnostics": diagnostics,
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "fresh_confirmation_labels_used_for_fit": True,
        "oos_labels_used_for_fit": False,
        "model_candidates_fit": 1,
        "residual_production_fits": 1,
        "pattern_eval_fits": 0,
        "oos_reads": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "oos_availability_preregistration_authorized": passed,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "target_free_two_pool_oos_availability" if passed else None,
    }
    return report, model


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--preregistration", type=Path, required=True)
    root.add_argument("--historical-pairs", type=Path, required=True)
    root.add_argument("--historical-shard", action="append", type=Path, required=True)
    root.add_argument("--confirmed-pairs", type=Path, required=True)
    root.add_argument("--confirmed-shard", action="append", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    root.add_argument("--model", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    load = lambda path: json.loads(path.read_text())
    report, model = fit(
        load(args.preregistration),
        load(args.historical_pairs),
        [load(path) for path in args.historical_shard],
        load(args.confirmed_pairs),
        [load(path) for path in args.confirmed_shard],
    )
    report["preregistration_sha256"] = hashlib.sha256(
        args.preregistration.read_bytes()
    ).hexdigest()
    report["historical_pairs_sha256"] = hashlib.sha256(
        args.historical_pairs.read_bytes()
    ).hexdigest()
    report["confirmed_pairs_sha256"] = hashlib.sha256(
        args.confirmed_pairs.read_bytes()
    ).hexdigest()
    _publish(args.report, report)
    _publish(args.model, model)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "support": report["support"]["feature_names"],
                "model_sha256": report["model_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
