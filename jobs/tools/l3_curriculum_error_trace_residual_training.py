#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Training-only OOF calibration of the preregistered CURRICULUM residual."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    from jobs.tools import l3_curriculum_error_action_ranker as ranker
    from jobs.tools import l3_curriculum_error_paired_coverage_screen as coverage
    from jobs.tools import l3_curriculum_error_trace_proxy_preregistration as prereg
    from jobs.tools import l3_curriculum_error_trace_variability_screen as variability
    from jobs.tools import l3_curriculum_search_error_atlas as atlas
except ModuleNotFoundError:  # pragma: no cover
    import l3_curriculum_error_action_ranker as ranker  # type: ignore
    import l3_curriculum_error_paired_coverage_screen as coverage  # type: ignore
    import l3_curriculum_error_trace_proxy_preregistration as prereg  # type: ignore
    import l3_curriculum_error_trace_variability_screen as variability  # type: ignore
    import l3_curriculum_search_error_atlas as atlas  # type: ignore


SCHEMA = "jass.l3_curriculum_error_trace_residual_training.v1"
MODEL_SCHEMA = "jass.l3_curriculum_error_trace_residual_model.v1"
READY = "JASS_CURRICULUM_ERROR_TRACE_RESIDUAL_TRAINING_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_TRACE_RESIDUAL_TRAINING_NOT_ESTABLISHED"
SHAM_REPLICATES = 100
SHAM_SEED = 2026082252
SHUFFLED_MODEL_SEED = 2026082253
BOOTSTRAP_SEED = 2026082254


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


def _check_preregistration(report: dict[str, Any]) -> None:
    if report.get("schema") != prereg.SCHEMA or report.get("verdict") != prereg.READY or report.get("passed") is not True:
        raise ValueError("training requires the passed immutable trace proxy pre-registration")
    architecture = report.get("fixed_architecture", {})
    if architecture.get("family") != "canonical_paired_trace_pairwise_ridge_residual_with_fixed_variability_gate":
        raise ValueError("training architecture family drift")
    if float(architecture.get("alpha", -1.0)) != prereg.ALPHA or float(architecture.get("correction_cap_cp", -1.0)) != prereg.CAP_CP:
        raise ValueError("training alpha/cap drift")
    gate = architecture.get("risk_gate", {})
    if gate.get("proxy") != prereg.SELECTED_PROXY or float(gate.get("lower_open", -1.0)) != prereg.LOWER_OPEN or float(gate.get("upper_closed", -1.0)) != prereg.UPPER_CLOSED:
        raise ValueError("training risk gate drift")
    for key in (
        "validation_action_value_reads",
        "outer_confirm_action_value_reads",
        "diagnostic_fits",
        "pattern_eval_fits",
        "production_model_fits",
        "strength_games",
        "new_selfplay_games",
        "frozen_reads",
    ):
        if int(report.get(key, -1)) != 0:
            raise ValueError(f"pre-registration sealed/forbidden counter drift: {key}")


