#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed sparse-Jacobian cross-fit screen for loss-first sibling labels.

The screen fits only diagnostic residual directions around the byte-identical
CURRICULUM prior.  Pool 1 may discover/fit coordinates only for evaluation on
pool 2, and conversely.  It cannot write a PJTW model or authorize strength
games.  A PASS merely authorizes a separately audited anchored local refit.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np


LABEL_SCHEMA = "jass.l3_curriculum_error_loss_first_labels.v1"
PAIR_SCHEMA = "jass.l3_curriculum_error_loss_first_matched_pairs.v1"
SOURCE_VERDICT = "JASS_CURRICULUM_ERROR_LOSS_FIRST_LABELS_READY"
SCHEMA = "jass.l3_curriculum_error_loss_first_sparse_jacobian_crossfit.v1"
MODEL_SCHEMA = "jass.l3_curriculum_error_loss_first_diagnostic_direction.v1"
READY = "JASS_CURRICULUM_ERROR_LOSS_FIRST_SPARSE_JACOBIAN_CROSSFIT_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_LOSS_FIRST_SPARSE_JACOBIAN_NOT_ESTABLISHED"

MIN_ERROR_OPENINGS = 12
MIN_SIGN_CONSISTENCY = 0.75
MAX_CANONICAL_BUCKETS = 128
PAIRWISE_TEMPERATURE_CP = 50.0
LISTWISE_TEMPERATURE_CP = 50.0
PAIRWISE_MIX = 0.5
# The hard ±40 cp bound is the primary diagnostic anchor.  This small fixed
# ridge resolves collinear sparse directions without preventing a genuinely
# replicated bucket from crossing a shallow 10–30 cp action margin.
RIDGE_ALPHA = 0.0001
MAX_RAW_DELTA_CP = 40.0
SCORE_RATE_SCALE_CP = 200.0
ERROR_THRESHOLD_CP = 50.0


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(_canonical(value)); tmp.replace(path)


def _total_buckets() -> int:
    from jobs.tools.l3_curriculum_error_residual_atlas import _patterns_module
    return int(_patterns_module().TOTAL_BUCKETS)


def _couple(vector: dict[str, Any] | dict[int, Any], total: int) -> dict[int, float]:
    result: dict[int, float] = defaultdict(float)
    for raw_key, raw_value in vector.items():
        key = int(raw_key); value = float(raw_value)
        if key < 0 or key >= 2 * total:
            raise ValueError(f"gradient coordinate outside exact-fold PatternEval: {key}")
        result[key % total] += value
    return {key: value for key, value in result.items() if abs(value) > 1e-15}


def _sub(left: dict[int, float], right: dict[int, float]) -> dict[int, float]:
    return {
        key: left.get(key, 0.0) - right.get(key, 0.0)
        for key in set(left) | set(right)
        if abs(left.get(key, 0.0) - right.get(key, 0.0)) > 1e-15
    }


def _softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - float(np.max(values))
    exp = np.exp(np.clip(shifted, -60.0, 60.0))
    return exp / float(exp.sum())


