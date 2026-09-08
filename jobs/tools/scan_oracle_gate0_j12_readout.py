#!/usr/bin/env python3
"""Read the fresh J12 2x2 factorial Gate0 against the existing Scan200k oracle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobs.tools import scan_oracle_gate0_readout as base  # noqa: E402

BOOTSTRAPS = 20_000
PAIRED_SEED = 2026090802
INTERACTION_SEED = 2026090803


def load_runtime_report(path: Path, arm: str) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "jass.scan_oracle_gate0_j12_arm.v1" or value.get("arm") != arm:
        raise ValueError(f"runtime report identity drift for {arm}")
    if value.get("selected_rows") != 512 or value.get("processed_rows") != 512:
        raise ValueError(f"runtime report cardinality drift for {arm}")
    if value.get("budget_nodes") != 20000 or value.get("threads") != 1 or value.get("book") is not False:
        raise ValueError(f"runtime report contract drift for {arm}")
    if any(value.get(k) != 0 for k in ("scan_searches", "fits", "strength_games")):
        raise ValueError(f"runtime report side effect drift for {arm}")
    return value


def bootstrap_mean(values: np.ndarray, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    n = int(values.size)
    boots = np.empty(BOOTSTRAPS, dtype=np.float64)
    for i in range(BOOTSTRAPS):
        idx = rng.integers(0, n, size=n)
        boots[i] = float(np.mean(values[idx]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {
        "mean": float(np.mean(values)),
        "ci95": [float(lo), float(hi)],
        "repetitions": BOOTSTRAPS,
        "seed": seed,
    }


def metrics(regret: np.ndarray) -> dict:
    return {
        "mean_regret": float(np.mean(regret)),
        "median_regret": float(np.median(regret)),
        "p95_regret": float(np.percentile(regret, 95)),
        "top_hit": float(np.mean(regret == 0.0)),
        "catastrophic_regret_ge_50": float(np.mean(regret >= 50.0)),
    }


def regret_for_arm(ordered: list[int], by_parent, semantic, scan, arm: dict[int, dict]) -> np.ndarray:
    out = []
    for pid in ordered:
        best = max(scan[rid] for rid in by_parent[pid])
        key = arm[pid]["key"]
        if key not in semantic:
            raise ValueError(f"selected move outside frozen siblings parent={pid}")
        regret = best - scan[semantic[key]]
        if regret < -1e-9:
            raise ValueError("negative Scan regret")
        out.append(regret)
    return np.asarray(out, dtype=np.float64)


def paired_view(control_regret: np.ndarray, candidate_regret: np.ndarray,
                ordered: list[int], control_arm: dict, candidate_arm: dict,
                seed: int) -> dict:
    improvement = control_regret - candidate_regret
    boot = bootstrap_mean(improvement, seed)
    wall = []
    depth = []
    evals = []
    for pid in ordered:
        cw = float(control_arm[pid]["wall_us"])
        dw = float(candidate_arm[pid]["wall_us"])
        if cw <= 0 or dw <= 0:
            raise ValueError("nonpositive wall timing")
        wall.append(dw / cw)
        depth.append(float(candidate_arm[pid]["depth"]) - float(control_arm[pid]["depth"]))
        evals.append(float(candidate_arm[pid]["eval_calls"]) - float(control_arm[pid]["eval_calls"]))
    control_top = float(np.mean(control_regret == 0.0))
    candidate_top = float(np.mean(candidate_regret == 0.0))
    median_wall = float(np.median(np.asarray(wall, dtype=np.float64)))
    supported = (
        boot["mean"] > 0.0
        and boot["ci95"][0] > 0.0
        and candidate_top >= control_top
        and median_wall <= 1.05
    )
    return {
        "mean_regret_improvement": boot["mean"],
        "regret_improvement_ci95": boot["ci95"],
        "top_hit_delta": candidate_top - control_top,
        "mean_completed_depth_delta": float(np.mean(depth)),
        "mean_eval_calls_delta": float(np.mean(evals)),
        "median_wall_ratio": median_wall,
        "gate": {
            "mean_regret_improvement_gt_0": boot["mean"] > 0.0,
            "regret_lcb95_gt_0": boot["ci95"][0] > 0.0,
            "top_hit_not_worse": candidate_top >= control_top,
            "median_wall_ratio_le_1p05": median_wall <= 1.05,
            "verdict": "GATE0_SUPPORTED" if supported else "GATE0_NOT_SUPPORTED",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--groups", type=Path, required=True)
    ap.add_argument("--ids", type=Path, required=True)
    ap.add_argument("--scan-score", type=Path, action="append", required=True)
    ap.add_argument("--control", type=Path, required=True)
    ap.add_argument("--j1", type=Path, required=True)
    ap.add_argument("--j2", type=Path, required=True)
    ap.add_argument("--j12", type=Path, required=True)
    ap.add_argument("--report-control", type=Path, required=True)
    ap.add_argument("--report-j1", type=Path, required=True)
    ap.add_argument("--report-j2", type=Path, required=True)
    ap.add_argument("--report-j12", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    ordered = base.selected_ids(args.ids)
    ids = set(ordered)
    by_parent, semantic, _phase = base.load_groups(args.groups, ids)
    wanted_rows = {rid for pid in ids for rid in by_parent[pid]}
    scan = base.load_scan(args.scan_score, wanted_rows)
    arm_paths = {
        "CONTROL": args.control,
        "J1_SCAN_VERIFY": args.j1,
        "J2_SCAN_THREAT_REENTRY": args.j2,
        "J12_SCAN_VERIFY_THREAT_REENTRY": args.j12,
    }
    runtime_reports = {
        "CONTROL": load_runtime_report(args.report_control, "CONTROL"),
        "J1_SCAN_VERIFY": load_runtime_report(args.report_j1, "J1_SCAN_VERIFY"),
        "J2_SCAN_THREAT_REENTRY": load_runtime_report(args.report_j2, "J2_SCAN_THREAT_REENTRY"),
        "J12_SCAN_VERIFY_THREAT_REENTRY": load_runtime_report(args.report_j12, "J12_SCAN_VERIFY_THREAT_REENTRY"),
    }
    arms = {name: base.load_arm(path, ids) for name, path in arm_paths.items()}
    regrets = {name: regret_for_arm(ordered, by_parent, semantic, scan, arm) for name, arm in arms.items()}
    rc = regrets["CONTROL"]

    views = {}
    for name in ("J1_SCAN_VERIFY", "J2_SCAN_THREAT_REENTRY", "J12_SCAN_VERIFY_THREAT_REENTRY"):
        paired = paired_view(rc, regrets[name], ordered, arms["CONTROL"], arms[name], PAIRED_SEED)
        activation = bool(runtime_reports[name]["required_activation_observed"])
        views[name] = {
            "candidate": metrics(regrets[name]),
            "paired": {k: v for k, v in paired.items() if k != "gate"},
            "gate": paired["gate"],
            "activation_observed": activation,
            "runtime_report": runtime_reports[name],
        }

    imp_j1 = rc - regrets["J1_SCAN_VERIFY"]
    imp_j2 = rc - regrets["J2_SCAN_THREAT_REENTRY"]
    imp_j12 = rc - regrets["J12_SCAN_VERIFY_THREAT_REENTRY"]
    interaction = imp_j12 - imp_j1 - imp_j2
    interaction_boot = bootstrap_mean(interaction, INTERACTION_SEED)
    incremental_vs_j1 = regrets["J1_SCAN_VERIFY"] - regrets["J12_SCAN_VERIFY_THREAT_REENTRY"]
    incremental_vs_j2 = regrets["J2_SCAN_THREAT_REENTRY"] - regrets["J12_SCAN_VERIFY_THREAT_REENTRY"]

    j12 = views["J12_SCAN_VERIFY_THREAT_REENTRY"]
    survivor = j12["gate"]["verdict"] == "GATE0_SUPPORTED" and j12["activation_observed"]
    verdict = "J12_FACTORIAL_GATE0_SURVIVOR_V1" if survivor else "J12_FACTORIAL_GATE0_NOT_SUPPORTED_V1"
    payload = {
        "schema": "jass.scan_oracle_gate0_j12_factorial_terminal.v1",
        "verdict": verdict,
        "benchmark_only": True,
        "parents": 512,
        "scan_reference_nodes": 200000,
        "control": metrics(rc),
        "control_runtime_report": runtime_reports["CONTROL"],
        "arms": views,
        "factorial": {
            "interaction_regret_improvement": interaction_boot,
            "interaction_definition": "J12 improvement - J1 improvement - J2 improvement",
            "interaction_is_diagnostic_not_gate": True,
            "j12_incremental_mean_regret_improvement_vs_j1": float(np.mean(incremental_vs_j1)),
            "j12_incremental_mean_regret_improvement_vs_j2": float(np.mean(incremental_vs_j2)),
        },
        "j12_survivor": survivor,
        "fresh_disjoint_confirmation_required_before_strength": survivor,
        "strength_authorized": False,
        "guards": {
            "new_scan_searches": 0,
            "fits": 0,
            "strength_games": 0,
            "selfplay_games": 0,
            "promotions": 0,
            "bakes": 0,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
