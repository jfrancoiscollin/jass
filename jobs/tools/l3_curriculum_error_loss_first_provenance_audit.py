#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit the provenance and score scale of the negative 1538 flip tail.

This is deliberately read-only.  It determines whether the apparent mean
gain/loss is carried by a few search-score sentinels, recomputes bounded
descriptive endpoints, and emits a fixed acquisition contract for the next
loss-first corpus.  It cannot authorize a fit or a strength match.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable


SCHEMA = "jass.l3_curriculum_error_loss_first_provenance_audit.v1"
READY = "JASS_CURRICULUM_ERROR_LOSS_FIRST_PROVENANCE_AUDIT_READY"
SOURCE_SCHEMA = "jass.curriculum_error_action_flip_tail_autopsy_terminal.v1"
SOURCE_VERDICT = "JASS_CURRICULUM_ERROR_ACTION_FLIP_TAIL_AUTOPSY_READY"
SOURCE_CODE = "8b315eafa95df2eea2c69b51b90f0dbada9109a5"
EXPECTED_COUNTS = {
    "pairs": 600,
    "error_interventions": 272,
    "control_interventions": 309,
    "error_positive_interventions": 152,
    "error_negative_interventions": 113,
    "error_zero_interventions": 7,
}
CAPS_CP = (100.0, 200.0, 500.0, 1000.0, 5000.0)
SENTINEL_SCALE_CP = 10_000.0


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


def _mean(values: Iterable[float]) -> float:
    series = list(values)
    return sum(series) / len(series) if series else 0.0


def _clip(value: float, cap: float) -> float:
    return max(-cap, min(cap, value))


def _require_source(report: dict[str, Any]) -> None:
    if (
        report.get("schema") != SOURCE_SCHEMA
        or report.get("code_sha") != SOURCE_CODE
        or report.get("verdict") != SOURCE_VERDICT
        or report.get("passed") is not True
        or report.get("next_stage") != "design_loss_first_corpus"
        or report.get("descriptively_stable_counterfactuals") != []
        or report.get("counts") != EXPECTED_COUNTS
    ):
        raise ValueError("requires the exact certified negative 1538 source")
    for key in (
        "anchored_local_refit_authorized", "production_model_authorized",
        "strength_gate_authorized", "promotion_authorized", "automatic_continuation",
    ):
        if report.get(key) is not False:
            raise ValueError(f"1538 forbidden authorization drift: {key}")
    expected_zero = {
        "new_exact_target_computations": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
    }
    for key, value in expected_zero.items():
        if int(report.get(key, -1)) != value:
            raise ValueError(f"1538 accounting drift: {key}")


def _compact_record(row: dict[str, Any]) -> dict[str, Any]:
    contributions = row.get("feature_contributions_cp", {})
    ranked = sorted(
        contributions.items(), key=lambda item: (abs(float(item[1])), item[0]), reverse=True
    )
    return {
        "pair_id": int(row["pair_id"]),
        "source_pool": str(row["source_pool"]),
        "role": str(row["role"]),
        "improvement_cp": float(row["improvement_cp"]),
        "phase": row.get("phase"),
        "piece_count": int(row.get("piece_count", 0)),
        "outcome": row.get("outcome"),
        "predicted_advantage_cp": row.get("predicted_advantage_cp"),
        "guard_margin_cp": row.get("guard_margin_cp"),
        "correction_clipped": bool(row.get("correction_clipped")),
        "anchor_disagreement": bool(row.get("anchor_disagreement")),
        "proposed_capture": bool(row.get("proposed_capture")),
        "exact_teacher_hit": bool(row.get("exact_teacher_hit")),
        "exact_anchor_regret_cp": float(row.get("exact_anchor_regret_cp", 0.0)),
        "dominant_feature": row.get("dominant_feature"),
        "dominant_feature_family": row.get("dominant_feature_family"),
        "top_signed_contributions_cp": [
            {"name": name, "value": float(value)} for name, value in ranked[:5]
        ],
    }


def _bounded_pair_metrics(
    records: list[dict[str, Any]], report: dict[str, Any], cap: float,
) -> dict[str, Any]:
    by_pool: dict[str, dict[str, float]] = {}
    for pool in ("pool1", "pool2"):
        pool_rows = [row for row in records if row["source_pool"] == pool]
        denominator = int(report["candidate_reproduction"]["by_pool"][pool]["pairs"])
        if denominator <= 0:
            raise ValueError("invalid 1538 pool denominator")
        error = sum(
            _clip(float(row["improvement_cp"]), cap)
            for row in pool_rows if row["role"] == "error"
        ) / denominator
        control = sum(
            _clip(float(row["improvement_cp"]), cap)
            for row in pool_rows if row["role"] == "control"
        ) / denominator
        by_pool[pool] = {
            "pairs": denominator,
            "error_mean_cp": error,
            "control_mean_cp": control,
            "paired_mean_cp": error - control,
        }
    total_pairs = sum(int(row["pairs"]) for row in by_pool.values())
    combined = {}
    for key in ("error_mean_cp", "control_mean_cp", "paired_mean_cp"):
        combined[key] = sum(
            float(row[key]) * int(row["pairs"]) for row in by_pool.values()
        ) / total_pairs
    return {"cap_cp": cap, "by_pool": by_pool, "combined": combined}