def _seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _state(row: dict[str, Any], *, role: str, stratum: str, total: int) -> dict[str, Any]:
    if row.get("accepted") is not True or row.get("label") != role:
        raise ValueError(f"matched {role} row is not a stable accepted {role}")
    actions = [str(action) for action in row["legal_actions"]]
    teacher = str(row["teacher_action"])
    if teacher not in actions or len(actions) < 2:
        raise ValueError("loss-first cross-fit requires a non-forced teacher action")
    comparisons = {str(item["sibling"]): item for item in row["comparisons"]}
    if set(comparisons) != set(actions) - {teacher}:
        raise ValueError("teacher-versus-all-siblings comparison coverage drift")
    vectors: dict[str, dict[str, dict[int, float]]] = {
        orientation: {teacher: {}} for orientation in ("symmetrised", "original", "exact_image")
    }
    field = {
        "symmetrised": "gradient", "original": "original_gradient",
        "exact_image": "exact_image_gradient",
    }
    for action, comparison in comparisons.items():
        for orientation, name in field.items():
            # comparison gradient is teacher minus sibling; an action vector
            # relative to the teacher is therefore its negative.
            gradient = _couple(comparison[name], total)
            vectors[orientation][action] = {key: -value for key, value in gradient.items()}
    baseline = {
        orientation: {str(action): float(value) for action, value in scores.items()}
        for orientation, scores in row["baseline_shallow_scores_cp"].items()
    }
    if any(set(scores) != set(actions) for scores in baseline.values()):
        raise ValueError("baseline action coverage drift")
    utilities = {str(action): float(value) for action, value in row["listwise_bounded_utility"].items()}
    if set(utilities) != set(actions) or max(utilities.values()) != 0.0:
        raise ValueError("bounded listwise utilities drift")
    deep = row["teacher_details"]["12"]
    deep_values = {
        "original": {str(action): float(value) for action, value in deep["original_values_cp"].items()},
        "exact_image": {str(action): float(value) for action, value in deep["exact_image_values_cp"].items()},
    }
    if any(set(values) != set(actions) for values in deep_values.values()):
        raise ValueError("deep action coverage drift")
    return {
        "pool": int(row["pool"]), "role": role, "stratum": stratum,
        "opening_id": str(row["opening_id"]), "game_uid": str(row["game_uid"]),
        "exact_state_key": str(row["exact_state_key"]), "actions": actions,
        "teacher": teacher, "historical": str(row["historical_action"]),
        "vectors": vectors, "baseline": baseline, "utilities": utilities,
        "deep": deep_values,
    }


def load_pairs(payload: dict[str, Any], *, total: int) -> dict[int, list[dict[str, Any]]]:
    if payload.get("schema") != PAIR_SCHEMA or payload.get("source_verdict") != SOURCE_VERDICT:
        raise ValueError("loss-first matched-pair source drift")
    by_pool: dict[int, list[dict[str, Any]]] = {1: [], 2: []}
    openings: dict[int, set[str]] = {1: set(), 2: set()}
    games: dict[int, set[str]] = {1: set(), 2: set()}
    canonical: dict[int, set[str]] = {1: set(), 2: set()}
    for raw in payload.get("pairs") or []:
        pool = int(raw["pool"])
        if pool not in by_pool:
            raise ValueError("unexpected loss-first pool")
        stratum = str(raw["matching_stratum"])
        pair = {
            "pair_id": int(raw["pair_id"]), "pool": pool, "stratum": stratum,
            "error": _state(raw["error"], role="error", stratum=stratum, total=total),
            "control": _state(raw["control"], role="control", stratum=stratum, total=total),
        }
        for state in (pair["error"], pair["control"]):
            if state["opening_id"] in openings[pool] or state["game_uid"] in games[pool] or state["exact_state_key"] in canonical[pool]:
                raise ValueError("opening/game/canonical component reused inside a pool")
            openings[pool].add(state["opening_id"]); games[pool].add(state["game_uid"]); canonical[pool].add(state["exact_state_key"])
        by_pool[pool].append(pair)
    if not by_pool[1] or not by_pool[2]:
        raise ValueError("both loss-first pools require matched support")
    if openings[1] & openings[2] or games[1] & games[2] or canonical[1] & canonical[2]:
        raise ValueError("cross-pool opening/game/canonical leakage")
    return by_pool


def _target_utilities(state: dict[str, Any], sham_seed: int | None) -> dict[str, float]:
    utilities = dict(state["utilities"])
    if sham_seed is None:
        return utilities
    actions = sorted(utilities); values = [utilities[action] for action in actions]
    rng = np.random.default_rng(_seed(sham_seed, state["stratum"], state["opening_id"], state["role"]))
    rng.shuffle(values)
    return dict(zip(actions, values, strict=True))


