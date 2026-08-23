#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sealed OOS comparison of anchored and confirmed baseline residual rules."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_anchored_local_refit as anchored
from jobs.tools import l3_curriculum_error_anchored_local_refit_preregistration as prereg
from jobs.tools import l3_curriculum_error_endgame_abstention_confirmation as confirmation
from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as fresh
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge


SCHEMA = "jass.l3_curriculum_error_anchored_local_refit_oos_audit.v1"
SCHEMA_TERMINAL = "jass.curriculum_error_anchored_local_refit_oos_audit_terminal.v1"
READY = "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_PASSED"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_ANCHORED_LOCAL_REFIT_OOS_NOT_ESTABLISHED"
FIT_TERMINAL_SCHEMA = "jass.curriculum_error_anchored_local_refit_terminal.v1"


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


def _check_fit(report: dict[str, Any], model: dict[str, Any]) -> None:
    if (
        report.get("schema") != FIT_TERMINAL_SCHEMA
        or report.get("verdict") != anchored.READY
        or report.get("passed") is not True
        or report.get("oos_labels_used_for_fit") is not False
        or report.get("oos_availability_preregistration_authorized") is not True
        or report.get("strength_gate_authorized") is not False
        or report.get("failed_gates") != []
        or not report.get("gates")
        or not all(report["gates"].values())
    ):
        raise ValueError("OOS audit requires the passed anchored fit")
    if (
        model.get("schema") != anchored.MODEL_SCHEMA
        or model.get("authorized_for_oos_audit") is not True
        or model.get("authorized_for_strength") is not False
        or model.get("authorized_for_promotion") is not False
        or report.get("model_sha256") != _digest(model)
        or report.get("support", {}).get("support_sha256")
        != model.get("support_sha256")
    ):
        raise ValueError("anchored OOS model identity/authorization drift")
    expected = {
        "model_candidates_fit": 1,
        "residual_production_fits": 1,
        "pattern_eval_fits": 0,
        "oos_reads": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }
    for key, value in expected.items():
        if int(report.get(key, -1)) != value:
            raise ValueError(f"anchored fit sealed/forbidden counter drift: {key}")


def _decision_model(model: dict[str, Any], coefficient_key: str) -> dict[str, Any]:
    return {
        "mean": np.asarray(model["mean"], dtype=float),
        "rms": np.asarray(model["rms"], dtype=float),
        "coef": np.asarray(model[coefficient_key], dtype=float),
    }


