#!/usr/bin/env python3
"""Frozen CLS-G0 paired runtime catastrophe gate.

Consumes one same-executable parent/candidate probe TSV, frozen phase metadata,
and the authenticated CURRICULUM 1M deep-reference table. No model fitting,
strength games, alpha, promotion or bake.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np

PHASES = ("P0", "P1", "P2", "P3")
ROOTS = 512
ROOTS_PER_PHASE = 128
PRIMARY_BUDGET = 200_000
DEEP_BUDGET = 1_000_000
BOOTSTRAP_REPLICATES = 100_000
BOOTSTRAP_SEED = 2026091605
NPS_FLOOR = 0.80
DEPTH_FLOOR = -1.0
NODES_TO_DEPTH_CEILING = 1.50
TRANSFER_FLOOR = -0.05
PASS_TERMINAL = "CLS_G0_RUNTIME_CATASTROPHE_GATE_PASS_V1"
FAIL_TERMINAL = "CLS_G0_RUNTIME_CATASTROPHE_GATE_FAIL_V1"


class GateError(RuntimeError):
    pass


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def require_finite(value: float, name: str) -> float:
    if not math.isfinite(value):
        raise GateError(f"nonfinite:{name}")
    return value


def build_phase_map(deep512: Iterable[dict[str, str]], *, roots_per_phase: int) -> dict[str, str]:
    phase_by_root: dict[str, str] = {}
    counts = {phase: 0 for phase in PHASES}
    for row in deep512:
        root = row.get("parent_id", "")
        phase = row.get("phase", "")
        if not root or phase not in counts or root in phase_by_root:
            raise GateError("invalid_phase_metadata")
        phase_by_root[root] = phase
        counts[phase] += 1
    if counts != {phase: roots_per_phase for phase in PHASES}:
        raise GateError(f"phase_quota_drift:{counts}")
    return phase_by_root


def index_probe(rows: Iterable[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    indexed: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        root = row.get("root_id", "")
        arm = row.get("arm", "")
        key = (root, arm)
        if not root or arm not in {"parent", "candidate"} or key in indexed:
            raise GateError("invalid_or_duplicate_probe_row")
        indexed[key] = row
    return indexed


def index_deep(rows: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for row in rows:
        root = row.get("root_id", "")
        if not root or root in indexed:
            raise GateError("invalid_or_duplicate_deep_row")
        if int(row.get("budget", "0")) != DEEP_BUDGET:
            raise GateError("deep_budget_drift")
        indexed[root] = row
    return indexed


def paired_vectors(
    probe_rows: list[dict[str, str]],
    deep512_rows: list[dict[str, str]],
    deep_rows: list[dict[str, str]],
    *,
    roots_per_phase: int = ROOTS_PER_PHASE,
) -> dict[str, np.ndarray]:
    phase_by_root = build_phase_map(deep512_rows, roots_per_phase=roots_per_phase)
    probe = index_probe(probe_rows)
    deep = index_deep(deep_rows)
    roots = set(phase_by_root)
    if set(deep) != roots:
        raise GateError("deep_root_set_drift")
    if set(root for root, _ in probe) != roots:
        raise GateError("probe_root_set_drift")
    if len(probe) != 2 * len(roots):
        raise GateError("probe_arm_cardinality_drift")

    values: dict[str, list[list[float]]] = {phase: [] for phase in PHASES}
    for root in sorted(roots, key=int):
        parent = probe[(root, "parent")]
        candidate = probe[(root, "candidate")]
        if parent.get("target_depth") != candidate.get("target_depth"):
            raise GateError(f"target_depth_arm_drift:{root}")
        pnps = require_finite(float(parent["nps"]), "parent_nps")
        cnps = require_finite(float(candidate["nps"]), "candidate_nps")
        pntd = require_finite(float(parent["nodes_to_target"]), "parent_nodes_to_target")
        cntd = require_finite(float(candidate["nodes_to_target"]), "candidate_nodes_to_target")
        if pnps <= 0 or cnps <= 0 or pntd <= 0 or cntd <= 0:
            raise GateError(f"nonpositive_runtime_metric:{root}")
        pdepth = require_finite(float(parent["completed_nominal_depth"]), "parent_depth")
        cdepth = require_finite(float(candidate["completed_nominal_depth"]), "candidate_depth")
        deep_move = deep[root].get("bestmove_canonical", "")
        if not deep_move:
            raise GateError(f"missing_deep_move:{root}")
        parent_match = 1.0 if parent.get("bestmove_canonical", "") == deep_move else 0.0
        candidate_match = 1.0 if candidate.get("bestmove_canonical", "") == deep_move else 0.0
        values[phase_by_root[root]].append([
            math.log(cnps / pnps),
            cdepth - pdepth,
            math.log(cntd / pntd),
            candidate_match - parent_match,
        ])

    arrays = {phase: np.asarray(rows, dtype=np.float64) for phase, rows in values.items()}
    expected = (roots_per_phase, 4)
    for phase, array in arrays.items():
        if array.shape != expected or not np.isfinite(array).all():
            raise GateError(f"vector_shape_or_finite:{phase}:{array.shape}")
    return arrays


def bootstrap(
    vectors: dict[str, np.ndarray],
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, dict[str, float]]:
    if replicates <= 0:
        raise GateError("invalid_replicates")
    samples = np.zeros((replicates, 4), dtype=np.float64)
    rng = np.random.default_rng(seed)
    for phase in PHASES:
        values = vectors[phase]
        n = values.shape[0]
        if n <= 0:
            raise GateError(f"empty_phase:{phase}")
        chunk = 1000
        for start in range(0, replicates, chunk):
            stop = min(start + chunk, replicates)
            idx = rng.integers(0, n, size=(stop - start, n))
            samples[start:stop] += values[idx].mean(axis=1) / len(PHASES)
    q = np.quantile(samples, [0.025, 0.5, 0.975], axis=0)
    names = ("log_nps_ratio", "depth_delta", "log_nodes_to_depth_ratio", "agreement_delta")
    return {
        name: {"q025": float(q[0, i]), "median": float(q[1, i]), "q975": float(q[2, i])}
        for i, name in enumerate(names)
    }


def decide(metrics: dict[str, dict[str, float]]) -> dict[str, object]:
    nps_lb = math.exp(metrics["log_nps_ratio"]["q025"])
    depth_lb = metrics["depth_delta"]["q025"]
    nodes_ub = math.exp(metrics["log_nodes_to_depth_ratio"]["q975"])
    transfer_lb = metrics["agreement_delta"]["q025"]
    gates = {
        "nps": {"value": nps_lb, "operator": ">=", "threshold": NPS_FLOOR, "pass": nps_lb >= NPS_FLOOR},
        "completed_nominal_depth": {"value": depth_lb, "operator": ">=", "threshold": DEPTH_FLOOR, "pass": depth_lb >= DEPTH_FLOOR},
        "nodes_to_depth": {"value": nodes_ub, "operator": "<=", "threshold": NODES_TO_DEPTH_CEILING, "pass": nodes_ub <= NODES_TO_DEPTH_CEILING},
        "search_transfer": {"value": transfer_lb, "operator": ">=", "threshold": TRANSFER_FLOOR, "pass": transfer_lb >= TRANSFER_FLOOR},
    }
    passed = all(bool(gate["pass"]) for gate in gates.values())
    return {
        "schema": "jass.cls_g0_runtime_gate.v1",
        "state": "completed",
        "terminal": PASS_TERMINAL if passed else FAIL_TERMINAL,
        "pass": passed,
        "gates": gates,
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "unit": "root_id",
            "phase_stratified": True,
            "quantile": "numpy_type_7",
            "metrics": metrics,
        },
        "alpha_spent": 0,
        "promotion_authorized": False,
        "bake_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-tsv", type=Path, required=True)
    parser.add_argument("--deep512-tsv", type=Path, required=True)
    parser.add_argument("--deep-reference-tsv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    vectors = paired_vectors(read_tsv(args.probe_tsv), read_tsv(args.deep512_tsv),
                             read_tsv(args.deep_reference_tsv))
    metrics = bootstrap(vectors)
    result = decide(metrics)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