def discover(pairs: list[dict[str, Any]], *, sham_seed: int | None = None,
             minimum_openings: int = MIN_ERROR_OPENINGS,
             minimum_consistency: float = MIN_SIGN_CONSISTENCY,
             maximum_buckets: int = MAX_CANONICAL_BUCKETS) -> dict[str, Any]:
    by_bucket: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for pair in pairs:
        state = pair["error"]; utilities = _target_utilities(state, sham_seed)
        teacher = sorted(utilities, key=lambda action: (utilities[action], action), reverse=True)[0]
        rivals = [action for action in state["actions"] if action != teacher and utilities[teacher] > utilities[action]]
        if not rivals:
            continue
        per_opening: dict[int, float] = defaultdict(float)
        for rival in rivals:
            gradient = _sub(state["vectors"]["symmetrised"][teacher], state["vectors"]["symmetrised"][rival])
            strength = min(200.0, utilities[teacher] - utilities[rival]) / 200.0
            for bucket, value in gradient.items():
                per_opening[bucket] += strength * value / len(rivals)
        for bucket, value in per_opening.items():
            if abs(value) > 1e-15:
                by_bucket[bucket][state["opening_id"]] += value
    candidates = []
    for bucket, values_by_opening in by_bucket.items():
        values = np.asarray(list(values_by_opening.values()), dtype=np.float64)
        support = int(values.size)
        positive = int(np.sum(values > 0)); negative = int(np.sum(values < 0))
        consistency = max(positive, negative) / support if support else 0.0
        direction = 1 if positive >= negative else -1
        if support >= minimum_openings and consistency >= minimum_consistency:
            mean_signed = float(values.mean())
            candidates.append({
                "bucket": int(bucket), "error_openings": support,
                "sign_consistency": float(consistency), "direction": direction,
                "mean_signed_gradient": mean_signed,
                "mean_abs_gradient": float(np.abs(values).mean()),
                "selection_score": float(support * consistency * np.abs(values).mean()),
            })
    candidates.sort(key=lambda row: (-row["selection_score"], -row["error_openings"], row["bucket"]))
    selected = candidates[:maximum_buckets]
    return {
        "selected": selected, "selected_buckets": [row["bucket"] for row in selected],
        "eligible_buckets": len(candidates), "scanned_nonzero_buckets": len(by_bucket),
        "minimum_error_openings": minimum_openings,
        "minimum_sign_consistency": minimum_consistency,
        "maximum_canonical_buckets": maximum_buckets,
        "sham_seed": sham_seed,
    }


def _design(state: dict[str, Any], buckets: list[int], *, orientation: str) -> np.ndarray:
    return np.asarray([
        [state["vectors"][orientation][action].get(bucket, 0.0) for bucket in buckets]
        for action in state["actions"]
    ], dtype=np.float64)


