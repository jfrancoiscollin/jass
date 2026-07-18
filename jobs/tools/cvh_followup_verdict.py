#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Aggregate and gate the Gen2-MMTO CVH follow-up campaign.

The tool is intentionally fail-closed: missing cells, too-small samples, parsing
errors and empty intersections are errors rather than neutral outcomes.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable

RESULT_RE = re.compile(r"^RESULT\s+(\d+)\s+(\d+)\s+(\d+)\s*$")
VALID_OUTCOMES = {"win", "draw", "loss"}


def score_stats(a_wins: int, draws: int, b_wins: int) -> dict[str, float | int]:
    n = a_wins + draws + b_wins
    if n <= 0:
        raise ValueError("n=0")
    rate = (a_wins + 0.5 * draws) / n
    ex2 = (a_wins + 0.25 * draws) / n
    variance = max(0.0, ex2 - rate * rate)
    se = math.sqrt(variance / n)
    half = 1.96 * se
    elo = -400.0 * math.log10(1.0 / rate - 1.0) if 0.0 < rate < 1.0 else 0.0
    return {
        "a_wins": a_wins,
        "draws": draws,
        "b_wins": b_wins,
        "n": n,
        "rate": rate,
        "ci95_low": rate - half,
        "ci95_high": rate + half,
        "elo": elo,
    }


def last_result(path: Path) -> tuple[int, int, int]:
    found: tuple[int, int, int] | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = RESULT_RE.match(line.strip())
        if match:
            found = tuple(int(match.group(i)) for i in range(1, 4))
    if found is None:
        raise ValueError(f"{path}: no RESULT line")
    return found


def aggregate_match(paths: Iterable[Path]) -> dict[str, object]:
    a = d = b = 0
    used: list[str] = []
    for path in paths:
        x, y, z = last_result(path)
        a += x
        d += y
        b += z
        used.append(str(path))
    out: dict[str, object] = {"schema": 1, "inputs": used}
    out.update(score_stats(a, d, b))
    return out


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected JSON object")
    return value


def nps_gate(general: dict[str, object], p3: dict[str, object],
             min_general_ratio: float, min_az_ratio: float,
             max_az_ratio: float) -> dict[str, object]:
    def cells(report: dict[str, object]) -> dict[str, dict[str, object]]:
        raw = report.get("cells")
        if not isinstance(raw, dict):
            raise ValueError("missing cells")
        for name in ("A", "Z", "C10"):
            if name not in raw or not isinstance(raw[name], dict):
                raise ValueError(f"missing cell {name}")
            if int(raw[name].get("searches", 0)) <= 0:
                raise ValueError(f"cell {name}: n=0")
            if int(raw[name].get("errors", 0)) != 0:
                raise ValueError(f"cell {name}: benchmark errors")
        return raw  # type: ignore[return-value]

    gc = cells(general)
    pc = cells(p3)
    if int(general.get("az_move_mismatches", -1)) != 0:
        raise ValueError("A/Z move mismatch")
    if int(general.get("az_common_searches", 0)) <= 0:
        raise ValueError("A/Z common n=0")
    z_ratio = float(gc["Z"].get("nps_ratio_vs_a", 0.0))
    c_ratio = float(gc["C10"].get("nps_ratio_vs_a", 0.0))
    p3_ratio = float(pc["C10"].get("nps_ratio_vs_a", 0.0))
    passed = (
        min_az_ratio <= z_ratio <= max_az_ratio
        and c_ratio >= min_general_ratio
    )
    return {
        "schema": 1,
        "stage": "nps",
        "verdict": "nps_pass" if passed else "nps_fail",
        "pass": passed,
        "az_nps_ratio": z_ratio,
        "c10_general_nps_ratio": c_ratio,
        "c10_p3_nps_ratio": p3_ratio,
        "gates": {
            "min_general_ratio": min_general_ratio,
            "min_az_ratio": min_az_ratio,
            "max_az_ratio": max_az_ratio,
        },
    }


def match_gate(report: dict[str, object], stage: str, min_n: int,
               min_rate: float) -> dict[str, object]:
    n = int(report.get("n", 0))
    rate = float(report.get("rate", -1.0))
    high = float(report.get("ci95_high", -1.0))
    if n < min_n:
        raise ValueError(f"{stage}: n={n} < {min_n}")
    # Non-regression screen: do not proceed when the point estimate is materially
    # below parity or when even the upper 95% bound is below parity.
    passed = rate >= min_rate and high >= 0.5
    return {
        "schema": 1,
        "stage": stage,
        "verdict": f"{stage}_pass" if passed else f"{stage}_regression",
        "pass": passed,
        "n": n,
        "rate": rate,
        "ci95_low": float(report.get("ci95_low", 0.0)),
        "ci95_high": high,
        "elo": float(report.get("elo", 0.0)),
        "gates": {"min_n": min_n, "min_rate": min_rate, "upper_ci_at_least": 0.5},
    }


