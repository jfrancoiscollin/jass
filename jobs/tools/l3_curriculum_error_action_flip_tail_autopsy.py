#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only loss autopsy of the selected 1536 action-margin candidate.

1536 found one reproducibly positive cross-pool point estimate, but no eligible
rule: its positive mean was tail-dominated and the paired interval spanned
zero.  This diagnostic reproduces that candidate exactly and attributes every
decision flip to target-free state/action descriptors and to the candidate's
20 signed feature contributions.  Post-hoc abstention counterfactuals are
descriptive only; they cannot authorize a refit or reuse 1524 for confirmation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from jobs.tools import l3_curriculum_error_action_margin_contrastive_screen as action
from jobs.tools import l3_curriculum_error_fresh_tail_autopsy as tail
from jobs.tools import l3_curriculum_error_target_specificity_autopsy as target


SCHEMA = "jass.l3_curriculum_error_action_flip_tail_autopsy.v1"
READY = "JASS_CURRICULUM_ERROR_ACTION_FLIP_TAIL_AUTOPSY_READY"
SOURCE_SCHEMA = "jass.curriculum_error_action_margin_contrastive_terminal.v1"
EXPECTED_BEST = "full20__alpha_30__control_10__threshold_5"
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


def _same(left: object, right: object) -> bool:
    return _canonical(left) == _canonical(right)


def _require_source(report: dict[str, Any], bucket_report: dict[str, Any]) -> dict[str, Any]:
    screen = report.get("action_margin_screen", {})
    best = screen.get("best_candidate", {})
    if (
        report.get("schema") != SOURCE_SCHEMA
        or report.get("verdict") != action.READY
        or report.get("passed") is not True
        or screen.get("passed") is not False
        or screen.get("status") != "action_margin_correction_not_established"
        or best.get("config", {}).get("name") != EXPECTED_BEST
        or report.get("new_fresh_pool_preregistration_recommended") is not False
    ):
        raise ValueError("tail autopsy requires certified negative 1536 source")
    if report.get("scientific_sources", {}).get("bucket_report_sha256") != _digest(bucket_report):
        raise ValueError("1536/1535 report identity drift")
    for key in (
        "anchored_local_refit_authorized", "production_model_authorized",
        "strength_gate_authorized", "promotion_authorized", "automatic_continuation",
    ):
        if report.get(key) is not False:
            raise ValueError(f"1536 forbidden authorization drift: {key}")
    return dict(best["config"])


def _top_margin(scores: dict[str, float]) -> float:
    ordered = sorted(scores.values(), reverse=True)
    return float(ordered[0] - ordered[1]) if len(ordered) > 1 else 0.0


def _feature_family(name: str) -> str:
    return tail._feature_family(name)