def _fit(pairs: list[dict[str, Any]], discovery: dict[str, Any], *, sham_seed: int | None = None) -> dict[str, Any]:
    buckets = [int(value) for value in discovery["selected_buckets"]]
    if not buckets:
        return {"schema": MODEL_SCHEMA, "converged": True, "empty_region": True,
                "selected_buckets": [], "raw_delta_cp": {}, "sham_seed": sham_seed}
    states = [pair[role] for pair in pairs for role in ("error", "control")]
    designs = [_design(state, buckets, orientation="symmetrised") for state in states]
    stacked = np.vstack(designs)
    rms = np.sqrt(np.mean(np.square(stacked), axis=0)); rms[rms < 1e-6] = 1.0
    scaled = [design / rms for design in designs]

    def objective(beta: np.ndarray) -> tuple[float, np.ndarray]:
        loss = 0.0; gradient = np.zeros_like(beta)
        for state, design in zip(states, scaled, strict=True):
            utilities_map = _target_utilities(state, sham_seed)
            utilities = np.asarray([utilities_map[action] for action in state["actions"]], dtype=np.float64)
            baseline = np.asarray([state["baseline"]["symmetrised"][action] for action in state["actions"]], dtype=np.float64)
            scores = baseline + design @ beta
            target = _softmax(utilities / LISTWISE_TEMPERATURE_CP)
            predicted = _softmax(scores / LISTWISE_TEMPERATURE_CP)
            listwise_loss = -float(np.sum(target * np.log(np.maximum(predicted, 1e-300))))
            listwise_gradient = design.T @ (predicted - target) / LISTWISE_TEMPERATURE_CP
            teacher = int(np.argmax(utilities)); rivals = [index for index in range(len(utilities)) if index != teacher and utilities[teacher] > utilities[index]]
            pair_loss = 0.0; pair_gradient = np.zeros_like(beta)
            for rival in rivals:
                diff = design[teacher] - design[rival]
                margin = float(scores[teacher] - scores[rival]) / PAIRWISE_TEMPERATURE_CP
                pair_loss += float(np.logaddexp(0.0, -margin)) / len(rivals)
                pair_gradient += (-1.0 / (1.0 + math.exp(max(-60.0, min(60.0, margin))))) * diff / PAIRWISE_TEMPERATURE_CP / len(rivals)
            loss += PAIRWISE_MIX * pair_loss + (1.0 - PAIRWISE_MIX) * listwise_loss
            gradient += PAIRWISE_MIX * pair_gradient + (1.0 - PAIRWISE_MIX) * listwise_gradient
        loss /= len(states); gradient /= len(states)
        loss += 0.5 * RIDGE_ALPHA * float(beta @ beta) / len(beta)
        gradient += RIDGE_ALPHA * beta / len(beta)
        return loss, gradient

    bounds = [(-MAX_RAW_DELTA_CP * float(scale), MAX_RAW_DELTA_CP * float(scale)) for scale in rms]
    try:
        from scipy.optimize import minimize  # CPX pinned scientific runtime
    except ModuleNotFoundError:  # lightweight local/CI runtime
        minimize = None
    if minimize is not None:
        result = minimize(objective, np.zeros(len(buckets), dtype=np.float64), method="L-BFGS-B",
                          jac=True, bounds=bounds, options={"maxiter": 300, "ftol": 1e-11, "gtol": 1e-7, "maxls": 40})
        success = bool(result.success); beta = np.asarray(result.x, dtype=np.float64)
        status = int(result.status); message = str(result.message); iterations = int(result.nit); final_objective = float(result.fun)
        optimizer = "scipy_L-BFGS-B"
    else:
        # Deterministic projected-gradient fallback keeps repository tests
        # independent of the CPX SciPy image.  CPX certificates record which
        # optimizer ran and require convergence either way.
        beta = np.zeros(len(buckets), dtype=np.float64); lower = np.asarray([item[0] for item in bounds]); upper = np.asarray([item[1] for item in bounds])
        final_objective, gradient = objective(beta); step = 1.0; success = False; iterations = 0
        for iterations in range(1, 2001):
            projected = gradient.copy()
            projected[(beta <= lower + 1e-12) & (gradient > 0)] = 0.0
            projected[(beta >= upper - 1e-12) & (gradient < 0)] = 0.0
            if float(np.max(np.abs(projected))) <= 1e-6:
                success = True; break
            trial_step = min(step * 1.5, 1e4); accepted = False
            for _ in range(40):
                candidate = np.clip(beta - trial_step * gradient, lower, upper)
                candidate_objective, candidate_gradient = objective(candidate)
                if candidate_objective <= final_objective + 1e-4 * float(gradient @ (candidate - beta)):
                    beta = candidate; final_objective = candidate_objective; gradient = candidate_gradient
                    step = trial_step; accepted = True; break
                trial_step *= 0.5
            if not accepted:
                break
        status = 0 if success else 1; message = "projected gradient converged" if success else "projected gradient did not converge"
        optimizer = "deterministic_projected_gradient_fallback"
    if not success or not np.all(np.isfinite(beta)):
        raise RuntimeError(f"diagnostic optimizer failed: status={status} message={message}")
    raw = beta / rms
    return {
        "schema": MODEL_SCHEMA, "converged": True, "empty_region": False,
        "selected_buckets": buckets,
        "raw_delta_cp": {str(bucket): float(value) for bucket, value in zip(buckets, raw, strict=True)},
        "standardised_delta": beta.tolist(), "fold_local_rms": rms.tolist(),
        "objective": final_objective, "iterations": iterations,
        "optimizer": optimizer, "optimizer_status": status, "optimizer_message": message,
        "ridge_alpha": RIDGE_ALPHA, "raw_delta_bound_cp": MAX_RAW_DELTA_CP,
        "pairwise_temperature_cp": PAIRWISE_TEMPERATURE_CP,
        "listwise_temperature_cp": LISTWISE_TEMPERATURE_CP,
        "opening_equal_weight": True, "outside_selected_region_delta_exactly_zero": True,
        "sham_seed": sham_seed,
    }


