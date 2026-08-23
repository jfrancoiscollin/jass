#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One-shot OOS feature audit of the fixed 1508 CURRICULUM residual."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_paired_coverage_screen as coverage
from jobs.tools import l3_curriculum_error_trace_proxy_preregistration as prereg
from jobs.tools import l3_curriculum_error_trace_residual_training as training
from jobs.tools import l3_curriculum_search_error_atlas as atlas


SCHEMA = "jass.l3_curriculum_error_trace_residual_feature_audit.v1"
PAIRS_SCHEMA = "jass.l3_curriculum_error_trace_residual_feature_audit_pairs.v1"
READY = "JASS_CURRICULUM_ERROR_TRACE_RESIDUAL_FEATURE_AUDIT_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_TRACE_RESIDUAL_FEATURE_AUDIT_NOT_ESTABLISHED"
BOOTSTRAP_SAMPLES = 20_000
BOOTSTRAP_SEED = 2026082255


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


def _check_training(
    registration: dict[str, Any],
    report: dict[str, Any],
    model: dict[str, Any],
) -> None:
    training._check_preregistration(registration)
    if report.get("schema") != training.SCHEMA or report.get("verdict") != training.READY or report.get("passed") is not True:
        raise ValueError("feature audit requires passed residual training")
    if model.get("schema") != training.MODEL_SCHEMA or model.get("authorized_for_feature_audit") is not True:
        raise ValueError("feature audit model authorization drift")
    if model.get("authorized_for_production") is not False or model.get("promotion_authorized") is not False:
        raise ValueError("feature audit model exposed production authorization")
    if model.get("aligned_model") is None or model.get("shuffled_model") is None:
        raise ValueError("feature audit fixed controls are incomplete")
    if model.get("fixed_architecture") != registration.get("fixed_architecture"):
        raise ValueError("feature audit architecture drift")
    if float(model.get("selected_threshold_cp", -1.0)) not in prereg.THRESHOLDS_CP:
        raise ValueError("feature audit threshold drift")
    for key in (
        "feature_audit_action_value_reads",
        "outer_confirm_action_value_reads",
        "pattern_eval_fits",
        "strength_games",
        "new_selfplay_games",
        "frozen_reads",
    ):
        if int(report.get(key, -1)) != 0:
            raise ValueError(f"feature audit sealed/forbidden training counter drift: {key}")


