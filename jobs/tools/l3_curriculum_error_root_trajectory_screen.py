#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Discovery-only screen for zero-node root-score trajectory correction.

The PatternEval residual route is closed by 1486/1489.  This screen leaves the
CURRICULUM scalar and the search tree unchanged.  It asks whether a bounded
extrapolation of each root action's score between completed depths 8 and 9 can
repair the final root ranking.  The rule uses no additional search nodes and
abstains outside a fixed uncertainty band.

Only the already consumed experiment's outer-discovery rows are available to
this exploratory screen.  Its outer-confirm rows are authenticated for source
completeness but never dereferenced for selection or evaluation.  A positive
inner holdout can authorize only an entirely fresh confirmation campaign.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np

try:
    from jobs.tools import l3_curriculum_error_learning as learning
    from jobs.tools import l3_curriculum_search_error_atlas as source
except ModuleNotFoundError:  # pragma: no cover
    import l3_curriculum_error_learning as learning  # type: ignore
    import l3_curriculum_search_error_atlas as source  # type: ignore


SCHEMA = "jass.l3_curriculum_error_root_trajectory_screen.v1"
HYPOTHESIS_SCHEMA = "jass.l3_curriculum_error_root_trajectory_hypothesis.v1"
BETAS = (0.25, 0.5, 1.0)
MARGINS_CP = (20.0, 50.0, 100.0, 1_000_000.0)
SLOPE_CLIP_CP = 100.0


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish(path: Path, value: object) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp." + hashlib.sha256(_canonical(value)).hexdigest()[:12])
    temporary.write_bytes(_canonical(value))
    temporary.replace(path)


def _bootstrap(values: Iterable[float], *, samples: int, seed: int) -> dict[str, Any]:
    array = np.asarray(list(values), dtype=np.float64)
    if not len(array):
        return {"n": 0, "mean": None, "ci95": [None, None], "probability_positive": None}
    rng = np.random.default_rng(seed)
    means = np.empty(samples, dtype=np.float64)
    for start in range(0, samples, 2048):
        stop = min(samples, start + 2048)
        indices = rng.integers(0, len(array), size=(stop - start, len(array)))
        means[start:stop] = array[indices].mean(axis=1)
    low, high = np.quantile(means, (0.025, 0.975))
    return {
        "n": len(array), "mean": float(array.mean()),
        "ci95": [float(low), float(high)],
        "probability_positive": float(np.mean(means > 0.0)),
    }


def _sign_flip(values: list[float], *, samples: int, seed: int) -> float:
    if not values:
        return 1.0
    array = np.asarray(values, dtype=np.float64)
    observed = float(array.mean())
    rng = np.random.default_rng(seed)
    extreme = 1
    done = 0
    while done < samples:
        size = min(2048, samples - done)
        signs = rng.choice(np.asarray((-1.0, 1.0)), size=(size, len(array)))
        extreme += int(np.count_nonzero((signs * array).mean(axis=1) >= observed))
        done += size
    return extreme / (samples + 1)