def _choice(state: dict[str, Any], model: dict[str, Any], orientation: str) -> dict[str, Any]:
    delta = {int(key): float(value) for key, value in model["raw_delta_cp"].items()}
    baseline = state["baseline"][orientation]
    corrected = {
        action: baseline[action] + sum(state["vectors"][orientation][action].get(bucket, 0.0) * value for bucket, value in delta.items())
        for action in state["actions"]
    }
    rank = lambda values: sorted(values, key=lambda action: (values[action], action), reverse=True)[0]
    baseline_action = rank(baseline); candidate_action = rank(corrected)
    deep = state["deep"][orientation]; best = max(deep.values())
    return {
        "baseline_action": baseline_action, "candidate_action": candidate_action,
        "baseline_regret_cp": best - deep[baseline_action],
        "candidate_regret_cp": best - deep[candidate_action],
        "baseline_teacher_hit": baseline_action == state["teacher"],
        "candidate_teacher_hit": candidate_action == state["teacher"],
        "baseline_error_50cp": best - deep[baseline_action] >= ERROR_THRESHOLD_CP,
        "candidate_error_50cp": best - deep[candidate_action] >= ERROR_THRESHOLD_CP,
    }


def evaluate(pairs: list[dict[str, Any]], model: dict[str, Any]) -> dict[str, Any]:
    decisions = []
    for pair in pairs:
        row = {"pair_id": pair["pair_id"], "pool": pair["pool"]}
        for role in ("error", "control"):
            state = pair[role]
            original = _choice(state, model, "original")
            image = _choice(state, model, "exact_image")
            improvement = np.mean([
                original["baseline_regret_cp"] - original["candidate_regret_cp"],
                image["baseline_regret_cp"] - image["candidate_regret_cp"],
            ])
            row[role] = {
                "opening_id": state["opening_id"], "improvement_cp": float(improvement),
                "baseline_teacher_hit": float(np.mean([original["baseline_teacher_hit"], image["baseline_teacher_hit"]])),
                "candidate_teacher_hit": float(np.mean([original["candidate_teacher_hit"], image["candidate_teacher_hit"]])),
                "baseline_error_50cp": float(np.mean([original["baseline_error_50cp"], image["baseline_error_50cp"]])),
                "candidate_error_50cp": float(np.mean([original["candidate_error_50cp"], image["candidate_error_50cp"]])),
                "orientation_symmetric": original["candidate_action"] == image["candidate_action"],
            }
        row["paired_error_minus_control_cp"] = row["error"]["improvement_cp"] - row["control"]["improvement_cp"]
        decisions.append(row)
    mean = lambda role, key: float(np.mean([row[role][key] for row in decisions]))
    error_teacher_gain = mean("error", "candidate_teacher_hit") - mean("error", "baseline_teacher_hit")
    control_teacher_gain = mean("control", "candidate_teacher_hit") - mean("control", "baseline_teacher_hit")
    error_rate_reduction = mean("error", "baseline_error_50cp") - mean("error", "candidate_error_50cp")
    symmetry = float(np.mean([row[role]["orientation_symmetric"] for row in decisions for role in ("error", "control")]))
    return {
        "pool": int(pairs[0]["pool"]), "matched_pairs": len(decisions),
        "error_teacher_top_hit_gain": error_teacher_gain,
        "control_teacher_top_hit_gain": control_teacher_gain,
        "stable_error_50cp_rate_reduction": error_rate_reduction,
        "error_mean_regret_improvement_cp": mean("error", "improvement_cp"),
        "control_mean_regret_improvement_cp": mean("control", "improvement_cp"),
        "paired_error_minus_control_mean_cp": float(np.mean([row["paired_error_minus_control_cp"] for row in decisions])),
        "orientation_symmetry_fraction": symmetry,
        "decisions": decisions,
    }


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    dot = sum(float(left.get(key, 0.0)) * float(right.get(key, 0.0)) for key in keys)
    ln = math.sqrt(sum(float(value) ** 2 for value in left.values()))
    rn = math.sqrt(sum(float(value) ** 2 for value in right.values()))
    return dot / (ln * rn) if ln and rn else 0.0


