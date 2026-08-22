#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Discovery-only screen for a conditional CURRICULUM error hypothesis.

The global 1486 residual direction failed its sealed confirmation.  This tool
does not revisit that confirmation and cannot authorize a fit.  It uses only
the original discovery population, keeps matched pairs and exact-state opening
components atomic, and asks whether one preregistered phase/king/tactical
population contains a direction worth confirming on an entirely fresh loss
campaign.
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

try:
    from jobs.tools import l3_curriculum_error_residual_atlas as residual
except ModuleNotFoundError:  # pragma: no cover
    import l3_curriculum_error_residual_atlas as residual  # type: ignore


SCHEMA = "jass.l3_curriculum_error_conditional_discovery_screen.v1"
HYPOTHESIS_SCHEMA = "jass.l3_curriculum_error_conditional_hypothesis.v1"


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


def _vector(row: dict[str, Any]) -> dict[int, float]:
    result = {int(item["coordinate"]): float(item["value"]) for item in row["gradient"]}
    if len(result) != len(row["gradient"]):
        raise ValueError("duplicate gradient coordinate")
    return result


def _dot(vector: dict[int, float], direction: dict[int, float]) -> float:
    return sum(value * direction.get(key, 0.0) for key, value in vector.items())


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
    return {"n": len(array), "mean": float(array.mean()), "ci95": [float(low), float(high)],
            "probability_positive": float(np.mean(means > 0.0))}


def _sign_flip(values: list[float], *, samples: int, seed: int) -> float:
    if not values:
        return 1.0
    array = np.asarray(values, dtype=np.float64)
    observed = float(array.mean())
    rng = np.random.default_rng(seed)
    extreme = 1
    for _ in range(samples):
        signs = rng.choice((-1.0, 1.0), size=len(array))
        extreme += int(float(np.mean(array * signs)) >= observed)
    return extreme / (samples + 1)


def _load(shards: list[dict[str, Any]], report: dict[str, Any]) -> list[dict[str, Any]]:
    if report.get("schema") != residual.SCHEMA_REPORT:
        raise ValueError("1486 report schema drift")
    if report.get("verdict") != "JASS_CURRICULUM_ERROR_RESIDUAL_REGION_NOT_ESTABLISHED":
        raise ValueError("conditional screen requires the sealed negative global atlas")
    if report.get("pairs") != 353 or report.get("informative_error_pairs") != 290:
        raise ValueError("1486 pair partition drift")
    if report.get("reclassified_exact_non_errors", {}).get("total") != 63:
        raise ValueError("1486 reclassification drift")
    if not shards or {int(row.get("shard", -1)) for row in shards} != set(range(len(shards))):
        raise ValueError("residual shards are incomplete")
    if any(row.get("schema") != residual.SCHEMA_SHARD for row in shards):
        raise ValueError("residual shard schema drift")
    if any(int(row.get("nshards", -1)) != len(shards) for row in shards):
        raise ValueError("residual shard count drift")
    for key in ("champion_sha256", "jass_sha256", "search_params_sha256"):
        if {str(row.get(key, "")) for row in shards} != {str(report.get(key, ""))}:
            raise ValueError(f"1486 shard/report {key} drift")
    rows = [item for shard in shards for item in shard["rows"]]
    rows.sort(key=lambda row: int(row["pair_id"]))
    if [int(row["pair_id"]) for row in rows] != list(range(353)):
        raise ValueError("residual shards do not cover all 353 pairs")
    # The consumed outer confirmation is deliberately never dereferenced below.
    discovery = [row for row in rows if row.get("split") == "discovery"]
    if len(discovery) != int(report["all_splits"]["discovery"]):
        raise ValueError("outer discovery cardinality drift")
    return discovery