def materialize(
    pairs: dict[str, Any],
    registration: dict[str, Any],
    split_manifest: dict[str, Any],
    gate_fit_pairs: dict[str, Any],
    training_report: dict[str, Any],
    model: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reproduce the sealed split and expose only the target-free audit profiles."""
    _check_training(registration, training_report, model)
    regenerated_fit, regenerated_manifest = training.split_profiles(pairs, registration)
    if split_manifest != regenerated_manifest:
        raise ValueError("feature audit split manifest drift")
    if gate_fit_pairs != regenerated_fit:
        raise ValueError("feature audit gate-fit source drift")
    gate_digest = hashlib.sha256(_canonical(gate_fit_pairs)).hexdigest()
    registration_digest = hashlib.sha256(_canonical(registration)).hexdigest()
    for payload, name in ((training_report, "training report"), (model, "training model")):
        if payload.get("gate_fit_pairs_sha256") != gate_digest:
            raise ValueError(f"feature audit {name} gate-fit identity drift")
        if payload.get("preregistration_sha256") != registration_digest:
            raise ValueError(f"feature audit {name} pre-registration identity drift")

    audit_ids = {int(value) for value in split_manifest.get("feature_audit_pair_ids", [])}
    rows = [row for row in pairs.get("pairs", []) if int(row["pair_id"]) in audit_ids]
    if {int(row["pair_id"]) for row in rows} != audit_ids:
        raise ValueError("feature audit profile coverage drift")
    if len(rows) < coverage.MIN_AUDIT_PAIRS:
        raise ValueError("feature audit support drift")
    if coverage._forbidden_keys(rows):
        raise ValueError("feature audit profiles contain action targets")
    fit_ids = coverage._identity_sets(gate_fit_pairs["pairs"])
    audit_identity = coverage._identity_sets(rows)
    overlap = {key: len(fit_ids[key] & audit_identity[key]) for key in fit_ids}
    if any(overlap.values()):
        raise ValueError(f"feature audit leakage: {overlap}")

    output = {
        "schema": atlas.SCHEMA_PAIRS,
        "matching_passed": True,
        "matched_pairs": len(rows),
        "pairs_by_split": {"discovery": len(rows), "confirm": 0},
        "pairs": rows,
        "source_pairs_sha256": hashlib.sha256(_canonical(pairs)).hexdigest(),
        "split_manifest_sha256": hashlib.sha256(_canonical(split_manifest)).hexdigest(),
        "subset": "feature_audit",
    }
    certificate = {
        "schema": PAIRS_SCHEMA,
        "feature_audit_pairs": len(rows),
        "pair_ids": sorted(audit_ids),
        "overlap": overlap,
        "feature_audit_pairs_sha256": hashlib.sha256(_canonical(output)).hexdigest(),
        "gate_fit_action_value_reads": int(training_report["gate_fit_action_value_reads"]),
        "feature_audit_action_value_reads": 0,
        "outer_confirm_profile_rows_examined": 0,
        "outer_confirm_action_value_reads": 0,
        "residual_fits": 0,
    }
    return output, certificate


def _load_rows(
    pairs: dict[str, Any], shards: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if pairs.get("subset") != "feature_audit" or pairs.get("matching_passed") is not True:
        raise ValueError("audit requires feature-audit-only pairs")
    profiles_list = list(pairs.get("pairs", []))
    if len(profiles_list) != int(pairs.get("matched_pairs", -1)):
        raise ValueError("audit feature pair count drift")
    if coverage._forbidden_keys(profiles_list):
        raise ValueError("audit profiles contain action targets")
    if len(shards) != 16 or {int(row.get("shard", -1)) for row in shards} != set(range(16)):
        raise ValueError("audit atlas shards incomplete")
    digest = hashlib.sha256(_canonical(pairs)).hexdigest()
    for shard in shards:
        if shard.get("schema") != atlas.SCHEMA_ATLAS_SHARD or shard.get("pairs_sha256") != digest:
            raise ValueError("audit atlas source drift")
        if int(shard.get("max_pairs", -1)) != 0 or int(shard.get("nshards", -1)) != 16:
            raise ValueError("audit atlas execution drift")

    identities: dict[str, str] = {}
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        values = {str(shard.get(key, "")) for shard in shards}
        if len(values) != 1 or not next(iter(values)):
            raise ValueError(f"audit atlas {key} drift")
        identities[key] = next(iter(values))

    judged = {int(row["pair_id"]): row for shard in shards for row in shard.get("rows", [])}
    profiles = {int(row["pair_id"]): row for row in profiles_list}
    if set(judged) != set(profiles):
        raise ValueError("audit atlas pair coverage drift")
    rows: list[dict[str, Any]] = []
    for pair_id in sorted(profiles):
        raw, exact = profiles[pair_id], judged[pair_id]
        row: dict[str, Any] = {"pair_id": pair_id}
        for role in ("error", "control"):
            features, original_scores, image_scores = training._paired_features(raw[role])
            values = ranker._true_values(exact[role])
            if set(features) != set(values):
                raise ValueError("audit feature/judge action set drift")
            row[role] = {
                "profile": raw[role],
                "features": features,
                "original_scores": original_scores,
                "image_scores": image_scores,
                "values": values,
            }
        rows.append(row)
    return rows, identities


def _decisions(
    rows: list[dict[str, Any]], model: dict[str, Any], threshold: float
) -> list[dict[str, Any]]:
    return [
        {
            "pair_id": row["pair_id"],
            "error": training._decision(row["error"], model, threshold=threshold),
            "control": training._decision(row["control"], model, threshold=threshold),
        }
        for row in rows
    ]


def _comparison(
    aligned: list[dict[str, Any]], shuffled: list[dict[str, Any]]
) -> dict[str, Any]:
    error = [
        left["error"]["improvement_cp"] - right["error"]["improvement_cp"]
        for left, right in zip(aligned, shuffled, strict=True)
    ]
    control = [
        left["control"]["improvement_cp"] - right["control"]["improvement_cp"]
        for left, right in zip(aligned, shuffled, strict=True)
    ]
    paired = [left - right for left, right in zip(error, control, strict=True)]
    return {
        "error": ranker._bootstrap(error, samples=BOOTSTRAP_SAMPLES, seed=BOOTSTRAP_SEED + 20),
        "control": ranker._bootstrap(control, samples=BOOTSTRAP_SAMPLES, seed=BOOTSTRAP_SEED + 21),
        "paired_error_minus_control": ranker._bootstrap(
            paired, samples=BOOTSTRAP_SAMPLES, seed=BOOTSTRAP_SEED + 22
        ),
    }


def audit(
    registration: dict[str, Any],
    training_report: dict[str, Any],
    model: dict[str, Any],
    pairs: dict[str, Any],
    shards: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate the fixed model exactly once; this function performs no fit."""
    _check_training(registration, training_report, model)
    rows, identities = _load_rows(pairs, shards)
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        if identities[key] != model.get(key) or identities[key] != training_report.get(key):
            raise ValueError(f"audit/training {key} drift")

    threshold = float(model["selected_threshold_cp"])
    aligned_decisions = _decisions(rows, model["aligned_model"], threshold)
    shuffled_decisions = _decisions(rows, model["shuffled_model"], threshold)
    aligned = training._evaluate(
        rows, model["aligned_model"], threshold=threshold, bootstrap_seed=BOOTSTRAP_SEED
    )
    shuffled = training._evaluate(
        rows,
        model["shuffled_model"],
        threshold=threshold,
        bootstrap_seed=BOOTSTRAP_SEED + 10,
    )
    versus_shuffled = _comparison(aligned_decisions, shuffled_decisions)

    symmetry_drops = {
        role: aligned[f"{role}_anchor_symmetry"] - aligned[f"{role}_aligned_symmetry"]
        for role in ("error", "control")
    }
    gates = {
        "feature_audit_pairs_at_least_24": len(rows) >= coverage.MIN_AUDIT_PAIRS,
        "error_vs_anchor_ci95_lower_gt_0cp": aligned["error_improvement"]["ci95"][0] > 0.0,
        "paired_error_minus_control_ci95_lower_gt_0cp": aligned["paired_error_minus_control"]["ci95"][0] > 0.0,
        "control_vs_anchor_ci95_lower_ge_minus_2cp": aligned["control_improvement"]["ci95"][0] >= -2.0,
        "error_interventions_at_least_6": aligned["error_interventions"] >= 6,
        "error_positive_realization_rate_ge_0_60": aligned["error_positive_realization_rate"] is not None
        and aligned["error_positive_realization_rate"] >= 0.60,
        "absolute_error_calibration_bias_at_most_75cp": aligned["error_calibration_mean_bias_cp"] is not None
        and abs(aligned["error_calibration_mean_bias_cp"]) <= 75.0,
        "aligned_error_symmetry_at_least_0_70": aligned["error_aligned_symmetry"] >= 0.70,
        "aligned_control_symmetry_at_least_0_70": aligned["control_aligned_symmetry"] >= 0.70,
        "error_symmetry_drop_at_most_0_02": symmetry_drops["error"] <= 0.02,
        "control_symmetry_drop_at_most_0_02": symmetry_drops["control"] <= 0.02,
        "aligned_error_over_shuffled_ci95_lower_gt_0cp": versus_shuffled["error"]["ci95"][0] > 0.0,
        "aligned_paired_over_shuffled_ci95_lower_gt_0cp": versus_shuffled["paired_error_minus_control"]["ci95"][0] > 0.0,
        "abstentions_bit_identical": aligned["abstentions_bit_identical"],
        "outside_gate_bit_identical": aligned["outside_gate_bit_identical"],
    }
    passed = all(gates.values())
    return {
        "schema": SCHEMA,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        **identities,
        "fixed_threshold_cp": threshold,
        "feature_audit_pairs": len(rows),
        "aligned": aligned,
        "shuffled": shuffled,
        "zero_residual_control": {
            "operation": "unaltered_CURRICULUM_action",
            "same_decision_cost": True,
            "interventions": 0,
            "mean_gain_cp": 0.0,
            "bit_identical": True,
        },
        "aligned_minus_shuffled": versus_shuffled,
        "symmetry_drops": symmetry_drops,
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "feature_audit_action_value_reads": len(rows) * 2,
        "outer_confirm_profile_rows_examined": 0,
        "outer_confirm_action_value_reads": 0,
        "residual_fits": 0,
        "pattern_eval_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "outer_confirm_authorized": passed,
        "production_rule_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "one_shot_outer_confirm_without_refit" if passed else None,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    material = sub.add_parser("materialize")
    material.add_argument("--pairs", type=Path, required=True)
    material.add_argument("--preregistration", type=Path, required=True)
    material.add_argument("--split-manifest", type=Path, required=True)
    material.add_argument("--gate-fit-pairs", type=Path, required=True)
    material.add_argument("--training-report", type=Path, required=True)
    material.add_argument("--model", type=Path, required=True)
    material.add_argument("--feature-audit-pairs", type=Path, required=True)
    material.add_argument("--certificate", type=Path, required=True)
    evaluate = sub.add_parser("audit")
    evaluate.add_argument("--preregistration", type=Path, required=True)
    evaluate.add_argument("--training-report", type=Path, required=True)
    evaluate.add_argument("--model", type=Path, required=True)
    evaluate.add_argument("--pairs", type=Path, required=True)
    evaluate.add_argument("--atlas-shard", action="append", type=Path, required=True)
    evaluate.add_argument("--report", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    registration = json.loads(args.preregistration.read_text())
    training_report = json.loads(args.training_report.read_text())
    model = json.loads(args.model.read_text())
    if args.command == "materialize":
        pairs, certificate = materialize(
            json.loads(args.pairs.read_text()),
            registration,
            json.loads(args.split_manifest.read_text()),
            json.loads(args.gate_fit_pairs.read_text()),
            training_report,
            model,
        )
        _publish(args.feature_audit_pairs, pairs)
        _publish(args.certificate, certificate)
        print(json.dumps({"feature_audit_pairs": pairs["matched_pairs"]}, sort_keys=True))
    else:
        report = audit(
            registration,
            training_report,
            model,
            json.loads(args.pairs.read_text()),
            [json.loads(path.read_text()) for path in args.atlas_shard],
        )
        report["preregistration_sha256"] = _sha256(args.preregistration)
        report["training_report_sha256"] = _sha256(args.training_report)
        report["model_sha256"] = _sha256(args.model)
        report["feature_audit_pairs_sha256"] = _sha256(args.pairs)
        _publish(args.report, report)
        print(json.dumps({"verdict": report["verdict"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
