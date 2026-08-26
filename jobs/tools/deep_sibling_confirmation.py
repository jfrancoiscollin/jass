#!/usr/bin/env python3
"""Zero-refit Phase-B confirmation evaluator for DSSD v1.

Consumes a fresh CURRICULUM-play parent set, its frozen 5k/50k/200k sibling
teacher extract, production 120-feature dump, and the already-fitted Phase-A D
policy. It performs no fit and applies the exact same stable-pair rule. The
preregistered confirmation gate is positive D-vs-T pairwise point delta in every
represented phase plus a global parent-cluster bootstrap 95% lower bound > 0.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from jobs.tools.deep_sibling_pairwise import (
    MOVE_FEATURE_NAMES,
    PHASES,
    ParentMeta,
    accepted_pairs,
    load_feat,
    load_groups,
    metrics_by_parent,
    move_features,
)

DEFAULT_BOOTSTRAP_SAMPLES = 100000
DEFAULT_BOOTSTRAP_SEED = 2026083103


def load_confirmation_parents(path: Path) -> dict[int, ParentMeta]:
    out: dict[int, ParentMeta] = {}
    with path.open(newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        required = {"parent_id", "parent_stm", "pieces", "legal_moves", "phase"}
        if rd.fieldnames is None or not required.issubset(rd.fieldnames):
            raise ValueError(f"confirmation parents missing fields: {rd.fieldnames!r}")
        for row in rd:
            p = ParentMeta(
                parent_id=int(row["parent_id"]),
                stm=int(row["parent_stm"]),
                pieces=int(row["pieces"]),
                legal_moves=int(row["legal_moves"]),
                phase=row["phase"],
                partition="holdout",  # compatibility only; no Phase-B fit occurs.
            )
            if p.parent_id in out:
                raise ValueError("duplicate confirmation parent_id")
            if p.stm not in (0, 1) or p.phase not in PHASES:
                raise ValueError("invalid confirmation parent metadata")
            if not (9 <= p.pieces <= 40 and 2 <= p.legal_moves <= 16):
                raise ValueError("confirmation parent outside frozen DSSD eligibility")
            out[p.parent_id] = p
    if sorted(out) != list(range(len(out))):
        raise ValueError("confirmation parent IDs are not contiguous 0..N-1")
    return out


def load_policy(path: Path) -> dict[int, np.ndarray]:
    p = json.loads(path.read_text(encoding="utf-8"))
    if p.get("schema") != "jass.deep_sibling_policy.v1" or p.get("usable") is not True:
        raise ValueError("Phase-A D policy is not a usable frozen DSSD policy")
    if p.get("eval_feature_width") != 120 or p.get("move_feature_names") != MOVE_FEATURE_NAMES:
        raise ValueError("Phase-A D policy feature contract drift")
    if p.get("score_convention") != "higher_is_better_for_parent":
        raise ValueError("Phase-A D policy score convention drift")
    w = p.get("weights") or {}
    out = {
        0: np.asarray(w.get("white_parent", []), dtype=np.float64),
        1: np.asarray(w.get("black_parent", []), dtype=np.float64),
    }
    if any(x.shape != (126,) or not np.all(np.isfinite(x)) for x in out.values()):
        raise ValueError("Phase-A D policy must contain two finite 126-weight banks")
    return out


def bootstrap_pairwise(delta: np.ndarray, samples: int, seed: int) -> dict:
    if len(delta) == 0:
        raise ValueError("confirmation bootstrap requires nonempty parent deltas")
    rng = np.random.default_rng(seed)
    n = len(delta)
    boot = np.empty(samples, dtype=np.float64)
    batch = 512
    for start in range(0, samples, batch):
        stop = min(samples, start + batch)
        idx = rng.integers(0, n, size=(stop - start, n))
        boot[start:stop] = delta[idx].mean(axis=1)
    return {
        "mean": float(delta.mean()),
        "ci_low": float(np.quantile(boot, 0.025)),
        "ci_high": float(np.quantile(boot, 0.975)),
        "probability_gt_zero": float(np.mean(boot > 0)),
        "samples": int(samples),
        "seed": int(seed),
        "cluster": "parent",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parents", type=Path, required=True)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--features", type=Path, required=True)
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--bootstrap-samples", type=int, default=DEFAULT_BOOTSTRAP_SAMPLES)
    ap.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    args = ap.parse_args()

    parents = load_confirmation_parents(args.parents)
    if len(parents) != 2000:
        raise SystemExit(f"Phase-B confirmation requires exactly 2000 selected parents, got {len(parents)}")
    meta = load_groups(args.groups, parents)
    feat = load_feat(args.features)
    if len(meta) != len(feat):
        raise SystemExit("confirmation groups/features row count mismatch")
    x = np.concatenate([feat, move_features(meta)], axis=1)
    if x.shape[1] != 126:
        raise SystemExit(f"confirmation DSSD feature width drift: {x.shape[1]} != 126")
    weights = load_policy(args.policy)

    parent_rows: dict[int, list[int]] = defaultdict(list)
    for i, m in enumerate(meta):
        parent_rows[m.parent_id].append(i)
    if set(parent_rows) != set(parents):
        raise SystemExit("confirmation teacher did not emit siblings for every selected parent")
    pairs = accepted_pairs(parent_rows, meta)
    accepted = sorted(pairs)

    model_score = np.asarray([float(x[i] @ weights[m.parent_stm]) for i, m in enumerate(meta)], dtype=np.float64)
    baseline_score = np.asarray([m.t_baseline_parent for m in meta], dtype=np.float64)

    selected_by_phase = {ph: [p for p in parents if parents[p].phase == ph] for ph in PHASES}
    accepted_by_phase = {ph: [p for p in accepted if parents[p].phase == ph] for ph in PHASES}
    selected_represented = [ph for ph in PHASES if selected_by_phase[ph]]
    stable_support_every_selected_phase = all(accepted_by_phase[ph] for ph in selected_represented)

    if accepted:
        mm = metrics_by_parent(parent_rows, pairs, accepted, model_score)["pairwise"]
        bm = metrics_by_parent(parent_rows, pairs, accepted, baseline_score)["pairwise"]
        delta = mm - bm
        boot = bootstrap_pairwise(delta, args.bootstrap_samples, args.bootstrap_seed)
        model_pairwise = float(mm.mean())
        baseline_pairwise = float(bm.mean())
    else:
        delta = np.asarray([], dtype=np.float64)
        boot = {"mean": math.nan, "ci_low": math.nan, "ci_high": math.nan,
                "probability_gt_zero": 0.0, "samples": args.bootstrap_samples,
                "seed": args.bootstrap_seed, "cluster": "parent"}
        model_pairwise = baseline_pairwise = math.nan

    phase = {}
    for ph in PHASES:
        ids = accepted_by_phase[ph]
        if ids:
            a = metrics_by_parent(parent_rows, pairs, ids, model_score)["pairwise"]
            b = metrics_by_parent(parent_rows, pairs, ids, baseline_score)["pairwise"]
            phase[ph] = {
                "selected_parents": len(selected_by_phase[ph]),
                "accepted_parents": len(ids),
                "pairwise_delta": float((a - b).mean()),
                "model_pairwise": float(a.mean()),
                "t_pairwise": float(b.mean()),
            }
        else:
            phase[ph] = {
                "selected_parents": len(selected_by_phase[ph]),
                "accepted_parents": 0,
                "pairwise_delta": math.nan,
                "model_pairwise": math.nan,
                "t_pairwise": math.nan,
            }

    phase_positive = all(phase[ph]["pairwise_delta"] > 0 for ph in selected_represented if phase[ph]["accepted_parents"] > 0)
    gates = {
        "exactly_2000_fresh_parents": len(parents) == 2000,
        "zero_refit": True,
        "stable_support_every_selected_phase": bool(stable_support_every_selected_phase),
        "positive_pairwise_delta_all_represented_phases": bool(stable_support_every_selected_phase and phase_positive),
        "global_parent_bootstrap_ci95_low_gt_0": bool(len(delta) and boot["ci_low"] > 0),
    }
    passed = all(gates.values())
    verdict = "DEEP_SIBLING_CONFIRMATION_ESTABLISHED" if passed else "DEEP_SIBLING_CONFIRMATION_NOT_ESTABLISHED"
    report = {
        "schema": "jass.deep_sibling_phase_b_confirmation.v1",
        "verdict": verdict,
        "passed": bool(passed),
        "experiment_terminal": True,
        "next_stage": None,
        "parents_selected": len(parents),
        "parents_with_stable_pair": len(accepted),
        "stable_pairs": int(sum(len(v) for v in pairs.values())),
        "selected_by_phase": {ph: len(selected_by_phase[ph]) for ph in PHASES},
        "accepted_by_phase": {ph: len(accepted_by_phase[ph]) for ph in PHASES},
        "represented_phases": selected_represented,
        "model_pairwise": model_pairwise,
        "t_pairwise": baseline_pairwise,
        "delta_model_minus_t": boot,
        "phase_strata": phase,
        "gates": gates,
        "stable_pair_rule": {
            "same_sign_50k_200k": True,
            "min_abs_d50_cp": 10,
            "min_abs_d200_cp": 30,
            "exact_terminal_tb_wdl_precedence": True,
            "teacher_target": "q200_parent",
        },
        "policy_refit": False,
        "pattern_eval_fits": 0,
        "curriculum_modified": False,
        "policy_value_blending": False,
        "strength_games": 0,
        "promotion_authorized": False,
        "automatic_promotion": False,
    }
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=True) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": verdict, "accepted_parents": len(accepted),
                      "pairwise_delta": boot["mean"], "ci_low": boot["ci_low"]},
                     sort_keys=True, allow_nan=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
