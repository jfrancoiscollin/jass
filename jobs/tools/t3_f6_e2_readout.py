#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

BOOTSTRAP_SEED = 2026100103
BOOTSTRAP = 200000


def elo(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError("Elo probability at boundary")
    return 400.0 * math.log10(p / (1.0 - p))


def load_pairs(paths: list[Path], expected_openings: int) -> np.ndarray:
    legs: dict[tuple[int, int], float] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = int(row["opening_index"])
            leg = int(row["leg"])
            score = float(row["a_score"])
            if leg not in (0, 1) or score not in (0.0, 0.5, 1.0):
                raise ValueError("bad E2 game row")
            if (key, leg) in legs:
                raise ValueError("duplicate E2 game leg")
            legs[(key, leg)] = score
    indices = sorted({key for key, _ in legs})
    if len(indices) != expected_openings or indices != list(range(expected_openings)):
        raise ValueError("E2 opening coverage drift")
    return np.array(
        [(legs[(i, 0)] + legs[(i, 1)]) / 2.0 for i in indices], dtype=np.float64
    )


def _empty_search_totals() -> dict[str, int]:
    return {
        "searches": 0,
        "nodes": 0,
        "eval_calls": 0,
        "wall_ns": 0,
        "completed_depth_sum": 0,
        "effective_depth_sum": 0,
        "cache_lookups": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "cache_replacements": 0,
        "extract_f6_executions": 0,
    }


def _add_search_totals(dst: dict[str, int], src: dict[str, object]) -> None:
    for key in dst:
        dst[key] += int(src.get(key, 0))


def _search_payload(total: dict[str, int]) -> dict[str, object]:
    searches = total["searches"]
    wall_ns = total["wall_ns"]
    lookups = total["cache_lookups"]
    return {
        **total,
        "nps": (total["nodes"] * 1.0e9 / wall_ns) if wall_ns else 0.0,
        "mean_completed_depth": (total["completed_depth_sum"] / searches) if searches else 0.0,
        "mean_effective_depth": (total["effective_depth_sum"] / searches) if searches else 0.0,
        "eval_calls_per_search": (total["eval_calls"] / searches) if searches else 0.0,
        "cache_hit_rate": (total["cache_hits"] / lookups) if lookups else 0.0,
    }


def sum_reports(paths: list[Path], cell: str) -> dict[str, object]:
    total = {
        "games": 0,
        "skipped": 0,
        "complement": 0,
        "a_wins": 0,
        "b_wins": 0,
        "draws": 0,
        "wall_ns": 0,
        "max_game_wall_ns": 0,
        "a_search": _empty_search_totals(),
        "b_search": _empty_search_totals(),
    }
    for path in paths:
        row = json.loads(path.read_text(encoding="utf-8"))
        if (
            row.get("schema") != "jass.t3_f6_e2_equal_nodes.v1"
            or row.get("mode") != "cell_run"
            or row.get("cell") != cell
            or row.get("threads") != 1
            or row.get("book") != "OFF"
            or row.get("movetime_ms") != 0
            or row.get("node_limit_mode") != "exact"
            or row.get("tt_mb") != 16
            or row.get("cache_o1_t3") != "ON_COLD_PER_ROOT"
        ):
            raise ValueError("E2 shard report drift")
        total["games"] += int(row["games"])
        total["skipped"] += int(row["game_skipped"])
        total["complement"] += int(row["paired_complementarity_failures"])
        total["a_wins"] += int(row["a_wins"])
        total["b_wins"] += int(row["b_wins"])
        total["draws"] += int(row["draws"])
        total["wall_ns"] += int(row["wall_ns_total"])
        total["max_game_wall_ns"] = max(
            int(total["max_game_wall_ns"]), int(row["max_game_wall_ns"])
        )
        _add_search_totals(total["a_search"], row.get("a_search", {}))
        _add_search_totals(total["b_search"], row.get("b_search", {}))
    total["a_search"] = _search_payload(total["a_search"])
    total["b_search"] = _search_payload(total["b_search"])
    return total


def e1_rows(path: Path) -> tuple[np.ndarray, np.ndarray, float]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if (
        report.get("schema") != "jass.t3_f6_e1_cost_profile.v1"
        or report.get("root_count") != 128
        or report.get("depth") != 9
        or report.get("threads") != 1
        or report.get("cache_o1") != "OFF"
    ):
        raise ValueError("E1 profile contract drift")
    rows = report.get("root_rows", [])
    if len(rows) != 128:
        raise ValueError("E1 root rows drift")
    t3 = np.array([int(row["t3_nodes"]) for row in rows], dtype=np.float64)
    curriculum = np.array(
        [int(row["curriculum_nodes"]) for row in rows], dtype=np.float64
    )
    ratio = float(t3.sum() / curriculum.sum())
    published = float(report.get("nodes_ratio_t3_over_curriculum", float("nan")))
    if not math.isfinite(ratio) or ratio <= 0 or not math.isclose(
        ratio, published, rel_tol=0.0, abs_tol=5e-15
    ):
        raise ValueError(f"E1 ratio drift {ratio} vs {published}")
    return t3, curriculum, ratio


def bootstrap(
    c1: np.ndarray,
    c2: np.ndarray,
    t3_nodes: np.ndarray,
    curriculum_nodes: np.ndarray,
    *,
    samples: int = BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, object]:
    rng = np.random.Generator(np.random.PCG64(seed))
    n1, n2, nr = len(c1), len(c2), len(t3_nodes)
    elo1_valid: list[np.ndarray] = []
    slope_valid: list[np.ndarray] = []
    ratio_valid: list[np.ndarray] = []
    h0_valid: list[np.ndarray] = []
    delta_valid: list[np.ndarray] = []
    invalid = 0
    chunk = 2000
    for start in range(0, samples, chunk):
        m = min(chunk, samples - start)
        i1 = rng.integers(0, n1, size=(m, n1), endpoint=False)
        i2 = rng.integers(0, n2, size=(m, n2), endpoint=False)
        ir = rng.integers(0, nr, size=(m, nr), endpoint=False)
        p1 = c1[i1].mean(axis=1)
        p2 = c2[i2].mean(axis=1)
        rr = t3_nodes[ir].sum(axis=1) / curriculum_nodes[ir].sum(axis=1)
        valid = (p1 > 0) & (p1 < 1) & (p2 > 0) & (p2 < 1) & np.isfinite(rr) & (rr > 0)
        invalid += int((~valid).sum())
        if not np.any(valid):
            continue
        p1v, p2v, rrv = p1[valid], p2[valid], rr[valid]
        e1 = 400.0 * np.log10(p1v / (1.0 - p1v))
        e2 = 400.0 * np.log10(p2v / (1.0 - p2v))
        h0 = -np.log2(rrv) * e2
        delta = e1 - h0
        elo1_valid.append(e1)
        slope_valid.append(e2)
        ratio_valid.append(rrv)
        h0_valid.append(h0)
        delta_valid.append(delta)
    if not elo1_valid:
        raise ValueError("E2 bootstrap has no valid replicates")
    arrays = {
        "elo_c1": np.concatenate(elo1_valid),
        "slope_c2": np.concatenate(slope_valid),
        "r_nodes": np.concatenate(ratio_valid),
        "h0_c1": np.concatenate(h0_valid),
        "delta_info": np.concatenate(delta_valid),
    }
    def ci(values: np.ndarray) -> list[float]:
        return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]
    return {
        "samples": samples,
        "seed": seed,
        "prng": "NumPy PCG64",
        "subflow_order": ["C1", "C2", "E1"],
        "invalid_replicates": invalid,
        "invalid_fraction": invalid / samples,
        "valid_replicates": int(arrays["elo_c1"].size),
        "elo_c1_ci95": ci(arrays["elo_c1"]),
        "slope_c2_ci95": ci(arrays["slope_c2"]),
        "r_nodes_ci95": ci(arrays["r_nodes"]),
        "h0_c1_ci95": ci(arrays["h0_c1"]),
        "delta_info_ci95": ci(arrays["delta_info"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    for cell in ("c1", "c2", "c3"):
        parser.add_argument(f"--{cell}-games", type=Path, action="append", required=True)
        parser.add_argument(f"--{cell}-report", type=Path, action="append", required=True)
    parser.add_argument("--e1-profile", type=Path, required=True)
    parser.add_argument("--pool-provenance", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    provenance = json.loads(args.pool_provenance.read_text(encoding="utf-8"))
    if (
        provenance.get("verdict") != "E2_FRESH_POOL_READY"
        or provenance.get("selected_openings") != 1350
        or provenance.get("forbidden_overlap") != 0
        or provenance.get("inter_cell_overlap") != 0
        or provenance.get("generation_seed") != 2026100101
        or provenance.get("selection_seed") != 2026100102
        or provenance.get("execution_seed") != 2026100104
        or provenance.get("score_reads") != 0
        or provenance.get("wdl_reads") != 0
        or provenance.get("deep_label_reads") != 0
    ):
        raise ValueError("E2 pool provenance drift")

    c1 = load_pairs(args.c1_games, 750)
    c2 = load_pairs(args.c2_games, 400)
    c3 = load_pairs(args.c3_games, 200)
    s1 = sum_reports(args.c1_report, "C1")
    s2 = sum_reports(args.c2_report, "C2")
    s3 = sum_reports(args.c3_report, "C3")
    if (s1["games"], s2["games"], s3["games"]) != (1500, 800, 400):
        raise ValueError("E2 game volume drift")

    t3_nodes, curriculum_nodes, r_nodes = e1_rows(args.e1_profile)
    bootstrap_result = bootstrap(c1, c2, t3_nodes, curriculum_nodes)
    p1, p2, p3 = float(c1.mean()), float(c2.mean()), float(c3.mean())
    observed_boundary = not (0.0 < p1 < 1.0 and 0.0 < p2 < 1.0)
    elo_c1 = slope_c2 = h0_c1 = delta_info = None
    if not observed_boundary:
        elo_c1 = elo(p1)
        slope_c2 = elo(p2)
        h0_c1 = -math.log2(r_nodes) * slope_c2
        delta_info = elo_c1 - h0_c1

    if s1["skipped"] or s2["skipped"] or s3["skipped"]:
        verdict, reason = "E2_INCONCLUSIVE_HARNESS", "GAME_SKIPPED_NONZERO"
    elif s3["complement"] or not np.all(c3 == 0.5) or p3 != 0.5:
        verdict, reason = "E2_INCONCLUSIVE_HARNESS", "C3_HARNESS_GUARD_FAILED"
    elif observed_boundary:
        verdict, reason = "E2_INCONCLUSIVE_HARNESS", "OBSERVED_CELL_SCORE_AT_BOUNDARY"
    elif bootstrap_result["invalid_fraction"] > 0.025:
        verdict, reason = "E2_INCONCLUSIVE_HARNESS", "BOOTSTRAP_BOUNDARY_FRACTION_GT_2P5"
    elif bootstrap_result["slope_c2_ci95"][0] <= 0:
        verdict, reason = "E2_INCONCLUSIVE_HARNESS", "C2_SLOPE_CI_LOW_NOT_POSITIVE"
    elif bootstrap_result["delta_info_ci95"][0] > 0:
        verdict, reason = "E2_F6_INFORMATION_VALUE_ESTABLISHED", "DELTA_INFO_CI_LOW_POSITIVE"
    else:
        verdict, reason = "E2_F6_INFORMATION_VALUE_NOT_ESTABLISHED", "DELTA_INFO_CI_LOW_NOT_POSITIVE"

    payload = {
        "schema": "jass.t3_f6_e2_terminal.v1",
        "code_sha": args.code_sha,
        "verdict": verdict,
        "reason": reason,
        "e3_authorized_by_e2": verdict == "E2_F6_INFORMATION_VALUE_ESTABLISHED",
        "cells": {
            "C1": {"openings": 750, "games": 1500, "a_score": p1, "elo_c1": elo_c1, **s1},
            "C2": {"openings": 400, "games": 800, "hi_score": p2, "slope_c2": slope_c2, **s2},
            "C3": {"openings": 200, "games": 400, "a_score": p3, **s3},
        },
        "r_nodes": r_nodes,
        "h0_c1": h0_c1,
        "delta_info": delta_info,
        "bootstrap": bootstrap_result,
        "game_skipped_total": int(s1["skipped"] + s2["skipped"] + s3["skipped"]),
        "strength_games": 2700,
        "fit_runs": 0,
        "bake": False,
        "promotion_authorized": False,
        "pool2_v4_authorized": False,
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
