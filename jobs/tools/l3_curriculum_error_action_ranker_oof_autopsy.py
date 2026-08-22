#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit the sealed OOF failure of the CURRICULUM action ranker.

This tool consumes only the already-published 1495 report and unauthorized
model envelope.  It must not read the inner-validation or outer-confirm
decision payloads, refit a model, or select a replacement rule.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_curriculum_error_action_ranker as ranker


SCHEMA = "jass.l3_curriculum_error_action_ranker_oof_autopsy.v1"
VERDICT = "JASS_CURRICULUM_ERROR_ACTION_RANKER_OOF_AUTOPSY_READY"
EXPECTED_NEGATIVE = "JASS_CURRICULUM_ERROR_ACTION_RANKER_NOT_ESTABLISHED"


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


def _candidate_row(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = candidate["oof"]
    gates = {str(key): bool(value) for key, value in candidate["oof_gates"].items()}
    return {
        "alpha": float(candidate["alpha"]),
        "advantage_threshold_cp": float(candidate["advantage_threshold_cp"]),
        "margin_band_cp": float(candidate["margin_band_cp"]),
        "selection_score": float(candidate["selection_score"]),
        "oof_passed": bool(candidate["oof_passed"]),
        "failed_gates": sorted(key for key, passed in gates.items() if not passed),
        "gates": gates,
        "error_improvement": metrics["error_improvement"],
        "control_improvement": metrics["control_improvement"],
        "paired_error_minus_control": metrics["paired_error_minus_control"],
        "error_changed_pairs": int(metrics["error_changed_pairs"]),
        "control_changed_pairs": int(metrics["control_changed_pairs"]),
        "error_baseline_symmetry": float(metrics["error_baseline_symmetry"]),
        "error_candidate_symmetry": float(metrics["error_candidate_symmetry"]),
        "control_baseline_symmetry": float(metrics["control_baseline_symmetry"]),
        "control_candidate_symmetry": float(metrics["control_candidate_symmetry"]),
        "error_rate_reduction": metrics["error_rate_reduction"],
        "teacher_hit_gain": metrics["teacher_hit_gain"],
    }


def analyze(report: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema") != ranker.SCHEMA:
        raise ValueError("source ranker report schema drift")
    if report.get("verdict") != EXPECTED_NEGATIVE or report.get("passed") is not False:
        raise ValueError("autopsy requires the sealed negative ranker verdict")
    if report.get("selected_candidate") is not None or report.get("sham") is not None:
        raise ValueError("autopsy requires failure before candidate selection and shams")
    if report.get("inner_validation") is not None or report.get("inner_validation_gates"):
        raise ValueError("inner validation was unexpectedly read")
    if report.get("outer_confirm") is not None or report.get("outer_confirm_gates"):
        raise ValueError("outer confirm was unexpectedly read")
    if int(report.get("outer_confirm_pairs_read", -1)) != 0:
        raise ValueError("outer confirm read count is not zero")
    for key in (
        "pattern_eval_fits",
        "production_model_fits",
        "strength_games",
        "new_selfplay_games",
        "frozen_reads",
    ):
        if int(report.get(key, -1)) != 0:
            raise ValueError(f"forbidden source action recorded: {key}")
    if report.get("production_rule_authorized") is not False:
        raise ValueError("negative ranker unexpectedly authorizes production")
    if model.get("schema") != ranker.MODEL_SCHEMA:
        raise ValueError("source model envelope schema drift")
    if model.get("authorized_for_implementation") is not False:
        raise ValueError("negative model envelope unexpectedly authorizes implementation")
    if model.get("hyperparameters") is not None or model.get("model") is not None:
        raise ValueError("negative model envelope leaked a fitted model")

    candidates = [_candidate_row(candidate) for candidate in report["candidates"]]
    expected_grid = {
        (float(alpha), float(threshold), float(margin))
        for alpha in ranker.RIDGE_ALPHAS
        for threshold in ranker.ADVANTAGE_THRESHOLDS_CP
        for margin in ranker.MARGIN_BANDS_CP
    }
    actual_grid = {
        (row["alpha"], row["advantage_threshold_cp"], row["margin_band_cp"])
        for row in candidates
    }
    if actual_grid != expected_grid or len(candidates) != len(expected_grid):
        raise ValueError("candidate grid coverage drift")
    if any(row["oof_passed"] for row in candidates):
        raise ValueError("negative source contains a passing OOF candidate")

    failures = Counter(
        gate for candidate in candidates for gate in candidate["failed_gates"]
    )
    pass_counts = Counter(
        gate
        for candidate in candidates
        for gate, passed in candidate["gates"].items()
        if passed
    )
    positive = [
        row for row in candidates if row["paired_error_minus_control"]["mean"] > 0.0
    ]
    positive.sort(
        key=lambda row: (
            -float(row["paired_error_minus_control"]["mean"]),
            row["alpha"],
            row["advantage_threshold_cp"],
            row["margin_band_cp"],
        )
    )
    best = max(
        candidates,
        key=lambda row: (
            float(row["paired_error_minus_control"]["mean"]),
            float(row["error_improvement"]["mean"]),
            -row["alpha"],
        ),
    )
    positive_failure_histogram = Counter(
        gate for candidate in positive for gate in candidate["failed_gates"]
    )
    classification = {
        "some_positive_paired_means": bool(positive),
        "any_positive_candidate_passed_paired_probability_gate": any(
            row["gates"].get("paired_probability_positive_ge_0_90", False)
            for row in positive
        ),
        "any_positive_candidate_preserved_controls": any(
            row["gates"].get("controls_not_harmed_mean", False) for row in positive
        ),
        "any_positive_candidate_preserved_symmetry": any(
            row["gates"].get("candidate_symmetry_not_worse", False)
            and row["gates"].get("candidate_symmetry_ge_0_70", False)
            for row in positive
        ),
        "any_positive_candidate_changed_enough_errors": any(
            row["gates"].get("at_least_12_error_pairs_changed", False)
            for row in positive
        ),
    }
    support = report["support"]
    if support.get("outer_confirm") is not None:
        raise ValueError("support manifest says confirm was materialized")
    return {
        "schema": SCHEMA,
        "verdict": VERDICT,
        "source_verdict": report["verdict"],
        "champion_sha256": report["champion_sha256"],
        "jass_sha256": report["jass_sha256"],
        "search_params_sha256": report["search_params_sha256"],
        "support": support,
        "inner_split": report["inner_split"],
        "candidate_count": len(candidates),
        "positive_paired_mean_candidate_count": len(positive),
        "gate_failure_histogram": dict(sorted(failures.items())),
        "gate_pass_histogram": dict(sorted(pass_counts.items())),
        "positive_candidate_failure_histogram": dict(
            sorted(positive_failure_histogram.items())
        ),
        "classification": classification,
        "best_paired_mean_candidate": best,
        "positive_paired_mean_candidates": positive,
        "all_candidates": candidates,
        "validation_decision_payload_reads": 0,
        "outer_confirm_decision_payload_reads": 0,
        "diagnostic_fits": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "production_rule_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "pre_register_one_risk_gated_architecture_or_close",
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--report", type=Path, required=True)
    root.add_argument("--model", type=Path, required=True)
    root.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    report = json.loads(args.report.read_text())
    model = json.loads(args.model.read_text())
    output = analyze(report, model)
    output["source_report_sha256"] = _sha256(args.report)
    output["source_model_sha256"] = _sha256(args.model)
    _publish(args.output, output)
    print(
        json.dumps(
            {
                "verdict": output["verdict"],
                "positive_candidates": output["positive_paired_mean_candidate_count"],
                "best_paired_mean_cp": output["best_paired_mean_candidate"]
                ["paired_error_minus_control"]["mean"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
