#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read-only autopsy of the catastrophic fresh tail from experiment 1517.

The fresh labels are outcomes only.  The residual is re-fitted exclusively on
the immutable 1508 gate-fit population, then the frozen 1517 rule is replayed
bit-for-bit.  This module may describe a future risk hypothesis, but it cannot
fit fresh labels, publish production weights, play games, or authorize a
continuation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from jobs.tools import l3_curriculum_error_action_ranker as ranker
from jobs.tools import l3_curriculum_error_fresh_pair_availability_preflight as availability
from jobs.tools import l3_curriculum_error_fresh_powered_confirmation as fresh
from jobs.tools import l3_curriculum_error_residual_ridge_path_screen as ridge
from jobs.tools import l3_curriculum_error_trace_proxy_preregistration as prereg
from jobs.tools import l3_curriculum_error_trace_residual_training as training
from jobs.tools import l3_curriculum_error_trace_variability_screen as variability


SCHEMA = "jass.l3_curriculum_error_fresh_tail_autopsy.v1"
READY = "JASS_CURRICULUM_ERROR_FRESH_TAIL_AUTOPSY_READY"
SOURCE_TERMINAL_SCHEMA = "jass.curriculum_error_fresh_powered_confirmation_terminal.v1"
AUDIT_SCHEMA = "jass.curriculum_error_fresh_powered_confirmation_final_audit.v1"
AUDIT_READY = "JASS_CURRICULUM_ERROR_FRESH_POWERED_CONFIRMATION_FINAL_AUDIT_READY"

EXPECTED_HYPOTHESIS = {
    "alpha": 300.0,
    "cap_cp": 100.0,
    "mode": "strict_both_change",
    "threshold_cp": 10.0,
}
TAIL_THRESHOLDS_CP = (-1000.0, -500.0, -200.0, -100.0, 0.0, 200.0, 500.0, 1000.0)
WORST_ROWS = 20
EPS = 1e-8


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


def _same(left: Any, right: Any, *, tolerance: float = EPS) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _same(left[key], right[key], tolerance=tolerance) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _same(a, b, tolerance=tolerance) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _require_source(
    summary: dict[str, Any], report: dict[str, Any], audit: dict[str, Any]
) -> None:
    if (
        summary.get("schema") != SOURCE_TERMINAL_SCHEMA
        or summary.get("verdict") != fresh.NOT_ESTABLISHED
        or summary.get("passed") is not False
    ):
        raise ValueError("tail autopsy requires the certified negative 1517 terminal")
    for key in (
        "verdict", "passed", "selected_hypothesis", "fresh_pairs",
        "fresh_pairs_by_pool", "metrics", "symmetry_drop", "sham", "gates",
        "failed_gates", "identities", "new_target_states",
        "fresh_confirmation_target_states", "discarded_labelled_states",
        "exact_target_batches", "exact_action_value_reads", "residual_fits",
        "diagnostic_fits",
    ):
        if not _same(summary.get(key), report.get(key)):
            raise ValueError(f"1517 terminal/report drift: {key}")
    if (
        audit.get("schema") != AUDIT_SCHEMA
        or audit.get("verdict") != AUDIT_READY
        or audit.get("scientific_verdict") != fresh.NOT_ESTABLISHED
        or not _same(audit.get("metrics"), report.get("metrics"))
        or audit.get("failed_gates") != report.get("failed_gates")
    ):
        raise ValueError("1517a final audit identity/metrics drift")
    selected = report.get("selected_hypothesis", {})
    if any(not _same(selected.get(key), value) for key, value in EXPECTED_HYPOTHESIS.items()):
        raise ValueError(f"1517 frozen hypothesis drift: {selected}")
    if int(report.get("fresh_pairs", -1)) != fresh.FRESH_PAIRS:
        raise ValueError("1517 fresh pair cardinality drift")
    if report.get("fresh_extension_labels_used_for_fit") is not False:
        raise ValueError("1517 reports fresh-label fitting")
    for key in (
        "pattern_eval_fits", "production_model_fits", "strength_games",
        "new_selfplay_games", "frozen_reads",
    ):
        if int(report.get(key, -1)) != 0:
            raise ValueError(f"1517 forbidden counter drift: {key}")


