#!/usr/bin/env python3
"""Fail closed unless an optimizer report satisfies the sealed convergence rule."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def verify_optimizer_report(
    report: dict,
    *,
    expected_max_iterations: int,
    expected_maxcor: int,
    expected_gtol: float,
) -> dict:
    """Validate both SciPy success and the actual final projected gradient."""
    if report.get("success") is not True:
        raise ValueError(f"optimizer did not report success: {report}")
    if int(report.get("status", -1)) != 0:
        raise ValueError(f"optimizer status is not zero: {report.get('status')}")
    iterations = int(report.get("iterations", 0))
    if iterations <= 0:
        raise ValueError("optimizer performed zero iterations")
    if int(report.get("max_iterations", -1)) != expected_max_iterations:
        raise ValueError("optimizer max-iteration contract drift")
    if int(report.get("maxcor", -1)) != expected_maxcor:
        raise ValueError("optimizer maxcor contract drift")
    gtol = float(report.get("gtol", float("nan")))
    if not math.isfinite(gtol) or gtol != expected_gtol:
        raise ValueError(f"optimizer gtol contract drift: {gtol}")
    gradient = float(report.get("gradient_inf_norm", float("nan")))
    if not math.isfinite(gradient):
        raise ValueError("optimizer final gradient is not finite")
    if gradient > expected_gtol:
        raise ValueError(
            f"optimizer stopped above gtol: gradient_inf_norm={gradient:.12g} "
            f"> gtol={expected_gtol:.12g}"
        )
    return {
        "success": True,
        "status": 0,
        "iterations": iterations,
        "gradient_inf_norm": gradient,
        "gtol": gtol,
        "max_iterations": expected_max_iterations,
        "maxcor": expected_maxcor,
        "message": str(report.get("message", "")),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--expected-max-iterations", required=True, type=int)
    parser.add_argument("--expected-maxcor", required=True, type=int)
    parser.add_argument("--expected-gtol", required=True, type=float)
    parser.add_argument("--receipt")
    args = parser.parse_args(argv)
    source = Path(args.report)
    verified = verify_optimizer_report(
        json.loads(source.read_text(encoding="utf-8")),
        expected_max_iterations=args.expected_max_iterations,
        expected_maxcor=args.expected_maxcor,
        expected_gtol=args.expected_gtol,
    )
    payload = {
        "schema": "jass.optimizer_convergence_receipt.v1",
        "label": args.label,
        "report": str(source),
        **verified,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        Path(args.receipt).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
