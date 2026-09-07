#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

VERDICT = "D3_RUNTIME_TERMINAL_AUTOPSY_COMPLETE_V1"
SOURCE_VERDICT = "D3_RUNTIME_EQUAL_NODE_NOT_ESTABLISHED_V1"
PAIR_SCHEMA = "jass.d3.runtime_equal_node.game_pair.v1"
NODE_BUDGET = 20000
MAX_PLIES = 160
PRIMARY_PAIRS = 750
HARNESS_PAIRS = 100


def read_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    value = json.loads(line)
                    if type(value) is not dict:
                        raise ValueError(f"{path}: non-object JSONL row")
                    rows.append(value)
    return rows


def q(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * p
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return float(xs[lo])
    frac = pos - lo
    return float(xs[lo] * (1.0 - frac) + xs[hi] * frac)


def summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None,
                "p05": None, "p25": None, "p75": None, "p95": None}
    return {
        "count": len(values),
        "mean": float(statistics.fmean(values)),
        "median": float(statistics.median(values)),
        "p05": q(values, 0.05), "p25": q(values, 0.25),
        "p75": q(values, 0.75), "p95": q(values, 0.95),
    }


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        r = (i + 1 + j) / 2.0
        for k in range(i, j):
            out[order[k]] = r
        i = j
    return out


def pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 2:
        return None
    ma = statistics.fmean(a); mb = statistics.fmean(b)
    da = [x - ma for x in a]; db = [x - mb for x in b]
    va = sum(x*x for x in da); vb = sum(x*x for x in db)
    if va == 0 or vb == 0:
        return None
    return float(sum(x*y for x, y in zip(da, db)) / math.sqrt(va * vb))


def spearman(a: list[float], b: list[float]) -> float | None:
    return pearson(ranks(a), ranks(b))


def pieces_from_fen(fen: str) -> int:
    parts = fen.split(":")
    if len(parts) < 3:
        raise ValueError(f"bad FEN: {fen}")
    count = 0
    for chunk in parts[1:]:
        if not chunk:
            continue
        rest = chunk[1:]
        for token in rest.split(","):
            token = token.strip().removeprefix("K")
            if not token:
                continue
            if "-" in token:
                lo, hi = map(int, token.split("-", 1))
                count += hi - lo + 1
            else:
                count += 1
    return count


def phase_from_fen(fen: str) -> str:
    pieces = pieces_from_fen(fen)
    if pieces >= 30:
        return "P0"
    if pieces >= 20:
        return "P1"
    return "OUT_OF_FROZEN_OPENING_SUPPORT"


def per_search(t: dict[str, Any], key: str) -> float:
    searches = int(t.get("searches", 0))
    return float(t.get(key, 0)) / searches if searches else 0.0


def game_metrics(game: dict[str, Any], phase: str) -> dict[str, Any]:
    d3 = game["d3_telemetry"]; ctl = game["control_telemetry"]
    d3_wall = per_search(d3, "wall_seconds")
    ctl_wall = per_search(ctl, "wall_seconds")
    depth_delta = float(d3["mean_completed_depth"]) - float(ctl["mean_completed_depth"])
    return {
        "score": float(game["d3_score"]),
        "wdl": game["d3_wdl"],
        "color": game["d3_color"],
        "phase": phase,
        "plies": float(game["plies"]),
        "reason": game["reason"],
        "depth_delta": depth_delta,
        "nodes_per_search_delta": per_search(d3, "nodes") - per_search(ctl, "nodes"),
        "eval_calls_per_search_delta": per_search(d3, "eval_calls") - per_search(ctl, "eval_calls"),
        "wall_ms_per_search_delta": 1000.0 * (d3_wall - ctl_wall),
        "wall_ratio": d3_wall / ctl_wall if ctl_wall > 0 else None,
        "d3_feature_calls_per_search": per_search(d3, "d3_feature_calls"),
    }


