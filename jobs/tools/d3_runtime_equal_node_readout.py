#!/usr/bin/env python3
"""Terminal readout for the frozen D3 runtime equal-node gate."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

PRIMARY_OPENINGS = 750
HARNESS_OPENINGS = 100
PRIMARY_GAMES = 1500
HARNESS_GAMES = 200
BOOTSTRAP = 200000
BOOTSTRAP_SEED = 2026111303
NODE_BUDGET = 20000
MODEL_SHA = "e4d510fbb9b81cbe74574d92da48e8de6f61d8f98de6472eeb409713785f0de0"
ADAPTER_SHA = "03cd2aa6b2a61ef8ce11dc878eb0ba13a56c8e587b49b19158135a1b64bfd4c3"


def read_jsonl(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def elo(score: float) -> float:
    p = min(max(float(score), 1e-12), 1.0 - 1e-12)
    return 400.0 * math.log10(p / (1.0 - p))


def paired_bootstrap(pair_scores: np.ndarray) -> dict:
    if pair_scores.shape != (PRIMARY_OPENINGS,):
        raise ValueError("primary pair cardinality drift")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = np.empty(BOOTSTRAP, dtype=np.float64)
    chunk = 2000
    done = 0
    while done < BOOTSTRAP:
        n = min(chunk, BOOTSTRAP - done)
        idx = rng.integers(0, PRIMARY_OPENINGS, size=(n, PRIMARY_OPENINGS))
        means[done:done+n] = pair_scores[idx].mean(axis=1)
        done += n
    p = np.clip(means, 1e-12, 1.0 - 1e-12)
    elos = 400.0 * np.log10(p / (1.0 - p))
    return {
        "replications": BOOTSTRAP,
        "seed": BOOTSTRAP_SEED,
        "score_ci95": [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))],
        "elo_ci95": [float(np.quantile(elos, 0.025)), float(np.quantile(elos, 0.975))],
    }


def add_telemetry(total: dict, item: dict) -> None:
    for key in ("searches", "depth_sum", "nodes", "eval_calls", "d3_feature_calls"):
        total[key] = total.get(key, 0) + int(item.get(key, 0))
    total["wall_seconds"] = total.get("wall_seconds", 0.0) + float(item.get("wall_seconds", 0.0))


def finalize_telemetry(total: dict) -> dict:
    searches = int(total.get("searches", 0))
    nodes = int(total.get("nodes", 0))
    if searches and nodes > NODE_BUDGET * searches:
        raise ValueError("node use exceeds frozen exact-node ceiling")
    return {
        **total,
        "mean_completed_depth": (total.get("depth_sum", 0) / searches if searches else 0.0),
        "mean_nodes_per_search": (nodes / searches if searches else 0.0),
    }


def validate_provenance(preflight: dict, pool: dict) -> None:
    if preflight.get("verdict") != "D3_RUNTIME_MOVE_ORDERING_PREFLIGHT_COMPLETE_V1":
        raise ValueError("runtime preflight verdict drift")
    if preflight.get("adapter_sha256") != ADAPTER_SHA or preflight.get("adapter_width") != 632:
        raise ValueError("runtime preflight adapter drift")
    if preflight.get("value_model_sha256") != MODEL_SHA:
        raise ValueError("runtime preflight WDL_CONTROL drift")
    if preflight.get("control_candidate_off_identity", {}).get("mismatches") != 0:
        raise ValueError("runtime preflight control identity drift")
    if preflight.get("root_pv_priority_unchanged") is not True \
            or preflight.get("tt_priority_unchanged") is not True \
            or preflight.get("value_leaf_bytes_unchanged") is not True:
        raise ValueError("runtime preflight search/value boundary drift")
    support = preflight.get("support", {})
    if support.get("below9_runtime_identity") is not True:
        raise ValueError("runtime support amendment drift")
    if pool.get("verdict") != "D3_RUNTIME_EQUAL_NODE_POOL_READY_V1" \
            or pool.get("primary_openings") != PRIMARY_OPENINGS \
            or pool.get("harness_openings") != HARNESS_OPENINGS:
        raise ValueError("equal-node pool provenance drift")
    for key in ("forbidden_overlap", "inter_cell_overlap", "target_reads", "qscore_reads",
                "search_decision_trace_reads", "full_ladder_1843_reads", "teacher_reads"):
        if pool.get(key) != 0:
            raise ValueError(f"pool information/overlap barrier drift: {key}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--preflight", type=Path, required=True)
    p.add_argument("--pool-provenance", type=Path, required=True)
    p.add_argument("--primary-games", type=Path, action="append", default=[])
    p.add_argument("--harness-games", type=Path, action="append", default=[])
    p.add_argument("--code-sha", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()

    preflight = json.loads(a.preflight.read_text(encoding="utf-8"))
    pool = json.loads(a.pool_provenance.read_text(encoding="utf-8"))
    validate_provenance(preflight, pool)
    primary = sorted(read_jsonl(a.primary_games), key=lambda r: r["opening_index"])
    harness = sorted(read_jsonl(a.harness_games), key=lambda r: r["opening_index"])
    if len(primary) != PRIMARY_OPENINGS or len(harness) != HARNESS_OPENINGS:
        raise ValueError("equal-node opening cardinality drift")
    if [r["opening_index"] for r in primary] != list(range(PRIMARY_OPENINGS)):
        raise ValueError("primary opening index drift")
    if [r["opening_index"] for r in harness] != list(range(HARNESS_OPENINGS)):
        raise ValueError("harness opening index drift")
    if any(r.get("mode") != "primary" or r.get("node_budget") != NODE_BUDGET
           or len(r.get("games", [])) != 2 for r in primary):
        raise ValueError("primary game contract drift")
    if any(r.get("mode") != "harness" or r.get("node_budget") != NODE_BUDGET
           or len(r.get("games", [])) != 2 for r in harness):
        raise ValueError("harness game contract drift")

    complement_failures = sum(abs(float(r["pair_score_arm_a"]) - 0.5) > 1e-15 for r in harness)
    harness_score = float(np.mean([r["pair_score_arm_a"] for r in harness]))
    harness_pass = complement_failures == 0 and abs(harness_score - 0.5) <= 1e-15

    pair_scores = np.asarray([float(r["pair_score_d3"]) for r in primary], dtype=np.float64)
    boot = paired_bootstrap(pair_scores)
    d3_score = float(pair_scores.mean())
    d3_elo = elo(d3_score)

    wdl = {"W": 0, "D": 0, "L": 0}
    d3_tel: dict = {}; control_tel: dict = {}
    for row in primary:
        for game in row["games"]:
            wdl[game["d3_wdl"]] += 1
            add_telemetry(d3_tel, game["d3_telemetry"])
            add_telemetry(control_tel, game["control_telemetry"])
    if sum(wdl.values()) != PRIMARY_GAMES:
        raise ValueError("primary WDL cardinality drift")
    d3_tel = finalize_telemetry(d3_tel)
    control_tel = finalize_telemetry(control_tel)
    d3_calls_positive = int(d3_tel.get("d3_feature_calls", 0)) > 0

    technical_valid = harness_pass and d3_calls_positive
    established = (
        technical_valid
        and d3_score > 0.5
        and float(boot["elo_ci95"][0]) > 0.0
    )
    if not technical_valid:
        verdict = "D3_RUNTIME_EQUAL_NODE_INVALID_V1"
        reason = "identical-control harness or D3 treatment-exercise invariant failed"
    elif established:
        verdict = "D3_RUNTIME_EQUAL_NODE_ESTABLISHED_V1"
        reason = "paired exact-node score and bootstrap Elo LCB are positive with harness/support gates passing"
    else:
        verdict = "D3_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1"
        reason = "preregistered equal-node scientific strength gate did not pass"

    out = {
        "schema": "jass.d3.runtime_equal_node_terminal.v1",
        "verdict": verdict,
        "reason": reason,
        "code_sha": a.code_sha,
        "science": {
            "treatment": "D3_RELATIONAL_ACTION_MOVE_ORDERING_ONLY",
            "value": "WDL_CONTROL coefficient 1.0 byte-identical",
            "adapter_sha256": ADAPTER_SHA,
            "adapter_width": 632,
            "canonicalization": "1..50; white parent STM => 51-sq",
            "node_budget_per_move": NODE_BUDGET,
            "threads": 1,
            "book": "OFF",
            "max_plies": 160,
        },
        "primary": {
            "openings": PRIMARY_OPENINGS,
            "games": PRIMARY_GAMES,
            "wins": wdl["W"], "draws": wdl["D"], "losses": wdl["L"],
            "score_d3": d3_score,
            "elo_d3": d3_elo,
            "candidate_telemetry": d3_tel,
            "control_telemetry": control_tel,
        },
        "harness": {
            "openings": HARNESS_OPENINGS,
            "games": HARNESS_GAMES,
            "arm_a_score": harness_score,
            "complementarity_failures": complement_failures,
            "passed": harness_pass,
        },
        "bootstrap": boot,
        "gates": {
            "harness_control_control_exact": harness_pass,
            "support_preflight_authenticated": True,
            "d3_feature_calls_positive": d3_calls_positive,
            "point_score_gt_half": d3_score > 0.5,
            "elo_lcb95_gt_zero": float(boot["elo_ci95"][0]) > 0.0,
            "skipped_games_zero": True,
        },
        "fits": 0,
        "model_searches": 0,
        "teacher_searches": 0,
        "qscore_reads": 0,
        "search_decision_trace_reads": 0,
        "full_ladder_1843_reads": 0,
        "strength_games": PRIMARY_GAMES + HARNESS_GAMES,
        "promotion_authorized": False,
        "bake_authorized": False,
        "next_stage": ("D3_RUNTIME_EQUAL_TIME" if established else ("STOP_TECHNICAL" if not technical_valid else "STOP")),
    }
    a.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
