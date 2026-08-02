#!/usr/bin/env python3
"""Fail closed when two L-BFGS arms reach the stopping surface asymmetrically."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def _arm(report: dict, label: str, expected_gtol: float) -> dict:
    required = {
        "success", "status", "message", "iterations", "function_evaluations",
        "gradient_inf_norm", "gtol",
    }
    missing = required - set(report)
    if missing:
        raise ValueError(f"{label}: missing optimizer keys {sorted(missing)}")
    iterations = report["iterations"]
    evaluations = report["function_evaluations"]
    gradient = report["gradient_inf_norm"]
    gtol = report["gtol"]
    if (
        not isinstance(report["success"], bool)
        or isinstance(report["status"], bool) or not isinstance(report["status"], int)
        or not isinstance(report["message"], str)
        or isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 0
        or isinstance(evaluations, bool) or not isinstance(evaluations, int) or evaluations < 1
        or isinstance(gradient, bool) or not isinstance(gradient, (int, float))
        or not math.isfinite(gradient) or gradient < 0.0
        or isinstance(gtol, bool) or not isinstance(gtol, (int, float))
        or not math.isfinite(gtol)
    ):
        raise ValueError(f"{label}: invalid optimizer scalar")
    if not math.isclose(float(gtol), expected_gtol, rel_tol=0.0, abs_tol=1e-15):
        raise ValueError(f"{label}: gtol={gtol}, expected {expected_gtol}")
    individual_valid = (
        report["success"] is True
        and report["status"] == 0
        and gradient <= expected_gtol
    )
    return {
        "success": report["success"],
        "status": report["status"],
        "message": report["message"],
        "iterations": iterations,
        "function_evaluations": evaluations,
        "gradient_inf_norm": gradient,
        "gtol": float(gtol),
        "gradient_to_gtol": gradient / expected_gtol,
        "individual_valid": individual_valid,
    }


def decide(
    arm_a: dict,
    arm_b: dict,
    *,
    expected_gtol: float,
    iteration_ratio_limit: float = 5.0,
) -> dict:
    if not math.isfinite(expected_gtol) or expected_gtol <= 0.0:
        raise ValueError("expected_gtol must be positive")
    if not math.isfinite(iteration_ratio_limit) or iteration_ratio_limit <= 1.0:
        raise ValueError("iteration_ratio_limit must be > 1")

    arms = {
        "a": _arm(arm_a, "arm a", expected_gtol),
        "b": _arm(arm_b, "arm b", expected_gtol),
    }
    counts = [arms[name]["iterations"] for name in ("a", "b")]
    if min(counts) == 0:
        iteration_ratio = 1.0 if max(counts) == 0 else None
        iteration_asymmetry = max(counts) > 0
    else:
        iteration_ratio = max(counts) / min(counts)
        iteration_asymmetry = iteration_ratio >= iteration_ratio_limit

    all_individual_valid = all(arm["individual_valid"] for arm in arms.values())
    pair_valid = all_individual_valid and not iteration_asymmetry
    if not all_individual_valid:
        verdict = "OPTIMIZER_PAIR_INVALID_ARM"
    elif iteration_asymmetry:
        verdict = "OPTIMIZER_PAIR_ASYMMETRY_BLOCK"
    else:
        verdict = "OPTIMIZER_PAIR_VALID"

    return {
        "schema": 1,
        "verdict": verdict,
        "pair_valid": pair_valid,
        "arms": arms,
        "thresholds": {
            "expected_gtol": expected_gtol,
            "iteration_ratio_limit_inclusive": iteration_ratio_limit,
        },
        "diagnostics": {
            "iteration_asymmetry": iteration_asymmetry,
            "iteration_ratio": iteration_ratio,
            "gradient_to_gtol_is_diagnostic_only": True,
        },
        "gate_authorized": pair_valid,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm-a", required=True, type=Path)
    parser.add_argument("--arm-b", required=True, type=Path)
    parser.add_argument("--expected-gtol", required=True, type=float)
    parser.add_argument("--iteration-ratio-limit", type=float, default=5.0)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = decide(
        json.loads(args.arm_a.read_text(encoding="utf-8")),
        json.loads(args.arm_b.read_text(encoding="utf-8")),
        expected_gtol=args.expected_gtol,
        iteration_ratio_limit=args.iteration_ratio_limit,
    )
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(result["verdict"])
    return 0 if result["pair_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