def _bootstrap(by_pool: dict[int, list[float]], *, samples: int, seed: int) -> dict[str, Any]:
    if samples <= 0 or set(by_pool) != {1, 2} or any(not values for values in by_pool.values()):
        raise ValueError("two-pool bootstrap requires positive samples and non-empty pools")
    arrays = {pool: np.asarray(values, dtype=np.float64) for pool, values in by_pool.items()}
    rng = np.random.default_rng(seed); output = np.empty(samples, dtype=np.float64); done = 0
    while done < samples:
        take = min(4096, samples - done); means = []
        for pool in (1, 2):
            values = arrays[pool]
            indices = rng.integers(0, len(values), size=(take, len(values)))
            means.append(values[indices].mean(axis=1))
        output[done:done + take] = 0.5 * (means[0] + means[1]); done += take
    point = 0.5 * (float(arrays[1].mean()) + float(arrays[2].mean()))
    return {
        "method": "paired_error_control_bootstrap_stratified_by_fresh_pool",
        "unit": "matched pair of disjoint opening components", "samples": samples, "seed": seed,
        "mean": point, "ci95": [float(np.quantile(output, 0.025)), float(np.quantile(output, 0.975))],
        "probability_positive": float(np.mean(output > 0.0)),
    }


def _crossfit(by_pool: dict[int, list[dict[str, Any]]], *, sham_seed: int | None = None) -> dict[str, Any]:
    discoveries = {}; models = {}; heldout = {}
    for train_pool, heldout_pool in ((1, 2), (2, 1)):
        discovery = discover(by_pool[train_pool], sham_seed=sham_seed)
        model = _fit(by_pool[train_pool], discovery, sham_seed=sham_seed)
        discoveries[str(train_pool)] = discovery; models[str(train_pool)] = model
        heldout[str(heldout_pool)] = evaluate(by_pool[heldout_pool], model)
    cosine = _cosine(models["1"]["raw_delta_cp"], models["2"]["raw_delta_cp"])
    paired = {
        pool: [float(row["paired_error_minus_control_cp"]) for row in heldout[str(pool)]["decisions"]]
        for pool in (1, 2)
    }
    minimum_teacher = min(float(heldout[str(pool)]["error_teacher_top_hit_gain"]) for pool in (1, 2))
    minimum_error_rate = min(float(heldout[str(pool)]["stable_error_50cp_rate_reduction"]) for pool in (1, 2))
    paired_mean = 0.5 * sum(float(heldout[str(pool)]["paired_error_minus_control_mean_cp"]) for pool in (1, 2))
    score = min(SCORE_RATE_SCALE_CP * minimum_teacher, SCORE_RATE_SCALE_CP * minimum_error_rate, paired_mean)
    return {
        "discoveries": discoveries, "models": models, "heldout": heldout,
        "selected_coordinate_cosine": cosine, "paired_values_by_pool": paired,
        "minimum_error_teacher_top_hit_gain": minimum_teacher,
        "minimum_stable_error_rate_reduction": minimum_error_rate,
        "paired_error_minus_control_mean_cp": paired_mean,
        "familywise_screen_score_cp_equivalent": score,
        "familywise_score_definition": "min(200*min_pool_teacher_hit_gain,200*min_pool_error_rate_reduction,two_pool_paired_mean_cp)",
        "sham_seed": sham_seed,
    }


