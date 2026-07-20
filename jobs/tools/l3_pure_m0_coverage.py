#!/usr/bin/env python3
"""Aggregate L3-PURE M0 bucket-coverage reports for C0 A and P1-0842."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_report(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("stage") != "l3_bucket_visits":
        raise ValueError(f"{path}: not an l3_bucket_visits report")
    if value.get("geometry", {}).get("trained_buckets_total") != 4_251_528:
        raise ValueError(f"{path}: unexpected 8cf trained bucket count")
    if int(value.get("corpus", {}).get("total_records", 0)) <= 0:
        raise ValueError(f"{path}: empty corpus")
    return value


def compact(report: dict) -> dict:
    return {
        "total_records": int(report["corpus"]["total_records"]),
        "coverage_fraction": float(report["coverage"]["coverage_fraction"]),
        "visited_buckets": int(report["coverage"]["visited_buckets"]),
        "ge_10": int(report["coverage"]["buckets_with_at_least"]["ge_10"]),
        "ge_100": int(report["coverage"]["buckets_with_at_least"]["ge_100"]),
        "frac_ge_100": float(report["coverage"]["frac_buckets_ge_100"]),
        "gini": float(report["concentration"]["gini"]),
        "capacity_heuristic": report["capacity_heuristic"],
    }


def bp(value: float) -> int:
    return int(round(value * 10_000))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--c0-generation", action="append", required=True, type=Path)
    ap.add_argument("--p1-generation", action="append", required=True, type=Path)
    ap.add_argument("--c0-cumulative", required=True, type=Path)
    ap.add_argument("--p1-cumulative", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--summary-out", required=True, type=Path)
    args = ap.parse_args(argv)

    c0_gens = [load_report(p) for p in args.c0_generation]
    p1_gens = [load_report(p) for p in args.p1_generation]
    c0_cum = load_report(args.c0_cumulative)
    p1_cum = load_report(args.p1_cumulative)
    if len(c0_gens) != 3 or len(p1_gens) != 4:
        raise ValueError("M0 requires exactly C0 G1-G3 and P1 G1-G4")

    c0 = compact(c0_cum)
    p1 = compact(p1_cum)
    leader = "P1_0842_G4" if p1["coverage_fraction"] > c0["coverage_fraction"] else "C0_A_G3"
    payload = {
        "schema": 1,
        "protocol": "L3-PURE-MATURITY-M0-COVERAGE",
        "decision": "M0_COVERAGE_AUDIT_READY",
        "c0_a": {
            "per_generation": [compact(x) for x in c0_gens],
            "cumulative": c0,
        },
        "p1_0842": {
            "per_generation": [compact(x) for x in p1_gens],
            "cumulative": p1,
        },
        "coverage_leader_diagnostic_only": leader,
        "interpretation": (
            "coverage is diagnostic and cannot select the M1 parent without the M0 force triangle"
        ),
        "m1_authorized": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "verdict": payload["decision"],
        "coverage_leader_diagnostic_only": leader,
        "c0_a_cumulative_records": c0["total_records"],
        "c0_a_coverage_fraction": c0["coverage_fraction"],
        "c0_a_ge_100": c0["ge_100"],
        "c0_a_gini": c0["gini"],
        "p1_0842_cumulative_records": p1["total_records"],
        "p1_0842_coverage_fraction": p1["coverage_fraction"],
        "p1_0842_ge_100": p1["ge_100"],
        "p1_0842_gini": p1["gini"],
        "m1_authorized": False,
        "result_file": "m0-coverage-audit.json",
    }
    args.summary_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["decision"])
    print(f"coverage_leader={leader}")
    print("markers=" + ",".join([
        "VERDICT__M0_COVERAGE_AUDIT_READY",
        f"C0_A_CUMULATIVE_COVERAGE_BP__{bp(c0['coverage_fraction']):04d}",
        f"P1_0842_CUMULATIVE_COVERAGE_BP__{bp(p1['coverage_fraction']):04d}",
        f"COVERAGE_LEADER_DIAGNOSTIC_ONLY__{leader}",
        "M1_AUTHORIZED__FALSE",
    ]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
