#!/usr/bin/env python3
"""Power plan and fail-closed confirmation gate for the fresh P3 holdout."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import NormalDist


def report_counts(report: dict) -> tuple[int, int]:
    n = int(report.get("n_pos", report.get("n", 0)) or 0)
    wins = int(report.get("n_win", 0) or 0)
    if n <= 0 or wins < 0 or wins > n or report.get("complete") is False:
        raise ValueError("incomplete conversion report")
    return wins, n


def wilson(wins: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n <= 0:
        raise ValueError("n must be positive")
    z = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    p = wins / n
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denominator
    radius = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return max(0.0, centre - radius), min(1.0, centre + radius)


def difference_report(candidate: dict, baseline: dict, alpha: float = 0.05) -> dict:
    cw, cn = report_counts(candidate)
    bw, bn = report_counts(baseline)
    c_rate, b_rate = cw / cn, bw / bn
    c_low, c_high = wilson(cw, cn, alpha)
    b_low, b_high = wilson(bw, bn, alpha)
    # Newcombe's unpaired Wilson interval is conservative for our matched
    # position schedule because the current harness does not retain pairs.
    return {
        "candidate": {"wins": cw, "n": cn, "rate": c_rate},
        "baseline": {"wins": bw, "n": bn, "rate": b_rate},
        "delta": c_rate - b_rate,
        "ci_low": c_low - b_high,
        "ci_high": c_high - b_low,
        "alpha": alpha,
        "method": "newcombe_unpaired_wilson_conservative",
    }


def required_n_per_arm(
    baseline_rate: float,
    min_delta: float = 0.02,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    if not 0.0 < baseline_rate < 1.0:
        raise ValueError("baseline_rate must be in (0,1)")
    if not 0.0 < min_delta < 1.0 - baseline_rate:
        raise ValueError("min_delta is incompatible with baseline_rate")
    if not 0.0 < alpha < 1.0 or not 0.0 < power < 1.0:
        raise ValueError("alpha and power must be in (0,1)")
    candidate_rate = baseline_rate + min_delta
    pooled = (baseline_rate + candidate_rate) / 2.0
    z_alpha = NormalDist().inv_cdf(1.0 - alpha / 2.0)
    z_power = NormalDist().inv_cdf(power)
    numerator = (
        z_alpha * math.sqrt(2.0 * pooled * (1.0 - pooled))
        + z_power * math.sqrt(
            baseline_rate * (1.0 - baseline_rate)
            + candidate_rate * (1.0 - candidate_rate)
        )
    ) ** 2
    return math.ceil(numerator / (min_delta * min_delta))


def power_plan(
    baseline: dict,
    *,
    min_delta: float = 0.02,
    alpha: float = 0.05,
    power: float = 0.80,
) -> dict:
    wins, n = report_counts(baseline)
    baseline_rate = wins / n
    required = required_n_per_arm(baseline_rate, min_delta, alpha, power)
    return {
        "schema": 1,
        "experiment": "p3-blind-confirmation",
        "baseline_rate": baseline_rate,
        "baseline_n": n,
        "min_effect": min_delta,
        "alpha": alpha,
        "target_power": power,
        "required_n_per_arm": required,
        "method": "two_independent_proportions_conservative",
    }


def gate_state(match: dict) -> str:
    if not isinstance(match, dict) or int(match.get("n", 0) or 0) <= 0:
        return "technical"
    high = match.get("ci_high")
    if high is None:
        return "technical"
    return "regression" if float(high) < 0.5 else "pass"


def decide(
    payload: dict,
    *,
    min_delta: float = 0.02,
    p4_margin: float = 0.02,
    alpha: float = 0.05,
    power: float = 0.80,
) -> dict:
    reasons: list[str] = []
    try:
        smoke = payload["smoke_decision"]
        winner = str(payload["winner"])
        if (
            smoke.get("decision") != "confirm"
            or smoke.get("winner") != winner
            or smoke.get("scientific_status") != f"confirm_{winner.lower()}"
        ):
            raise ValueError("winner does not match the pre-engaged smoke decision")
        p3 = difference_report(payload["candidate_p3"], payload["baseline_p3"], alpha)
        p4 = difference_report(payload["candidate_p4"], payload["baseline_p4"], alpha)
        plan = power_plan(
            payload["baseline_p3"], min_delta=min_delta, alpha=alpha, power=power
        )
        vs_a = gate_state(payload["vs_a"])
        vs_absolute = gate_state(payload["vs_absolute"])
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "schema": 1,
            "decision": "reject",
            "scientific_status": "stop_technical",
            "winner": payload.get("winner"),
            "reasons": [str(exc)],
        }

    required = plan["required_n_per_arm"]
    observed_min = min(p3["candidate"]["n"], p3["baseline"]["n"])
    if "technical" in (vs_a, vs_absolute):
        status, decision = "stop_technical", "reject"
        reasons.append("generalist gate is incomplete")
    elif "regression" in (vs_a, vs_absolute):
        status, decision = "stop_regression", "reject"
        reasons.append("generalist regression is established")
    elif observed_min < required:
        status, decision = "complete_underpowered", "reject"
        reasons.append(f"P3 n={observed_min} < conservative target {required} per arm")
    elif p3["delta"] < min_delta or p3["ci_low"] <= 0.0:
        status, decision = "complete_no_confirmation", "reject"
        reasons.append(
            f"P3 delta={p3['delta']:+.4f}, CI low={p3['ci_low']:+.4f}"
        )
    elif p4["delta"] < -p4_margin:
        status, decision = "stop_p4_regression", "reject"
        reasons.append(f"P4 point delta={p4['delta']:+.4f} < {-p4_margin:+.4f}")
    else:
        status, decision = "confirmed", "confirm"
        reasons.append(
            f"fresh P3 delta={p3['delta']:+.4f}, CI low={p3['ci_low']:+.4f}"
        )
    return {
        "schema": 1,
        "experiment": "teacher-p3-blind-confirmation",
        "decision": decision,
        "scientific_status": status,
        "winner": winner,
        "thresholds": {
            "p3_min_delta": min_delta,
            "p4_point_non_regression_margin": p4_margin,
            "generalist_non_regression_ci_high": 0.5,
            "alpha": alpha,
            "target_power": power,
        },
        "power_plan": plan,
        "p3": p3,
        "p4": p4,
        "vs_a": vs_a,
        "vs_absolute": vs_absolute,
        "reasons": reasons,
    }


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--baseline-report", type=Path, required=True)
    confirm = sub.add_parser("confirm")
    confirm.add_argument("--input", type=Path, required=True)
    for command in (plan, confirm):
        command.add_argument("--min-delta", type=float, default=0.02)
        command.add_argument("--alpha", type=float, default=0.05)
        command.add_argument("--power", type=float, default=0.80)
        command.add_argument("--out", type=Path, required=True)
    confirm.add_argument("--p4-margin", type=float, default=0.02)
    args = parser.parse_args(argv)
    if args.command == "plan":
        result = power_plan(
            json.loads(args.baseline_report.read_text(encoding="utf-8")),
            min_delta=args.min_delta,
            alpha=args.alpha,
            power=args.power,
        )
    else:
        result = decide(
            json.loads(args.input.read_text(encoding="utf-8")),
            min_delta=args.min_delta,
            p4_margin=args.p4_margin,
            alpha=args.alpha,
            power=args.power,
        )
    write_result(args.out, result)
    return 2 if result.get("scientific_status") == "stop_technical" else 0


if __name__ == "__main__":
    raise SystemExit(main())
