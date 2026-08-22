#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pre-register one fixed equivariant-annular CURRICULUM action correction.

The input is limited to the already-published 1495 OOF report and its 1497
read-only autopsy.  No decision payload, validation row, confirm row or fitted
model is read here.  The only architecture that can be emitted is the fixed
strongly-regularised annulus suggested by the replicated margin interaction in
the original 27-candidate OOF lattice.  The universal symmetry failure found
by the sealed autopsy is addressed structurally through a canonical coordinate
system, not by another tuned candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from jobs.tools import l3_curriculum_error_action_ranker as ranker
    from jobs.tools import l3_curriculum_error_action_ranker_oof_autopsy as autopsy
except ModuleNotFoundError:  # pragma: no cover - direct CPX script execution
    import l3_curriculum_error_action_ranker as ranker  # type: ignore
    import l3_curriculum_error_action_ranker_oof_autopsy as autopsy  # type: ignore


SCHEMA = "jass.l3_curriculum_error_action_annulus_preregistration.v1"
READY = "JASS_CURRICULUM_ERROR_ACTION_ANNULUS_PREREGISTERED"
CLOSED = "JASS_CURRICULUM_ERROR_ACTION_ANNULUS_NOT_JUSTIFIED"

FIXED_ALPHA = 100.0
FIXED_ADVANTAGE_THRESHOLD_CP = 25.0
FIXED_MARGIN_LOWER_OPEN_CP = 50.0
FIXED_MARGIN_UPPER_CLOSED_CP = 100.0
MIN_REPLICATED_ANNULUS_DELTA_CP = 50.0


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


def _candidate(
    report: dict[str, Any], *, alpha: float, threshold: float, margin: float
) -> dict[str, Any]:
    rows = [
        row
        for row in report["candidates"]
        if float(row["alpha"]) == alpha
        and float(row["advantage_threshold_cp"]) == threshold
        and float(row["margin_band_cp"]) == margin
    ]
    if len(rows) != 1:
        raise ValueError(
            f"candidate lattice drift for alpha={alpha} threshold={threshold} margin={margin}"
        )
    return rows[0]


def _paired(row: dict[str, Any]) -> float:
    return float(row["oof"]["paired_error_minus_control"]["mean"])