def _piece_metadata(profile: dict[str, Any]) -> dict[str, Any]:
    source = profile["source"]
    pieces = availability._piece(source)
    return {
        "phase": str(pieces["phase"]),
        "piece_count": int(pieces["piece_count"]),
        "king_count": int(pieces["king_count"]),
        "stm_material_balance": int(pieces["stm_material_balance"]),
        "ply": int(source["ply"]),
        "legal_moves": int(profile["legal_moves"]),
        "capture_historical": "x" in str(source.get("actual_move", source.get("actual_apply", ""))),
        "outcome": str(source.get("outcome", "unknown")),
        "opening_id": str(source["opening_id"]),
        "game_uid": str(source["game_uid"]),
        "exact_state_key": str(source["exact_state_key"]),
    }


def _raw_correction(model: dict[str, Any], vector: np.ndarray) -> float:
    return float(((vector - model["mean"]) / model["rms"]) @ model["coef"])


def _top_margin(scores: dict[str, float]) -> float:
    ordered = sorted(scores.values(), reverse=True)
    return float(ordered[0] - ordered[1]) if len(ordered) > 1 else 0.0


def _feature_family(name: str) -> str:
    if name.startswith("centered_score"):
        return "depth_scores"
    if name.startswith("present"):
        return "depth_presence"
    if name.startswith("rank_fraction"):
        return "depth_rank"
    if name.startswith("slope") or name in {"curvature_d7_d9", "trajectory_volatility"}:
        return "trajectory_shape"
    if name in {"top_frequency", "baseline_d9"}:
        return "trajectory_stability"
    if name == "capture":
        return "capture"
    raise ValueError(f"unclassified feature: {name}")


def _detail(
    state: dict[str, Any], model: dict[str, Any], decision: dict[str, Any],
    *, role: str, pair_id: int, source_pool: str,
) -> dict[str, Any]:
    original_anchor = ridge._best(state["original_scores"])
    image_anchor = ridge._best(state["image_scores"])
    raw = {action: _raw_correction(model, vector) for action, vector in state["features"].items()}
    clipped = {
        action: max(-EXPECTED_HYPOTHESIS["cap_cp"], min(EXPECTED_HYPOTHESIS["cap_cp"], value))
        for action, value in raw.items()
    }
    original_corrected = {
        action: state["original_scores"][action] + clipped[action] for action in clipped
    }
    image_corrected = {
        action: state["image_scores"][action] + clipped[action] for action in clipped
    }
    original_proposed = ridge._best(original_corrected)
    image_proposed = ridge._best(image_corrected)
    proposed = original_proposed if original_proposed == image_proposed else None
    intervention = bool(decision["intervention"])
    if intervention and (proposed is None or proposed != decision.get("action")):
        raise ValueError("tail autopsy decision/action reproduction drift")

    original_advantage = (
        original_corrected[original_proposed] - original_corrected[original_anchor]
    )
    image_advantage = image_corrected[image_proposed] - image_corrected[image_anchor]
    proxy = float(variability._profile_values(state["profile"])[prereg.SELECTED_PROXY])
    output: dict[str, Any] = {
        "pair_id": pair_id,
        "role": role,
        "source_pool": source_pool,
        "eligible": bool(decision["eligible"]),
        "intervention": intervention,
        "improvement_cp": float(decision["improvement_cp"]),
        "predicted_advantage_cp": decision["predicted_advantage_cp"],
        "guard_margin_cp": (
            float(min(original_advantage, image_advantage) - EXPECTED_HYPOTHESIS["threshold_cp"])
            if intervention else None
        ),
        "proxy_cp": proxy,
        "anchor_disagreement": original_anchor != image_anchor,
        "original_anchor": original_anchor,
        "image_anchor": image_anchor,
        "proposed_action": proposed,
        "proposed_capture": bool(proposed and "x" in proposed),
        "original_anchor_margin_cp": _top_margin(state["original_scores"]),
        "image_anchor_margin_cp": _top_margin(state["image_scores"]),
        "correction_clipped": any(abs(value) >= EXPECTED_HYPOTHESIS["cap_cp"] - EPS for value in raw.values()),
        **_piece_metadata(state["profile"]),
    }
    if not intervention:
        output.update({
            "feature_contributions_cp": {}, "feature_family_contributions_cp": {},
            "dominant_feature": None, "dominant_feature_family": None,
            "raw_correction_delta_cp": None, "clipped_correction_delta_cp": None,
        })
        return output

    assert proposed is not None
    coefficient = np.asarray(model["coef"], dtype=float)
    rms = np.asarray(model["rms"], dtype=float)
    anchor_vectors = (state["features"][original_anchor], state["features"][image_anchor])
    delta = sum((state["features"][proposed] - vector) / rms for vector in anchor_vectors) / 2.0
    contributions = delta * coefficient
    by_feature = {
        name: float(value) for name, value in zip(ranker.FEATURE_NAMES, contributions, strict=True)
    }
    by_family: dict[str, float] = defaultdict(float)
    for name, value in by_feature.items():
        by_family[_feature_family(name)] += value
    dominant_feature = max(by_feature, key=lambda name: (abs(by_feature[name]), name))
    dominant_family = max(by_family, key=lambda name: (abs(by_family[name]), name))
    raw_delta = ((raw[proposed] - raw[original_anchor]) + (raw[proposed] - raw[image_anchor])) / 2.0
    clipped_delta = ((clipped[proposed] - clipped[original_anchor]) + (clipped[proposed] - clipped[image_anchor])) / 2.0
    if abs(sum(by_feature.values()) - raw_delta) > 1e-6:
        raise ValueError("feature contributions do not recompose raw correction delta")
    output.update({
        "feature_contributions_cp": by_feature,
        "feature_family_contributions_cp": dict(sorted(by_family.items())),
        "dominant_feature": dominant_feature,
        "dominant_feature_family": dominant_family,
        "raw_correction_delta_cp": float(raw_delta),
        "clipped_correction_delta_cp": float(clipped_delta),
    })
    return output


