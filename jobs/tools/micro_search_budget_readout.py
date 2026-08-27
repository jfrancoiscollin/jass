#!/usr/bin/env python3
"""M1 exploratory budget-curve readout for micro-search teacher v1.

Consumes the frozen Rich-D Phase-C parents/groups plus freshly re-searched
budget-ladder scores.  No model is fit.  The only model-selection action is the
fully preregistered deterministic B* rule in
L3_MICRO_SEARCH_TEACHER_TO_T_V1_20260827.md.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import numpy as np

from jobs.tools.rich_d_phase_c_readout import (
    PHASES,
    accepted_pairs,
    load_d1,
    load_groups,
    load_parents,
    metrics,
    move_features,
)
from jobs.tools.rich_d_teacher import read_feat

BUDGETS = (125, 250, 500, 1000, 2000, 5000)
BOOTSTRAP_SAMPLES = 100_000
# Diagnostic-only M1 seed, frozen here before any budget-curve result is read.
BOOTSTRAP_SEED = 2026090200


def load_ladder(path: Path, expected_rows: int) -> dict[int, dict[str, np.ndarray]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"row_index"}
        for budget in BUDGETS:
            required |= {
                f"q{budget}_parent", f"nodes{budget}",
                f"completed_depth{budget}", f"effective_depth{budget}",
                f"elapsed_us{budget}", f"pv{budget}_enters_egdb",
            }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"ladder fields drift: {reader.fieldnames!r}")
        rows = list(reader)
    if len(rows) != expected_rows:
        raise ValueError(f"ladder row count {len(rows)} != expected {expected_rows}")
    ids = [int(row["row_index"]) for row in rows]
    if ids != list(range(expected_rows)):
        raise ValueError("ladder row_index must be contiguous and sorted")

    out: dict[int, dict[str, np.ndarray]] = {}
    for budget in BUDGETS:
        out[budget] = {
            "score": np.asarray([float(r[f"q{budget}_parent"]) for r in rows], dtype=np.float64),
            "nodes": np.asarray([int(r[f"nodes{budget}"]) for r in rows], dtype=np.int64),
            "completed_depth": np.asarray([int(r[f"completed_depth{budget}"]) for r in rows], dtype=np.int64),
            "effective_depth": np.asarray([int(r[f"effective_depth{budget}"]) for r in rows], dtype=np.int64),
            "elapsed_us": np.asarray([int(r[f"elapsed_us{budget}"]) for r in rows], dtype=np.int64),
            "pv_enters_egdb": np.asarray([int(r[f"pv{budget}_enters_egdb"]) for r in rows], dtype=np.int8),
        }
        if not np.all(np.isfinite(out[budget]["score"])):
            raise ValueError(f"non-finite ladder score at budget {budget}")
    return out


def bootstrap_absolute(metric: dict[str, np.ndarray], samples: int, seed: int) -> dict:
    if samples <= 0:
        raise ValueError("bootstrap samples must be positive")
    pairwise = metric["pairwise"]
    top_hit = metric["top_hit"]
    if len(pairwise) == 0 or len(pairwise) != len(top_hit):
        raise ValueError("invalid bootstrap metric arrays")
    rng = np.random.default_rng(seed)
    n = len(pairwise)
    pboot = np.empty(samples, dtype=np.float64)
    tboot = np.empty(samples, dtype=np.float64)
    batch = 128
    for start in range(0, samples, batch):
        stop = min(samples, start + batch)
        sample_ids = rng.integers(0, n, size=(stop - start, n))
        pboot[start:stop] = pairwise[sample_ids].mean(axis=1)
        tboot[start:stop] = top_hit[sample_ids].mean(axis=1)

    def summarize(values: np.ndarray, boot: np.ndarray) -> dict:
        return {
            "mean": float(values.mean()),
            "ci_low": float(np.quantile(boot, 0.025)),
            "ci_high": float(np.quantile(boot, 0.975)),
            "samples": int(samples),
            "seed": int(seed),
        }

    return {
        "pairwise": summarize(pairwise, pboot),
        "top_hit": summarize(top_hit, tboot),
    }


def score_pair(score: np.ndarray, good: int, bad: int) -> float:
    if score[good] > score[bad]:
        return 1.0
    if score[good] == score[bad]:
        return 0.5
    return 0.0


def pair_transition_stats(
    pairs: dict[int, list[tuple[int, int]]],
    d1_score: np.ndarray,
    candidate_score: np.ndarray,
) -> dict[str, float | int]:
    d1_errors = 0
    d1_correct = 0
    fixed = 0
    broken = 0
    ties_d1 = 0
    ties_candidate = 0
    total = 0
    for pid in sorted(pairs):
        for good, bad in pairs[pid]:
            total += 1
            da = score_pair(d1_score, good, bad)
            ca = score_pair(candidate_score, good, bad)
            ties_d1 += int(da == 0.5)
            ties_candidate += int(ca == 0.5)
            if da < 1.0:
                d1_errors += 1
                fixed += int(ca == 1.0)
            else:
                d1_correct += 1
                broken += int(ca < 1.0)
    return {
        "stable_pairs": total,
        "d1_non_strict_correct_pairs": d1_errors,
        "d1_strict_correct_pairs": d1_correct,
        "d1_ties": ties_d1,
        "candidate_ties": ties_candidate,
        "d1_error_fraction_fixed_strict": float(fixed / d1_errors) if d1_errors else 0.0,
        "d1_correct_fraction_broken": float(broken / d1_correct) if d1_correct else 0.0,
    }


def ordering_disagreement(
    pairs: dict[int, list[tuple[int, int]]],
    left: np.ndarray,
    right: np.ndarray,
) -> dict[str, float | int]:
    disagree = 0
    total = 0
    for pid in sorted(pairs):
        for good, bad in pairs[pid]:
            ld = np.sign(left[good] - left[bad])
            rd = np.sign(right[good] - right[bad])
            disagree += int(ld != rd)
            total += 1
    return {
        "stable_pairs": total,
        "ordering_disagreement_fraction": float(disagree / total) if total else 0.0,
    }


def dist_summary(values: np.ndarray) -> dict[str, float | int]:
    if len(values) == 0:
        return {"count": 0}
    v = values.astype(np.float64, copy=False)
    return {
        "count": int(len(v)),
        "min": float(np.min(v)),
        "p50": float(np.quantile(v, 0.50)),
        "p90": float(np.quantile(v, 0.90)),
        "p99": float(np.quantile(v, 0.99)),
        "max": float(np.max(v)),
        "mean": float(np.mean(v)),
    }


def select_budget(curve: dict[int, dict], d1_pairwise: float) -> tuple[int | None, dict[int, dict]]:
    if 5000 not in curve:
        raise ValueError("5000-node arm missing")
    a5 = float(curve[5000]["global"]["pairwise"])
    denom = max(1e-12, a5 - d1_pairwise)
    decisions: dict[int, dict] = {}
    chosen: int | None = None
    for budget in BUDGETS:
        arm = curve[budget]
        a = float(arm["global"]["pairwise"])
        headroom = float((a - d1_pairwise) / denom)
        phase_ok = all(float(arm["by_phase"][phase]["pairwise"]) >= 0.87 for phase in PHASES)
        colour_ok = all(float(arm["by_colour"][colour]["pairwise"]) >= 0.88 for colour in ("white", "black"))
        global_ok = a >= 0.90
        headroom_ok = headroom >= 0.85
        if budget == 5000:
            qualifies = global_ok and phase_ok and colour_ok
        else:
            qualifies = global_ok and headroom_ok and phase_ok and colour_ok
        decisions[budget] = {
            "global_pairwise": a,
            "recovered_headroom": headroom,
            "global_ge_0_90": global_ok,
            "headroom_ge_0_85": headroom_ok,
            "each_phase_ge_0_87": phase_ok,
            "both_colours_ge_0_88": colour_ok,
            "qualifies": qualifies,
        }
        if chosen is None and qualifies:
            chosen = budget
    return chosen, decisions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parents", type=Path, required=True)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--ladder", type=Path, required=True)
    parser.add_argument("--d1", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--bootstrap-samples", type=int, default=BOOTSTRAP_SAMPLES)
    parser.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    args = parser.parse_args()

    if args.bootstrap_seed != BOOTSTRAP_SEED:
        raise ValueError(f"M1 bootstrap seed is frozen at {BOOTSTRAP_SEED}")

    parents = load_parents(args.parents)
    meta = load_groups(args.groups, parents)
    feat = read_feat(args.features)
    if len(meta) != len(feat):
        raise ValueError("feature/group row-count drift")
    ladder = load_ladder(args.ladder, len(meta))

    parent_rows: dict[int, list[int]] = defaultdict(list)
    for index, sibling in enumerate(meta):
        parent_rows[sibling.parent_id].append(index)
    pairs = accepted_pairs(parent_rows, meta)
    accepted_ids = sorted(pairs)
    if not accepted_ids:
        raise ValueError("no stable-pair parents")

    d1 = load_d1(args.d1)
    xd1 = np.concatenate([feat, move_features(meta)], axis=1)
    d1_score = np.empty(len(meta), dtype=np.float64)
    for index, sibling in enumerate(meta):
        bank = "white_parent" if sibling.parent_stm == 0 else "black_parent"
        d1_score[index] = float(xd1[index] @ np.asarray(d1["weights"][bank], dtype=np.float64))
    d1_metric = metrics(parent_rows, pairs, accepted_ids, d1_score)
    d1_global = {name: float(values.mean()) for name, values in d1_metric.items()}

    old_q5k = np.asarray([s.q5k_parent for s in meta], dtype=np.float64)
    curve: dict[int, dict] = {}
    for budget in BUDGETS:
        arm = ladder[budget]
        score = arm["score"]
        metric = metrics(parent_rows, pairs, accepted_ids, score)
        by_phase = {}
        for phase in PHASES:
            ids = [pid for pid in accepted_ids if parents[pid].phase == phase]
            phase_metric = metrics(parent_rows, pairs, ids, score)
            by_phase[phase] = {
                "parents": len(ids),
                "pairwise": float(phase_metric["pairwise"].mean()),
                "top_hit": float(phase_metric["top_hit"].mean()),
            }
        by_colour = {}
        for stm, name in ((0, "white"), (1, "black")):
            ids = [pid for pid in accepted_ids if parents[pid].stm == stm]
            colour_metric = metrics(parent_rows, pairs, ids, score)
            by_colour[name] = {
                "parents": len(ids),
                "pairwise": float(colour_metric["pairwise"].mean()),
                "top_hit": float(colour_metric["top_hit"].mean()),
            }
        curve[budget] = {
            "global": {name: float(values.mean()) for name, values in metric.items()},
            "bootstrap": bootstrap_absolute(metric, args.bootstrap_samples, args.bootstrap_seed),
            "by_phase": by_phase,
            "by_colour": by_colour,
            "d1_pair_transitions": pair_transition_stats(pairs, d1_score, score),
            "vs_prior_q5k": ordering_disagreement(pairs, score, old_q5k),
            "compute": {
                "nodes_total": int(arm["nodes"].sum()),
                "elapsed_us_total": int(arm["elapsed_us"].sum()),
                "elapsed_seconds_total": float(arm["elapsed_us"].sum() / 1e6),
                "completed_depth": dist_summary(arm["completed_depth"]),
                "effective_depth": dist_summary(arm["effective_depth"]),
                "pv_enters_egdb_fraction": float(np.mean(arm["pv_enters_egdb"] != 0)),
            },
        }

    selected, decisions = select_budget(curve, d1_global["pairwise"])
    a5 = float(curve[5000]["global"]["pairwise"])
    for budget in BUDGETS:
        curve[budget]["recovered_headroom"] = decisions[budget]["recovered_headroom"]
        curve[budget]["selection_gates"] = decisions[budget]

    report = {
        "schema": "jass.micro_search_budget_curve.v1",
        "exploratory_only": True,
        "budgets_nodes": list(BUDGETS),
        "bootstrap": {"cluster": "parent", "samples": args.bootstrap_samples, "seed": args.bootstrap_seed},
        "selected_parents": len(parents),
        "emitted_siblings": len(meta),
        "accepted_parents": len(accepted_ids),
        "stable_pairs": int(sum(len(v) for v in pairs.values())),
        "d1": d1_global,
        "fresh_5000_pairwise": a5,
        "curve": {str(k): curve[k] for k in BUDGETS},
        "selection": {
            "selected_budget_nodes": selected,
            "rule": "smallest budget meeting prereg gates; 5000 fallback ignores H only",
            "decisions": {str(k): decisions[k] for k in BUDGETS},
        },
        "fits": 0,
        "t_refits": 0,
        "selfplay": 0,
        "strength_games": 0,
        "runtime_micro_search": False,
        "promotion_authorized": False,
    }
    if selected is None:
        report.update({
            "passed": False,
            "verdict": "MICRO_SEARCH_TEACHER_BUDGET_NOT_ESTABLISHED",
            "next_stage": None,
        })
    else:
        report.update({
            "passed": True,
            "verdict": "MICRO_SEARCH_TEACHER_BUDGET_SELECTED",
            "next_stage": "M2_FRESH_CONFIRMATION",
        })
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