def _detail(
    state: dict[str, Any], model: dict[str, Any], config: dict[str, Any],
    decision: dict[str, Any], *, pair_id: int, source_pool: str, role: str,
) -> dict[str, Any]:
    indices = list(config["indices"])
    names = list(config["feature_names"])
    original_anchor = action._best(state["original_scores"])
    image_anchor = action._best(state["image_scores"])
    raw = {}
    clipped = {}
    for candidate, vector in state["features"].items():
        selected = np.asarray(vector, dtype=float)[indices]
        value = float(((selected - model["mean"]) / model["rms"]) @ model["coefficient"])
        raw[candidate] = value
        clipped[candidate] = max(-action.CAP_CP, min(action.CAP_CP, value))
    original_corrected = {
        candidate: state["original_scores"][candidate] + clipped[candidate]
        for candidate in clipped
    }
    image_corrected = {
        candidate: state["image_scores"][candidate] + clipped[candidate]
        for candidate in clipped
    }
    original_proposed = action._best(original_corrected)
    image_proposed = action._best(image_corrected)
    proposed = original_proposed if original_proposed == image_proposed else None
    if bool(decision["intervention"]) and proposed != decision.get("action"):
        raise ValueError("action-flip decision reproduction drift")
    original_advantage = original_corrected[original_proposed] - original_corrected[original_anchor]
    image_advantage = image_corrected[image_proposed] - image_corrected[image_anchor]
    metadata = tail._piece_metadata(state["profile"])
    values = state["values"]
    exact_teacher = max(values, key=lambda candidate: (values[candidate], candidate))
    anchor_value = (values[original_anchor] + values[image_anchor]) / 2.0
    output: dict[str, Any] = {
        "pair_id": pair_id,
        "source_pool": source_pool,
        "role": role,
        "intervention": bool(decision["intervention"]),
        "improvement_cp": float(decision["improvement_cp"]),
        "predicted_advantage_cp": decision.get("predicted_advantage_cp"),
        "guard_margin_cp": (
            float(min(original_advantage, image_advantage) - float(config["threshold_cp"]))
            if decision["intervention"] else None
        ),
        "anchor_disagreement": original_anchor != image_anchor,
        "original_anchor": original_anchor,
        "image_anchor": image_anchor,
        "proposed_action": proposed,
        "proposed_capture": bool(proposed and "x" in proposed),
        "original_anchor_margin_cp": _top_margin(state["original_scores"]),
        "image_anchor_margin_cp": _top_margin(state["image_scores"]),
        "correction_clipped": any(abs(value) >= action.CAP_CP - EPS for value in raw.values()),
        "exact_teacher_action": exact_teacher,
        "exact_teacher_hit": bool(decision["intervention"] and proposed == exact_teacher),
        "exact_anchor_regret_cp": float(values[exact_teacher] - anchor_value),
        **metadata,
    }
    if not decision["intervention"] or proposed is None:
        output.update({
            "feature_contributions_cp": {}, "feature_family_contributions_cp": {},
            "dominant_feature": None, "dominant_feature_family": None,
            "raw_correction_delta_cp": None, "clipped_correction_delta_cp": None,
        })
        return output
    anchor_vectors = (
        np.asarray(state["features"][original_anchor], dtype=float)[indices],
        np.asarray(state["features"][image_anchor], dtype=float)[indices],
    )
    proposed_vector = np.asarray(state["features"][proposed], dtype=float)[indices]
    delta = sum((proposed_vector - vector) / model["rms"] for vector in anchor_vectors) / 2.0
    contributions = delta * model["coefficient"]
    by_feature = {
        name: float(value) for name, value in zip(names, contributions, strict=True)
    }
    by_family: dict[str, float] = defaultdict(float)
    for name, value in by_feature.items():
        by_family[_feature_family(name)] += value
    raw_delta = ((raw[proposed] - raw[original_anchor]) + (raw[proposed] - raw[image_anchor])) / 2.0
    clipped_delta = (
        (clipped[proposed] - clipped[original_anchor])
        + (clipped[proposed] - clipped[image_anchor])
    ) / 2.0
    if abs(sum(by_feature.values()) - raw_delta) > 1e-6:
        raise ValueError("feature contributions do not recompose action correction")
    output.update({
        "feature_contributions_cp": by_feature,
        "feature_family_contributions_cp": dict(sorted(by_family.items())),
        "dominant_feature": max(by_feature, key=lambda name: (abs(by_feature[name]), name)),
        "dominant_feature_family": max(by_family, key=lambda name: (abs(by_family[name]), name)),
        "raw_correction_delta_cp": float(raw_delta),
        "clipped_correction_delta_cp": float(clipped_delta),
    })
    return output


def _risk_flags(row: dict[str, Any]) -> dict[str, bool]:
    if not row["intervention"]:
        return {}
    predicted = float(row["predicted_advantage_cp"])
    guard = float(row["guard_margin_cp"])
    anchor_margin = min(float(row["original_anchor_margin_cp"]), float(row["image_anchor_margin_cp"]))
    return {
        "predicted_advantage_lt_10cp": predicted < 10.0,
        "predicted_advantage_lt_15cp": predicted < 15.0,
        "predicted_advantage_lt_20cp": predicted < 20.0,
        "guard_margin_lt_2cp": guard < 2.0,
        "guard_margin_lt_5cp": guard < 5.0,
        "guard_margin_lt_10cp": guard < 10.0,
        "correction_clipped": bool(row["correction_clipped"]),
        "anchor_disagreement": bool(row["anchor_disagreement"]),
        "proposed_capture": bool(row["proposed_capture"]),
        "anchor_margin_gt_25cp": anchor_margin > 25.0,
        "anchor_margin_gt_50cp": anchor_margin > 50.0,
        "piece_count_le_8": int(row["piece_count"]) <= 8,
        "piece_count_le_12": int(row["piece_count"]) <= 12,
        "phase_early": row["phase"] == "early",
        "phase_middle": row["phase"] == "middle",
        "phase_endgame": row["phase"] == "endgame",
    }