def _quantile(values: np.ndarray, q: float) -> float | None:
    return float(np.quantile(values, q)) if values.size else None


def _distribution(values: Iterable[float]) -> dict[str, Any]:
    data = np.asarray(list(values), dtype=float)
    if not data.size:
        return {"n": 0}
    result: dict[str, Any] = {
        "n": int(data.size), "mean": float(data.mean()), "minimum": float(data.min()),
        "maximum": float(data.max()), "negative_rate": float(np.mean(data < 0.0)),
        "zero_rate": float(np.mean(data == 0.0)), "positive_rate": float(np.mean(data > 0.0)),
        "quantiles_cp": {
            key: _quantile(data, q) for key, q in (
                ("p01", .01), ("p05", .05), ("p10", .10), ("p25", .25),
                ("p50", .50), ("p75", .75), ("p90", .90), ("p95", .95), ("p99", .99),
            )
        },
        "lower_tail_cvar_cp": {},
        "threshold_counts": {str(int(t)): int(np.sum(data <= t)) for t in TAIL_THRESHOLDS_CP},
    }
    for label, q in (("q05", .05), ("q10", .10), ("q20", .20)):
        boundary = float(np.quantile(data, q))
        result["lower_tail_cvar_cp"][label] = float(data[data <= boundary].mean())
    return result


def _loss_concentration(records: list[dict[str, Any]]) -> dict[str, Any]:
    losses = sorted(
        ((-float(row["improvement_cp"]), row) for row in records if float(row["improvement_cp"]) < 0.0),
        key=lambda item: item[0], reverse=True,
    )
    total = sum(value for value, _row in losses)
    if not losses:
        return {"negative_interventions": 0, "total_loss_cp": 0.0}
    shares = {
        f"top_{count}_share": float(sum(value for value, _row in losses[:count]) / total)
        for count in (1, 3, 5, 10) if count <= len(losses)
    }
    counts = {}
    for threshold in (.50, .80, .90):
        cumulative = 0.0
        for index, (value, _row) in enumerate(losses, start=1):
            cumulative += value
            if cumulative / total >= threshold:
                counts[f"events_for_{int(threshold * 100)}pct_loss"] = index
                break
    return {
        "negative_interventions": len(losses), "total_loss_cp": float(total),
        **shares, **counts,
    }