def _informative_symmetric(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts: dict[str, int] = defaultdict(int)
    result = []
    for pair in rows:
        error = pair["error"]
        if bool(error.get("reclassified_exact_non_error", False)):
            counts["reclassified"] += 1
            continue
        control = pair["control"]
        if bool(control.get("forced_single_action", False)):
            counts["forced_control"] += 1
            continue
        if error.get("informative_ranking") is not True or control.get("informative_ranking") is not True:
            raise ValueError("eligible discovery pair lacks informative rankings")
        if float(error["orientation_cosine"]) < 0.0 or float(control["orientation_cosine"]) < 0.0:
            counts["orientation_unstable"] += 1
            continue
        if str(error["source"]["stratum"]) != str(control["source"]["stratum"]):
            # Matching was intentionally broader than this conditional screen.
            counts["stratum_mismatch"] += 1
            continue
        result.append(pair)
    counts["eligible"] = len(result)
    return result, dict(sorted(counts.items()))


def _inner_split(rows: list[dict[str, Any]], *, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    # Pair IDs are vertices. Pairs sharing an opening or exact-symmetry state
    # form one indivisible component; this also keeps error/control paired.
    parent = {int(row["pair_id"]): int(row["pair_id"]) for row in rows}

    def find(value: int) -> int:
        root = value
        while parent[root] != root:
            root = parent[root]
        while parent[value] != value:
            nxt = parent[value]; parent[value] = root; value = nxt
        return root

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            low, high = sorted((a, b)); parent[high] = low

    owners: dict[tuple[str, str], int] = {}
    for pair in rows:
        pid = int(pair["pair_id"])
        for label in ("error", "control"):
            source = pair[label]["source"]
            for kind, value in (("opening", source["opening_id"]), ("state", source["exact_state_key"])):
                key = (kind, str(value)); previous = owners.setdefault(key, pid)
                union(previous, pid)
    components: dict[int, list[int]] = defaultdict(list)
    for pid in parent:
        components[find(pid)].append(pid)
    validation_ids: set[int] = set()
    component_manifest = []
    for members in sorted((sorted(value) for value in components.values()), key=lambda value: tuple(value)):
        digest = hashlib.sha256(f"{seed}|{','.join(map(str, members))}".encode()).digest()
        split = "validation" if int.from_bytes(digest[:8], "big") % 4 == 0 else "fit"
        if split == "validation":
            validation_ids.update(members)
        component_manifest.append({"members": members, "split": split})
    fit = [row for row in rows if int(row["pair_id"]) not in validation_ids]
    validation = [row for row in rows if int(row["pair_id"]) in validation_ids]
    if not fit or not validation:
        raise ValueError("inner component split lacks fit or validation")
    return fit, validation, {
        "method": "paired_opening_exact_state_components_sha256_mod4",
        "seed": seed, "components": len(components), "fit_pairs": len(fit),
        "validation_pairs": len(validation), "overlap": 0,
        "manifest_sha256": hashlib.sha256(_canonical(component_manifest)).hexdigest(),
    }


def _views(stratum: str) -> tuple[str, ...]:
    phase, kings, tactical = stratum.split("|")
    return (
        "ALL",
        f"PHASE={phase}",
        f"TACTICAL={tactical}",
        f"KINGS={kings}",
        f"PHASE={phase}|TACTICAL={tactical}",
        f"PHASE={phase}|KINGS={kings}",
        f"FULL={stratum}",
    )


def _groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for view in _views(str(row["error"]["source"]["stratum"])):
            groups[view].append(row)
    return dict(groups)


def _direction(rows: list[dict[str, Any]], *, total: int, min_hits: int, max_buckets: int) -> tuple[dict[int, float], list[dict[str, Any]]]:
    sums: dict[int, float] = defaultdict(float); hits: dict[int, int] = defaultdict(int)
    positive: dict[int, int] = defaultdict(int); negative: dict[int, int] = defaultdict(int)
    for row in rows:
        for key, value in _vector(row["error"]).items():
            sums[key] += value; hits[key] += 1
            positive[key] += int(value > 0); negative[key] += int(value < 0)
    candidates = []
    for key, count in hits.items():
        if count < min_hits:
            continue
        consistency = max(positive[key], negative[key]) / count
        if consistency < 0.80:
            continue
        mean = sums[key] / len(rows)
        candidates.append((abs(mean), count, consistency, key, 1.0 if mean > 0 else -1.0))
    candidates.sort(reverse=True)
    selected, buckets = [], set()
    for magnitude, count, consistency, key, sign in candidates:
        bucket = key % total
        if bucket not in buckets and len(buckets) >= max_buckets:
            continue
        buckets.add(bucket)
        selected.append({"coordinate": key, "bucket": bucket, "sign": sign,
                         "fit_hits": count, "fit_sign_consistency": consistency,
                         "fit_mean_abs": magnitude})
    norm = math.sqrt(len(selected)) if selected else 1.0
    return {int(row["coordinate"]): float(row["sign"]) / norm for row in selected}, selected


def _evaluate(rows: list[dict[str, Any]], direction: dict[int, float], selected: list[dict[str, Any]], *, samples: int, seed: int) -> dict[str, Any]:
    error = [_dot(_vector(row["error"]), direction) for row in rows]
    control = [_dot(_vector(row["control"]), direction) for row in rows]
    paired = [left - right for left, right in zip(error, control, strict=True)]
    replicated = 0; coordinate_evidence = []
    for item in selected:
        values = [_vector(row["error"]).get(int(item["coordinate"]), 0.0) for row in rows]
        nonzero = [value for value in values if value]
        same = sum((value > 0) == (float(item["sign"]) > 0) for value in nonzero)
        consistency = same / len(nonzero) if nonzero else 0.0
        passed = len(nonzero) >= 2 and consistency >= 0.60
        replicated += int(passed)
        coordinate_evidence.append({**item, "validation_hits": len(nonzero),
                                    "validation_sign_consistency": consistency,
                                    "replicated": passed})
    return {
        "error_projection": _bootstrap(error, samples=samples, seed=seed),
        "control_projection": _bootstrap(control, samples=samples, seed=seed + 1),
        "paired_error_minus_control": _bootstrap(paired, samples=samples, seed=seed + 2),
        "paired_sign_flip_pvalue": _sign_flip(paired, samples=min(samples, 10_000), seed=seed + 3),
        "coordinate_replication_fraction": replicated / len(selected) if selected else 0.0,
        "coordinates": coordinate_evidence,
    }


def screen(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    report = json.loads(args.atlas_report.read_text())
    shards = [json.loads(path.read_text()) for path in args.shard]
    discovery = _load(shards, report)
    eligible, exclusions = _informative_symmetric(discovery)
    fit_rows, validation_rows, split = _inner_split(eligible, seed=args.split_seed)
    fit_groups, validation_groups = _groups(fit_rows), _groups(validation_rows)
    total = int(args.total_buckets)
    if total <= 0:
        raise ValueError("invalid active PatternEval geometry")
    candidates = []
    candidate_preflight = []
    for index, name in enumerate(sorted(set(fit_groups) & set(validation_groups))):
        fit_group, validation_group = fit_groups[name], validation_groups[name]
        if len(fit_group) < args.min_fit_pairs or len(validation_group) < args.min_validation_pairs:
            candidate_preflight.append({
                "population": name, "fit_pairs": len(fit_group),
                "validation_pairs": len(validation_group),
                "stage": "insufficient_population_support",
                "required_fit_pairs": args.min_fit_pairs,
                "required_validation_pairs": args.min_validation_pairs,
            })
            continue
        min_hits = max(args.min_coordinate_hits, math.ceil(args.min_coordinate_fraction * len(fit_group)))
        direction, selected = _direction(fit_group, total=total, min_hits=min_hits, max_buckets=args.max_buckets)
        selected_buckets = len({row["bucket"] for row in selected})
        if selected_buckets < args.min_buckets:
            candidate_preflight.append({
                "population": name, "fit_pairs": len(fit_group),
                "validation_pairs": len(validation_group),
                "stage": "insufficient_stable_coordinate_direction",
                "min_coordinate_hits": min_hits,
                "selected_canonical_buckets": selected_buckets,
                "selected_coordinates": len(selected),
                "required_canonical_buckets": args.min_buckets,
            })
            continue
        metrics = _evaluate(validation_group, direction, selected, samples=args.bootstrap_samples,
                            seed=args.bootstrap_seed + 10 * index)
        gates = {
            "validation_error_probability_ge_0_90": metrics["error_projection"]["probability_positive"] >= 0.90,
            "validation_paired_probability_ge_0_90": metrics["paired_error_minus_control"]["probability_positive"] >= 0.90,
            "validation_control_mean_not_harmed": metrics["control_projection"]["mean"] >= -0.02,
            "validation_coordinate_replication_ge_0_60": metrics["coordinate_replication_fraction"] >= 0.60,
        }
        score = (
            metrics["error_projection"]["probability_positive"]
            + metrics["paired_error_minus_control"]["probability_positive"]
            + metrics["coordinate_replication_fraction"]
            - 0.002 * len(selected)
        )
        candidate_preflight.append({
            "population": name, "fit_pairs": len(fit_group),
            "validation_pairs": len(validation_group), "stage": "evaluated",
            "min_coordinate_hits": min_hits,
            "selected_canonical_buckets": selected_buckets,
            "selected_coordinates": len(selected),
        })
        candidates.append({"population": name, "fit_pairs": len(fit_group),
                           "validation_pairs": len(validation_group), "min_coordinate_hits": min_hits,
                           "selected_canonical_buckets": len({row["bucket"] for row in selected}),
                           "selected_coordinates": len(selected), "direction": selected,
                           "validation": metrics, "gates": gates, "passed": all(gates.values()),
                           "selection_score": score})
    passing = [row for row in candidates if row["passed"]]
    passing.sort(key=lambda row: (-row["selection_score"], -row["validation_pairs"], row["population"]))
    chosen = passing[0] if passing else None
    output = {
        "schema": SCHEMA, "verdict": (
            "JASS_CURRICULUM_ERROR_CONDITIONAL_HYPOTHESIS_READY" if chosen
            else "JASS_CURRICULUM_ERROR_CONDITIONAL_HYPOTHESIS_NOT_ESTABLISHED"),
        "passed": bool(chosen), "source_verdict": report["verdict"],
        "source_atlas_sha256": sha256(args.atlas_report),
        "source_shards": [{"path": str(path), "sha256": sha256(path)} for path in args.shard],
        "outer_confirm_pairs_read_for_selection_or_evaluation": 0,
        "outer_confirm_is_consumed_and_forbidden": True,
        "outer_discovery_pairs": len(discovery), "exclusions": exclusions,
        "eligible_exact_symmetry_stable_pairs": len(eligible), "inner_split": split,
        "candidate_family": "ALL+phase+tactical+kings+phase_tactical+phase_kings+full_stratum",
        "pattern_total_buckets": total,
        "multiple_candidate_screen_is_exploratory_only": True,
        "candidate_preflight": candidate_preflight,
        "candidate_results": candidates, "selected_population": chosen,
        "fresh_campaign_authorized": bool(chosen), "fit_authorized": False,
        "strength_games": 0, "selfplay_games": 0, "fits": 0, "frozen_reads": 0,
        "promotion_authorized": False, "automatic_continuation": False,
        "next_stage": "fresh_conditional_error_confirmation" if chosen else None,
    }
    hypothesis = {
        "schema": HYPOTHESIS_SCHEMA, "authorized": bool(chosen),
        "source_screen_verdict": output["verdict"], "population": chosen["population"] if chosen else None,
        "symmetry_filter": "error_and_matched_control_orientation_cosine_ge_0",
        "direction": chosen["direction"] if chosen else [],
        "fresh_confirmation_contract": {
            "reuse_outer_confirm": False, "opening_and_exact_state_overlap": 0,
            "same_champion_teacher_judge_and_search_params": True,
            "min_informative_error_pairs": 64,
            "error_projection_ci95_low_gt_0": True,
            "paired_error_minus_control_ci95_low_gt_0": True,
            "control_projection_ci95_low_ge": -0.02,
            "paired_sign_flip_p_le": 0.025,
            "coordinate_replication_fraction_ge": 0.70,
        },
        "fit_authorized": False, "promotion_authorized": False,
    }
    return output, hypothesis


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--atlas-report", type=Path, required=True)
    root.add_argument("--shard", action="append", type=Path, required=True)
    root.add_argument("--report", type=Path, required=True)
    root.add_argument("--hypothesis", type=Path, required=True)
    root.add_argument("--total-buckets", type=int, required=True,
                      help="active exact-fold PatternEval bucket count from production patterns.py")
    root.add_argument("--split-seed", type=int, default=2026082226)
    root.add_argument("--bootstrap-seed", type=int, default=2026082227)
    root.add_argument("--bootstrap-samples", type=int, default=10_000)
    root.add_argument("--min-fit-pairs", type=int, default=12)
    root.add_argument("--min-validation-pairs", type=int, default=6)
    root.add_argument("--min-coordinate-hits", type=int, default=4)
    root.add_argument("--min-coordinate-fraction", type=float, default=0.15)
    root.add_argument("--min-buckets", type=int, default=4)
    root.add_argument("--max-buckets", type=int, default=32)
    return root


def main() -> int:
    args = parser().parse_args(); report, hypothesis = screen(args)
    _publish(args.report, report); _publish(args.hypothesis, hypothesis)
    print(json.dumps({"verdict": report["verdict"], "selected_population": hypothesis["population"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
