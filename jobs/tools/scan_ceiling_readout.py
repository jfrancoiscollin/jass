#!/usr/bin/env python3
"""Terminal benchmark-only readout for the preregistered Scan ceiling study.

The tool joins immutable sibling-level score shards, applies the exact tie
contract, runs the fixed 200,000-sample parent-cluster bootstrap, and emits
only aggregate science.  It contains no fit, calibration, selection, game,
bake, or promotion path.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


BOOTSTRAP_SAMPLES = 200_000
BOOTSTRAP_SEED = 2026091303
SCAN_BUDGETS = (1_000, 5_000, 50_000, 200_000, 1_000_000, 2_000_000, 5_000_000)
JASS_BUDGETS = (1_000, 5_000, 50_000, 200_000, 1_000_000)
ARTIFACTS = {
    "CURRICULUM": "319d174f4b548b1655aad4bb30d4c6dc86c08dd715c9c23f8b19ba1937dc0be1",
    "D1": "e91a55500713154f50be74db5d699b64d7684e1c078725d09e1d15e713549b49",
    "RF1": "0d26ba50b668160b3da3e247cd4e1bd709c2cb7989b3b5877b9ea7deb34db58b",
    "T3-A": "16e5db8fd78849bba12b158eee5c1da4ab170129d8aeac1b91ab7a40ad9d0bb2",
}
STATIC_NAMES = ("T0", "D1", "RF1", "T3-A")
METRIC_NAMES = (
    "pairwise_primary", "pairwise_strict", "top_hit_primary",
    "top_hit_strict", "kendall_tau_b", "spearman_rho",
)
FORBIDDEN_POLICY_FIELDS = (
    "training_allowed", "tuning_allowed", "calibration_allowed",
    "model_selection_allowed", "runtime_scale_selection_allowed",
)


def open_text(path: Path):
    return gzip.open(path, "rt", encoding="utf-8", newline="") \
        if path.suffix == ".gz" else path.open("r", encoding="utf-8", newline="")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, object]:
    with open_text(path) as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root is not an object")
    return value


def finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def percentile_summary(values: np.ndarray) -> dict[str, object]:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = flat[np.isfinite(flat)]
    if finite.size == 0:
        return {"ci95": [None, None], "bootstrap_valid": 0, "bootstrap_na": int(flat.size)}
    lo, hi = np.percentile(finite, [2.5, 97.5])
    return {
        "ci95": [float(lo), float(hi)],
        "bootstrap_valid": int(finite.size),
        "bootstrap_na": int(flat.size - finite.size),
    }


@dataclass(frozen=True)
class Groups:
    rows: list[dict[str, str]]
    sibling_id: np.ndarray
    parent_id: np.ndarray
    phase: np.ndarray
    stm: np.ndarray
    pieces: np.ndarray
    branching: np.ndarray
    rows_by_parent: dict[int, np.ndarray]


def load_groups(path: Path) -> Groups:
    required = {
        "row_index", "sibling_identity", "parent_id", "parent_phase",
        "parent_stm", "parent_pieces", "parent_legal_moves",
    }
    with open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("sibling group fields drift")
        rows = list(reader)
    count = len(rows)
    if count == 0 or [int(row["row_index"]) for row in rows] != list(range(count)):
        raise ValueError("sibling group row_index drift")
    parent_id = np.asarray([int(row["parent_id"]) for row in rows], dtype=np.int32)
    phase = np.asarray([row["parent_phase"] for row in rows], dtype=object)
    stm = np.asarray([int(row["parent_stm"]) for row in rows], dtype=np.int8)
    pieces = np.asarray([int(row["parent_pieces"]) for row in rows], dtype=np.int16)
    branching = np.asarray([int(row["parent_legal_moves"]) for row in rows], dtype=np.int8)
    sibling_id = np.asarray([row["sibling_identity"] for row in rows], dtype=object)
    if len(set(sibling_id.tolist())) != count:
        raise ValueError("duplicate sibling identity")
    rows_by_parent: dict[int, np.ndarray] = {}
    for pid in sorted(set(parent_id.tolist())):
        indices = np.flatnonzero(parent_id == pid)
        if (indices.size != branching[indices[0]] or np.any(phase[indices] != phase[indices[0]])
                or np.any(stm[indices] != stm[indices[0]])
                or np.any(pieces[indices] != pieces[indices[0]])
                or np.any(branching[indices] != branching[indices[0]])):
            raise ValueError(f"parent metadata/sibling cardinality drift for {pid}")
        rows_by_parent[pid] = indices
    if sorted(rows_by_parent) != list(range(2000)):
        raise ValueError("benchmark parent IDs are not exactly 0..1999")
    if {name: sum(phase[rows_by_parent[pid][0]] == name for pid in rows_by_parent)
            for name in ("P0", "P1", "P2", "P3")} != {name: 500 for name in ("P0", "P1", "P2", "P3")}:
        raise ValueError("parent phase quota drift")
    return Groups(rows, sibling_id, parent_id, phase, stm, pieces, branching, rows_by_parent)


def load_row_ids(path: Path, row_count: int) -> set[int]:
    with open_text(path) as stream:
        values = [int(line.strip()) for line in stream if line.strip()]
    result = set(values)
    if not result or len(result) != len(values) or min(result) < 0 or max(result) >= row_count:
        raise ValueError(f"{path}: invalid row-id set")
    return result


def parent_ids_for_rows(groups: Groups, rows: set[int], expected: int) -> list[int]:
    parents = sorted({int(groups.parent_id[row]) for row in rows})
    if len(parents) != expected:
        raise ValueError(f"subset parent cardinality {len(parents)} != {expected}")
    expected_rows = {int(row) for pid in parents for row in groups.rows_by_parent[pid]}
    if rows != expected_rows:
        raise ValueError("subset row IDs do not contain every sibling of each parent")
    phases = {name: sum(groups.phase[groups.rows_by_parent[pid][0]] == name for pid in parents)
              for name in ("P0", "P1", "P2", "P3")}
    target = expected // 4
    if phases != {name: target for name in phases}:
        raise ValueError("subset phase quota drift")
    return parents


def load_static(path: Path, row_count: int) -> dict[str, np.ndarray]:
    fields = ("row_index", "t0_parent", "d1_parent", "rf1_parent", "t3_a_parent")
    columns = {name: [] for name in fields}
    with open_text(path) as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames != list(fields):
            raise ValueError("static score fields drift")
        for row in reader:
            for field in fields:
                columns[field].append(row[field])
    if len(columns["row_index"]) != row_count \
            or [int(value) for value in columns["row_index"]] != list(range(row_count)):
        raise ValueError("static score row alignment drift")
    result = {
        "T0": np.asarray(columns["t0_parent"], dtype=np.float64),
        "D1": np.asarray(columns["d1_parent"], dtype=np.float64),
        "RF1": np.asarray(columns["rf1_parent"], dtype=np.float64),
        "T3-A": np.asarray(columns["t3_a_parent"], dtype=np.float64),
    }
    if not all(np.all(np.isfinite(value)) for value in result.values()):
        raise ValueError("nonfinite static score")
    return result


def load_long_scores(
    paths: list[Path], row_count: int, expected_rows: set[int], budgets: tuple[int, ...], kind: str,
) -> tuple[dict[int, np.ndarray], dict[str, object]]:
    if not paths:
        raise ValueError(f"no {kind} score shards")
    values: dict[tuple[int, int], float] = {}
    diagnostics: dict[int, dict[str, object]] = {
        budget: {
            "output_rows": 0, "searched_rows": 0,
            "terminal_exact_rows": 0, "tb_exact_rows": 0,
            "searched_nodes": [],
        }
        for budget in budgets
    }
    for path in paths:
        with open_text(path) as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            required = {"row_index", "budget_nodes"}
            score_field = "parent_score" if kind == "jass" else "parent_score_centi"
            required.add(score_field)
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ValueError(f"{path}: {kind} score fields drift")
            for row in reader:
                index = int(row["row_index"]); budget = int(row["budget_nodes"])
                key = (index, budget)
                if index not in expected_rows or budget not in budgets or key in values:
                    raise ValueError(f"{path}: duplicate/out-of-scope {kind} score key {key}")
                score = float(row[score_field])
                if not math.isfinite(score):
                    raise ValueError("nonfinite search score")
                if kind == "jass":
                    nodes = int(row["nodes"])
                    terminal = int(row.get("terminal_exact", "0"))
                    tb_exact = int(row.get("tb_exact", "0"))
                    exact = terminal or tb_exact
                    if (exact and nodes != 0) or (not exact and nodes != budget):
                        raise ValueError("Jass exact-node contract drift")
                else:
                    requested = int(row["requested_nodes"])
                    nodes = int(row["last_info_nodes"])
                    terminal = int(row["terminal_exact"])
                    if requested != budget or (terminal and nodes != 0) \
                            or (not terminal and not 0 < nodes <= budget):
                        raise ValueError("Scan requested/snapshot node contract drift")
                    tb_exact = 0
                    exact = terminal
                diag = diagnostics[budget]
                diag["output_rows"] = int(diag["output_rows"]) + 1
                diag["terminal_exact_rows"] = int(diag["terminal_exact_rows"]) + int(terminal)
                diag["tb_exact_rows"] = int(diag["tb_exact_rows"]) + int(tb_exact)
                if not exact:
                    diag["searched_rows"] = int(diag["searched_rows"]) + 1
                    cast_nodes = diag["searched_nodes"]
                    assert isinstance(cast_nodes, list)
                    cast_nodes.append(nodes)
                values[key] = score
    expected_keys = {(row, budget) for row in expected_rows for budget in budgets}
    if set(values) != expected_keys:
        missing = len(expected_keys - set(values)); extra = len(set(values) - expected_keys)
        raise ValueError(f"{kind} score coverage drift: missing={missing} extra={extra}")
    output: dict[int, np.ndarray] = {}
    for budget in budgets:
        array = np.full(row_count, np.nan, dtype=np.float64)
        for row in expected_rows:
            array[row] = values[(row, budget)]
        output[budget] = array
    by_budget: dict[str, object] = {}
    for budget in budgets:
        diag = diagnostics[budget]
        observed = np.asarray(diag.pop("searched_nodes"), dtype=np.int64)
        searched = int(diag["searched_rows"])
        by_budget[str(budget)] = {
            **diag,
            "requested_budget_nodes": budget,
            "nominal_requested_search_nodes_sum": searched * budget,
            "reported_or_snapshot_nodes_sum": int(np.sum(observed)) if observed.size else 0,
            "reported_or_snapshot_nodes_min": int(np.min(observed)) if observed.size else None,
            "reported_or_snapshot_nodes_max": int(np.max(observed)) if observed.size else None,
            "reported_or_snapshot_nodes_mean": float(np.mean(observed)) if observed.size else None,
            "node_semantics": (
                "exact_reported_search_nodes" if kind == "jass"
                else "last_complete_info_progressive_snapshot_not_total_consumed"
            ),
        }
    return output, {"engine": kind, "by_budget": by_budget}


def average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def spearman_rho(x: np.ndarray, y: np.ndarray) -> float:
    rx = average_ranks(x); ry = average_ranks(y)
    rx -= np.mean(rx); ry -= np.mean(ry)
    denominator = math.sqrt(float(np.dot(rx, rx) * np.dot(ry, ry)))
    return float(np.dot(rx, ry) / denominator) if denominator > 0 else math.nan


def kendall_tau_b(x: np.ndarray, y: np.ndarray) -> float:
    concordant = discordant = ties_x = ties_y = 0
    total = 0
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            total += 1
            dx = int(x[i] > x[j]) - int(x[i] < x[j])
            dy = int(y[i] > y[j]) - int(y[i] < y[j])
            ties_x += int(dx == 0)
            ties_y += int(dy == 0)
            if dx != 0 and dy != 0:
                if dx == dy: concordant += 1
                else: discordant += 1
    denominator = math.sqrt((total - ties_x) * (total - ties_y))
    return (concordant - discordant) / denominator if denominator > 0 else math.nan


@dataclass
class ParentStats:
    parent_ids: list[int]
    signal_names: list[str]
    pair_num: np.ndarray
    pair_den: np.ndarray
    strict_pair_num: np.ndarray
    strict_pair_den: np.ndarray
    top: np.ndarray
    strict_top: np.ndarray
    tau: np.ndarray
    rho: np.ndarray
    siblings: np.ndarray
    pairs_total: np.ndarray
    pairs_tied: np.ndarray


def compute_parent_stats(
    groups: Groups, parent_ids: list[int], reference: np.ndarray,
    signals: dict[str, np.ndarray],
) -> ParentStats:
    names = list(signals)
    n = len(parent_ids); width = len(names)
    pair_num = np.zeros((n, width)); pair_den = np.zeros(n)
    strict_num = np.zeros((n, width)); strict_den = np.zeros(n)
    top = np.full((n, width), np.nan); strict_top = np.full((n, width), np.nan)
    tau = np.full((n, width), np.nan); rho = np.full((n, width), np.nan)
    siblings = np.zeros(n, dtype=np.int32); pairs_total = np.zeros(n, dtype=np.int32)
    pairs_tied = np.zeros(n, dtype=np.int32)
    for pindex, pid in enumerate(parent_ids):
        rows = groups.rows_by_parent[pid]
        ids = groups.sibling_id[rows]
        ref = reference[rows]
        matrix = np.vstack([signals[name][rows] for name in names])
        if not np.all(np.isfinite(ref)) or not np.all(np.isfinite(matrix)):
            raise ValueError(f"missing score in metric scope for parent {pid}")
        siblings[pindex] = len(rows)
        total = len(rows) * (len(rows) - 1) // 2
        pairs_total[pindex] = total; strict_den[pindex] = total
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                ref_delta = ref[i] - ref[j]
                signal_delta = matrix[:, i] - matrix[:, j]
                if ref_delta != 0:
                    pair_den[pindex] += 1
                    oriented = signal_delta * (1.0 if ref_delta > 0 else -1.0)
                    pair_num[pindex] += np.where(oriented > 0, 1.0, np.where(oriented == 0, 0.5, 0.0))
                else:
                    pairs_tied[pindex] += 1
                ref_i_wins = ref_delta > 0 or (ref_delta == 0 and ids[i] < ids[j])
                signal_i_wins = (signal_delta > 0) | ((signal_delta == 0) & (ids[i] < ids[j]))
                strict_num[pindex] += signal_i_wins == ref_i_wins
        ref_top = set(np.flatnonzero(ref == np.max(ref)).tolist())
        ref_strict = min(ref_top, key=lambda index: ids[index])
        for sindex in range(width):
            score = matrix[sindex]
            candidates = np.flatnonzero(score == np.max(score)).tolist()
            choice = min(candidates, key=lambda index: ids[index])
            top[pindex, sindex] = float(choice in ref_top)
            strict_top[pindex, sindex] = float(choice == ref_strict)
            tau[pindex, sindex] = kendall_tau_b(score, ref)
            rho[pindex, sindex] = spearman_rho(score, ref)
    return ParentStats(
        parent_ids, names, pair_num, pair_den, strict_num, strict_den,
        top, strict_top, tau, rho, siblings, pairs_total, pairs_tied,
    )


def ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    out = np.full(np.broadcast_shapes(numerator.shape, denominator.shape), np.nan, dtype=np.float64)
    np.divide(numerator, denominator, out=out, where=denominator > 0)
    return out


def point_metrics(stats: ParentStats) -> dict[str, np.ndarray]:
    def column_nanmean(values: np.ndarray) -> np.ndarray:
        finite = np.isfinite(values)
        counts = np.sum(finite, axis=0)
        return ratio(np.sum(np.where(finite, values, 0.0), axis=0), counts)

    return {
        "pairwise_primary": ratio(np.sum(stats.pair_num, axis=0), np.asarray(np.sum(stats.pair_den))),
        "pairwise_strict": ratio(np.sum(stats.strict_pair_num, axis=0), np.asarray(np.sum(stats.strict_pair_den))),
        "top_hit_primary": np.nanmean(stats.top, axis=0) if len(stats.parent_ids) else np.full(len(stats.signal_names), np.nan),
        "top_hit_strict": np.nanmean(stats.strict_top, axis=0) if len(stats.parent_ids) else np.full(len(stats.signal_names), np.nan),
        "kendall_tau_b": column_nanmean(stats.tau),
        "spearman_rho": column_nanmean(stats.rho),
    }


def bootstrap_metrics(
    stats: ParentStats, rng: np.random.Generator, samples: int, chunk: int = 256,
) -> dict[str, np.ndarray]:
    width = len(stats.signal_names)
    output = {name: np.full((samples, width), np.nan, dtype=np.float64) for name in METRIC_NAMES}
    n = len(stats.parent_ids)
    if n == 0:
        return output
    probabilities = np.full(n, 1.0 / n)
    tau_valid = np.isfinite(stats.tau).astype(np.float64)
    rho_valid = np.isfinite(stats.rho).astype(np.float64)
    tau_values = np.nan_to_num(stats.tau, nan=0.0)
    rho_values = np.nan_to_num(stats.rho, nan=0.0)
    for start in range(0, samples, chunk):
        stop = min(samples, start + chunk)
        counts = rng.multinomial(n, probabilities, size=stop - start).astype(np.float64)
        pair_den = counts @ stats.pair_den
        strict_den = counts @ stats.strict_pair_den
        output["pairwise_primary"][start:stop] = ratio(
            counts @ stats.pair_num, pair_den[:, None],
        )
        output["pairwise_strict"][start:stop] = ratio(
            counts @ stats.strict_pair_num, strict_den[:, None],
        )
        output["top_hit_primary"][start:stop] = (counts @ stats.top) / n
        output["top_hit_strict"][start:stop] = (counts @ stats.strict_top) / n
        output["kendall_tau_b"][start:stop] = ratio(
            counts @ tau_values, counts @ tau_valid,
        )
        output["spearman_rho"][start:stop] = ratio(
            counts @ rho_values, counts @ rho_valid,
        )
    return output


def metric_report(stats: ParentStats, points: dict[str, np.ndarray], boots: dict[str, np.ndarray]) -> dict[str, object]:
    report: dict[str, object] = {}
    for sindex, signal in enumerate(stats.signal_names):
        metrics: dict[str, object] = {}
        for metric in METRIC_NAMES:
            metrics[metric] = {
                "point": finite_or_none(points[metric][sindex]),
                **percentile_summary(boots[metric][:, sindex]),
            }
        metrics["pairwise_primary"].update({
            "raw_numerator": float(np.sum(stats.pair_num[:, sindex])),
            "raw_denominator": int(np.sum(stats.pair_den)),
        })
        metrics["pairwise_strict"].update({
            "raw_numerator": int(np.sum(stats.strict_pair_num[:, sindex])),
            "raw_denominator": int(np.sum(stats.strict_pair_den)),
        })
        metrics["top_hit_primary"].update({
            "raw_numerator": int(np.sum(stats.top[:, sindex])),
            "raw_denominator": len(stats.parent_ids),
        })
        metrics["top_hit_strict"].update({
            "raw_numerator": int(np.sum(stats.strict_top[:, sindex])),
            "raw_denominator": len(stats.parent_ids),
        })
        metrics["kendall_tau_b"]["defined_parents"] = int(np.sum(np.isfinite(stats.tau[:, sindex])))
        metrics["spearman_rho"]["defined_parents"] = int(np.sum(np.isfinite(stats.rho[:, sindex])))
        report[signal] = metrics
    return report


def parent_descriptor(groups: Groups, pid: int) -> tuple[str, int, int, int]:
    row = groups.rows_by_parent[pid][0]
    return str(groups.phase[row]), int(groups.stm[row]), int(groups.branching[row]), int(groups.pieces[row])


def strata_for(groups: Groups, parent_ids: list[int]) -> list[tuple[str, list[int]]]:
    descriptors = {pid: parent_descriptor(groups, pid) for pid in parent_ids}
    result: list[tuple[str, list[int]]] = [("all", list(parent_ids))]
    for phase in ("P0", "P1", "P2", "P3"):
        result.append((f"phase:{phase}", [pid for pid in parent_ids if descriptors[pid][0] == phase]))
    for label, stm in (("white", 0), ("black", 1)):
        result.append((f"colour:{label}", [pid for pid in parent_ids if descriptors[pid][1] == stm]))
    for label, lo, hi in (("2..4", 2, 4), ("5..8", 5, 8), ("9..12", 9, 12), ("13..16", 13, 16)):
        result.append((f"branching:{label}", [pid for pid in parent_ids if lo <= descriptors[pid][2] <= hi]))
    for label, lo, hi in (
        ("9..11", 9, 11), ("12..15", 12, 15), ("16..19", 16, 19),
        ("20..24", 20, 24), ("25..29", 25, 29), ("30..34", 30, 34), ("35..40", 35, 40),
    ):
        result.append((f"pieces:{label}", [pid for pid in parent_ids if lo <= descriptors[pid][3] <= hi]))
    return result


def run_scope(
    name: str, groups: Groups, parent_ids: list[int], reference_name: str,
    reference: np.ndarray,
    signals: dict[str, np.ndarray], rng: np.random.Generator, samples: int,
    retain_global_pair_bootstrap: bool,
) -> tuple[dict[str, object], np.ndarray | None, list[str], dict[str, np.ndarray]]:
    scope: dict[str, object] = {
        "reference": reference_name, "parents": len(parent_ids),
        "signals": list(signals), "strata": {},
    }
    retained: np.ndarray | None = None
    global_points: dict[str, np.ndarray] = {}
    for stratum, ids in strata_for(groups, parent_ids):
        stats = compute_parent_stats(groups, ids, reference, signals)
        points = point_metrics(stats)
        boots = bootstrap_metrics(stats, rng, samples)
        if stratum == "all":
            global_points = points
            if retain_global_pair_bootstrap:
                retained = boots["pairwise_primary"]
        scope["strata"][stratum] = {
            "parents": len(ids),
            "siblings": int(np.sum(stats.siblings)),
            "pairs_total": int(np.sum(stats.pairs_total)),
            "pairs_comparable": int(np.sum(stats.pair_den)),
            "pairs_reference_tied": int(np.sum(stats.pairs_tied)),
            "parents_kendall_defined_by_signal": {
                signal: int(np.sum(np.isfinite(stats.tau[:, index])))
                for index, signal in enumerate(stats.signal_names)
            },
            "parents_spearman_defined_by_signal": {
                signal: int(np.sum(np.isfinite(stats.rho[:, index])))
                for index, signal in enumerate(stats.signal_names)
            },
            "metrics": metric_report(stats, points, boots),
        }
    return scope, retained, list(signals), global_points


def series_summary(point: float, samples: np.ndarray) -> dict[str, object]:
    return {"point": finite_or_none(point), **percentile_summary(samples)}


def pava(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    blocks: list[list[float | int]] = []
    for index, (value, weight) in enumerate(zip(values, weights)):
        blocks.append([index, index, float(value), float(weight)])
        while len(blocks) >= 2 and float(blocks[-2][2]) > float(blocks[-1][2]):
            right = blocks.pop(); left = blocks.pop()
            total_weight = float(left[3]) + float(right[3])
            mean = (float(left[2]) * float(left[3]) + float(right[2]) * float(right[3])) / total_weight
            blocks.append([int(left[0]), int(right[1]), mean, total_weight])
    fitted = np.empty(len(values), dtype=np.float64)
    for start, stop, value, _ in blocks:
        fitted[int(start):int(stop) + 1] = float(value)
    return fitted


def invert_curve(nodes: np.ndarray, fitted: np.ndarray, target: float) -> tuple[str, float, float, float]:
    if target < fitted[0]:
        return "below_1k", math.nan, math.nan, math.nan
    if target > fitted[-1]:
        return "above_2m", math.nan, math.nan, math.nan
    equal = np.flatnonzero(np.isclose(fitted, target, rtol=0.0, atol=1e-15))
    if equal.size:
        lo = float(nodes[equal[0]]); hi = float(nodes[equal[-1]])
        return "plateau" if hi > lo else "finite", math.sqrt(lo * hi), lo, hi
    upper = int(np.searchsorted(fitted, target, side="right"))
    upper = min(max(upper, 1), len(nodes) - 1)
    lower = upper - 1
    if fitted[upper] == fitted[lower]:
        lo = float(nodes[lower]); hi = float(nodes[upper])
        return "plateau", math.sqrt(lo * hi), lo, hi
    fraction = (target - fitted[lower]) / (fitted[upper] - fitted[lower])
    log_value = np.log10(nodes[lower]) + fraction * (np.log10(nodes[upper]) - np.log10(nodes[lower]))
    value = float(10 ** log_value)
    return "finite", value, value, value


def scan_node_equivalents(
    names: list[str], points: dict[str, np.ndarray], boot: np.ndarray,
) -> dict[str, object]:
    nodes = np.asarray((1_000, 5_000, 50_000, 200_000, 1_000_000, 2_000_000), dtype=np.float64)
    curve_names = ["Scan1k", "Scan5k", "Scan50k", "Scan200k", "Scan1M", "Scan2M"]
    index = {name: i for i, name in enumerate(names)}
    curve_indices = [index[name] for name in curve_names]
    curve_point = np.asarray([points["pairwise_primary"][i] for i in curve_indices])
    fitted_point = pava(curve_point, np.ones(len(nodes)))
    result: dict[str, object] = {
        "curve": [
            {"scan_nodes": int(node), "raw_accuracy": float(raw), "isotonic_accuracy": float(fitted)}
            for node, raw, fitted in zip(nodes, curve_point, fitted_point)
        ],
        "signals": {},
    }
    target_names = [name for name in names if name != "Scan5M"]
    finite = {name: np.full(len(boot), np.nan) for name in target_names}
    below = {name: 0 for name in target_names}; above = {name: 0 for name in target_names}
    plateau = {name: 0 for name in target_names}
    for name in target_names:
        category, value, lo, hi = invert_curve(nodes, fitted_point, float(points["pairwise_primary"][index[name]]))
        result["signals"][name] = {
            "point_category": category, "point_scan_node_equivalent": finite_or_none(value),
            "point_plateau_nodes": [finite_or_none(lo), finite_or_none(hi)],
        }
    curve_boot = boot[:, curve_indices]
    for sample_index in range(len(boot)):
        fitted = pava(curve_boot[sample_index], np.ones(len(nodes)))
        for name in target_names:
            category, value, lo, hi = invert_curve(nodes, fitted, float(boot[sample_index, index[name]]))
            if math.isfinite(value): finite[name][sample_index] = value
            if category == "below_1k": below[name] += 1
            elif category == "above_2m": above[name] += 1
            elif category == "plateau" and hi > lo: plateau[name] += 1
    total = len(boot)
    for name in target_names:
        result["signals"][name].update({
            **percentile_summary(finite[name]),
            "bootstrap_below_1k_proportion": below[name] / total,
            "bootstrap_above_2m_proportion": above[name] / total,
            "bootstrap_plateau_proportion": plateau[name] / total,
        })
    return result


def practical_recovery(names: list[str], points: dict[str, np.ndarray], boot: np.ndarray) -> dict[str, object]:
    index = {name: i for i, name in enumerate(names)}
    t0 = points["pairwise_primary"][index["T0"]]
    ceiling = points["pairwise_primary"][index["Scan2M"]]
    denominator = ceiling - t0
    targets = ("D1", "RF1", "T3-A", "Jass1k", "Jass50k", "Jass200k", "Jass1M")
    output: dict[str, object] = {
        "definition": "(A_M-A_T0)/(A_Scan2M-A_T0)",
        "a_t0": float(t0), "a_ceiling_scan2m_vs_scan5m": float(ceiling),
        "point_denominator": float(denominator), "signals": {},
    }
    sample_denominator = boot[:, index["Scan2M"]] - boot[:, index["T0"]]
    for name in targets:
        point = (points["pairwise_primary"][index[name]] - t0) / denominator if denominator > 0 else math.nan
        samples = np.full(len(boot), np.nan)
        if denominator > 0:
            valid = sample_denominator > 0
            samples[valid] = (
                boot[valid, index[name]] - boot[valid, index["T0"]]
            ) / sample_denominator[valid]
        output["signals"][name] = series_summary(float(point), samples)
    return output


def bottleneck_analysis(names: list[str], points: dict[str, np.ndarray], boot: np.ndarray) -> dict[str, object]:
    index = {name: i for i, name in enumerate(names)}
    point_values = points["pairwise_primary"]
    def delta(label: str, left: str, right: str) -> tuple[str, dict[str, object]]:
        return label, series_summary(
            float(point_values[index[left]] - point_values[index[right]]),
            boot[:, index[left]] - boot[:, index[right]],
        )
    output = dict([
        delta("t3_a_minus_t0", "T3-A", "T0"),
        delta("jass200k_minus_t3_a", "Jass200k", "T3-A"),
        delta("jass1m_minus_jass200k", "Jass1M", "Jass200k"),
        delta("scan200k_minus_jass200k", "Scan200k", "Jass200k"),
        delta("scan1m_minus_jass1m", "Scan1M", "Jass1M"),
    ])
    a_t0 = point_values[index["T0"]]; a_t3 = point_values[index["T3-A"]]
    denominator = 1.0 - a_t0
    sample_denominator = 1.0 - boot[:, index["T0"]]
    recovery_samples = np.full(len(boot), np.nan)
    valid = sample_denominator > 0
    recovery_samples[valid] = (
        boot[valid, index["T3-A"]] - boot[valid, index["T0"]]
    ) / sample_denominator[valid]
    output["t3_a_fraction_of_t0_to_reference"] = series_summary(
        float((a_t3 - a_t0) / denominator) if denominator > 0 else math.nan,
        recovery_samples,
    )
    for name in ("Jass200k", "Jass1M"):
        output[f"one_minus_{name.lower()}"] = series_summary(
            float(1.0 - point_values[index[name]]), 1.0 - boot[:, index[name]],
        )
    return output


def scan_convergence(
    deep_names: list[str], deep_points: dict[str, np.ndarray], deep_boot: np.ndarray,
    ultra_names: list[str], ultra_points: dict[str, np.ndarray], ultra_boot: np.ndarray,
) -> dict[str, object]:
    di = {name: i for i, name in enumerate(deep_names)}
    ui = {name: i for i, name in enumerate(ultra_names)}
    return {
        "DEEP512_Scan1M_vs_Scan2M": series_summary(
            float(deep_points["pairwise_primary"][di["Scan1M"]]), deep_boot[:, di["Scan1M"]],
        ),
        "ULTRA256_Scan1M_vs_Scan5M": series_summary(
            float(ultra_points["pairwise_primary"][ui["Scan1M"]]), ultra_boot[:, ui["Scan1M"]],
        ),
        "ULTRA256_Scan2M_vs_Scan5M": series_summary(
            float(ultra_points["pairwise_primary"][ui["Scan2M"]]), ultra_boot[:, ui["Scan2M"]],
        ),
    }


def top_choice(rows: np.ndarray, ids: np.ndarray, scores: np.ndarray) -> int:
    values = scores[rows]
    candidates = np.flatnonzero(values == np.max(values)).tolist()
    local = min(candidates, key=lambda index: ids[rows[index]])
    return int(rows[local])


def disagreements(groups: Groups, parents: list[int], scores: dict[str, np.ndarray]) -> dict[str, object]:
    strata = {name: set(ids) for name, ids in strata_for(groups, parents)}
    counters = {name: np.zeros(4, dtype=np.int64) for name in strata}
    denominators = {name: len(ids) for name, ids in strata.items()}
    for pid in parents:
        rows = groups.rows_by_parent[pid]
        scan_values = scores["Scan5M"][rows]
        scan_top = set(rows[np.flatnonzero(scan_values == np.max(scan_values))].tolist())
        scan_choice = top_choice(rows, groups.sibling_id, scores["Scan5M"])
        jass_choice = top_choice(rows, groups.sibling_id, scores["Jass200k"])
        t3_choice = top_choice(rows, groups.sibling_id, scores["T3-A"])
        flags = np.asarray([
            scan_choice != jass_choice,
            t3_choice == jass_choice and t3_choice not in scan_top,
            t3_choice in scan_top and jass_choice not in scan_top,
            jass_choice in scan_top and t3_choice not in scan_top,
        ], dtype=np.int64)
        for name, ids in strata.items():
            if pid in ids: counters[name] += flags
    labels = (
        "scan5m_vs_jass200k_top_choice_different",
        "t3_a_equals_jass200k_outside_scan5m_top_tie",
        "t3_a_in_scan5m_top_tie_jass200k_outside",
        "jass200k_in_scan5m_top_tie_t3_a_outside",
    )
    return {
        "aggregate_only": True, "individual_positions_published": False,
        "strata": {
            name: {
                "parents": denominators[name],
                **{
                    label: {"count": int(counters[name][i]),
                            "rate": float(counters[name][i] / denominators[name]) if denominators[name] else None}
                    for i, label in enumerate(labels)
                },
            }
            for name in strata
        },
    }


def verdict_and_roadmap(
    names: list[str], points: dict[str, np.ndarray], boot: np.ndarray,
) -> dict[str, object]:
    index = {name: i for i, name in enumerate(names)}
    q200 = series_summary(float(points["pairwise_primary"][index["Jass200k"]]), boot[:, index["Jass200k"]])
    low, high = q200["ci95"]
    if low is not None and low >= 0.95:
        verdict = "JASS_Q200_NEAR_SCAN_PRACTICAL_CEILING"
    elif high is not None and high < 0.85:
        verdict = "JASS_SEARCH_LARGE_HEADROOM_TO_SCAN_ESTABLISHED"
    elif high is not None and high < 0.95:
        verdict = "JASS_SEARCH_HEADROOM_TO_SCAN_ESTABLISHED"
    else:
        verdict = "JASS_Q200_SCAN_DISTANCE_INCONCLUSIVE"
    student_delta = boot[:, index["Jass200k"]] - boot[:, index["T3-A"]]
    depth_delta = boot[:, index["Jass1M"]] - boot[:, index["Jass200k"]]
    student_ci = percentile_summary(student_delta)
    depth_summary = series_summary(
        float(points["pairwise_primary"][index["Jass1M"]] - points["pairwise_primary"][index["Jass200k"]]),
        depth_delta,
    )
    q1m = series_summary(float(points["pairwise_primary"][index["Jass1M"]]), boot[:, index["Jass1M"]])
    q200_point = float(points["pairwise_primary"][index["Jass200k"]])
    depth_point = float(depth_summary["point"])
    closure = depth_point / (1.0 - q200_point) if q200_point < 1.0 else math.nan
    if verdict == "JASS_Q200_NEAR_SCAN_PRACTICAL_CEILING" \
            and student_ci["ci95"][0] is not None and student_ci["ci95"][0] > 0.02:
        roadmap = "STUDENT_DISTILLATION_PRIMARY"
    elif verdict != "JASS_Q200_NEAR_SCAN_PRACTICAL_CEILING" \
            and depth_summary["ci95"][0] is not None and depth_summary["ci95"][0] > 0 \
            and depth_point >= 0.02 and math.isfinite(closure) and closure >= 0.30:
        roadmap = "SEARCH_DEPTH_PRIMARY"
    elif q1m["ci95"][1] is not None and q1m["ci95"][1] < 0.90 \
            and depth_summary["ci95"][1] is not None and depth_summary["ci95"][1] <= 0.02:
        roadmap = "JASS_SEARCH_SEMANTICS_PRIMARY"
    else:
        roadmap = "MIXED_OR_INCONCLUSIVE_HEADROOM"
    return {
        "terminal_verdict": verdict, "roadmap_reading": roadmap,
        "jass200k_accuracy": q200,
        "jass200k_minus_t3_a": {
            "point": float(points["pairwise_primary"][index["Jass200k"]]
                           - points["pairwise_primary"][index["T3-A"]]),
            **student_ci,
        },
        "jass1m_minus_jass200k": depth_summary,
        "jass1m_gap_closure_fraction": finite_or_none(closure),
        "jass1m_accuracy": q1m,
        "action_authorized": False,
    }


def ci_text(metric: dict[str, object]) -> str:
    point = metric.get("point")
    ci = metric.get("ci95", [None, None])
    if point is None:
        text = "NA"
    elif ci[0] is None:
        text = f"{float(point):.4f} [NA]"
    else:
        text = f"{float(point):.4f} [{float(ci[0]):.4f}, {float(ci[1]):.4f}]"
    if "raw_denominator" in metric:
        numerator = float(metric["raw_numerator"])
        rendered = str(int(numerator)) if numerator.is_integer() else f"{numerator:.1f}"
        text += f"; brut {rendered}/{int(metric['raw_denominator'])}"
    return text


def render_markdown(payload: dict[str, object]) -> str:
    provenance = payload["scan_provenance"]
    runtime = provenance.get("scan_runtime_params", {})
    lines = [
        "# L3 Scan ceiling benchmark v1 — terminal scientific memo", "",
        f"- Verdict descriptif : `{payload['decision']['terminal_verdict']}`",
        f"- Lecture roadmap : `{payload['decision']['roadmap_reading']}`",
        "- Statut : benchmark-only consommé ; aucune action de training/tuning/promotion autorisée.", "",
        "## Provenance et contrat", "",
        f"- Scan : `{provenance.get('release', 'NA')}`, source `{provenance.get('source_url', 'NA')}`, "
        f"commit `{provenance.get('source_commit', 'NA')}`, tree `{provenance.get('source_tree', 'NA')}`.",
        f"- Binaire HOME SHA256 : `{provenance.get('scan_binary_sha256', 'NA')}` ; "
        f"eval SHA256 : `{provenance.get('scan_eval_sha256', 'NA')}` ; ini SHA256 : `{provenance.get('scan_ini_sha256', 'NA')}`.",
        f"- Compilation : `{provenance.get('cxxflags', 'NA')}` ; link `{provenance.get('ldflags', 'NA')}` ; "
        f"compilateur `{str(provenance.get('compiler_version', 'NA')).splitlines()[0]}`.",
        f"- Runtime Scan : `{json.dumps(runtime, sort_keys=True)}` ; tablebase Scan désactivée (`bb-size=0`) ; "
        "un thread/recherche, livre OFF, `new-game` avant chaque sibling/budget.",
        f"- Cohort identity SHA256 : `{payload['cohort'].get('cohort_identity_sha256', 'NA')}`.",
        f"- Snapshot exclusions runtime : cutoff `{payload['runtime_exclusion_snapshot'].get('cutoff_utc', 'NA')}`, "
        f"control-plane `{payload['runtime_exclusion_snapshot'].get('control_plane_head', 'NA')}`, "
        f"artifacts observables `{payload['runtime_exclusion_snapshot'].get('observable_pool_artifacts', 'NA')}`.",
        f"- Bootstrap : {BOOTSTRAP_SAMPLES} resamples parent-cluster, seed {BOOTSTRAP_SEED}, CI percentile 95%.",
        f"- Artifacts : " + ", ".join(f"{name} `{value}`" for name, value in ARTIFACTS.items()), "",
        "CPU HOME (`lscpu`) :", "", "```text",
        str(provenance.get("cpu_information", "NA")), "```", "",
        "## Ladders et compteurs de nœuds", "",
        "| Stage | Budget | Lignes | Recherches | Terminal exact | TB exact | Nœuds demandés (recherches) | Nœuds reportés/snapshot | Sémantique |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for stage, stage_data in payload["node_ladders"]["observed"].items():
        for budget, item in stage_data["by_budget"].items():
            lines.append(
                f"| {stage} | {budget} | {item['output_rows']} | {item['searched_rows']} | "
                f"{item['terminal_exact_rows']} | {item['tb_exact_rows']} | "
                f"{item['nominal_requested_search_nodes_sum']} | {item['reported_or_snapshot_nodes_sum']} | "
                f"{item['node_semantics']} |"
            )
    lines += ["",
        "## Résultats globaux pairwise / top-hit", "",
    ]
    for scope_name in ("BASE2000", "DEEP512", "ULTRA256"):
        scope = payload["scopes"][scope_name]
        lines += [f"### {scope_name} vs {scope['reference']}", "",
                  "| Signal | Pairwise primaire | Pairwise strict diag. | Top-hit primaire | Top-hit strict diag. | Kendall tau-b | Spearman rho |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        metrics = scope["strata"]["all"]["metrics"]
        for signal in scope["signals"]:
            item = metrics[signal]
            lines.append(
                f"| {signal} | {ci_text(item['pairwise_primary'])} | {ci_text(item['pairwise_strict'])} | "
                f"{ci_text(item['top_hit_primary'])} | {ci_text(item['top_hit_strict'])} | "
                f"{ci_text(item['kendall_tau_b'])} | {ci_text(item['spearman_rho'])} |"
            )
        lines.append("")
    lines += ["## Bottleneck DEEP512 / Scan2M", "",
              "| Quantité | Point et CI95 |", "|---|---:|"]
    for name, value in payload["bottleneck"].items():
        lines.append(f"| {name} | {ci_text(value)} |")
    lines += ["", "## Convergence Scan", "", "| Comparaison | Accuracy et CI95 |", "|---|---:|"]
    for name, value in payload["scan_convergence"].items():
        lines.append(f"| {name} | {ci_text(value)} |")
    lines += ["", "## Equivalent descriptif Scan-nodes (ULTRA256 / Scan5M)", "",
              "| Signal | Catégorie | Equivalent point | CI95 fini | <1k | >2M | plateau |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for signal, item in payload["scan_node_equivalent"]["signals"].items():
        point = item["point_scan_node_equivalent"]
        ci = item["ci95"]
        lines.append(
            f"| {signal} | {item['point_category']} | {point if point is not None else 'NA'} | "
            f"{ci if ci[0] is not None else 'NA'} | {item['bootstrap_below_1k_proportion']:.4f} | "
            f"{item['bootstrap_above_2m_proportion']:.4f} | {item['bootstrap_plateau_proportion']:.4f} |"
        )
    lines += ["", "## Practical headroom recovery (ULTRA256)", "",
              "| Signal | Recovery et CI95 |", "|---|---:|"]
    for signal, item in payload["practical_headroom_recovery"]["signals"].items():
        lines.append(f"| {signal} | {ci_text(item)} |")
    lines += ["", "## Ventilations préenregistrées", ""]
    for scope_name in ("BASE2000", "DEEP512", "ULTRA256"):
        scope = payload["scopes"][scope_name]
        lines += [f"### {scope_name}", "",
                  "| Strate | Signal | Parents | Pairs totaux | Pairs comparables | Ties référence | Pairwise | Top-hit |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"]
        for stratum, data in scope["strata"].items():
            if stratum == "all": continue
            for signal in scope["signals"]:
                item = data["metrics"][signal]
                lines.append(
                    f"| {stratum} | {signal} | {data['parents']} | {data['pairs_total']} | "
                    f"{data['pairs_comparable']} | {data['pairs_reference_tied']} | "
                    f"{ci_text(item['pairwise_primary'])} | {ci_text(item['top_hit_primary'])} |"
                )
        lines.append("")
    lines += [
        "## Désaccords Jass / Scan", "",
        "| Catégorie agrégée ULTRA256 | Compte | Taux |", "|---|---:|---:|",
    ]
    disagreement_all = payload["jass_scan_disagreements"]["strata"]["all"]
    for label, value in disagreement_all.items():
        if label == "parents":
            continue
        lines.append(f"| {label} | {value['count']} | {value['rate']:.4f} |")
    lines += [
        "",
        "Le JSON compagnon ventile aussi ces comptes/taux par phase, couleur, branching et pièces. "
        "Aucune FEN, identité sibling ou liste de position benchmark n'est publiée.", "",
        "## Quarantaine", "",
        "`SCAN_BENCHMARK_ONLY=true`. Le cohort et tous ses scores sont consommés et interdits "
        "pour tout training, tuning, feature/model selection, calibration, bake, force game ou promotion.", "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--groups", type=Path, required=True)
    parser.add_argument("--deep-row-ids", type=Path, required=True)
    parser.add_argument("--ultra-row-ids", type=Path, required=True)
    parser.add_argument("--static", type=Path, required=True)
    parser.add_argument("--jass-base", type=Path, action="append", required=True)
    parser.add_argument("--jass-deep", type=Path, action="append", required=True)
    parser.add_argument("--scan-base", type=Path, action="append", required=True)
    parser.add_argument("--scan-deep", type=Path, action="append", required=True)
    parser.add_argument("--scan-ultra", type=Path, action="append", required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--selection-report", type=Path, required=True)
    parser.add_argument("--sibling-manifest", type=Path, required=True)
    parser.add_argument("--cohort-freeze", type=Path, required=True)
    parser.add_argument("--runtime-exclusion-snapshot", type=Path, required=True)
    parser.add_argument("--source-stage-manifest", type=Path, required=True)
    parser.add_argument("--sibling-export-stage-manifest", type=Path, required=True)
    parser.add_argument("--stage-manifest", type=Path, action="append", default=[])
    parser.add_argument("--bootstrap-samples", type=int, default=BOOTSTRAP_SAMPLES)
    parser.add_argument("--bootstrap-seed", type=int, default=BOOTSTRAP_SEED)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    if args.bootstrap_samples != BOOTSTRAP_SAMPLES or args.bootstrap_seed != BOOTSTRAP_SEED:
        raise ValueError("preregistered bootstrap contract drift")

    groups = load_groups(args.groups)
    row_count = len(groups.rows)
    all_rows = set(range(row_count))
    deep_rows = load_row_ids(args.deep_row_ids, row_count)
    ultra_rows = load_row_ids(args.ultra_row_ids, row_count)
    if not ultra_rows < deep_rows:
        raise ValueError("ULTRA256 rows are not a strict DEEP512 subset")
    base_parents = list(range(2000))
    deep_parents = parent_ids_for_rows(groups, deep_rows, 512)
    ultra_parents = parent_ids_for_rows(groups, ultra_rows, 256)

    scores = load_static(args.static, row_count)
    jass_base, jass_base_nodes = load_long_scores(
        args.jass_base, row_count, all_rows, JASS_BUDGETS[:4], "jass",
    )
    jass_deep, jass_deep_nodes = load_long_scores(
        args.jass_deep, row_count, deep_rows, (1_000_000,), "jass",
    )
    scan_base, scan_base_nodes = load_long_scores(
        args.scan_base, row_count, all_rows, SCAN_BUDGETS[:4], "scan",
    )
    scan_deep, scan_deep_nodes = load_long_scores(
        args.scan_deep, row_count, deep_rows, (1_000_000, 2_000_000), "scan",
    )
    scan_ultra, scan_ultra_nodes = load_long_scores(
        args.scan_ultra, row_count, ultra_rows, (5_000_000,), "scan",
    )
    for budget, array in jass_base.items(): scores[f"Jass{budget // 1000}k"] = array
    scores["Jass1M"] = jass_deep[1_000_000]
    for budget, array in scan_base.items(): scores[f"Scan{budget // 1000}k"] = array
    scores["Scan1M"] = scan_deep[1_000_000]
    scores["Scan2M"] = scan_deep[2_000_000]
    scores["Scan5M"] = scan_ultra[5_000_000]

    base_names = list(STATIC_NAMES) + ["Jass1k", "Jass5k", "Jass50k", "Jass200k",
        "Scan1k", "Scan5k", "Scan50k"]
    deep_names = list(STATIC_NAMES) + ["Jass1k", "Jass5k", "Jass50k", "Jass200k", "Jass1M",
        "Scan1k", "Scan5k", "Scan50k", "Scan200k", "Scan1M"]
    ultra_names = list(STATIC_NAMES) + ["Jass1k", "Jass5k", "Jass50k", "Jass200k", "Jass1M",
        "Scan1k", "Scan5k", "Scan50k", "Scan200k", "Scan1M", "Scan2M"]
    rng = np.random.Generator(np.random.PCG64(args.bootstrap_seed))
    base_scope, _, _, _ = run_scope(
        "BASE2000", groups, base_parents, "Scan200k",
        scores["Scan200k"],
        {name: scores[name] for name in base_names}, rng, args.bootstrap_samples, False,
    )
    deep_scope, deep_boot, deep_order, deep_points = run_scope(
        "DEEP512", groups, deep_parents, "Scan2M",
        scores["Scan2M"],
        {name: scores[name] for name in deep_names}, rng, args.bootstrap_samples, True,
    )
    ultra_scope, ultra_boot, ultra_order, ultra_points = run_scope(
        "ULTRA256", groups, ultra_parents, "Scan5M",
        scores["Scan5M"],
        {name: scores[name] for name in ultra_names}, rng, args.bootstrap_samples, True,
    )
    assert deep_boot is not None and ultra_boot is not None

    preflight = read_json(args.preflight_report)
    selection = read_json(args.selection_report)
    sibling_manifest = read_json(args.sibling_manifest)
    cohort_freeze = read_json(args.cohort_freeze)
    runtime_exclusion_snapshot = read_json(args.runtime_exclusion_snapshot)
    source_stage_manifest = read_json(args.source_stage_manifest)
    sibling_export_stage_manifest = read_json(args.sibling_export_stage_manifest)
    if selection.get("cohort_identity_sha256") is None or selection.get("selected") != 2000:
        raise ValueError("selection receipt drift at readout")
    if any(selection.get(name) is not False for name in FORBIDDEN_POLICY_FIELDS) \
            or any(sibling_manifest.get(name) is not False for name in FORBIDDEN_POLICY_FIELDS) \
            or any(cohort_freeze.get(name) is not False for name in FORBIDDEN_POLICY_FIELDS) \
            or any(source_stage_manifest.get(name) is not False for name in FORBIDDEN_POLICY_FIELDS) \
            or any(sibling_export_stage_manifest.get(name) is not False for name in FORBIDDEN_POLICY_FIELDS):
        raise ValueError("selection/freeze/stage quarantine policy drift at readout")
    if cohort_freeze.get("cohort_identity_sha256") != selection["cohort_identity_sha256"] \
            or cohort_freeze.get("selection_report_sha256") != sha256(args.selection_report) \
            or cohort_freeze.get("runtime_snapshot_sha256") != sha256(args.runtime_exclusion_snapshot):
        raise ValueError("cohort freeze chain drift at readout")
    stage_receipts = [
        {"path": str(path), "sha256": sha256(path), "payload": read_json(path)}
        for path in args.stage_manifest
    ]
    if len(stage_receipts) != 5 or any(
        receipt["payload"].get(name) is not False
        for receipt in stage_receipts for name in FORBIDDEN_POLICY_FIELDS
    ):
        raise ValueError("score stage manifest quarantine drift at readout")
    payload: dict[str, object] = {
        "schema": "jass.scan_ceiling_terminal_readout.v1",
        "benchmark_only": True,
        "scan_benchmark_only": True,
        "reference_language": {
            "primary": "external_deep_reference",
            "ceiling": "practical_scan_ceiling",
            "convergence": "scan_convergence",
            "perfect_truth_claimed": False,
        },
        "bootstrap": {
            "samples": args.bootstrap_samples, "seed": args.bootstrap_seed,
            "rng": "numpy.random.Generator(numpy.random.PCG64(seed))",
            "cluster": "parent", "ci": "percentile_[2.5,97.5]",
            "execution_order": "BASE2000 then DEEP512 then ULTRA256; within each: all, phase, colour, branching, pieces",
        },
        "artifacts": ARTIFACTS,
        "scan_provenance": preflight,
        "cohort": selection,
        "cohort_freeze": cohort_freeze,
        "runtime_exclusion_snapshot": runtime_exclusion_snapshot,
        "source_stage_manifest": source_stage_manifest,
        "sibling_export_stage_manifest": sibling_export_stage_manifest,
        "sibling_manifest": sibling_manifest,
        "input_receipts": {
            "groups_sha256": sha256(args.groups), "static_sha256": sha256(args.static),
            "deep_row_ids_sha256": sha256(args.deep_row_ids),
            "ultra_row_ids_sha256": sha256(args.ultra_row_ids),
            "cohort_freeze_sha256": sha256(args.cohort_freeze),
            "runtime_exclusion_snapshot_sha256": sha256(args.runtime_exclusion_snapshot),
            "source_stage_manifest_sha256": sha256(args.source_stage_manifest),
            "sibling_export_stage_manifest_sha256": sha256(args.sibling_export_stage_manifest),
            "stage_manifests": stage_receipts,
        },
        "node_ladders": {
            "requested": {
                "Jass_BASE2000": list(JASS_BUDGETS[:4]),
                "Jass_DEEP512_additional": [1_000_000],
                "Scan_BASE2000": list(SCAN_BUDGETS[:4]),
                "Scan_DEEP512_additional": [1_000_000, 2_000_000],
                "Scan_ULTRA256_additional": [5_000_000],
            },
            "observed": {
                "Jass_BASE2000": jass_base_nodes,
                "Jass_DEEP512": jass_deep_nodes,
                "Scan_BASE2000": scan_base_nodes,
                "Scan_DEEP512": scan_deep_nodes,
                "Scan_ULTRA256": scan_ultra_nodes,
            },
        },
        "scopes": {"BASE2000": base_scope, "DEEP512": deep_scope, "ULTRA256": ultra_scope},
        "bottleneck": bottleneck_analysis(deep_order, deep_points, deep_boot),
        "scan_convergence": scan_convergence(
            deep_order, deep_points, deep_boot, ultra_order, ultra_points, ultra_boot,
        ),
        "scan_node_equivalent": scan_node_equivalents(ultra_order, ultra_points, ultra_boot),
        "practical_headroom_recovery": practical_recovery(ultra_order, ultra_points, ultra_boot),
        "jass_scan_disagreements": disagreements(groups, ultra_parents, scores),
        "decision": verdict_and_roadmap(deep_order, deep_points, deep_boot),
        "guards": {
            "fits": 0, "refits": 0, "calibrations": 0, "feature_selections": 0,
            "model_selections": 0, "strength_games": 0, "bakes": 0,
            "promotions": 0, "promotion_authorized": False,
            "cohort_and_scores_consumed": True,
            "future_training_tuning_selection_calibration_forbidden": True,
            "training_allowed": False, "tuning_allowed": False,
            "calibration_allowed": False, "model_selection_allowed": False,
            "runtime_scale_selection_allowed": False,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({
        "verdict": payload["decision"]["terminal_verdict"],
        "roadmap": payload["decision"]["roadmap_reading"],
        "parents": 2000, "bootstrap_samples": args.bootstrap_samples,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
