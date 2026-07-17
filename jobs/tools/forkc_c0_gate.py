#!/usr/bin/env python3
"""Fail-closed C0 decision gate for the weak-bootstrap fork C.

The full T1-C tour is justified only when the cheap shared-corpus refit shows
both a behavioural basin change and a pre-engaged gain on hard conversion
strata (p3/p4), without an established regression versus the strong absolute
reference.  The raw weak-vs-strong match is retained as telemetry only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _number(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _divergence(report: dict) -> float | None:
    value = _number(report.get("divergence"))
    if value is not None:
        return value
    agreement = _number(report.get("agreement"))
    return None if agreement is None else 1.0 - agreement


def _hard_conversion(report: dict) -> float | None:
    values = [_number(report.get(name)) for name in ("p3_mince", "p4_egal")]
    return None if any(value is None for value in values) else sum(values) / 2.0


def decide(
    *,
    policy_raw: dict,
    policy_refit: dict,
    gate_refit_vs_strong: dict,
    conversion_baseline: dict,
    conversion_refit: dict,
    gate_raw_weak_vs_strong: dict | None = None,
    min_policy_divergence: float = 0.05,
    min_hard_delta: float = 0.02,
) -> dict:
    raw_div = _divergence(policy_raw)
    refit_div = _divergence(policy_refit)
    baseline_hard = _hard_conversion(conversion_baseline)
    refit_hard = _hard_conversion(conversion_refit)
    ci_high = _number(gate_refit_vs_strong.get("ci_high"))
    gate_n = int(gate_refit_vs_strong.get("n", 0) or 0)

    reasons: list[str] = []
    missing = []
    for name, value in (
        ("policy_raw.divergence", raw_div),
        ("policy_refit.divergence", refit_div),
        ("conversion_baseline.p3/p4", baseline_hard),
        ("conversion_refit.p3/p4", refit_hard),
        ("gate_refit_vs_strong.ci_high", ci_high),
    ):
        if value is None:
            missing.append(name)
    if gate_n <= 0:
        missing.append("gate_refit_vs_strong.n")

    hard_delta = (
        None if baseline_hard is None or refit_hard is None
        else refit_hard - baseline_hard
    )
    max_div = None if raw_div is None or refit_div is None else max(raw_div, refit_div)

    if missing:
        status = "stop_technical"
        decision = "reject"
        reasons.append("mesures C0 incomplètes: " + ", ".join(missing))
    elif ci_high < 0.5:
        status = "stop_regression"
        decision = "reject"
        reasons.append(f"régression vs référence forte établie (ci_high={ci_high:.6f})")
    elif max_div < min_policy_divergence:
        status = "stop_same_policy"
        decision = "reject"
        reasons.append(
            f"divergence politique max={max_div:.4f} < {min_policy_divergence:.4f}"
        )
    elif hard_delta < min_hard_delta:
        status = "stop_flat_c0"
        decision = "reject"
        reasons.append(
            f"conversion dure Δ={hard_delta:+.4f} < {min_hard_delta:+.4f}"
        )
    else:
        status = "proceed_t1"
        decision = "proceed"
        reasons.append(
            f"signal C0: divergence={max_div:.4f}, conversion dure Δ={hard_delta:+.4f}"
        )

    return {
        "schema": 1,
        "experiment": "forkc-c0",
        "decision": decision,
        "scientific_status": status,
        "thresholds": {
            "min_policy_divergence": min_policy_divergence,
            "min_hard_conversion_delta": min_hard_delta,
            "absolute_non_regression_ci_high": 0.5,
        },
        "metrics": {
            "raw_policy_divergence": raw_div,
            "refit_policy_divergence": refit_div,
            "max_policy_divergence": max_div,
            "baseline_hard_conversion": baseline_hard,
            "refit_hard_conversion": refit_hard,
            "hard_conversion_delta": hard_delta,
            "refit_vs_strong": gate_refit_vs_strong,
            "raw_weak_vs_strong": gate_raw_weak_vs_strong,
        },
        "reasons": reasons,
    }


def _read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-raw", type=Path, required=True)
    parser.add_argument("--policy-refit", type=Path, required=True)
    parser.add_argument("--gate-refit-vs-strong", type=Path, required=True)
    parser.add_argument("--gate-raw-weak-vs-strong", type=Path)
    parser.add_argument("--conversion-baseline", type=Path, required=True)
    parser.add_argument("--conversion-refit", type=Path, required=True)
    parser.add_argument("--min-policy-divergence", type=float, default=0.05)
    parser.add_argument("--min-hard-delta", type=float, default=0.02)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = decide(
        policy_raw=_read(args.policy_raw),
        policy_refit=_read(args.policy_refit),
        gate_refit_vs_strong=_read(args.gate_refit_vs_strong),
        gate_raw_weak_vs_strong=(
            _read(args.gate_raw_weak_vs_strong) if args.gate_raw_weak_vs_strong else None
        ),
        conversion_baseline=_read(args.conversion_baseline),
        conversion_refit=_read(args.conversion_refit),
        min_policy_divergence=args.min_policy_divergence,
        min_hard_delta=args.min_hard_delta,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, ensure_ascii=False))
    if manifest["scientific_status"] == "stop_technical":
        return 2
    return 0 if manifest["decision"] == "proceed" else 3


if __name__ == "__main__":
    sys.exit(main())
