#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Target-free coverage screen for a paired-image local residual gate.

The screen consumes matched root *profiles* only.  It never consumes exact
action judgements.  Discovery pairs are split atomically by opening, source
game and exact state.  A single relative uncertainty band (Q20, Q60] is fixed
on the fit side and its support is checked once on the feature-audit side.
The outer-confirm profiles and every action-value payload stay unexamined.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    from jobs.tools import l3_curriculum_error_action_ranker as ranker
    from jobs.tools import l3_curriculum_search_error_atlas as source
except ModuleNotFoundError:  # pragma: no cover - direct CPX invocation
    import l3_curriculum_error_action_ranker as ranker  # type: ignore
    import l3_curriculum_search_error_atlas as source  # type: ignore


SCHEMA = "jass.l3_curriculum_error_paired_coverage_screen.v1"
READY = "JASS_CURRICULUM_ERROR_PAIRED_COVERAGE_SCREEN_READY"
NOT_ESTABLISHED = "JASS_CURRICULUM_ERROR_PAIRED_COVERAGE_SCREEN_NOT_ESTABLISHED"
SPLIT_SEED = 2026082250
LOWER_QUANTILE = 0.20
UPPER_QUANTILE = 0.60
MIN_DISCOVERY_PAIRS = 96
MIN_FIT_PAIRS = 64
MIN_AUDIT_PAIRS = 24
MIN_AUDIT_ELIGIBLE_PER_ROLE = 8
MIN_AUDIT_RATE = 0.20
MAX_AUDIT_RATE = 0.65
MAX_ROLE_RATE_GAP = 0.20
FORBIDDEN_TARGET_KEYS = {
    "action_values",
    "exact_teacher_action",
    "judged",
    "child_original",
    "child_exact_image",
    "root_cp",
}


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _forbidden_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key) in FORBIDDEN_TARGET_KEYS:
                found.add(str(key))
            found.update(_forbidden_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_forbidden_keys(nested))
    return found


def _source(profile: dict[str, Any]) -> dict[str, Any]:
    row = profile.get("source")
    if not isinstance(row, dict):
        raise ValueError("paired profile lacks source identity")
    for key in ("opening_id", "game_uid", "exact_state_key"):
        if row.get(key) in (None, ""):
            raise ValueError(f"paired profile lacks {key}")
    return row


def _components(rows: list[dict[str, Any]]) -> list[list[int]]:
    parent = {int(row["pair_id"]): int(row["pair_id"]) for row in rows}

    def find(value: int) -> int:
        root = value
        while parent[root] != root:
            root = parent[root]
        while parent[value] != value:
            nxt = parent[value]
            parent[value] = root
            value = nxt
        return root

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            low, high = sorted((a, b))
            parent[high] = low

    owners: dict[tuple[str, str], int] = {}
    for pair in rows:
        pair_id = int(pair["pair_id"])
        for role in ("error", "control"):
            identity = _source(pair[role])
            for kind, key in (
                ("opening", "opening_id"),
                ("game", "game_uid"),
                ("state", "exact_state_key"),
            ):
                token = (kind, str(identity[key]))
                previous = owners.setdefault(token, pair_id)
                union(previous, pair_id)
    grouped: dict[int, list[int]] = defaultdict(list)
    for pair_id in parent:
        grouped[find(pair_id)].append(pair_id)
    return sorted((sorted(members) for members in grouped.values()), key=tuple)