def _run_rule(
    rows: list[dict[str, Any]], model: dict[str, Any], coefficient_key: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    decision_model = _decision_model(model, coefficient_key)
    decisions = ridge._decisions(
        rows,
        {row["pair_id"]: decision_model for row in rows},
        cap_cp=100.0,
        threshold_cp=10.0,
        mode="strict_both_change",
    )
    return confirmation._apply_endgame_abstention(rows, decisions)


def _calibration(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    changed = [row["error"] for row in decisions if row["error"]["intervention"]]
    if not changed:
        return {"interventions": 0, "mean_bias_cp": None, "absolute_mean_bias_cp": None}
    biases = [
        float(row["realized_gain_cp"]) - float(row["predicted_advantage_cp"])
        for row in changed
    ]
    mean = float(np.mean(biases))
    return {
        "interventions": len(changed),
        "mean_bias_cp": mean,
        "absolute_mean_bias_cp": abs(mean),
    }


def _changed(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        bool(left["intervention"]) != bool(right["intervention"])
        or left.get("action") != right.get("action")
    )


def _incremental_metrics(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    *,
    seed: int,
) -> dict[str, Any]:
    if [row["pair_id"] for row in baseline] != [row["pair_id"] for row in candidate]:
        raise ValueError("OOS baseline/candidate pair order drift")
    error = [
        float(new["error"]["improvement_cp"])
        - float(old["error"]["improvement_cp"])
        for old, new in zip(baseline, candidate, strict=True)
    ]
    control = [
        float(new["control"]["improvement_cp"])
        - float(old["control"]["improvement_cp"])
        for old, new in zip(baseline, candidate, strict=True)
    ]
    paired = [left - right for left, right in zip(error, control, strict=True)]
    error_changes = sum(
        _changed(old["error"], new["error"])
        for old, new in zip(baseline, candidate, strict=True)
    )
    control_changes = sum(
        _changed(old["control"], new["control"])
        for old, new in zip(baseline, candidate, strict=True)
    )
    return {
        "pairs": len(baseline),
        "error_regret_improvement": ranker._bootstrap(
            error, samples=prereg.OOS_BOOTSTRAP_SAMPLES, seed=seed
        ),
        "control_improvement": ranker._bootstrap(
            control, samples=prereg.OOS_BOOTSTRAP_SAMPLES, seed=seed + 1
        ),
        "paired_error_minus_control": ranker._bootstrap(
            paired, samples=prereg.OOS_BOOTSTRAP_SAMPLES, seed=seed + 2
        ),
        "error_decision_changes": error_changes,
        "control_decision_changes": control_changes,
        "total_decision_changes": error_changes + control_changes,
        "error_values_cp_sha256": _digest(error),
        "control_values_cp_sha256": _digest(control),
        "paired_values_cp_sha256": _digest(paired),
    }


def audit_rows(
    rows: list[dict[str, Any]],
    fit_report: dict[str, Any],
    model: dict[str, Any],
    *,
    champion_sha256: str,
) -> dict[str, Any]:
    _check_fit(fit_report, model)
    pools = Counter(str(row.get("source_pool")) for row in rows)
    baseline, baseline_proof = _run_rule(rows, model, "base_coef")
    candidate, candidate_proof = _run_rule(rows, model, "coef")
    baseline_metrics = confirmation._metrics(
        baseline, seed=prereg.OOS_BOOTSTRAP_SEED + 100
    )
    candidate_metrics = confirmation._metrics(
        candidate, seed=prereg.OOS_BOOTSTRAP_SEED + 200
    )
    incremental = _incremental_metrics(
        baseline, candidate, seed=prereg.OOS_BOOTSTRAP_SEED
    )
    by_pool = {}
    for index, pool in enumerate(("pool1", "pool2"), start=1):
        old = [row for row in baseline if row["source_pool"] == pool]
        new = [row for row in candidate if row["source_pool"] == pool]
        by_pool[pool] = _incremental_metrics(
            old, new, seed=prereg.OOS_BOOTSTRAP_SEED + 1000 * index
        )

    base_calibration = _calibration(baseline)
    candidate_calibration = _calibration(candidate)
    symmetry_drop = (
        float(candidate_metrics["error_anchor_symmetry_rate"])
        - float(candidate_metrics["error_aligned_symmetry_rate"])
    )
    support = [int(index) for index in model["support_indices"]]
    outside = sorted(set(range(len(model["coef"]))) - set(support))
    base_coefficient = np.asarray(model["base_coef"], dtype=float)
    candidate_coefficient = np.asarray(model["coef"], dtype=float)
    identity = {
        "pattern_eval_sha256": champion_sha256,
        "expected_pattern_eval_sha256": model["identities"]["champion_sha256"],
        "pattern_eval_sha256_identical": champion_sha256
        == model["identities"]["champion_sha256"],
        "feature_mean_rms_frozen": True,
        "coefficients_outside_support_bit_identical": bool(
            np.array_equal(base_coefficient[outside], candidate_coefficient[outside])
        ),
        "support_coefficient_signs_preserved": bool(
            np.all(
                np.sign(base_coefficient[support])
                == np.sign(candidate_coefficient[support])
            )
        ),
        "endgame_decisions_bit_identical_to_anchor": candidate_proof[
            "endgame_decisions_bit_identical_to_anchor"
        ],
        "outside_gate_bit_identical": candidate_metrics["outside_gate_bit_identical"],
    }
    gates = {
        "fresh_pairs_exactly_600": len(rows) == prereg.OOS_PAIRS,
        "pool1_pairs_exactly_300": pools == Counter({"pool1": 300, "pool2": 300}),
        "error_decision_changes_at_least_20": incremental["error_decision_changes"]
        >= prereg.MIN_OOS_ERROR_DECISION_CHANGES,
        "control_decision_changes_at_least_12": incremental[
            "control_decision_changes"
        ]
        >= prereg.MIN_OOS_CONTROL_DECISION_CHANGES,
        "total_decision_changes_at_least_32": incremental["total_decision_changes"]
        >= prereg.MIN_OOS_TOTAL_DECISION_CHANGES,
        "incremental_error_regret_ci95_lower_gt_0cp": float(
            incremental["error_regret_improvement"]["ci95"][0]
        )
        > 0.0,
        "incremental_paired_ci95_lower_gt_0cp": float(
            incremental["paired_error_minus_control"]["ci95"][0]
        )
        > 0.0,
        "incremental_control_mean_ge_minus_1cp": float(
            incremental["control_improvement"]["mean"]
        )
        >= -1.0,
        "error_positive_realization_rate_ge_0_60": candidate_metrics[
            "error_positive_realization_rate"
        ]
        is not None
        and float(candidate_metrics["error_positive_realization_rate"]) >= 0.60,
        "calibration_absolute_bias_not_worse_by_more_than_2cp": base_calibration[
            "absolute_mean_bias_cp"
        ]
        is not None
        and candidate_calibration["absolute_mean_bias_cp"] is not None
        and float(candidate_calibration["absolute_mean_bias_cp"])
        <= float(base_calibration["absolute_mean_bias_cp"]) + 2.0,
        "aligned_symmetry_ge_0_70": float(
            candidate_metrics["error_aligned_symmetry_rate"]
        )
        >= 0.70,
        "symmetry_drop_le_0_02": symmetry_drop <= 0.02,
        "endgame_interventions_exactly_0": int(candidate_proof["endgame_interventions"])
        == 0,
        "identity_guards_all_pass": all(
            value for key, value in identity.items() if key.endswith("identical") or key.endswith("preserved") or key == "feature_mean_rms_frozen"
        ),
    }
    for pool, metrics in by_pool.items():
        gates[f"{pool}_incremental_error_mean_gt_0cp"] = float(
            metrics["error_regret_improvement"]["mean"]
        ) > 0.0
        gates[f"{pool}_incremental_paired_mean_gt_0cp"] = float(
            metrics["paired_error_minus_control"]["mean"]
        ) > 0.0
        gates[f"{pool}_incremental_control_mean_ge_minus_1cp"] = float(
            metrics["control_improvement"]["mean"]
        ) >= -1.0
    passed = all(gates.values())
    return {
        "schema": SCHEMA,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        "pairs": len(rows),
        "pairs_by_pool": dict(sorted(pools.items())),
        "baseline_metrics": {
            key: value for key, value in baseline_metrics.items() if key != "paired_values_cp"
        },
        "candidate_metrics": {
            key: value for key, value in candidate_metrics.items() if key != "paired_values_cp"
        },
        "incremental_metrics": incremental,
        "incremental_metrics_by_pool": by_pool,
        "baseline_calibration": base_calibration,
        "candidate_calibration": candidate_calibration,
        "symmetry_drop": symmetry_drop,
        "baseline_rule_proof": baseline_proof,
        "candidate_rule_proof": candidate_proof,
        "identity": identity,
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "model_sha256": _digest(model),
        "support_sha256": model["support_sha256"],
        "oos_labels_used_for_fit_or_selection": False,
        "diagnostic_fits": 0,
        "pattern_eval_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "two_pool_strength_gate_preregistration_authorized": passed,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "two_pool_native_strength_gate_preregistration" if passed else None,
    }


def audit(
    fit_report: dict[str, Any],
    model: dict[str, Any],
    oos_pairs: dict[str, Any],
    oos_shards: list[dict[str, Any]],
    *,
    champion_sha256: str,
) -> dict[str, Any]:
    rows, identities = fresh._load_fresh_rows(
        oos_pairs, oos_shards, pair_count=prereg.OOS_PAIRS
    )
    if identities != model.get("identities") or identities != fit_report.get("identities"):
        raise ValueError("OOS/model scientific identity drift")
    return audit_rows(rows, fit_report, model, champion_sha256=champion_sha256)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--fit-report", type=Path, required=True)
    root.add_argument("--model", type=Path, required=True)
    root.add_argument("--oos-pairs", type=Path, required=True)
    root.add_argument("--oos-shard", action="append", type=Path, required=True)
    root.add_argument("--champion", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    load = lambda path: json.loads(path.read_text())
    report = audit(
        load(args.fit_report),
        load(args.model),
        load(args.oos_pairs),
        [load(path) for path in args.oos_shard],
        champion_sha256=hashlib.sha256(args.champion.read_bytes()).hexdigest(),
    )
    report["fit_report_sha256"] = hashlib.sha256(args.fit_report.read_bytes()).hexdigest()
    report["oos_pairs_sha256"] = hashlib.sha256(args.oos_pairs.read_bytes()).hexdigest()
    _publish(args.report, report)
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "decision_changes": report["incremental_metrics"][
                    "total_decision_changes"
                ],
                "failed_gates": report["failed_gates"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