def numeric_view(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ("score", "plies", "depth_delta", "nodes_per_search_delta",
              "eval_calls_per_search_delta", "wall_ms_per_search_delta",
              "wall_ratio", "d3_feature_calls_per_search")
    out: dict[str, Any] = {}
    for field in fields:
        vals = [float(row[field]) for row in rows if row.get(field) is not None]
        out[field] = summary(vals)
    return out


def grouped(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    return {name: numeric_view(items) for name, items in sorted(groups.items())}


def validate_pair(row: dict[str, Any], mode: str) -> None:
    if row.get("schema") != PAIR_SCHEMA or row.get("mode") != mode:
        raise ValueError(f"{mode} pair schema/mode drift")
    if row.get("node_budget") != NODE_BUDGET or row.get("max_plies") != MAX_PLIES:
        raise ValueError(f"{mode} node/max-plies drift")
    games = row.get("games")
    if type(games) is not list or len(games) != 2:
        raise ValueError(f"{mode} pair game cardinality drift")


def sum_telemetry(games: list[dict[str, Any]], key: str) -> dict[str, float]:
    fields = ("searches", "depth_sum", "nodes", "eval_calls", "d3_feature_calls")
    out = {field: 0.0 for field in fields}
    for game in games:
        t = game[key]
        for field in fields:
            out[field] += float(t.get(field, 0))
    return out


def autopsy(primary: list[dict[str, Any]], harness: list[dict[str, Any]],
            source: dict[str, Any], pool: dict[str, Any]) -> dict[str, Any]:
    if source.get("verdict") != SOURCE_VERDICT or source.get("next_stage") != "STOP":
        raise ValueError("source terminal verdict/stop drift")
    if source.get("strength_games") != 1700 or source.get("fits") != 0:
        raise ValueError("source side-effect drift")
    if len(primary) != PRIMARY_PAIRS or len(harness) != HARNESS_PAIRS:
        raise ValueError("pair cardinality drift")
    for row in primary: validate_pair(row, "primary")
    for row in harness: validate_pair(row, "harness")
    for mode, rows in (("primary", primary), ("harness", harness)):
        ids = [int(row["opening_index"]) for row in rows]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{mode} duplicate opening index")
    if pool.get("verdict") != "D3_RUNTIME_EQUAL_NODE_POOL_READY_V1" \
            or pool.get("primary_openings") != PRIMARY_PAIRS \
            or pool.get("harness_openings") != HARNESS_PAIRS:
        raise ValueError("pool provenance drift")

    primary_games = [g for row in primary for g in row["games"]]
    harness_games = [g for row in harness for g in row["games"]]
    wins = sum(g["d3_wdl"] == "W" for g in primary_games)
    draws = sum(g["d3_wdl"] == "D" for g in primary_games)
    losses = sum(g["d3_wdl"] == "L" for g in primary_games)
    score = statistics.fmean(float(g["d3_score"]) for g in primary_games)
    sealed = source["primary"]
    if (wins, draws, losses) != (sealed["wins"], sealed["draws"], sealed["losses"]):
        raise ValueError("primary WDL reconstruction drift")
    if not math.isclose(score, float(sealed["score_d3"]), rel_tol=0, abs_tol=1e-15):
        raise ValueError("primary score reconstruction drift")

    d3_total = sum_telemetry(primary_games, "d3_telemetry")
    ctl_total = sum_telemetry(primary_games, "control_telemetry")
    for observed, expected, label in (
        (d3_total, sealed["candidate_telemetry"], "candidate"),
        (ctl_total, sealed["control_telemetry"], "control"),
    ):
        for key in ("searches", "depth_sum", "nodes", "eval_calls", "d3_feature_calls"):
            if int(observed[key]) != int(expected.get(key, 0)):
                raise ValueError(f"{label} telemetry reconstruction drift {key}")

    harness_score = statistics.fmean(
        float(g["arm_a_score"]) for g in harness_games
    )
    if not math.isclose(harness_score, 0.5, rel_tol=0, abs_tol=1e-15):
        raise ValueError("harness aggregate not exactly neutral")

    game_rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    metric_names = ("depth_delta", "nodes_per_search_delta",
                    "eval_calls_per_search_delta", "wall_ms_per_search_delta",
                    "wall_ratio", "d3_feature_calls_per_search")
    for pair in primary:
        phase = phase_from_fen(pair["fen"])
        gm = [game_metrics(g, phase) for g in pair["games"]]
        game_rows.extend(gm)
        prow: dict[str, Any] = {"score": float(pair["pair_score_d3"])}
        for name in metric_names:
            vals = [float(g[name]) for g in gm if g.get(name) is not None]
            prow[name] = statistics.fmean(vals) if vals else None
        pair_rows.append(prow)

    pair_scores = [float(row["score"]) for row in pair_rows]
    associations = {}
    for name in metric_names:
        xs = [float(row[name]) for row in pair_rows if row.get(name) is not None]
        ys = [pair_scores[i] for i, row in enumerate(pair_rows) if row.get(name) is not None]
        associations[name] = {"spearman_rho_with_pair_score": spearman(ys, xs),
                              "pairs": len(xs)}

    overall = numeric_view(game_rows)
    by_color = grouped(game_rows, "color")
    by_phase = grouped(game_rows, "phase")
    by_wdl = grouped(game_rows, "wdl")
    by_reason = grouped(game_rows, "reason")
    depth_degraded = score < 0.5 and float(overall["depth_delta"]["mean"]) < 0.0
    runtime_cost = float(overall["wall_ratio"]["mean"]) > 1.0
    broad_color = all(float(view["score"]["mean"]) < 0.5 for view in by_color.values())
    represented = [view for name, view in by_phase.items() if name in {"P0", "P1"}]
    broad_phase = bool(represented) and all(float(view["score"]["mean"]) < 0.5
                                            for view in represented)
    rho_depth = associations["depth_delta"]["spearman_rho_with_pair_score"]
    if depth_degraded and broad_color and broad_phase:
        classification = "BROAD_EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION"
    elif depth_degraded:
        classification = "EQUAL_NODE_SEARCH_EFFICIENCY_DEGRADATION"
    else:
        classification = "EQUAL_NODE_FAILURE_WITHOUT_MEAN_DEPTH_DEGRADATION"

    return {
        "schema": "jass.d3.runtime_terminal_autopsy.v1",
        "verdict": VERDICT,
        "source": {
            "verdict": source["verdict"],
            "primary_games": 1500,
            "harness_games": 200,
            "primary_score_d3": score,
            "primary_wdl": {"wins": wins, "draws": draws, "losses": losses},
            "harness_score": harness_score,
        },
        "overall": overall,
        "by_wdl": by_wdl,
        "by_color": by_color,
        "by_opening_phase": by_phase,
        "by_terminal_reason": by_reason,
        "pair_associations": associations,
        "flags": {
            "equal_node_depth_efficiency_degraded": depth_degraded,
            "runtime_cost_amplified": runtime_cost,
            "failure_broad_across_color": broad_color,
            "failure_broad_across_opening_phase": broad_phase,
            "depth_delta_tracks_pair_score_positive": rho_depth is not None and rho_depth > 0.0,
        },
        "classification": classification,
        "fits": 0, "model_searches": 0, "teacher_searches": 0,
        "strength_games": 0, "searches": 0, "promotions": 0, "bakes": 0,
        "equal_time_authorized": False,
        "next_stage": "D4_SEARCH_UTILITY_PREREGISTRATION_ONLY",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--primary", type=Path, action="append", required=True)
    p.add_argument("--harness", type=Path, action="append", required=True)
    p.add_argument("--source-summary", type=Path, required=True)
    p.add_argument("--pool-provenance", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    result = autopsy(read_jsonl(a.primary), read_jsonl(a.harness),
                     json.loads(a.source_summary.read_text(encoding="utf-8")),
                     json.loads(a.pool_provenance.read_text(encoding="utf-8")))
    a.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"verdict": result["verdict"],
                      "classification": result["classification"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