def _group(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in records:
        grouped[str(row[key])].append(float(row["improvement_cp"]))
    return {name: _distribution(values) for name, values in sorted(grouped.items())}


def _correlation(records: list[dict[str, Any]], key: str) -> float | None:
    rows = [row for row in records if row.get(key) is not None]
    if len(rows) < 3:
        return None
    x = np.asarray([float(row[key]) for row in rows]); y = np.asarray([float(row["improvement_cp"]) for row in rows])
    if float(np.std(x)) <= EPS or float(np.std(y)) <= EPS:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _feature_attribution(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    names = sorted({name for row in records for name in row[field]})
    catastrophic = [row for row in records if float(row["improvement_cp"]) <= -500.0]
    return [
        {
            "name": name,
            "mean_signed_cp": float(np.mean([row[field].get(name, 0.0) for row in records])),
            "mean_absolute_cp": float(np.mean([abs(row[field].get(name, 0.0)) for row in records])),
            "catastrophic_mean_signed_cp": (
                float(np.mean([row[field].get(name, 0.0) for row in catastrophic]))
                if catastrophic else None
            ),
            "dominant_count": sum(
                row["dominant_feature" if field == "feature_contributions_cp" else "dominant_feature_family"] == name
                for row in records
            ),
            "pool_means_cp": {
                pool: float(np.mean([row[field].get(name, 0.0) for row in records if row["source_pool"] == pool]))
                for pool in sorted({row["source_pool"] for row in records})
                if any(row["source_pool"] == pool for row in records)
            },
        }
        for name in names
    ]


def _risk_flags(row: dict[str, Any]) -> dict[str, bool]:
    return {
        "predicted_advantage_lt_20cp": float(row["predicted_advantage_cp"]) < 20.0,
        "guard_margin_lt_5cp": float(row["guard_margin_cp"]) < 5.0,
        "correction_clipped": bool(row["correction_clipped"]),
        "anchor_disagreement": bool(row["anchor_disagreement"]),
        "proposed_capture": bool(row["proposed_capture"]),
        "proxy_gt_110cp": float(row["proxy_cp"]) > 110.0,
    }


def _risk_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pools = sorted({row["source_pool"] for row in records})
    total_loss = sum(-min(float(row["improvement_cp"]), 0.0) for row in records)
    candidates = []
    for name in _risk_flags(records[0]) if records else ():
        inside = [row for row in records if _risk_flags(row)[name]]
        outside = [row for row in records if not _risk_flags(row)[name]]
        pool_effects = {}
        for pool in pools:
            left = [float(row["improvement_cp"]) for row in inside if row["source_pool"] == pool]
            right = [float(row["improvement_cp"]) for row in outside if row["source_pool"] == pool]
            pool_effects[pool] = {
                "inside_n": len(left), "outside_n": len(right),
                "inside_mean_cp": float(np.mean(left)) if left else None,
                "outside_mean_cp": float(np.mean(right)) if right else None,
                "inside_minus_outside_cp": float(np.mean(left) - np.mean(right)) if left and right else None,
            }
        loss_mass = sum(-min(float(row["improvement_cp"]), 0.0) for row in inside)
        stable = (
            len(inside) >= 12
            and all(pool_effects[pool]["inside_n"] >= 4 and pool_effects[pool]["outside_n"] >= 4 for pool in pools)
            and all(float(pool_effects[pool]["inside_minus_outside_cp"]) <= -200.0 for pool in pools)
            and total_loss > 0.0 and loss_mass / total_loss >= .50
        )
        candidates.append({
            "name": name, "inside": _distribution(row["improvement_cp"] for row in inside),
            "outside": _distribution(row["improvement_cp"] for row in outside),
            "negative_loss_mass_share": float(loss_mass / total_loss) if total_loss else 0.0,
            "pool_effects": pool_effects, "descriptively_pool_stable": stable,
            "fresh_1517_reuse_for_validation_forbidden": True,
        })
    return sorted(candidates, key=lambda row: (not row["descriptively_pool_stable"], -row["negative_loss_mass_share"], row["name"]))


def autopsy(
    training_report: dict[str, Any], failed_model: dict[str, Any],
    training_pairs: dict[str, Any], training_shards: list[dict[str, Any]],
    fresh_summary: dict[str, Any], fresh_report: dict[str, Any],
    fresh_pairs: dict[str, Any], fresh_shards: list[dict[str, Any]],
    target_cache: dict[str, Any], final_audit: dict[str, Any],
) -> dict[str, Any]:
    _require_source(fresh_summary, fresh_report, final_audit)
    ridge._check_source(training_report, failed_model)
    training_rows, training_identities = training._load_rows(training_pairs, training_shards)
    fresh_rows, fresh_identities = fresh._load_fresh_rows(fresh_pairs, fresh_shards)
    if training_identities != fresh_identities or fresh_report.get("identities") != fresh_identities:
        raise ValueError("1508/1517 engine, champion or search identity drift")
    if target_cache.get("schema") != fresh.SCHEMA_CACHE:
        raise ValueError("1517 target-cache schema drift")

    model = ridge._fit(training_rows, alpha=EXPECTED_HYPOTHESIS["alpha"])
    models = {row["pair_id"]: model for row in fresh_rows}
    decisions = ridge._decisions(
        fresh_rows, models, cap_cp=EXPECTED_HYPOTHESIS["cap_cp"],
        threshold_cp=EXPECTED_HYPOTHESIS["threshold_cp"], mode=EXPECTED_HYPOTHESIS["mode"],
    )
    errors = [float(row["error"]["improvement_cp"]) for row in decisions]
    controls = [float(row["control"]["improvement_cp"]) for row in decisions]
    paired = [left - right for left, right in zip(errors, controls, strict=True)]
    error_changed = [row["error"] for row in decisions if row["error"]["intervention"]]
    reproduced = {
        "pairs": len(decisions),
        "error_interventions": len(error_changed),
        "control_interventions": sum(bool(row["control"]["intervention"]) for row in decisions),
        "error_mean_cp": float(np.mean(errors)),
        "control_mean_cp": float(np.mean(controls)),
        "paired_mean_cp": float(np.mean(paired)),
        "error_positive_realization_rate": float(np.mean([float(row["realized_gain_cp"]) > 0.0 for row in error_changed])),
        "outside_gate_bit_identical": all(row[role]["outside_gate_bit_identical"] for row in decisions for role in ("error", "control")),
    }
    expected_metrics = fresh_report["metrics"]
    expected_reproduction = {
        "pairs": fresh.FRESH_PAIRS,
        "error_interventions": expected_metrics["error_interventions"],
        "control_interventions": expected_metrics["control_interventions"],
        "error_mean_cp": expected_metrics["error_improvement"]["mean"],
        "control_mean_cp": expected_metrics["control_improvement"]["mean"],
        "paired_mean_cp": expected_metrics["paired_error_minus_control"]["mean"],
        "error_positive_realization_rate": expected_metrics["error_positive_realization_rate"],
        "outside_gate_bit_identical": expected_metrics["outside_gate_bit_identical"],
    }
    if not _same(reproduced, expected_reproduction):
        raise ValueError(f"1517 decision reproduction drift got={reproduced} want={expected_reproduction}")

    detailed = []
    for row, decision in zip(fresh_rows, decisions, strict=True):
        for role in ("error", "control"):
            detailed.append(_detail(
                row[role], model, decision[role], role=role, pair_id=int(row["pair_id"]),
                source_pool=str(row["source_pool"]),
            ))
    interventions = [row for row in detailed if row["intervention"]]
    error_interventions = [row for row in interventions if row["role"] == "error"]
    control_interventions = [row for row in interventions if row["role"] == "control"]
    risk = _risk_candidates(error_interventions)
    stable = [row for row in risk if row["descriptively_pool_stable"]]
    worst = sorted(interventions, key=lambda row: (row["improvement_cp"], row["pair_id"], row["role"]))[:WORST_ROWS]
    worst_compact = [{
        key: row[key] for key in (
            "pair_id", "role", "source_pool", "improvement_cp", "predicted_advantage_cp",
            "guard_margin_cp", "proxy_cp", "phase", "piece_count", "king_count",
            "ply", "legal_moves", "anchor_disagreement", "correction_clipped",
            "proposed_capture", "dominant_feature", "dominant_feature_family",
            "opening_id", "game_uid", "exact_state_key",
        )
    } for row in worst]
    pool_pair_ids = {
        pool: sorted(int(row["pair_id"]) for row in fresh_rows if row["source_pool"] == pool)
        for pool in sorted({str(row["source_pool"]) for row in fresh_rows})
    }
    return {
        "schema": SCHEMA, "verdict": READY, "passed": True,
        "scientific_source_verdict": fresh.NOT_ESTABLISHED,
        "purpose": "descriptive_discovery_of_1517_catastrophic_tail_only",
        "reproduction": reproduced, "frozen_hypothesis": EXPECTED_HYPOTHESIS,
        "identities": fresh_identities,
        "source_hashes": {
            "training_pairs_sha256": _digest(training_pairs),
            "fresh_pairs_sha256": _digest(fresh_pairs),
            "fresh_target_cache_sha256": _digest(target_cache),
            "fresh_report_sha256": _digest(fresh_report),
            "final_audit_sha256": _digest(final_audit),
            "model_coef_sha256": _digest(np.asarray(model["coef"]).tolist()),
        },
        "split_integrity": {
            "fresh_pools": pool_pair_ids,
            "fresh_pool_pair_overlap": len(set(pool_pair_ids.get("pool1", [])) & set(pool_pair_ids.get("pool2", []))),
            "fresh_pairs_never_fit": True, "training_population": "immutable_1508_gate_fit_only",
        },
        "distributions": {
            "all_error_pairs": _distribution(errors), "all_control_pairs": _distribution(controls),
            "paired_error_minus_control": _distribution(paired),
            "error_interventions": _distribution(row["improvement_cp"] for row in error_interventions),
            "control_interventions": _distribution(row["improvement_cp"] for row in control_interventions),
        },
        "loss_concentration": {
            "error_interventions": _loss_concentration(error_interventions),
            "control_interventions": _loss_concentration(control_interventions),
        },
        "error_intervention_slices": {
            "by_pool": _group(error_interventions, "source_pool"),
            "by_phase": _group(error_interventions, "phase"),
            "by_piece_count": _group(error_interventions, "piece_count"),
            "by_king_count": _group(error_interventions, "king_count"),
            "by_dominant_feature": _group(error_interventions, "dominant_feature"),
            "by_dominant_feature_family": _group(error_interventions, "dominant_feature_family"),
        },
        "correlations_with_realized_improvement": {
            key: _correlation(error_interventions, key) for key in (
                "predicted_advantage_cp", "guard_margin_cp", "proxy_cp",
                "original_anchor_margin_cp", "image_anchor_margin_cp",
                "raw_correction_delta_cp", "clipped_correction_delta_cp",
            )
        },
        "feature_attribution": _feature_attribution(error_interventions, "feature_contributions_cp"),
        "feature_family_attribution": _feature_attribution(error_interventions, "feature_family_contributions_cp"),
        "predeclared_risk_factors": risk,
        "descriptively_pool_stable_risk_factors": [row["name"] for row in stable],
        "risk_hypothesis_status": (
            "candidate_for_preregistration_on_entirely_new_fresh_pools" if stable
            else "no_predeclared_pool_stable_risk_factor_established"
        ),
        "worst_interventions": worst_compact,
        "accounting": {
            "fresh_pairs_examined": len(fresh_rows), "fresh_states_examined": len(detailed),
            "authenticated_source_target_states_read": len(detailed),
            "new_exact_target_computations": 0,
            "diagnostic_residual_fits_on_immutable_1508": 1,
            "fresh_label_fits": 0, "pattern_eval_fits": 0, "production_model_fits": 0,
            "strength_games": 0, "new_selfplay_games": 0, "frozen_reads": 0,
        },
        "fresh_1517_reuse_for_validation_forbidden": True,
        "production_rule_authorized": False, "production_refit_authorized": False,
        "strength_gate_authorized": False, "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": (
            "separate_preregistration_then_entirely_new_fresh_pool_confirmation" if stable else None
        ),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--training-report", type=Path, required=True)
    root.add_argument("--failed-model", type=Path, required=True)
    root.add_argument("--training-pairs", type=Path, required=True)
    root.add_argument("--training-shard", action="append", type=Path, required=True)
    root.add_argument("--fresh-summary", type=Path, required=True)
    root.add_argument("--fresh-report", type=Path, required=True)
    root.add_argument("--fresh-pairs", type=Path, required=True)
    root.add_argument("--fresh-shard", action="append", type=Path, required=True)
    root.add_argument("--target-cache", type=Path, required=True)
    root.add_argument("--final-audit", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    load = lambda path: json.loads(path.read_text())
    report = autopsy(
        load(args.training_report), load(args.failed_model), load(args.training_pairs),
        [load(path) for path in args.training_shard], load(args.fresh_summary),
        load(args.fresh_report), load(args.fresh_pairs), [load(path) for path in args.fresh_shard],
        load(args.target_cache), load(args.final_audit),
    )
    _publish(args.report, report)
    print(json.dumps({
        "verdict": report["verdict"], "risk_hypothesis_status": report["risk_hypothesis_status"],
        "error_loss_concentration": report["loss_concentration"]["error_interventions"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
