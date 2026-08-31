#!/usr/bin/env python3
"""Preregistered joint E2 readout for T3/F6 transfer.

Primary estimand:
  delta_info = Elo(C1) + log2(r_nodes_E1) * Elo(C2_hi_vs_lo)
with a 200000-replicate joint opening-pair/E1-root bootstrap.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

BOOTSTRAP_REPS = 200000
BOOTSTRAP_SEED = 2026100103
EXPECTED_GAMES = {"C1": 1500, "C2": 800, "C3": 400}
EXPECTED_OPENINGS = {"C1": 750, "C2": 400, "C3": 200}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def elo_scalar(p: float) -> float:
    require(0.0 < p < 1.0, "Elo endpoint")
    return 400.0 * math.log10(p / (1.0 - p))


def elo_array(p: np.ndarray) -> np.ndarray:
    return 400.0 * np.log10(p / (1.0 - p))


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pair_scores(paths: list[Path], cell: str) -> tuple[np.ndarray, dict[str, int]]:
    rows: dict[int, dict[int, float]] = defaultdict(dict)
    outcomes = {"white_win": 0, "black_win": 0, "draw": 0}
    seen_games = 0
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            idx = int(row["opening_index"])
            leg = int(row["leg"])
            score = float(row["a_score"])
            require(leg in (0, 1), f"{cell} leg drift")
            require(score in (0.0, 0.5, 1.0), f"{cell} score drift")
            require(leg not in rows[idx], f"{cell} duplicate opening/leg")
            rows[idx][leg] = score
            outcome = str(row["outcome"])
            require(outcome in outcomes, f"{cell} outcome drift")
            outcomes[outcome] += 1
            seen_games += 1
    require(seen_games == EXPECTED_GAMES[cell],
            f"{cell} games {seen_games} != {EXPECTED_GAMES[cell]}")
    require(len(rows) == EXPECTED_OPENINGS[cell],
            f"{cell} openings {len(rows)} != {EXPECTED_OPENINGS[cell]}")
    require(set(rows) == set(range(EXPECTED_OPENINGS[cell])),
            f"{cell} opening index coverage drift")
    values = []
    for idx in range(EXPECTED_OPENINGS[cell]):
        require(set(rows[idx]) == {0, 1}, f"{cell} pair incomplete at {idx}")
        values.append((rows[idx][0] + rows[idx][1]) / 2.0)
    return np.asarray(values, dtype=np.float64), outcomes


def report_totals(paths: list[Path], cell: str) -> dict:
    games = skipped = complement = 0
    out: dict[str, dict[str, int]] = {
        "a_search": defaultdict(int), "b_search": defaultdict(int)
    }
    fields = ("searches", "nodes", "eval_calls", "wall_ns", "completed_depth_sum",
              "effective_depth_sum", "cache_lookups", "cache_hits", "cache_misses",
              "cache_replacements", "extract_f6_executions")
    for path in paths:
        row = load_json(path)
        require(row.get("schema") == "jass.t3_f6_e2_equal_nodes.v1", f"{cell} report schema")
        require(row.get("mode") == "cell_run" and row.get("cell") == cell, f"{cell} report mode")
        require(row.get("threads") == 1 and row.get("book") == "OFF", f"{cell} runtime contract")
        require(row.get("movetime_ms") == 0 and row.get("node_limit_mode") == "exact", f"{cell} node contract")
        require(row.get("tt_mb") == 16 and row.get("game_timeout_ms") == 60000, f"{cell} timeout/TT")
        games += int(row.get("games", -1))
        skipped += int(row.get("game_skipped", -1))
        complement += int(row.get("paired_complementarity_failures", -1))
        for arm in ("a_search", "b_search"):
            src = row.get(arm, {})
            for field in fields:
                out[arm][field] += int(src.get(field, 0))
    require(games == EXPECTED_GAMES[cell], f"{cell} report game total drift")
    return {
        "games": games,
        "game_skipped": skipped,
        "paired_complementarity_failures": complement,
        "a_search": dict(out["a_search"]),
        "b_search": dict(out["b_search"]),
    }


def search_diagnostics(totals: dict) -> dict:
    result = {}
    for arm in ("a_search", "b_search"):
        t = totals[arm]
        searches = t["searches"]
        wall = t["wall_ns"]
        result[arm] = {
            **t,
            "nps": 0.0 if wall == 0 else t["nodes"] * 1.0e9 / wall,
            "mean_completed_depth": 0.0 if searches == 0 else t["completed_depth_sum"] / searches,
            "mean_effective_depth": 0.0 if searches == 0 else t["effective_depth_sum"] / searches,
            "cache_hit_rate": 0.0 if t["cache_lookups"] == 0 else t["cache_hits"] / t["cache_lookups"],
        }
    return result


def percentile(values: np.ndarray) -> list[float]:
    q = np.percentile(values, [2.5, 97.5])
    return [float(q[0]), float(q[1])]


def main() -> int:
    parser = argparse.ArgumentParser()
    for cell in ("c1", "c2", "c3"):
        parser.add_argument(f"--{cell}-games", type=Path, action="append", required=True)
        parser.add_argument(f"--{cell}-report", type=Path, action="append", required=True)
    parser.add_argument("--e1-profile", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    c1_pairs, c1_outcomes = pair_scores(args.c1_games, "C1")
    c2_pairs, c2_outcomes = pair_scores(args.c2_games, "C2")
    c3_pairs, c3_outcomes = pair_scores(args.c3_games, "C3")
    c1_tot = report_totals(args.c1_report, "C1")
    c2_tot = report_totals(args.c2_report, "C2")
    c3_tot = report_totals(args.c3_report, "C3")

    e1 = load_json(args.e1_profile)
    require(e1.get("schema") == "jass.t3_f6_e1_cost_profile.v1", "E1 profile schema drift")
    roots = e1.get("root_rows")
    require(isinstance(roots, list) and len(roots) == 128, "E1 root support drift")
    e1_t3 = np.asarray([int(r["t3_nodes"]) for r in roots], dtype=np.float64)
    e1_cur = np.asarray([int(r["curriculum_nodes"]) for r in roots], dtype=np.float64)
    require(np.all(e1_t3 > 0) and np.all(e1_cur > 0), "E1 node rows invalid")
    r_nodes = float(e1_t3.sum() / e1_cur.sum())
    require(math.isfinite(r_nodes) and r_nodes > 0, "E1 nodes ratio invalid")
    require(abs(r_nodes - 2.023410) < 5e-6, "E1 nodes ratio terminal marker drift")

    point_c1 = float(c1_pairs.mean())
    point_c2 = float(c2_pairs.mean())
    point_c3 = float(c3_pairs.mean())

    harness_reasons: list[str] = []
    if c1_tot["game_skipped"] != 0 or c2_tot["game_skipped"] != 0 or c3_tot["game_skipped"] != 0:
        harness_reasons.append("GAME_SKIPPED_NONZERO")
    if point_c3 != 0.5 or c3_tot["paired_complementarity_failures"] != 0 \
            or np.any(c3_pairs != 0.5):
        harness_reasons.append("C3_EXACT_SYMMETRY_FAILED")
    if point_c1 in (0.0, 1.0) or point_c2 in (0.0, 1.0):
        harness_reasons.append("POINT_ELO_ENDPOINT")

    bootstrap = None
    if not harness_reasons:
        # Frozen implementation of the preregistered same-seed substreams: spawn
        # exactly three child streams in C1/C2/E1 order, once.
        seed_sequence = np.random.SeedSequence(BOOTSTRAP_SEED)
        child_c1, child_c2, child_e1 = seed_sequence.spawn(3)
        rng_c1 = np.random.default_rng(child_c1)
        rng_c2 = np.random.default_rng(child_c2)
        rng_e1 = np.random.default_rng(child_e1)

        elo1_chunks: list[np.ndarray] = []
        elo2_chunks: list[np.ndarray] = []
        ratio_chunks: list[np.ndarray] = []
        delta_chunks: list[np.ndarray] = []
        invalid = 0
        chunk = 2000
        for start in range(0, BOOTSTRAP_REPS, chunk):
            n = min(chunk, BOOTSTRAP_REPS - start)
            ix1 = rng_c1.integers(0, len(c1_pairs), size=(n, len(c1_pairs)))
            ix2 = rng_c2.integers(0, len(c2_pairs), size=(n, len(c2_pairs)))
            ixr = rng_e1.integers(0, len(e1_t3), size=(n, len(e1_t3)))
            p1 = c1_pairs[ix1].mean(axis=1)
            p2 = c2_pairs[ix2].mean(axis=1)
            rr = e1_t3[ixr].sum(axis=1) / e1_cur[ixr].sum(axis=1)
            valid = (p1 > 0.0) & (p1 < 1.0) & (p2 > 0.0) & (p2 < 1.0) \
                    & np.isfinite(rr) & (rr > 0.0)
            invalid += int((~valid).sum())
            if np.any(valid):
                e1v = elo_array(p1[valid])
                e2v = elo_array(p2[valid])
                rrv = rr[valid]
                dv = e1v + np.log2(rrv) * e2v
                elo1_chunks.append(e1v)
                elo2_chunks.append(e2v)
                ratio_chunks.append(rrv)
                delta_chunks.append(dv)

        invalid_fraction = invalid / BOOTSTRAP_REPS
        if invalid_fraction > 0.025:
            harness_reasons.append("BOOTSTRAP_ELO_ENDPOINT_FRACTION_GT_2P5")
        else:
            b_elo1 = np.concatenate(elo1_chunks)
            b_elo2 = np.concatenate(elo2_chunks)
            b_ratio = np.concatenate(ratio_chunks)
            b_delta = np.concatenate(delta_chunks)
            elo_c1 = elo_scalar(point_c1)
            slope_c2 = elo_scalar(point_c2)
            h0_c1 = -math.log2(r_nodes) * slope_c2
            delta_info = elo_c1 - h0_c1
            bootstrap = {
                "replicates": BOOTSTRAP_REPS,
                "seed": BOOTSTRAP_SEED,
                "substream_derivation": "numpy.SeedSequence(2026100103).spawn(3): C1,C2,E1",
                "invalid_endpoint_replicates": invalid,
                "invalid_endpoint_fraction": invalid_fraction,
                "valid_replicates": int(len(b_delta)),
                "elo_c1": elo_c1,
                "elo_c1_ci95": percentile(b_elo1),
                "slope_c2": slope_c2,
                "slope_c2_ci95": percentile(b_elo2),
                "r_nodes": r_nodes,
                "r_nodes_ci95": percentile(b_ratio),
                "h0_c1": h0_c1,
                "delta_info": delta_info,
                "delta_info_ci95": percentile(b_delta),
            }

    if harness_reasons:
        verdict = "E2_INCONCLUSIVE_HARNESS"
        e3_authorized = False
    elif bootstrap is None:
        raise AssertionError("bootstrap missing without harness reason")
    elif bootstrap["slope_c2_ci95"][0] <= 0.0:
        verdict = "E2_INCONCLUSIVE_HARNESS"
        harness_reasons.append("C2_SLOPE_CI_LOW_NOT_POSITIVE")
        e3_authorized = False
    elif bootstrap["delta_info_ci95"][0] > 0.0:
        verdict = "E2_F6_INFORMATION_VALUE_ESTABLISHED"
        e3_authorized = True
    else:
        verdict = "E2_F6_INFORMATION_VALUE_NOT_ESTABLISHED"
        e3_authorized = False

    payload = {
        "schema": "jass.t3_f6_e2_joint_readout.v1",
        "verdict": verdict,
        "e3_authorized_by_e2_gate": e3_authorized,
        "strength_games": sum(EXPECTED_GAMES.values()),
        "fit_runs": 0,
        "retunes": 0,
        "calibrations": 0,
        "d1": False,
        "bake": False,
        "promotion_authorized": False,
        "pool2_v4": False,
        "cells": {
            "C1": {"openings": 750, "games": 1500, "score": point_c1,
                   "outcomes": c1_outcomes, "diagnostics": search_diagnostics(c1_tot)},
            "C2": {"openings": 400, "games": 800, "score_hi": point_c2,
                   "outcomes": c2_outcomes, "diagnostics": search_diagnostics(c2_tot)},
            "C3": {"openings": 200, "games": 400, "score_a": point_c3,
                   "outcomes": c3_outcomes,
                   "paired_complementarity_failures": c3_tot["paired_complementarity_failures"],
                   "diagnostics": search_diagnostics(c3_tot)},
        },
        "game_skipped_total": c1_tot["game_skipped"] + c2_tot["game_skipped"] + c3_tot["game_skipped"],
        "harness_reasons": harness_reasons,
        "bootstrap": bootstrap,
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