def analyze(report: dict[str, Any], readout: dict[str, Any]) -> dict[str, Any]:
    if report.get("schema") != ranker.SCHEMA:
        raise ValueError("ranker report schema drift")
    if report.get("verdict") != autopsy.EXPECTED_NEGATIVE or report.get("passed") is not False:
        raise ValueError("pre-registration requires the negative 1495 OOF verdict")
    if report.get("selected_candidate") is not None or report.get("sham") is not None:
        raise ValueError("source unexpectedly selected a candidate")
    if report.get("inner_validation") is not None or report.get("inner_validation_gates"):
        raise ValueError("source inner validation was already evaluated")
    if report.get("outer_confirm") is not None or report.get("outer_confirm_gates"):
        raise ValueError("source outer confirm was already evaluated")
    if int(report.get("outer_confirm_pairs_read", -1)) != 0:
        raise ValueError("source outer confirm read count drift")
    if readout.get("schema") != autopsy.SCHEMA or readout.get("verdict") != autopsy.VERDICT:
        raise ValueError("1497 OOF autopsy identity drift")
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        if report.get(key) != readout.get(key):
            raise ValueError(f"source/readout {key} mismatch")
    for key in ("validation_decision_payload_reads", "outer_confirm_decision_payload_reads"):
        if int(readout.get(key, -1)) != 0:
            raise ValueError(f"sealed readout counter drift: {key}")
    for key in (
        "diagnostic_fits",
        "pattern_eval_fits",
        "production_model_fits",
        "strength_games",
        "new_selfplay_games",
        "frozen_reads",
    ):
        if int(readout.get(key, -1)) != 0:
            raise ValueError(f"forbidden readout action: {key}")

    evidence: list[dict[str, Any]] = []
    gates: dict[str, bool] = {}
    for alpha in (10.0, 100.0):
        low = _candidate(report, alpha=alpha, threshold=25.0, margin=50.0)
        annulus_plus_low = _candidate(report, alpha=alpha, threshold=25.0, margin=100.0)
        wide = _candidate(report, alpha=alpha, threshold=25.0, margin=200.0)
        low_mean, upper_mean, wide_mean = map(_paired, (low, annulus_plus_low, wide))
        delta = upper_mean - low_mean
        evidence.append(
            {
                "alpha": alpha,
                "threshold_cp": 25.0,
                "margin_le_50_paired_mean_cp": low_mean,
                "margin_le_100_paired_mean_cp": upper_mean,
                "margin_le_200_paired_mean_cp": wide_mean,
                "increment_attributable_to_50_100_cp_annulus": delta,
                "error_changed_pairs_by_margin": {
                    "50": int(low["oof"]["error_changed_pairs"]),
                    "100": int(annulus_plus_low["oof"]["error_changed_pairs"]),
                    "200": int(wide["oof"]["error_changed_pairs"]),
                },
            }
        )
        gates[f"alpha_{int(alpha)}_low_band_negative"] = low_mean < 0.0
        gates[f"alpha_{int(alpha)}_upper_band_positive"] = upper_mean > 0.0
        gates[f"alpha_{int(alpha)}_annulus_delta_ge_50cp"] = (
            delta >= MIN_REPLICATED_ANNULUS_DELTA_CP
        )
        gates[f"alpha_{int(alpha)}_no_increment_above_100cp"] = abs(wide_mean - upper_mean) <= 1e-12

    strong_t25 = _candidate(report, alpha=100.0, threshold=25.0, margin=100.0)
    strong_t50 = _candidate(report, alpha=100.0, threshold=50.0, margin=100.0)
    gates["strong_anchor_best_of_replicated_positive_points"] = _paired(strong_t25) >= max(
        _paired(_candidate(report, alpha=10.0, threshold=25.0, margin=100.0)),
        _paired(strong_t50),
    )
    gates["threshold_robust_at_50cp"] = _paired(strong_t50) > 0.0
    classification = readout["classification"]
    failure_histogram = {
        str(key): int(value) for key, value in readout["gate_failure_histogram"].items()
    }
    gates["positive_candidates_exist"] = bool(
        readout.get("positive_paired_mean_candidate_count", 0)
    )
    gates["positive_candidate_changed_enough_errors"] = bool(
        classification.get("any_positive_candidate_changed_enough_errors")
    )
    gates["positive_candidate_preserved_controls"] = bool(
        classification.get("any_positive_candidate_preserved_controls")
    )
    gates["paired_probability_failure_is_universal"] = (
        failure_histogram.get("paired_probability_positive_ge_0_90") == 27
        and not classification.get("any_positive_candidate_passed_paired_probability_gate")
    )
    gates["symmetry_failure_is_universal"] = (
        failure_histogram.get("candidate_symmetry_ge_0_70") == 27
        and failure_histogram.get("candidate_symmetry_not_worse") == 27
        and not classification.get("any_positive_candidate_preserved_symmetry")
    )
    gates["no_other_universal_gate_failure"] = set(failure_histogram) == {
        "paired_probability_positive_ge_0_90",
        "candidate_symmetry_ge_0_70",
        "candidate_symmetry_not_worse",
    }

    passed = all(gates.values())
    architecture = {
        "family": "canonical_equivariant_pairwise_ridge_root_trace_residual_with_annular_risk_gate",
        "features": list(ranker.FEATURE_NAMES),
        "feature_depths": list(ranker.FEATURE_DEPTHS),
        "alpha": FIXED_ALPHA,
        "predicted_advantage_threshold_cp": FIXED_ADVANTAGE_THRESHOLD_CP,
        "baseline_d9_margin_lower_open_cp": FIXED_MARGIN_LOWER_OPEN_CP,
        "baseline_d9_margin_upper_closed_cp": FIXED_MARGIN_UPPER_CLOSED_CP,
        "correction_cap_cp": ranker.CORRECTION_CAP_CP,
        "anchor": "CURRICULUM_Q00_d9",
        "additional_search_nodes": 0,
        "canonical_coordinates": "lexicographic_min_of_exact_state_and_its_exact_image",
        "canonical_tie_break": "action_code_in_canonical_coordinates",
        "trace_transport": "remap_completed_d6_d9_root_trace_without_new_search",
        "symmetry": "equivariant_by_construction_map_selected_action_back_to_caller_orientation",
        "intervention": "only_if_50_lt_baseline_margin_le_100_and_predicted_advantage_ge_25",
        "abstention": "bit_identical_to_CURRICULUM_outside_annulus",
    }
    return {
        "schema": SCHEMA,
        "verdict": READY if passed else CLOSED,
        "passed": passed,
        "source_verdict": report["verdict"],
        "champion_sha256": report["champion_sha256"],
        "jass_sha256": report["jass_sha256"],
        "search_params_sha256": report["search_params_sha256"],
        "support": report["support"],
        "inner_split": report["inner_split"],
        "mechanistic_evidence": evidence,
        "source_gate_failure_histogram": failure_histogram,
        "mechanistic_gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "fixed_architecture": architecture if passed else None,
        "architectures_considered": 1,
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
        "next_stage": "one_shot_inner_validation_31" if passed else None,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--ranker-report", type=Path, required=True)
    root.add_argument("--oof-autopsy", type=Path, required=True)
    root.add_argument("--output", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    report = json.loads(args.ranker_report.read_text())
    readout = json.loads(args.oof_autopsy.read_text())
    output = analyze(report, readout)
    output["source_ranker_report_sha256"] = _sha256(args.ranker_report)
    output["source_oof_autopsy_sha256"] = _sha256(args.oof_autopsy)
    _publish(args.output, output)
    print(
        json.dumps(
            {
                "verdict": output["verdict"],
                "failed_gates": output["failed_gates"],
                "next_stage": output["next_stage"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
