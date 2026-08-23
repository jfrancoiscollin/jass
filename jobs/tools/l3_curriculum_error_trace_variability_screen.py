#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Target-free search for a non-degenerate CURRICULUM trace uncertainty gate.

This diagnostic is allowed only after the fixed paired-margin screen failed
because both quantiles were zero.  It traverses discovery profiles only,
keeps the outer confirm profiles sealed, and compares a short predeclared set
of mechanistic trace-variability proxies.  No judged action is consumed.
"""
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
    from jobs.tools import l3_curriculum_search_error_atlas as source
except ModuleNotFoundError:  # pragma: no cover
    import l3_curriculum_error_action_ranker as ranker  # type: ignore
    import l3_curriculum_error_paired_coverage_screen as coverage  # type: ignore
    import l3_curriculum_search_error_atlas as source  # type: ignore


SCHEMA = "jass.l3_curriculum_error_trace_variability_screen.v1"
READY = "JASS_CURRICULUM_ERROR_TRACE_VARIABILITY_SCREEN_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_TRACE_VARIABILITY_NOT_ESTABLISHED"
CANDIDATE_PRIORITY = (
    "max_depth_score_spread_cp",
    "mean_depth_score_spread_cp",
    "image_score_disagreement_cp",
    "trace_presence_churn_rate",
    "paired_feature_disagreement_l2",
    "within_state_feature_dispersion_l2",
)
FEATURE_INDICES = tuple(
    index
    for index, name in enumerate(ranker.FEATURE_NAMES)
    if not name.startswith("rank_fraction_") and name not in {"capture", "baseline_d9"}
)


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


def _profile_values(profile: dict[str, Any]) -> dict[str, float]:
    original_maps = ranker._score_maps(profile, image=False)
    image_maps = ranker._score_maps(profile, image=True)
    if set(original_maps[9]) != set(image_maps[9]):
        raise ValueError("mapped exact-image legal action set drift")
    spans = []
    score_differences = []
    presence_missing = []
    for maps in (original_maps, image_maps):
        actions9 = sorted(maps[9])
        for depth in ranker.FEATURE_DEPTHS:
            values = list(maps[depth].values())
            spans.append(max(values) - min(values) if len(values) > 1 else 0.0)
        for action in actions9:
            presence_missing.extend(float(action not in maps[depth]) for depth in ranker.FEATURE_DEPTHS[:-1])
    for depth in ranker.FEATURE_DEPTHS:
        common = sorted(set(original_maps[depth]) & set(image_maps[depth]))
        score_differences.extend(abs(original_maps[depth][action] - image_maps[depth][action]) for action in common)

    original_features, _ = ranker._raw_features(profile, image=False)
    image_features, _ = ranker._raw_features(profile, image=True)
    actions = sorted(original_features)
    if actions != sorted(image_features):
        raise ValueError("mapped exact-image feature action set drift")
    feature_indices = list(FEATURE_INDICES)
    original = np.vstack([original_features[action][feature_indices] for action in actions])
    image = np.vstack([image_features[action][feature_indices] for action in actions])
    paired = (original + image) / 2.0
    centered = paired - paired.mean(axis=0, keepdims=True)
    return {
        "max_depth_score_spread_cp": float(max(spans, default=0.0)),
        "mean_depth_score_spread_cp": float(np.mean(spans)) if spans else 0.0,
        "image_score_disagreement_cp": float(np.mean(score_differences)) if score_differences else 0.0,
        "trace_presence_churn_rate": float(np.mean(presence_missing)) if presence_missing else 0.0,
        "paired_feature_disagreement_l2": float(np.sqrt(np.mean((original - image) ** 2))),
        "within_state_feature_dispersion_l2": float(np.sqrt(np.mean(centered ** 2))),
    }


def _values(rows: list[dict[str, Any]]) -> dict[str, dict[str, list[float]]]:
    output = {name: {"error": [], "control": []} for name in CANDIDATE_PRIORITY}
    for pair in rows:
        for role in ("error", "control"):
            values = _profile_values(pair[role])
            for name in CANDIDATE_PRIORITY:
                output[name][role].append(float(values[name]))
    return output


def _metrics(values: dict[str, list[float]], *, lower: float, upper: float) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for role, raw in values.items():
        array = np.asarray(raw, dtype=float)
        eligible = (array > lower) & (array <= upper)
        output[role] = {
            "profiles": int(array.size),
            "eligible": int(eligible.sum()),
            "eligible_rate": float(eligible.mean()) if array.size else 0.0,
            "quantiles": {
                str(q): float(np.quantile(array, q, method="higher"))
                for q in (0.1, 0.2, 0.4, 0.6, 0.8, 0.9)
            } if array.size else {},
            "nonzero_rate": float(np.mean(np.abs(array) > 1e-12)) if array.size else 0.0,
        }
    return output


def run(pairs: dict[str, Any], failed_coverage: dict[str, Any]) -> dict[str, Any]:
    if pairs.get("schema") != source.SCHEMA_PAIRS or pairs.get("matching_passed") is not True:
        raise ValueError("trace diagnostic requires passed profile matching")
    if failed_coverage.get("schema") != coverage.SCHEMA or failed_coverage.get("verdict") != coverage.NOT_ESTABLISHED:
        raise ValueError("trace diagnostic requires the failed fixed margin screen")
    failed_gate = failed_coverage.get("fixed_gate", {})
    if float(failed_gate.get("lower_margin_cp", -1.0)) != 0.0 or float(failed_gate.get("upper_margin_cp", -1.0)) != 0.0:
        raise ValueError("trace diagnostic only follows the certified zero-width margin failure")
    for key in ("exact_action_value_reads", "outer_confirm_action_value_reads", "diagnostic_fits", "strength_games", "frozen_reads"):
        if int(failed_coverage.get(key, -1)) != 0:
            raise ValueError(f"failed coverage forbidden counter drift: {key}")

    all_rows = list(pairs.get("pairs", []))
    discovery = [row for row in all_rows if row.get("split") == "discovery"]
    if len(discovery) != int(pairs.get("pairs_by_split", {}).get("discovery", -1)):
        raise ValueError("discovery pair count drift")
    forbidden = coverage._forbidden_keys(discovery)
    if forbidden:
        raise ValueError(f"trace diagnostic input contains action targets: {sorted(forbidden)}")
    fit, audit, split = coverage._split(discovery, seed=coverage.SPLIT_SEED)
    fit_values, audit_values = _values(fit), _values(audit)
    fit_ids, audit_ids = coverage._identity_sets(fit), coverage._identity_sets(audit)
    overlap = {key: len(fit_ids[key] & audit_ids[key]) for key in fit_ids}

    candidates = []
    for name in CANDIDATE_PRIORITY:
        combined = fit_values[name]["error"] + fit_values[name]["control"]
        lower = coverage._quantile(combined, coverage.LOWER_QUANTILE)
        upper = coverage._quantile(combined, coverage.UPPER_QUANTILE)
        fit_metrics = _metrics(fit_values[name], lower=lower, upper=upper)
        audit_metrics = _metrics(audit_values[name], lower=lower, upper=upper)
        error, control = audit_metrics["error"], audit_metrics["control"]
        gates = {
            "quantile_band_strictly_ordered": np.isfinite(lower) and np.isfinite(upper) and lower < upper,
            "error_audit_eligible_at_least_8": int(error["eligible"]) >= coverage.MIN_AUDIT_ELIGIBLE_PER_ROLE,
            "control_audit_eligible_at_least_8": int(control["eligible"]) >= coverage.MIN_AUDIT_ELIGIBLE_PER_ROLE,
            "error_audit_coverage_0_20_to_0_65": coverage.MIN_AUDIT_RATE <= float(error["eligible_rate"]) <= coverage.MAX_AUDIT_RATE,
            "control_audit_coverage_0_20_to_0_65": coverage.MIN_AUDIT_RATE <= float(control["eligible_rate"]) <= coverage.MAX_AUDIT_RATE,
            "audit_role_coverage_gap_at_most_0_20": abs(float(error["eligible_rate"]) - float(control["eligible_rate"])) <= coverage.MAX_ROLE_RATE_GAP,
        }
        candidates.append({
            "name": name,
            "priority": CANDIDATE_PRIORITY.index(name),
            "lower_open": lower,
            "upper_closed": upper,
            "gate_fit": fit_metrics,
            "feature_audit": audit_metrics,
            "gates": gates,
            "passed": all(gates.values()),
            "failed_gates": sorted(key for key, value in gates.items() if not value),
        })
    passing = [row for row in candidates if row["passed"]]
    selected = passing[0] if passing else None
    global_gates = {
        "discovery_pairs_at_least_96": len(discovery) >= coverage.MIN_DISCOVERY_PAIRS,
        "gate_fit_pairs_at_least_64": len(fit) >= coverage.MIN_FIT_PAIRS,
        "feature_audit_pairs_at_least_24": len(audit) >= coverage.MIN_AUDIT_PAIRS,
        "opening_game_state_overlap_zero": not any(overlap.values()),
        "action_targets_absent": not forbidden,
        "outer_confirm_unexamined": True,
        "at_least_one_predeclared_proxy_passed": selected is not None,
    }
    passed = all(global_gates.values())
    return {
        "schema": SCHEMA,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        "source_failure": "PAIRED_IMAGE_D9_ACTION_SCORE_MARGIN_IDENTICALLY_ZERO",
        "candidate_priority": list(CANDIDATE_PRIORITY),
        "excluded_artifactual_features": [ranker.FEATURE_NAMES[index] for index in range(len(ranker.FEATURE_NAMES)) if index not in FEATURE_INDICES],
        "split": split,
        "split_overlap": overlap,
        "candidates": candidates,
        "selected_proxy": selected,
        "global_gates": global_gates,
        "failed_global_gates": sorted(key for key, value in global_gates.items() if not value),
        "preregistration_authorized": passed,
        "outer_confirm_profile_rows_examined": 0,
        "outer_confirm_action_value_reads": 0,
        "exact_action_value_reads": 0,
        "diagnostic_fits": 0,
        "pattern_eval_fits": 0,
        "strength_games": 0,
        "new_selfplay_games": 0,
        "frozen_reads": 0,
        "promotion_authorized": False,
        "automatic_continuation": False,
        "next_stage": "single_proxy_preregistration" if passed else None,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--pairs", type=Path, required=True)
    root.add_argument("--failed-coverage", type=Path, required=True)
    root.add_argument("--coverage-job", required=True)
    root.add_argument("--coverage-attempt", required=True)
    root.add_argument("--coverage-code", required=True)
    root.add_argument("--report", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    report = run(json.loads(args.pairs.read_text()), json.loads(args.failed_coverage.read_text()))
    report["coverage_job"] = args.coverage_job
    report["coverage_attempt"] = args.coverage_attempt
    report["coverage_code_sha"] = args.coverage_code
    report["pairs_sha256"] = _sha256(args.pairs)
    report["failed_coverage_sha256"] = _sha256(args.failed_coverage)
    _publish(args.report, report)
    print(json.dumps({"verdict": report["verdict"], "selected_proxy": report["selected_proxy"] and report["selected_proxy"]["name"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