def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def _counterfactual(details: list[dict[str, Any]], flag: str) -> dict[str, Any]:
    pairs: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in details:
        pairs[int(row["pair_id"])][str(row["role"])] = row
    values = {"error": [], "control": [], "paired": []}
    by_pool: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"error": [], "control": [], "paired": []}
    )
    removed = {"error": 0, "control": 0}
    retained_error = []
    retained_error_by_pool: dict[str, int] = defaultdict(int)
    for pair_id in sorted(pairs):
        roles = pairs[pair_id]
        if set(roles) != {"error", "control"}:
            raise ValueError("action-flip counterfactual pair coverage drift")
        adjusted = {}
        pool = str(roles["error"]["source_pool"])
        if pool != str(roles["control"]["source_pool"]):
            raise ValueError("action-flip pair pool drift")
        for role in ("error", "control"):
            row = roles[role]
            abstain = bool(_risk_flags(row).get(flag, False))
            adjusted[role] = 0.0 if abstain else float(row["improvement_cp"])
            if abstain:
                removed[role] += 1
            elif role == "error" and row["intervention"]:
                retained_error.append(float(row["improvement_cp"]) > 0.0)
                retained_error_by_pool[pool] += 1
        paired = adjusted["error"] - adjusted["control"]
        for key, value in (("error", adjusted["error"]), ("control", adjusted["control"]), ("paired", paired)):
            values[key].append(value)
            by_pool[pool][key].append(value)
    metrics = {key: _mean(series) for key, series in values.items()}
    pool_metrics = {
        pool: {key: _mean(series) for key, series in series_by_role.items()}
        for pool, series_by_role in sorted(by_pool.items())
    }
    stable = (
        sum(retained_error_by_pool.values()) >= 16
        and all(retained_error_by_pool.get(pool, 0) >= 5 for pool in ("pool1", "pool2"))
        and retained_error and float(np.mean(retained_error)) >= 0.60
        and all(pool_metrics[pool]["error"] > 0.0 for pool in ("pool1", "pool2"))
        and all(pool_metrics[pool]["paired"] > 0.0 for pool in ("pool1", "pool2"))
        and all(pool_metrics[pool]["control"] >= -2.0 for pool in ("pool1", "pool2"))
    )
    return {
        "rule": f"abstain_when_{flag}",
        "flag": flag,
        "removed_interventions": removed,
        "retained_error_interventions": sum(retained_error_by_pool.values()),
        "retained_error_interventions_by_pool": dict(sorted(retained_error_by_pool.items())),
        "retained_error_positive_realization_rate": (
            float(np.mean(retained_error)) if retained_error else None
        ),
        "mean_gain_cp": metrics,
        "mean_gain_cp_by_pool": pool_metrics,
        "minimum_pool_paired_mean_cp": min(
            pool_metrics[pool]["paired"] for pool in ("pool1", "pool2")
        ),
        "descriptive_stability_gates_pass": bool(stable),
        "posthoc_discovery_only": True,
    }


