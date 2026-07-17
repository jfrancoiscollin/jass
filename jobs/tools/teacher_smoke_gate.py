#!/usr/bin/env python3
"""Pre-engaged verdict for the matched A/B1/B2/B3 conversion smoke."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CELLS = ("A", "B1", "B2", "B3")


def _number(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def hard_conversion(report: dict) -> float | None:
    values = [_number(report.get(key)) for key in ("p3_mince", "p4_egal")]
    return None if any(value is None for value in values) else sum(values) / 2.0


def gate_state(match: dict | None) -> str:
    if not isinstance(match, dict) or int(match.get("n", 0) or 0) <= 0:
        return "technical"
    high = _number(match.get("ci_high"))
    if high is None:
        return "technical"
    return "regression" if high < 0.5 else "pass"


def decide(
    cells: dict,
    *,
    min_hard_delta: float = 0.02,
    simplicity_tolerance: float = 0.005,
) -> dict:
    missing = [cell for cell in CELLS if cell not in cells]
    if missing:
        return {
            "schema": 1,
            "decision": "reject",
            "scientific_status": "stop_technical",
            "reasons": ["cellules absentes: " + ", ".join(missing)],
            "cells": {},
        }
    baseline = hard_conversion(cells["A"].get("conversion", {}))
    reports = {}
    technical = baseline is None
    for name in CELLS:
        conversion = hard_conversion(cells[name].get("conversion", {}))
        if name == "A":
            vs_a = vs_absolute = "baseline"
        else:
            vs_a = gate_state(cells[name].get("vs_a"))
            vs_absolute = gate_state(cells[name].get("vs_absolute"))
            technical = technical or "technical" in (vs_a, vs_absolute)
        delta = None if baseline is None or conversion is None else conversion - baseline
        technical = technical or conversion is None
        eligible = (
            name != "A"
            and vs_a == "pass"
            and vs_absolute == "pass"
            and delta is not None
            and delta >= min_hard_delta
        )
        reports[name] = {
            "hard_conversion": conversion,
            "hard_delta_vs_a": delta,
            "vs_a": vs_a,
            "vs_absolute": vs_absolute,
            "eligible": eligible,
        }
    if technical:
        status, decision = "stop_technical", "reject"
        reasons = ["au moins une mesure de cellule est incomplète"]
        winner = None
    else:
        eligible = [name for name in ("B1", "B2", "B3") if reports[name]["eligible"]]
        if not eligible:
            status, decision, winner = "complete_no_signal", "reject", None
            reasons = [f"aucune cellule ne gagne ≥ {min_hard_delta:+.4f} sans régression"]
        else:
            best_delta = max(reports[name]["hard_delta_vs_a"] for name in eligible)
            # Small differences do not buy extra objective complexity.
            winner = next(
                name for name in ("B1", "B2", "B3")
                if name in eligible
                and reports[name]["hard_delta_vs_a"] >= best_delta - simplicity_tolerance
            )
            status, decision = f"confirm_{winner.lower()}", "confirm"
            reasons = [
                f"{winner} retenu: Δhard={reports[winner]['hard_delta_vs_a']:+.4f}; "
                f"tolérance simplicité={simplicity_tolerance:.4f}"
            ]
    return {
        "schema": 1,
        "experiment": "conversion-teacher-smoke",
        "decision": decision,
        "scientific_status": status,
        "winner": winner,
        "thresholds": {
            "min_hard_conversion_delta": min_hard_delta,
            "simplicity_tolerance": simplicity_tolerance,
            "non_regression_ci_high": 0.5,
        },
        "cells": reports,
        "interpretation": {
            "B1": "counterfactual information fits through ordinary WDL",
            "B2": "static preference composes; leaf-mode complexity is unnecessary",
            "B3": "benefit is specific to through-search preference",
        },
        "reasons": reasons,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--min-hard-delta", type=float, default=0.02)
    parser.add_argument("--simplicity-tolerance", type=float, default=0.005)
    args = parser.parse_args(argv)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    manifest = decide(
        payload,
        min_hard_delta=args.min_hard_delta,
        simplicity_tolerance=args.simplicity_tolerance,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, ensure_ascii=False))
    if manifest["scientific_status"] == "stop_technical":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