def merge_position_results(paths: Iterable[Path]) -> dict[int, str]:
    merged: dict[int, str] = {}
    for path in paths:
        data = load_json(path)
        rows = data.get("position_results")
        if not isinstance(rows, list):
            raise ValueError(f"{path}: missing position_results")
        for row in rows:
            if not isinstance(row, dict):
                continue
            result = row.get("result")
            if result not in VALID_OUTCOMES:
                continue
            index = int(row["index"])
            if index in merged:
                raise ValueError(f"duplicate position index {index}")
            merged[index] = str(result)
    return merged


def confirmation_gate(baseline_paths: Iterable[Path], candidate_paths: Iterable[Path],
                      min_n: int, min_delta: float) -> dict[str, object]:
    baseline = merge_position_results(baseline_paths)
    candidate = merge_position_results(candidate_paths)
    common = sorted(set(baseline) & set(candidate))
    if len(common) < min_n:
        raise ValueError(f"paired confirmation n={len(common)} < {min_n}")
    diffs: list[float] = []
    a_wins = c_wins = 0
    for index in common:
        av = 1.0 if baseline[index] == "win" else 0.0
        cv = 1.0 if candidate[index] == "win" else 0.0
        a_wins += int(av)
        c_wins += int(cv)
        diffs.append(cv - av)
    n = len(diffs)
    delta = sum(diffs) / n
    if n > 1:
        mean = delta
        variance = sum((x - mean) ** 2 for x in diffs) / (n - 1)
        se = math.sqrt(variance / n)
    else:
        se = 0.0
    half = 1.96 * se
    low, high = delta - half, delta + half
    passed = delta >= min_delta and low > 0.0
    return {
        "schema": 1,
        "stage": "p3_confirmation",
        "verdict": "candidate_for_l3_fork" if passed else "p3_not_confirmed",
        "pass": passed,
        "paired_n": n,
        "baseline_conversion": a_wins / n,
        "candidate_conversion": c_wins / n,
        "delta": delta,
        "ci95_low": low,
        "ci95_high": high,
        "gates": {"min_n": min_n, "min_delta": min_delta, "lower_ci_above": 0.0},
    }


def write_report(report: dict[str, object], out: Path | None) -> None:
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    agg = sub.add_parser("aggregate-match")
    agg.add_argument("inputs", nargs="+", type=Path)
    agg.add_argument("--out", type=Path)

    ng = sub.add_parser("nps-gate")
    ng.add_argument("--general", required=True, type=Path)
    ng.add_argument("--p3", required=True, type=Path)
    ng.add_argument("--min-general-ratio", type=float, default=0.98)
    ng.add_argument("--min-az-ratio", type=float, default=0.99)
    ng.add_argument("--max-az-ratio", type=float, default=1.01)
    ng.add_argument("--out", type=Path)

    mg = sub.add_parser("match-gate")
    mg.add_argument("--match", required=True, type=Path)
    mg.add_argument("--stage", choices=("common_search", "movetime"), required=True)
    mg.add_argument("--min-n", type=int, default=64)
    mg.add_argument("--min-rate", type=float, default=0.49)
    mg.add_argument("--out", type=Path)

    cg = sub.add_parser("confirm")
    cg.add_argument("--baseline", nargs="+", required=True, type=Path)
    cg.add_argument("--candidate", nargs="+", required=True, type=Path)
    cg.add_argument("--min-n", type=int, default=400)
    cg.add_argument("--min-delta", type=float, default=0.02)
    cg.add_argument("--out", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "aggregate-match":
            report = aggregate_match(args.inputs)
        elif args.command == "nps-gate":
            report = nps_gate(load_json(args.general), load_json(args.p3),
                              args.min_general_ratio, args.min_az_ratio,
                              args.max_az_ratio)
        elif args.command == "match-gate":
            report = match_gate(load_json(args.match), args.stage,
                                args.min_n, args.min_rate)
        else:
            report = confirmation_gate(args.baseline, args.candidate,
                                       args.min_n, args.min_delta)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    write_report(report, args.out)
    return 0 if bool(report.get("pass", True)) else 3


if __name__ == "__main__":
    raise SystemExit(main())