def _group(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return tail._group(records, key)


def autopsy(
    training_report: dict[str, Any], failed_model: dict[str, Any],
    training_pairs: dict[str, Any], training_shards: list[dict[str, Any]],
    fresh_summary: dict[str, Any], fresh_report: dict[str, Any],
    fresh_pairs: dict[str, Any], fresh_shards: list[dict[str, Any]],
    target_cache: dict[str, Any], subspace_report: dict[str, Any],
    target_report: dict[str, Any], bucket_report: dict[str, Any],
    action_report: dict[str, Any],
) -> dict[str, Any]:
    config = _require_source(action_report, bucket_report)
    rows, stable_indices, split, reproduction = action._reconstruct(
        training_report, failed_model, training_pairs, training_shards,
        fresh_summary, fresh_report, fresh_pairs, fresh_shards,
        target_cache, subspace_report, target_report, bucket_report,
    )
    evaluation = action._evaluate(rows, config)
    if not _same(action._compact(evaluation), action_report["action_margin_screen"]["best_candidate"]):
        raise ValueError("1536 best candidate reproduction drift")
    source_by_pair = {int(row["pair_id"]): row for row in rows}
    details = []
    for decision in evaluation["decisions"]:
        pair_id = int(decision["pair_id"])
        pool = str(decision["source_pool"])
        training_pool = "pool2" if pool == "pool1" else "pool1"
        model = evaluation["fits_internal"][training_pool]
        for role in ("error", "control"):
            details.append(_detail(
                source_by_pair[pair_id][role], model, config, decision[role],
                pair_id=pair_id, source_pool=pool, role=role,
            ))
    interventions = [row for row in details if row["intervention"]]
    error_interventions = [row for row in interventions if row["role"] == "error"]
    control_interventions = [row for row in interventions if row["role"] == "control"]
    error_losses = [row for row in error_interventions if row["improvement_cp"] < 0.0]
    error_wins = [row for row in error_interventions if row["improvement_cp"] > 0.0]
    flags = sorted({flag for row in interventions for flag in _risk_flags(row)})
    counterfactuals = [_counterfactual(details, flag) for flag in flags]
    counterfactuals.sort(
        key=lambda row: (
            row["descriptive_stability_gates_pass"],
            row["minimum_pool_paired_mean_cp"],
            row["retained_error_positive_realization_rate"] or -1.0,
        ),
        reverse=True,
    )
    descriptive = [row for row in counterfactuals if row["descriptive_stability_gates_pass"]]
    group_keys = (
        "phase", "piece_count", "king_count", "stm_material_balance", "outcome",
        "anchor_disagreement", "proposed_capture", "correction_clipped",
        "dominant_feature", "dominant_feature_family", "exact_teacher_hit",
    )
    return {
        "schema": SCHEMA,
        "verdict": READY,
        "passed": True,
        "scientific_status": "action_margin_tail_mechanism_audited",
        "source": {
            "action_margin_report_sha256": _digest(action_report),
            "bucket_report_sha256": _digest(bucket_report),
            "best_candidate": config,
        },
        "stable_support_indices": stable_indices,
        "split_integrity": split,
        "reproduction": reproduction,
        "candidate_reproduction": action._compact(evaluation),
        "counts": {
            "pairs": len(rows), "states": len(details),
            "error_interventions": len(error_interventions),
            "control_interventions": len(control_interventions),
            "error_positive_interventions": len(error_wins),
            "error_negative_interventions": len(error_losses),
            "error_zero_interventions": len(error_interventions) - len(error_wins) - len(error_losses),
        },
        "distributions": {
            "error_interventions": tail._distribution(row["improvement_cp"] for row in error_interventions),
            "control_interventions": tail._distribution(row["improvement_cp"] for row in control_interventions),
            "error_losses": tail._distribution(row["improvement_cp"] for row in error_losses),
            "error_wins": tail._distribution(row["improvement_cp"] for row in error_wins),
        },
        "loss_concentration": tail._loss_concentration(error_interventions),
        "groups": {
            "error_interventions": {key: _group(error_interventions, key) for key in group_keys},
            "error_losses": {key: _group(error_losses, key) for key in group_keys},
            "error_wins": {key: _group(error_wins, key) for key in group_keys},
        },
        "continuous_correlations_with_error_gain": {
            key: tail._correlation(error_interventions, key)
            for key in (
                "predicted_advantage_cp", "guard_margin_cp", "original_anchor_margin_cp",
                "image_anchor_margin_cp", "raw_correction_delta_cp",
                "clipped_correction_delta_cp", "piece_count", "legal_moves",
                "exact_anchor_regret_cp",
            )
        },
        "feature_attribution": {
            "all_error_interventions": tail._feature_attribution(error_interventions, "feature_contributions_cp"),
            "negative_error_interventions": tail._feature_attribution(error_losses, "feature_contributions_cp"),
            "positive_error_interventions": tail._feature_attribution(error_wins, "feature_contributions_cp"),
            "feature_families_all_errors": tail._feature_attribution(error_interventions, "feature_family_contributions_cp"),
        },
        "posthoc_abstention_counterfactuals": counterfactuals,
        "descriptively_stable_counterfactuals": descriptive,
        "detailed_interventions": interventions,
        "fresh_1524_reuse_for_confirmation_forbidden": True,
        "new_exact_target_computations": 0,
        "diagnostic_base_residual_fits_on_immutable_1508": 1,
        "diagnostic_action_margin_reproduction_fits": 2,
        "pattern_eval_fits": 0,
        "production_model_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "new_fresh_pool_preregistration_recommended": False,
        "anchored_local_refit_authorized": False,
        "production_model_authorized": False,
        "strength_gate_authorized": False,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "preregister_tail_safe_subgroup_screen" if descriptive else "design_loss_first_corpus",
    }


def parser() -> argparse.ArgumentParser:
    out = argparse.ArgumentParser(description=__doc__)
    out.add_argument("--training-report", type=Path, required=True)
    out.add_argument("--failed-model", type=Path, required=True)
    out.add_argument("--training-pairs", type=Path, required=True)
    out.add_argument("--training-shard", type=Path, action="append", required=True)
    out.add_argument("--fresh-summary", type=Path, required=True)
    out.add_argument("--fresh-report", type=Path, required=True)
    out.add_argument("--fresh-pairs", type=Path, required=True)
    out.add_argument("--fresh-shard", type=Path, action="append", required=True)
    out.add_argument("--target-cache", type=Path, required=True)
    out.add_argument("--subspace-report", type=Path, required=True)
    out.add_argument("--target-report", type=Path, required=True)
    out.add_argument("--bucket-report", type=Path, required=True)
    out.add_argument("--action-report", type=Path, required=True)
    out.add_argument("--report", type=Path, required=True)
    return out


def main() -> int:
    args = parser().parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    report = autopsy(
        load(args.training_report), load(args.failed_model), load(args.training_pairs),
        [load(path) for path in args.training_shard],
        load(args.fresh_summary), load(args.fresh_report), load(args.fresh_pairs),
        [load(path) for path in args.fresh_shard], load(args.target_cache),
        load(args.subspace_report), load(args.target_report), load(args.bucket_report),
        load(args.action_report),
    )
    _publish(args.report, report)
    print(json.dumps({
        "verdict": report["verdict"], "counts": report["counts"],
        "descriptive_rules": len(report["descriptively_stable_counterfactuals"]),
        "next_stage": report["next_stage"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