def _load(
    pairs: dict[str, Any], atlas_shards: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if pairs.get("schema") != source.SCHEMA_PAIRS or pairs.get("matching_passed") is not True:
        raise ValueError("1476 matched-pair certificate drift")
    if pairs.get("matched_pairs") != 353 or pairs.get("pairs_by_split") != {"confirm": 158, "discovery": 195}:
        raise ValueError("1476 matched-pair cardinality drift")
    expected = len(atlas_shards)
    if expected != 16 or {int(row.get("shard", -1)) for row in atlas_shards} != set(range(expected)):
        raise ValueError("1476 atlas shards are incomplete")
    if any(row.get("schema") != source.SCHEMA_ATLAS_SHARD for row in atlas_shards):
        raise ValueError("1476 atlas shard schema drift")
    if any(int(row.get("nshards", -1)) != expected or int(row.get("max_pairs", -1)) != 0 for row in atlas_shards):
        raise ValueError("1476 atlas shard execution drift")
    digest = hashlib.sha256(_canonical(pairs)).hexdigest()
    if any(row.get("pairs_sha256") != digest for row in atlas_shards):
        raise ValueError("1476 atlas/pairs hash drift")
    identities = {}
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        values = {str(row.get(key, "")) for row in atlas_shards}
        if len(values) != 1 or not next(iter(values)):
            raise ValueError(f"1476 {key} identity drift")
        identities[key] = next(iter(values))

    atlas_rows = [item for shard in atlas_shards for item in shard["rows"]]
    atlas_rows.sort(key=lambda row: int(row["pair_id"]))
    matched_rows = sorted(pairs["pairs"], key=lambda row: int(row["pair_id"]))
    expected_ids = list(range(353))
    if [int(row["pair_id"]) for row in atlas_rows] != expected_ids:
        raise ValueError("1476 atlas pair coverage drift")
    if [int(row["pair_id"]) for row in matched_rows] != expected_ids:
        raise ValueError("1476 matched pair coverage drift")

    # Filter on pair metadata before reading either decision.  The 158 outer
    # confirm decisions remain consumed and unavailable to all calculations.
    matched_discovery = {
        int(row["pair_id"]): row for row in matched_rows if row.get("split") == "discovery"
    }
    atlas_discovery = {
        int(row["pair_id"]): row for row in atlas_rows if row.get("split") == "discovery"
    }
    if set(matched_discovery) != set(atlas_discovery) or len(matched_discovery) != 195:
        raise ValueError("1476 outer-discovery join drift")
    rows = []
    reclassified = 0
    for pair_id in sorted(matched_discovery):
        matched, judged = matched_discovery[pair_id], atlas_discovery[pair_id]
        if float(judged["error"]["historical_regret_cp"]) < 50.0:
            reclassified += 1
            continue
        rows.append({
            "pair_id": pair_id,
            "error": {"profile": matched["error"], "judged": judged["error"]},
            "control": {"profile": matched["control"], "judged": judged["control"]},
        })
    if len(rows) != 160 or reclassified != 35:
        raise ValueError("1476 discovery exact-error partition drift")
    return rows, identities


def _inner_split(
    rows: list[dict[str, Any]], *, seed: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
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
            src = pair[role]["profile"]["source"]
            for kind, value in (("opening", src["opening_id"]), ("state", src["exact_state_key"])):
                key = (kind, str(value))
                previous = owners.setdefault(key, pair_id)
                union(previous, pair_id)
    components: dict[int, list[int]] = defaultdict(list)
    for pair_id in parent:
        components[find(pair_id)].append(pair_id)
    validation_ids: set[int] = set()
    manifest = []
    for members in sorted((sorted(value) for value in components.values()), key=tuple):
        digest = hashlib.sha256(f"{seed}|{','.join(map(str, members))}".encode()).digest()
        split = "validation" if int.from_bytes(digest[:8], "big") % 4 == 0 else "fit"
        if split == "validation":
            validation_ids.update(members)
        manifest.append({"members": members, "split": split})
    fit = [row for row in rows if int(row["pair_id"]) not in validation_ids]
    validation = [row for row in rows if int(row["pair_id"]) in validation_ids]
    if len(fit) < 96 or len(validation) < 24:
        raise ValueError("inner component split lacks preregistered support")
    return fit, validation, {
        "method": "paired_opening_exact_state_components_sha256_mod4",
        "seed": seed, "components": len(components), "fit_pairs": len(fit),
        "validation_pairs": len(validation), "overlap": 0,
        "manifest_sha256": hashlib.sha256(_canonical(manifest)).hexdigest(),
    }


def _scores(profile: dict[str, Any], *, depth: int, image: bool) -> dict[str, float]:
    orientation = "exact_image" if image else "original"
    rows = profile["trace"][orientation]["depths"][str(depth)]["moves"]
    result: dict[str, float] = {}
    for row in rows:
        action = str(row["action"])
        if image:
            action = source._mapped_image_action(action)
        if action in result:
            raise ValueError("duplicate root action after exact-image mapping")
        result[action] = float(row["score"])
    if not result:
        raise ValueError("empty root score vector")
    return result


def _rank(scores: dict[str, float]) -> list[str]:
    return sorted(scores, key=lambda action: (scores[action], action), reverse=True)


def _choice(
    profile: dict[str, Any], *, beta: float, margin_cp: float, image: bool
) -> dict[str, Any]:
    depth8, depth9 = _scores(profile, depth=8, image=image), _scores(profile, depth=9, image=image)
    ranked = _rank(depth9)
    baseline = ranked[0]
    margin = depth9[ranked[0]] - depth9[ranked[1]] if len(ranked) > 1 else float("inf")
    extrapolated = {}
    missing = 0
    for action, score9 in depth9.items():
        if action in depth8:
            slope = max(-SLOPE_CLIP_CP, min(SLOPE_CLIP_CP, score9 - depth8[action]))
        else:
            slope = 0.0
            missing += 1
        extrapolated[action] = score9 + beta * slope
    proposed = _rank(extrapolated)[0]
    chosen = proposed if margin <= margin_cp else baseline
    return {
        "baseline": baseline, "proposed": proposed, "chosen": chosen,
        "baseline_margin_cp": margin, "changed": chosen != baseline,
        "depth8_missing_actions": missing, "depth9_actions": len(depth9),
    }


def _value(judged: dict[str, Any], action: str) -> float:
    values = judged["action_values"]
    if action not in values:
        raise ValueError(f"root trajectory selected unjudged action {action}")
    return float(values[action]["root_cp"])


def _decision(
    row: dict[str, Any], *, beta: float, margin_cp: float
) -> dict[str, Any]:
    profile, judged = row["profile"], row["judged"]
    original = _choice(profile, beta=beta, margin_cp=margin_cp, image=False)
    image = _choice(profile, beta=beta, margin_cp=margin_cp, image=True)
    teacher = str(judged["exact_teacher_action"])
    teacher_value = _value(judged, teacher)
    baseline_regrets = [
        teacher_value - _value(judged, original["baseline"]),
        teacher_value - _value(judged, image["baseline"]),
    ]
    chosen_regrets = [
        teacher_value - _value(judged, original["chosen"]),
        teacher_value - _value(judged, image["chosen"]),
    ]
    return {
        "baseline_mean_regret_cp": float(np.mean(baseline_regrets)),
        "candidate_mean_regret_cp": float(np.mean(chosen_regrets)),
        "improvement_cp": float(np.mean(baseline_regrets) - np.mean(chosen_regrets)),
        "baseline_error_50cp": float(np.mean([value >= 50.0 for value in baseline_regrets])),
        "candidate_error_50cp": float(np.mean([value >= 50.0 for value in chosen_regrets])),
        "baseline_teacher_hit": float(np.mean([
            original["baseline"] == teacher, image["baseline"] == teacher,
        ])),
        "candidate_teacher_hit": float(np.mean([
            original["chosen"] == teacher, image["chosen"] == teacher,
        ])),
        "baseline_exact_image_agreement": original["baseline"] == image["baseline"],
        "candidate_exact_image_agreement": original["chosen"] == image["chosen"],
        "changed_pair": original["changed"] or image["changed"],
        "changed_orientations": int(original["changed"]) + int(image["changed"]),
        "depth8_missing_actions": original["depth8_missing_actions"] + image["depth8_missing_actions"],
        "depth9_actions": original["depth9_actions"] + image["depth9_actions"],
    }


def _evaluate(
    rows: list[dict[str, Any]], *, beta: float, margin_cp: float,
    bootstrap_samples: int, bootstrap_seed: int,
) -> dict[str, Any]:
    decisions = []
    for pair in rows:
        decisions.append({
            "pair_id": int(pair["pair_id"]),
            "error": _decision(pair["error"], beta=beta, margin_cp=margin_cp),
            "control": _decision(pair["control"], beta=beta, margin_cp=margin_cp),
        })
    error = [row["error"]["improvement_cp"] for row in decisions]
    control = [row["control"]["improvement_cp"] for row in decisions]
    paired = [left - right for left, right in zip(error, control, strict=True)]
    error_rate = [
        row["error"]["baseline_error_50cp"] - row["error"]["candidate_error_50cp"]
        for row in decisions
    ]
    teacher_hit = [
        row["error"]["candidate_teacher_hit"] - row["error"]["baseline_teacher_hit"]
        for row in decisions
    ]
    orientations = sum(row[role]["depth9_actions"] for row in decisions for role in ("error", "control"))
    missing = sum(row[role]["depth8_missing_actions"] for row in decisions for role in ("error", "control"))
    rate = lambda role, key: float(np.mean([row[role][key] for row in decisions]))
    return {
        "pairs": len(rows),
        "error_improvement": _bootstrap(error, samples=bootstrap_samples, seed=bootstrap_seed),
        "control_improvement": _bootstrap(control, samples=bootstrap_samples, seed=bootstrap_seed + 1),
        "paired_error_minus_control": _bootstrap(paired, samples=bootstrap_samples, seed=bootstrap_seed + 2),
        "error_rate_reduction": _bootstrap(error_rate, samples=bootstrap_samples, seed=bootstrap_seed + 3),
        "teacher_hit_gain": _bootstrap(teacher_hit, samples=bootstrap_samples, seed=bootstrap_seed + 4),
        "paired_sign_flip_pvalue": _sign_flip(
            paired, samples=min(bootstrap_samples, 10_000), seed=bootstrap_seed + 5
        ),
        "error_changed_pairs": sum(row["error"]["changed_pair"] for row in decisions),
        "control_changed_pairs": sum(row["control"]["changed_pair"] for row in decisions),
        "error_changed_orientations": sum(row["error"]["changed_orientations"] for row in decisions),
        "control_changed_orientations": sum(row["control"]["changed_orientations"] for row in decisions),
        "error_baseline_exact_image_agreement": rate("error", "baseline_exact_image_agreement"),
        "error_candidate_exact_image_agreement": rate("error", "candidate_exact_image_agreement"),
        "control_baseline_exact_image_agreement": rate("control", "baseline_exact_image_agreement"),
        "control_candidate_exact_image_agreement": rate("control", "candidate_exact_image_agreement"),
        "depth8_missing_action_fraction": missing / orientations if orientations else 1.0,
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    pairs = json.loads(args.pairs.read_text())
    shards = [json.loads(path.read_text()) for path in args.atlas_shard]
    rows, identities = _load(pairs, shards)
    fit_rows, validation_rows, split = _inner_split(rows, seed=args.split_seed)
    candidates = []
    for index, (beta, margin_cp) in enumerate(
        (beta, margin) for beta in BETAS for margin in MARGINS_CP
    ):
        metrics = _evaluate(
            fit_rows, beta=beta, margin_cp=margin_cp,
            bootstrap_samples=args.bootstrap_samples,
            bootstrap_seed=args.bootstrap_seed + index * 10,
        )
        gates = {
            "error_probability_positive_ge_0_90": metrics["error_improvement"]["probability_positive"] >= 0.90,
            "paired_probability_positive_ge_0_90": metrics["paired_error_minus_control"]["probability_positive"] >= 0.90,
            "controls_not_harmed_mean": metrics["control_improvement"]["mean"] >= -2.0,
            "at_least_8_error_pairs_changed": metrics["error_changed_pairs"] >= 8,
            "candidate_symmetry_ge_0_70": metrics["error_candidate_exact_image_agreement"] >= 0.70,
            "candidate_symmetry_not_worse_than_baseline": (
                metrics["error_candidate_exact_image_agreement"]
                >= metrics["error_baseline_exact_image_agreement"] - 0.02
            ),
            "depth8_missing_action_fraction_le_0_01": metrics["depth8_missing_action_fraction"] <= 0.01,
        }
        score = (
            float(metrics["paired_error_minus_control"]["mean"])
            + 0.5 * float(metrics["error_improvement"]["mean"])
            + 10.0 * float(metrics["teacher_hit_gain"]["mean"])
        )
        candidates.append({
            "beta": beta, "margin_cp": margin_cp,
            "margin_label": "always" if margin_cp >= 1_000_000 else str(int(margin_cp)),
            "fit": metrics, "fit_gates": gates, "fit_passed": all(gates.values()),
            "fit_selection_score": score,
        })
    passing = [row for row in candidates if row["fit_passed"]]
    passing.sort(key=lambda row: (-row["fit_selection_score"], row["beta"], row["margin_cp"]))
    selected = passing[0] if passing else None
    validation = None
    validation_gates: dict[str, bool] = {}
    if selected:
        validation = _evaluate(
            validation_rows, beta=float(selected["beta"]), margin_cp=float(selected["margin_cp"]),
            bootstrap_samples=args.bootstrap_samples,
            bootstrap_seed=args.bootstrap_seed + 10_000,
        )
        validation_gates = {
            "at_least_24_validation_pairs": validation["pairs"] >= 24,
            "error_improvement_ci95_positive": validation["error_improvement"]["ci95"][0] > 0.0,
            "paired_improvement_ci95_positive": validation["paired_error_minus_control"]["ci95"][0] > 0.0,
            "controls_not_harmed_ci95": validation["control_improvement"]["ci95"][0] >= -2.0,
            "paired_sign_flip_p_le_0_025": validation["paired_sign_flip_pvalue"] <= 0.025,
            "at_least_4_validation_error_pairs_changed": validation["error_changed_pairs"] >= 4,
            "candidate_symmetry_ge_0_70": validation["error_candidate_exact_image_agreement"] >= 0.70,
            "candidate_symmetry_not_worse_than_baseline": (
                validation["error_candidate_exact_image_agreement"]
                >= validation["error_baseline_exact_image_agreement"] - 0.02
            ),
            "depth8_missing_action_fraction_le_0_01": validation["depth8_missing_action_fraction"] <= 0.01,
        }
    passed = selected is not None and all(validation_gates.values())
    report = {
        "schema": SCHEMA,
        "verdict": (
            "JASS_CURRICULUM_ERROR_ROOT_TRAJECTORY_HYPOTHESIS_READY"
            if passed else "JASS_CURRICULUM_ERROR_ROOT_TRAJECTORY_HYPOTHESIS_NOT_ESTABLISHED"
        ),
        "passed": passed, **identities,
        "source_pairs_sha256": sha256(args.pairs),
        "source_atlas_shards": [{"path": str(path), "sha256": sha256(path)} for path in args.atlas_shard],
        "outer_discovery_pairs": 195, "informative_discovery_pairs": 160,
        "outer_confirm_pairs_read_for_selection_or_evaluation": 0,
        "outer_confirm_is_consumed_and_forbidden": True,
        "inner_split": split,
        "protocol": {
            "baseline": "Q00_root_depth9_action_scores",
            "signal": "per_action_clipped_score_slope_depth8_to_depth9",
            "slope_clip_cp": SLOPE_CLIP_CP,
            "betas": list(BETAS), "uncertainty_margins_cp": list(MARGINS_CP),
            "additional_search_nodes": 0, "curriculum_scalar_unchanged": True,
            "candidate_selection": "inner_fit_only",
            "candidate_evaluation": "single_selected_candidate_on_inner_validation",
        },
        "candidate_results": candidates,
        "selected_candidate": (
            {"beta": selected["beta"], "margin_cp": selected["margin_cp"],
             "margin_label": selected["margin_label"], "fit": selected["fit"],
             "fit_gates": selected["fit_gates"]} if selected else None
        ),
        "validation": validation, "validation_gates": validation_gates,
        "failed_validation_gates": [key for key, value in validation_gates.items() if not value],
        "fresh_campaign_authorized": passed, "production_rule_authorized": False,
        "pattern_eval_fits": 0, "production_model_fits": 0,
        "strength_games": 0, "selfplay_games": 0, "frozen_reads": 0,
        "promotion_authorized": False, "automatic_continuation": False,
        "next_stage": "fresh_root_trajectory_confirmation" if passed else None,
    }
    hypothesis = {
        "schema": HYPOTHESIS_SCHEMA, "authorized": passed,
        "source_screen_verdict": report["verdict"],
        "rule": ({
            "beta": selected["beta"], "margin_cp": selected["margin_cp"],
            "slope_clip_cp": SLOPE_CLIP_CP,
            "uses_last_two_completed_depths": True,
            "additional_search_nodes": 0,
        } if passed and selected else None),
        "fresh_confirmation_contract": {
            "reuse_1476_outer_confirm": False,
            "opening_and_exact_state_overlap": 0,
            "same_champion_teacher_judge_and_search_params": True,
            "min_informative_error_pairs": 96,
            "error_improvement_ci95_low_gt_0": True,
            "paired_error_minus_control_ci95_low_gt_0": True,
            "control_improvement_ci95_low_ge": -2.0,
            "paired_sign_flip_p_le": 0.025,
            "candidate_symmetry_ge": 0.70,
        },
        "production_rule_authorized": False, "promotion_authorized": False,
    }
    return report, hypothesis


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--pairs", type=Path, required=True)
    root.add_argument("--atlas-shard", action="append", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    root.add_argument("--hypothesis", type=Path, required=True)
    root.add_argument("--split-seed", type=int, default=2026082228)
    root.add_argument("--bootstrap-seed", type=int, default=2026082229)
    root.add_argument("--bootstrap-samples", type=int, default=10_000)
    return root


def main() -> int:
    args = parser().parse_args()
    report, hypothesis = run(args)
    _publish(args.report, report)
    _publish(args.hypothesis, hypothesis)
    print(json.dumps({
        "verdict": report["verdict"],
        "selected_candidate": report["selected_candidate"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