def _split(
    rows: list[dict[str, Any]], *, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    audit: set[int] = set()
    manifest = []
    for members in _components(rows):
        digest = hashlib.sha256(f"{seed}|{','.join(map(str, members))}".encode()).digest()
        owner = "feature_audit" if int.from_bytes(digest[:8], "big") % 4 == 0 else "gate_fit"
        if owner == "feature_audit":
            audit.update(members)
        manifest.append({"members": members, "split": owner})
    fit = [row for row in rows if int(row["pair_id"]) not in audit]
    holdout = [row for row in rows if int(row["pair_id"]) in audit]
    return fit, holdout, {
        "method": "paired_opening_game_exact_state_components_sha256_mod4",
        "seed": seed,
        "components": len(manifest),
        "gate_fit_pairs": len(fit),
        "feature_audit_pairs": len(holdout),
        "manifest_sha256": hashlib.sha256(_canonical(manifest)).hexdigest(),
    }


def _identity_sets(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    values = {key: set() for key in ("opening_id", "game_uid", "exact_state_key")}
    for pair in rows:
        for role in ("error", "control"):
            identity = _source(pair[role])
            for key in values:
                values[key].add(str(identity[key]))
    return values


def _margin(scores: dict[str, float]) -> float:
    ordered = sorted(scores.values(), reverse=True)
    return ordered[0] - ordered[1] if len(ordered) > 1 else float("inf")


def _profile(profile: dict[str, Any]) -> dict[str, Any]:
    original = ranker._score_maps(profile, image=False)[9]
    image = ranker._score_maps(profile, image=True)[9]
    if set(original) != set(image):
        raise ValueError("paired-image mapped legal action set drift")
    original_best = max(original, key=lambda action: (original[action], action))
    image_best = max(image, key=lambda action: (image[action], action))
    original_margin = _margin(original)
    image_margin = _margin(image)
    return {
        "original_margin_cp": original_margin,
        "exact_image_margin_cp": image_margin,
        "dual_max_margin_cp": max(original_margin, image_margin),
        "best_action_agreement": original_best == image_best,
        "legal_actions": len(original),
    }


def _quantile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("coverage quantile has zero profiles")
    return float(np.quantile(np.asarray(values, dtype=float), quantile, method="higher"))


def _metrics(
    rows: list[dict[str, Any]], *, lower: float, upper: float
) -> dict[str, Any]:
    by_role: dict[str, list[dict[str, Any]]] = {"error": [], "control": []}
    for pair in rows:
        for role in by_role:
            by_role[role].append(_profile(pair[role]))
    output: dict[str, Any] = {"pairs": len(rows), "roles": {}}
    for role, profiles in by_role.items():
        eligible = [
            lower < float(row["dual_max_margin_cp"]) <= upper for row in profiles
        ]
        output["roles"][role] = {
            "profiles": len(profiles),
            "eligible": sum(eligible),
            "eligible_rate": float(np.mean(eligible)) if eligible else 0.0,
            "best_action_agreement_rate": float(
                np.mean([bool(row["best_action_agreement"]) for row in profiles])
            ) if profiles else 0.0,
            "dual_max_margin_quantiles_cp": {
                str(q): _quantile(
                    [float(row["dual_max_margin_cp"]) for row in profiles], q
                )
                for q in (0.1, 0.2, 0.4, 0.6, 0.8, 0.9)
            },
        }
    return output


def run(pairs: dict[str, Any]) -> dict[str, Any]:
    if pairs.get("schema") != source.SCHEMA_PAIRS or pairs.get("matching_passed") is not True:
        raise ValueError("coverage screen requires passed profile-only matching")
    all_rows = list(pairs.get("pairs", []))
    discovery = [row for row in all_rows if row.get("split") == "discovery"]
    if len(discovery) != int(pairs.get("pairs_by_split", {}).get("discovery", -1)):
        raise ValueError("discovery pair count drift")
    if any(row.get("split") not in {"discovery", "confirm"} for row in all_rows):
        raise ValueError("unsealed pair split")
    # Only discovery rows are traversed below.  Confirm pair dictionaries are
    # counted from their sealed split metadata but their profile payloads are
    # never recursively inspected.
    forbidden = _forbidden_keys(discovery)
    if forbidden:
        raise ValueError(f"coverage input contains action targets: {sorted(forbidden)}")
    fit, audit, split = _split(discovery, seed=SPLIT_SEED)
    fit_values = [
        float(_profile(pair[role])["dual_max_margin_cp"])
        for pair in fit
        for role in ("error", "control")
    ]
    lower = _quantile(fit_values, LOWER_QUANTILE)
    upper = _quantile(fit_values, UPPER_QUANTILE)
    fit_metrics = _metrics(fit, lower=lower, upper=upper)
    audit_metrics = _metrics(audit, lower=lower, upper=upper)
    fit_ids, audit_ids = _identity_sets(fit), _identity_sets(audit)
    overlap = {key: len(fit_ids[key] & audit_ids[key]) for key in fit_ids}
    error_audit = audit_metrics["roles"]["error"]
    control_audit = audit_metrics["roles"]["control"]
    gates = {
        "matching_passed": pairs.get("matching_passed") is True,
        "discovery_pairs_at_least_96": len(discovery) >= MIN_DISCOVERY_PAIRS,
        "gate_fit_pairs_at_least_64": len(fit) >= MIN_FIT_PAIRS,
        "feature_audit_pairs_at_least_24": len(audit) >= MIN_AUDIT_PAIRS,
        "quantile_band_strictly_ordered": np.isfinite(lower) and np.isfinite(upper) and lower < upper,
        "error_audit_eligible_at_least_8": int(error_audit["eligible"]) >= MIN_AUDIT_ELIGIBLE_PER_ROLE,
        "control_audit_eligible_at_least_8": int(control_audit["eligible"]) >= MIN_AUDIT_ELIGIBLE_PER_ROLE,
        "error_audit_coverage_0_20_to_0_65": MIN_AUDIT_RATE <= float(error_audit["eligible_rate"]) <= MAX_AUDIT_RATE,
        "control_audit_coverage_0_20_to_0_65": MIN_AUDIT_RATE <= float(control_audit["eligible_rate"]) <= MAX_AUDIT_RATE,
        "audit_role_coverage_gap_at_most_0_20": abs(float(error_audit["eligible_rate"]) - float(control_audit["eligible_rate"])) <= MAX_ROLE_RATE_GAP,
        "opening_game_state_overlap_zero": not any(overlap.values()),
        "action_targets_absent": not forbidden,
        "outer_confirm_action_values_unread": True,
    }
    passed = all(gates.values())
    return {
        "schema": SCHEMA,
        "verdict": READY if passed else NOT_ESTABLISHED,
        "passed": passed,
        "source_matching": {
            "matched_pairs": pairs.get("matched_pairs"),
            "pairs_by_split": pairs.get("pairs_by_split"),
            "opening_overlap": pairs.get("opening_overlap"),
            "maximum_cardinality_matching": pairs.get("maximum_cardinality_matching"),
        },
        "feature_contract": {
            "fields_accessed": [
                "pair_id",
                "split",
                "profile.source.opening_id",
                "profile.source.game_uid",
                "profile.source.exact_state_key",
                "profile.trace.original.depths.6_to_9.moves.action_score",
                "profile.trace.exact_image.depths.6_to_9.moves.action_score",
            ],
            "action_target_keys_forbidden": sorted(FORBIDDEN_TARGET_KEYS),
            "action_targets_present": False,
            "uses_exact_action_judgements": False,
        },
        "split": split,
        "split_overlap": overlap,
        "fixed_gate": {
            "family": "paired_image_dual_max_margin_relative_uncertainty_band",
            "fit_population": "discovery_gate_fit_error_and_control_profiles_pair_equal",
            "lower_quantile_open": LOWER_QUANTILE,
            "upper_quantile_closed": UPPER_QUANTILE,
            "lower_margin_cp": lower,
            "upper_margin_cp": upper,
            "eligibility": "lower_margin_cp < max(original_margin_cp, exact_image_margin_cp) <= upper_margin_cp",
            "outside_gate": "byte_identical_CURRICULUM",
        },
        "gate_fit_metrics": fit_metrics,
        "feature_audit_metrics": audit_metrics,
        "gates": gates,
        "failed_gates": sorted(key for key, value in gates.items() if not value),
        "preregistration_authorized": passed,
        "residual_fit_authorized": False,
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
        "next_stage": "paired_coverage_preregistration" if passed else None,
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--pairs", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    pairs = json.loads(args.pairs.read_text())
    report = run(pairs)
    _publish(args.report, report)
    print(json.dumps({"verdict": report["verdict"], "failed_gates": report["failed_gates"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