def run(labels: dict[str, Any], pairs_payload: dict[str, Any], *, labels_sha: str,
        pairs_sha: str, bootstrap_samples: int, bootstrap_seed: int,
        sham_replicates: int, sham_seed: int, total_buckets: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if labels.get("schema") != LABEL_SCHEMA or labels.get("verdict") != SOURCE_VERDICT or labels.get("passed") is not True:
        raise ValueError("requires certified loss-first labels")
    if int(labels.get("matched_pairs", -1)) != len(pairs_payload.get("pairs") or []):
        raise ValueError("label/pair cardinality drift")
    for key in ("anchored_local_refit_authorized", "production_model_authorized", "strength_gate_authorized", "promotion_authorized", "automatic_continuation"):
        if labels.get(key) is not False:
            raise ValueError(f"source authorization drift: {key}")
    by_pool = load_pairs(pairs_payload, total=total_buckets)
    real = _crossfit(by_pool)
    bootstrap = _bootstrap(real["paired_values_by_pool"], samples=bootstrap_samples, seed=bootstrap_seed)
    sham_scores = []
    for replicate in range(sham_replicates):
        sham = _crossfit(by_pool, sham_seed=sham_seed + replicate)
        sham_scores.append(float(sham["familywise_screen_score_cp_equivalent"]))
    sham_q99 = float(np.quantile(np.asarray(sham_scores, dtype=np.float64), 0.99))
    heldout = real["heldout"]
    symmetry = float(np.mean([heldout[str(pool)]["orientation_symmetry_fraction"] for pool in (1, 2)]))
    gates = {
        "both_pool_fits_converged": all(real["models"][str(pool)]["converged"] for pool in (1, 2)),
        "both_regions_nonempty_and_le_128": all(0 < len(real["discoveries"][str(pool)]["selected_buckets"]) <= MAX_CANONICAL_BUCKETS for pool in (1, 2)),
        "every_selected_bucket_has_12_error_openings_and_75pct_sign": all(
            row["error_openings"] >= MIN_ERROR_OPENINGS and row["sign_consistency"] >= MIN_SIGN_CONSISTENCY
            for pool in (1, 2) for row in real["discoveries"][str(pool)]["selected"]
        ),
        "both_heldout_pools_improve_teacher_top": all(heldout[str(pool)]["error_teacher_top_hit_gain"] > 0.0 for pool in (1, 2)),
        "both_heldout_pools_reduce_stable_50cp_error": all(heldout[str(pool)]["stable_error_50cp_rate_reduction"] > 0.0 for pool in (1, 2)),
        "paired_error_minus_control_ci95_lower_positive": bootstrap["ci95"][0] > 0.0,
        "control_teacher_top_regression_le_0_5pp": all(heldout[str(pool)]["control_teacher_top_hit_gain"] >= -0.005 for pool in (1, 2)),
        "orientation_symmetry_ge_99_9pct": symmetry >= 0.999,
        "selected_coordinate_cosine_ge_0_50": real["selected_coordinate_cosine"] >= 0.50,
        "exactly_1000_opening_cluster_label_shams": sham_replicates == 1000,
        "real_familywise_score_exceeds_sham_q99": real["familywise_screen_score_cp_equivalent"] > sham_q99,
    }
    passed = all(gates.values())
    report = {
        "schema": SCHEMA, "verdict": READY if passed else NOT_ESTABLISHED, "passed": passed,
        "source_labels_sha256": labels_sha, "source_pairs_sha256": pairs_sha,
        "source_verdict": SOURCE_VERDICT, "source_matched_pairs": len(pairs_payload["pairs"]),
        "total_pattern_buckets": total_buckets,
        "protocol": {
            "cross_fit": "pool1_fit_pool2_evaluate_and_pool2_fit_pool1_evaluate",
            "coordinate_geometry": "exact_fold_MG_EG_coupled_canonical_PV_leaf_Jacobians",
            "minimum_error_openings": MIN_ERROR_OPENINGS,
            "minimum_sign_consistency": MIN_SIGN_CONSISTENCY,
            "maximum_canonical_buckets": MAX_CANONICAL_BUCKETS,
            "loss": "equal_mix_bounded_pairwise_logistic_and_listwise_cross_entropy",
            "ridge_alpha": RIDGE_ALPHA, "raw_delta_bound_cp": MAX_RAW_DELTA_CP,
            "prior_mean": "byte_identical_CURRICULUM",
            "outside_selected_region": "exactly_frozen_delta_zero",
            "weighting": "per_opening_equal",
            "bootstrap": {"samples": bootstrap_samples, "seed": bootstrap_seed},
            "shams": {"replicates": sham_replicates, "seed": sham_seed,
                      "method": "within_state_action_label_permutation_clustered_by_opening_and_matching_stratum"},
        },
        "real_crossfit": real, "paired_bootstrap": bootstrap,
        "orientation_symmetry_fraction": symmetry,
        "sham": {"replicates": sham_replicates, "seed": sham_seed,
                 "score_cp_equivalent_q99": sham_q99, "scores_cp_equivalent": sham_scores,
                 "real_score_cp_equivalent": real["familywise_screen_score_cp_equivalent"]},
        "gates": gates,
        "diagnostic_residual_fits": 2 + 2 * sham_replicates,
        "pattern_eval_fits": 0, "production_model_fits": 0, "strength_games": 0,
        "new_selfplay_games": 0, "frozen_reads": 0,
        "anchored_local_refit_authorized": passed,
        "production_model_authorized": False, "strength_gate_authorized": False,
        "promotion_authorized": False, "automatic_continuation": False,
        "next_stage": "anchored_local_refit_with_exact_outside_region_invariance" if passed else None,
    }
    models = {
        "schema": "jass.l3_curriculum_error_loss_first_crossfit_models.v1",
        "source_verdict": report["verdict"], "diagnostic_only": True,
        "authorized_for_anchored_local_refit_design": passed,
        "authorized_for_production": False, "models_by_training_pool": real["models"],
        "outside_selected_region_delta_exactly_zero": True,
    }
    return report, models


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--labels", type=Path, required=True)
    root.add_argument("--pairs", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    root.add_argument("--models", type=Path, required=True)
    root.add_argument("--bootstrap-samples", type=int, default=200000)
    root.add_argument("--bootstrap-seed", type=int, default=2026082345)
    root.add_argument("--sham-replicates", type=int, default=1000)
    root.add_argument("--sham-seed", type=int, default=2026082346)
    return root


def main() -> int:
    args = parser().parse_args()
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    pairs = json.loads(args.pairs.read_text(encoding="utf-8"))
    report, models = run(labels, pairs, labels_sha=sha256(args.labels), pairs_sha=sha256(args.pairs),
                         bootstrap_samples=args.bootstrap_samples, bootstrap_seed=args.bootstrap_seed,
                         sham_replicates=args.sham_replicates, sham_seed=args.sham_seed,
                         total_buckets=_total_buckets())
    _publish(args.report, report); _publish(args.models, models)
    print(json.dumps({"verdict": report["verdict"], "gates": report["gates"], "next_stage": report["next_stage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