def split_profiles(pairs: dict[str, Any], preregistration: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    _check_preregistration(preregistration)
    if pairs.get("schema") != atlas.SCHEMA_PAIRS or pairs.get("matching_passed") is not True:
        raise ValueError("training split requires passed matched profiles")
    source_digest = hashlib.sha256(_canonical(pairs)).hexdigest()
    expected_digest = str(preregistration.get("coverage_source", {}).get("pairs_sha256", ""))
    if source_digest != expected_digest:
        raise ValueError("training split source pairs identity drift")
    discovery = [row for row in pairs.get("pairs", []) if row.get("split") == "discovery"]
    if len(discovery) != int(pairs.get("pairs_by_split", {}).get("discovery", -1)):
        raise ValueError("training discovery count drift")
    if coverage._forbidden_keys(discovery):
        raise ValueError("training split profile source contains action targets")
    fit, audit, manifest = coverage._split(discovery, seed=coverage.SPLIT_SEED)
    fit_ids, audit_ids = coverage._identity_sets(fit), coverage._identity_sets(audit)
    overlap = {key: len(fit_ids[key] & audit_ids[key]) for key in fit_ids}
    if any(overlap.values()):
        raise ValueError(f"training split leakage: {overlap}")
    reduced = {
        "schema": atlas.SCHEMA_PAIRS,
        "matching_passed": True,
        "matched_pairs": len(fit),
        "pairs_by_split": {"discovery": len(fit), "confirm": 0},
        "pairs": fit,
        "source_pairs_sha256": source_digest,
        "subset": "gate_fit",
    }
    audit_manifest = {
        "schema": "jass.l3_curriculum_error_trace_residual_split.v1",
        "split": manifest,
        "overlap": overlap,
        "gate_fit_pair_ids": [int(row["pair_id"]) for row in fit],
        "feature_audit_pair_ids": [int(row["pair_id"]) for row in audit],
        "gate_fit_pairs_sha256": hashlib.sha256(_canonical(reduced)).hexdigest(),
        "feature_audit_profiles_sha256": hashlib.sha256(_canonical(audit)).hexdigest(),
        "outer_confirm_profile_rows_examined": 0,
        "action_value_reads": 0,
    }
    return reduced, audit_manifest


def _paired_features(profile: dict[str, Any]) -> tuple[dict[str, np.ndarray], dict[str, float], dict[str, float]]:
    of, oscores = ranker._raw_features(profile, image=False)
    imf, iscores = ranker._raw_features(profile, image=True)
    if set(of) != set(imf) or set(oscores) != set(iscores):
        raise ValueError("paired feature legal action set drift")
    return {action: (of[action] + imf[action]) / 2.0 for action in of}, oscores, iscores


def _load_rows(pairs: dict[str, Any], shards: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if pairs.get("subset") != "gate_fit" or pairs.get("matching_passed") is not True:
        raise ValueError("training requires gate-fit-only pairs")
    profiles = list(pairs.get("pairs", []))
    if len(profiles) != int(pairs.get("matched_pairs", -1)):
        raise ValueError("training gate-fit pair count drift")
    if coverage._forbidden_keys(profiles):
        raise ValueError("training gate-fit profiles contain action targets")
    if len(shards) != 16 or {int(row.get("shard", -1)) for row in shards} != set(range(16)):
        raise ValueError("training atlas shards incomplete")
    digest = hashlib.sha256(_canonical(pairs)).hexdigest()
    if any(row.get("schema") != atlas.SCHEMA_ATLAS_SHARD or row.get("pairs_sha256") != digest or int(row.get("max_pairs", -1)) != 0 for row in shards):
        raise ValueError("training atlas identity/execution drift")
    identities = {}
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        values = {str(row.get(key, "")) for row in shards}
        if len(values) != 1 or not next(iter(values)):
            raise ValueError(f"training atlas {key} drift")
        identities[key] = next(iter(values))
    judged = {int(row["pair_id"]): row for shard in shards for row in shard.get("rows", [])}
    profiles = {int(row["pair_id"]): row for row in profiles}
    if set(judged) != set(profiles):
        raise ValueError("training atlas pair coverage drift")
    rows = []
    for pair_id in sorted(profiles):
        raw, exact = profiles[pair_id], judged[pair_id]
        row = {"pair_id": pair_id}
        for role in ("error", "control"):
            features, original_scores, image_scores = _paired_features(raw[role])
            values = ranker._true_values(exact[role])
            if set(features) != set(values):
                raise ValueError("training feature/judge action set drift")
            row[role] = {
                "profile": raw[role], "features": features,
                "original_scores": original_scores, "image_scores": image_scores,
                "values": values,
            }
        rows.append(row)
    return rows, identities


def _components_folds(rows: list[dict[str, Any]]) -> tuple[dict[int, int], dict[str, Any]]:
    raw = [{"pair_id": row["pair_id"], "error": row["error"]["profile"], "control": row["control"]["profile"]} for row in rows]
    assignments = {}
    payload = []
    for members in coverage._components(raw):
        digest = hashlib.sha256(f"{prereg.FOLD_SEED}|{','.join(map(str, members))}".encode()).digest()
        fold = int.from_bytes(digest[:8], "big") % prereg.FOLDS
        for pair_id in members:
            assignments[pair_id] = fold
        payload.append({"members": members, "fold": fold})
    counts = {str(fold): sum(value == fold for value in assignments.values()) for fold in range(prereg.FOLDS)}
    if any(value == 0 for value in counts.values()):
        raise ValueError(f"training OOF fold empty: {counts}")
    return assignments, {"method": "component_sha256_mod5", "seed": prereg.FOLD_SEED, "counts": counts, "manifest_sha256": hashlib.sha256(_canonical(payload)).hexdigest()}


def _fit(rows: list[dict[str, Any]], *, sham_seed: int | None = None) -> dict[str, Any]:
    matrix = np.vstack([vector for row in rows for role in ("error", "control") for vector in row[role]["features"].values()])
    mean = matrix.mean(axis=0); rms = np.sqrt(np.mean((matrix - mean) ** 2, axis=0)); rms[rms < 1e-6] = 1.0
    gram = np.zeros((len(ranker.FEATURE_NAMES), len(ranker.FEATURE_NAMES))); target = np.zeros(len(ranker.FEATURE_NAMES)); total = 0.0; comparisons = 0
    for row in rows:
        for role in ("error", "control"):
            state = row[role]; values = state["values"] if sham_seed is None else ranker._permuted_values(state["values"], seed=sham_seed, state_key=f"{row['pair_id']}|{role}")
            teacher = max(values, key=lambda action: (values[action], action)); others = [action for action in sorted(values) if action != teacher]
            if not others: continue
            weight = 0.5 / len(rows) / len(others)
            paired_scores = {action: (state["original_scores"][action] + state["image_scores"][action]) / 2.0 for action in values}
            for other in others:
                x = (state["features"][teacher] - state["features"][other]) / rms
                y = (values[teacher] - values[other]) - (paired_scores[teacher] - paired_scores[other])
                gram += weight * np.outer(x, x); target += weight * x * y; total += weight; comparisons += 1
    if total <= 0.0: raise ValueError("training fit has zero comparisons")
    coef = np.linalg.solve(gram / total + prereg.ALPHA * np.eye(len(ranker.FEATURE_NAMES)), target / total)
    return {"schema": MODEL_SCHEMA, "feature_names": list(ranker.FEATURE_NAMES), "mean": mean.tolist(), "rms": rms.tolist(), "coef": coef.tolist(), "alpha": prereg.ALPHA, "correction_cap_cp": prereg.CAP_CP, "states": len(rows) * 2, "comparisons": comparisons, "sham_seed": sham_seed}


def _correction(model: dict[str, Any], vector: np.ndarray) -> float:
    value = float(((vector - np.asarray(model["mean"])) / np.asarray(model["rms"])) @ np.asarray(model["coef"]))
    return max(-prereg.CAP_CP, min(prereg.CAP_CP, value))


def _best(scores: dict[str, float]) -> str:
    return max(scores, key=lambda action: (scores[action], action))


def _decision(state: dict[str, Any], model: dict[str, Any], *, threshold: float) -> dict[str, Any]:
    proxy = variability._profile_values(state["profile"])[prereg.SELECTED_PROXY]
    eligible = prereg.LOWER_OPEN < proxy <= prereg.UPPER_CLOSED
    original_anchor, image_anchor = _best(state["original_scores"]), _best(state["image_scores"])
    correction = {action: _correction(model, state["features"][action]) for action in state["features"]}
    original_corrected = {action: state["original_scores"][action] + correction[action] for action in correction}
    image_corrected = {action: state["image_scores"][action] + correction[action] for action in correction}
    original_proposed, image_proposed = _best(original_corrected), _best(image_corrected)
    original_advantage = original_corrected[original_proposed] - original_corrected[original_anchor]
    image_advantage = image_corrected[image_proposed] - image_corrected[image_anchor]
    intervene = eligible and original_proposed == image_proposed and original_proposed not in {original_anchor, image_anchor} and min(original_advantage, image_advantage) >= threshold
    chosen_original = original_proposed if intervene else original_anchor; chosen_image = image_proposed if intervene else image_anchor
    values = state["values"]
    anchor_value = (values[original_anchor] + values[image_anchor]) / 2.0; chosen_value = (values[chosen_original] + values[chosen_image]) / 2.0
    return {
        "eligible": eligible,
        "intervention": intervene,
        "improvement_cp": chosen_value - anchor_value,
        "predicted_advantage_cp": (original_advantage + image_advantage) / 2.0 if intervene else None,
        "realized_gain_cp": chosen_value - anchor_value if intervene else None,
        "anchor_symmetry": original_anchor == image_anchor,
        "aligned_symmetry": chosen_original == chosen_image,
        "abstention_bit_identical": not intervene and chosen_original == original_anchor and chosen_image == image_anchor,
        "outside_gate_bit_identical": eligible or (chosen_original == original_anchor and chosen_image == image_anchor),
    }


def _evaluate(rows: list[dict[str, Any]], models: dict[int, dict[str, Any]] | dict[str, Any], *, threshold: float, bootstrap_seed: int) -> dict[str, Any]:
    decisions = []
    per_pair = isinstance(next(iter(models)), int)
    for row in rows:
        model = models[row["pair_id"]] if per_pair else models
        decisions.append({"pair_id": row["pair_id"], "error": _decision(row["error"], model, threshold=threshold), "control": _decision(row["control"], model, threshold=threshold)})
    errors = [row["error"]["improvement_cp"] for row in decisions]; controls = [row["control"]["improvement_cp"] for row in decisions]; paired = [left - right for left, right in zip(errors, controls, strict=True)]
    calibration = [row["error"] for row in decisions if row["error"]["intervention"]]
    predicted = np.asarray([row["predicted_advantage_cp"] for row in calibration], dtype=float); realized = np.asarray([row["realized_gain_cp"] for row in calibration], dtype=float)
    rate = lambda role, key: float(np.mean([bool(row[role][key]) for row in decisions])) if decisions else 0.0
    return {"pairs": len(rows), "error_improvement": ranker._bootstrap(errors, samples=10000, seed=bootstrap_seed), "control_improvement": ranker._bootstrap(controls, samples=10000, seed=bootstrap_seed + 1), "paired_error_minus_control": ranker._bootstrap(paired, samples=10000, seed=bootstrap_seed + 2), "error_interventions": sum(row["error"]["intervention"] for row in decisions), "control_interventions": sum(row["control"]["intervention"] for row in decisions), "error_eligible": sum(row["error"]["eligible"] for row in decisions), "control_eligible": sum(row["control"]["eligible"] for row in decisions), "error_positive_realization_rate": float(np.mean(realized > 0.0)) if realized.size else None, "error_calibration_mean_bias_cp": float(np.mean(realized - predicted)) if realized.size else None, "error_anchor_symmetry": rate("error", "anchor_symmetry"), "error_aligned_symmetry": rate("error", "aligned_symmetry"), "control_anchor_symmetry": rate("control", "anchor_symmetry"), "control_aligned_symmetry": rate("control", "aligned_symmetry"), "abstentions_bit_identical": all(row[role]["abstention_bit_identical"] for row in decisions for role in ("error", "control") if not row[role]["intervention"]), "outside_gate_bit_identical": all(row[role]["outside_gate_bit_identical"] for row in decisions for role in ("error", "control"))}


def _oof_models(rows: list[dict[str, Any]], folds: dict[int, int], *, sham_seed: int | None = None) -> dict[int, dict[str, Any]]:
    output = {}
    for fold in range(prereg.FOLDS):
        model = _fit([row for row in rows if folds[row["pair_id"]] != fold], sham_seed=sham_seed)
        for row in rows:
            if folds[row["pair_id"]] == fold: output[row["pair_id"]] = model
    return output


def train(preregistration: dict[str, Any], pairs: dict[str, Any], shards: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    _check_preregistration(preregistration); rows, identities = _load_rows(pairs, shards)
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        if identities[key] != preregistration.get(key): raise ValueError(f"training/pre-registration {key} drift")
    folds, fold_manifest = _components_folds(rows); oof = _oof_models(rows, folds)
    candidates = []
    for index, threshold in enumerate(prereg.THRESHOLDS_CP):
        metrics = _evaluate(rows, oof, threshold=threshold, bootstrap_seed=BOOTSTRAP_SEED + index * 10)
        gates = {"error_interventions_at_least_12": metrics["error_interventions"] >= 12, "control_interventions_at_least_8": metrics["control_interventions"] >= 8, "total_interventions_at_least_20": metrics["error_interventions"] + metrics["control_interventions"] >= 20, "error_positive_realization_rate_ge_0_60": metrics["error_positive_realization_rate"] is not None and metrics["error_positive_realization_rate"] >= 0.60, "control_mean_gain_ge_minus_2cp": metrics["control_improvement"]["mean"] >= -2.0, "outside_gate_bit_identical": metrics["outside_gate_bit_identical"]}
        candidates.append({"threshold_cp": threshold, "metrics": metrics, "gates": gates, "passed": all(gates.values())})
    passing = [row for row in candidates if row["passed"]]; passing.sort(key=lambda row: (-float(row["metrics"]["paired_error_minus_control"]["ci95"][0]), -float(row["threshold_cp"])))
    selected = passing[0] if passing else None; sham = None; aligned = None; shuffled = None
    if selected:
        real = float(selected["metrics"]["paired_error_minus_control"]["mean"]); sham_means = []
        for index in range(SHAM_REPLICATES):
            models = _oof_models(rows, folds, sham_seed=SHAM_SEED + index)
            metrics = _evaluate(rows, models, threshold=float(selected["threshold_cp"]), bootstrap_seed=SHAM_SEED + 1000 + index * 10)
            sham_means.append(float(metrics["paired_error_minus_control"]["mean"]))
        q95 = float(np.quantile(sham_means, 0.95)); sham = {"replicates": SHAM_REPLICATES, "seed": SHAM_SEED, "real_paired_mean_cp": real, "sham_q95_cp": q95, "real_exceeds_sham_q95": real > q95}
        if sham["real_exceeds_sham_q95"]:
            aligned = _fit(rows); shuffled = _fit(rows, sham_seed=SHUFFLED_MODEL_SEED)
    gates = {"gate_fit_pairs_at_least_64": len(rows) >= coverage.MIN_FIT_PAIRS, "five_nonempty_component_folds": all(int(value) > 0 for value in fold_manifest["counts"].values()), "threshold_selected": selected is not None, "real_exceeds_100_shams_q95": sham is not None and sham["real_exceeds_sham_q95"]}
    passed = all(gates.values()) and aligned is not None and shuffled is not None
    report = {"schema": SCHEMA, "verdict": READY if passed else NOT_ESTABLISHED, "passed": passed, **identities, "support": {"gate_fit_pairs": len(rows), "feature_audit_pairs": None, "outer_confirm_pairs": None}, "fold_manifest": fold_manifest, "candidates": candidates, "selected_threshold": selected, "sham": sham, "training_gates": gates, "failed_gates": sorted(key for key, value in gates.items() if not value), "gate_fit_action_value_reads": len(rows) * 2, "feature_audit_action_value_reads": 0, "outer_confirm_action_value_reads": 0, "residual_fits": prereg.FOLDS * (1 + (SHAM_REPLICATES if selected else 0)) + (2 if passed else 0), "pattern_eval_fits": 0, "strength_games": 0, "new_selfplay_games": 0, "frozen_reads": 0, "feature_audit_authorized": passed, "production_rule_authorized": False, "promotion_authorized": False, "automatic_continuation": False, "next_stage": "one_shot_feature_audit" if passed else None}
    envelope = {"schema": MODEL_SCHEMA, "authorized_for_feature_audit": passed, "authorized_for_production": False, "fixed_architecture": preregistration.get("fixed_architecture"), "selected_threshold_cp": float(selected["threshold_cp"]) if passed and selected else None, "aligned_model": aligned if passed else None, "shuffled_model": shuffled if passed else None, "zero_residual_control": {"operation": "unaltered_CURRICULUM_action", "same_decision_cost": True}, **identities, "feature_audit_action_value_reads": 0, "outer_confirm_action_value_reads": 0, "promotion_authorized": False}
    return report, envelope


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__); sub = root.add_subparsers(dest="command", required=True)
    split = sub.add_parser("split"); split.add_argument("--pairs", type=Path, required=True); split.add_argument("--preregistration", type=Path, required=True); split.add_argument("--gate-fit-pairs", type=Path, required=True); split.add_argument("--audit-manifest", type=Path, required=True)
    fit = sub.add_parser("train"); fit.add_argument("--preregistration", type=Path, required=True); fit.add_argument("--pairs", type=Path, required=True); fit.add_argument("--atlas-shard", action="append", type=Path, required=True); fit.add_argument("--report", type=Path, required=True); fit.add_argument("--model", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "split":
        pairs, manifest = split_profiles(json.loads(args.pairs.read_text()), json.loads(args.preregistration.read_text())); _publish(args.gate_fit_pairs, pairs); _publish(args.audit_manifest, manifest); print(json.dumps({"gate_fit": pairs["matched_pairs"], "feature_audit": len(manifest["feature_audit_pair_ids"])}, sort_keys=True))
    else:
        report, model = train(json.loads(args.preregistration.read_text()), json.loads(args.pairs.read_text()), [json.loads(path.read_text()) for path in args.atlas_shard])
        report["preregistration_sha256"] = _sha256(args.preregistration)
        report["gate_fit_pairs_sha256"] = _sha256(args.pairs)
        model["preregistration_sha256"] = report["preregistration_sha256"]
        model["gate_fit_pairs_sha256"] = report["gate_fit_pairs_sha256"]
        _publish(args.report, report)
        _publish(args.model, model)
        print(json.dumps({"verdict": report["verdict"], "threshold": model["selected_threshold_cp"]}, sort_keys=True))
    return 0


if __name__ == "__main__": raise SystemExit(main())