def _leave_worst_out(
    records: list[dict[str, Any]], report: dict[str, Any], count: int,
) -> dict[str, Any]:
    error_losses = sorted(
        (row for row in records if row["role"] == "error" and float(row["improvement_cp"]) < 0.0),
        key=lambda row: (float(row["improvement_cp"]), int(row["pair_id"])),
    )
    removed = {(row["source_pool"], int(row["pair_id"]), row["role"]) for row in error_losses[:count]}
    adjusted = [row for row in records if (row["source_pool"], int(row["pair_id"]), row["role"]) not in removed]
    # An omitted intervention is exactly an abstention and contributes zero.
    return {
        "worst_error_interventions_removed": count,
        "removed_pair_ids": [int(row["pair_id"]) for row in error_losses[:count]],
        "metrics": _bounded_pair_metrics(adjusted, report, cap=1e12),
    }


def audit(report: dict[str, Any]) -> dict[str, Any]:
    _require_source(report)
    records = [dict(row) for row in report.get("detailed_interventions", [])]
    errors = [row for row in records if row.get("role") == "error"]
    controls = [row for row in records if row.get("role") == "control"]
    losses = sorted(
        (row for row in errors if float(row["improvement_cp"]) < 0.0),
        key=lambda row: (float(row["improvement_cp"]), int(row["pair_id"])),
    )
    wins = [row for row in errors if float(row["improvement_cp"]) > 0.0]
    if (
        len(errors) != EXPECTED_COUNTS["error_interventions"]
        or len(controls) != EXPECTED_COUNTS["control_interventions"]
        or len(losses) != EXPECTED_COUNTS["error_negative_interventions"]
        or len(wins) != EXPECTED_COUNTS["error_positive_interventions"]
    ):
        raise ValueError("1538 detailed intervention count drift")
    source_loss = report["loss_concentration"]
    total_loss = -sum(float(row["improvement_cp"]) for row in losses)
    if abs(total_loss - float(source_loss["total_loss_cp"])) > 1e-6:
        raise ValueError("1538 total loss recomposition drift")
    sentinel_losses = [row for row in losses if abs(float(row["improvement_cp"])) >= SENTINEL_SCALE_CP]
    top3_share = float(source_loss["top_3_share"])
    score_scale_tail_dominated = bool(sentinel_losses and top3_share >= 0.80)
    raw_error_values = [float(row["improvement_cp"]) for row in errors]
    raw_control_values = [float(row["improvement_cp"]) for row in controls]
    robust = {
        "error_intervention_median_cp": float(median(raw_error_values)),
        "control_intervention_median_cp": float(median(raw_control_values)),
        "bounded_pair_means": [_bounded_pair_metrics(records, report, cap) for cap in CAPS_CP],
        "leave_worst_out": [_leave_worst_out(records, report, count) for count in (1, 3, 5, 10)],
    }
    acquisition = {
        "name": "loss_first_sibling_rank_corpus_v1",
        "selection_before_teacher": (
            "all champion decisions from fresh lost/drawn/won games; opening/game split and "
            "candidate sampling use only shallow-search instability, phase, material and branching"
        ),
        "teacher": "same champion, two independent deeper budgets, all legal sibling actions",
        "accepted_label": (
            "teacher top-action and WDL ordering agree across both deep budgets and exact symmetry"
        ),
        "primary_target": "bounded pairwise/listwise sibling ordering; no raw CP mean endpoint",
        "per_opening_vote_cap": 1,
        "per_game_state_cap": 2,
        "controls": "opening-disjoint regret<=10cp decisions matched by phase/material/capture/branching",
        "split_unit": "connected opening_id/game_uid/canonical-state component",
        "fit_scope": "not authorized by this audit",
        "reason": (
            "catastrophic CP tail makes raw mean gain non-robust"
            if score_scale_tail_dominated
            else "no target-free abstention rule replicated in 1538"
        ),
    }
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "scientific_status": (
            "raw_cp_endpoint_tail_dominated__loss_first_rank_supervision_required"
            if score_scale_tail_dominated
            else "simple_abstention_closed__loss_first_acquisition_required"
        ),
        "source": {
            "job": "cpx62-1538-l3-curriculum-error-action-flip-tail-autopsy-v1",
            "attempt": "20260823T143226Z-8b315eaf",
            "code_sha": SOURCE_CODE,
            "report_sha256": _digest(report),
        },
        "counts": dict(report["counts"]),
        "loss_tail": {
            "total_loss_cp": total_loss,
            "top_1_share": float(source_loss["top_1_share"]),
            "top_3_share": top3_share,
            "sentinel_scale_cp": SENTINEL_SCALE_CP,
            "sentinel_scale_loss_count": len(sentinel_losses),
            "sentinel_scale_loss_share": (
                -sum(float(row["improvement_cp"]) for row in sentinel_losses) / total_loss
                if total_loss else 0.0
            ),
            "score_scale_tail_dominated": score_scale_tail_dominated,
        },
        "worst_error_interventions": [_compact_record(row) for row in losses[:10]],
        "robustness": robust,
        "negative_weight_axis": report["feature_attribution"]["negative_error_interventions"],
        "loss_first_acquisition_contract": acquisition,
        "descriptive_rules_reused_for_confirmation": 0,
        "new_exact_target_computations": 0,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "anchored_local_refit_authorized": False,
        "production_model_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "preregister_loss_first_sibling_rank_corpus",
    }


def parser() -> argparse.ArgumentParser:
    output = argparse.ArgumentParser(description=__doc__)
    output.add_argument("--source-report", type=Path, required=True)
    output.add_argument("--report", type=Path, required=True)
    return output


def main() -> int:
    args = parser().parse_args()
    report = audit(json.loads(args.source_report.read_text(encoding="utf-8")))
    _publish(args.report, report)
    print(json.dumps({
        "verdict": report["verdict"],
        "scientific_status": report["scientific_status"],
        "next_stage": report["next_stage"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
