#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed gates for the staged Gen2-MMTO P3 decision campaign."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected object")
    return value


def autopsy(data: dict, args: argparse.Namespace) -> dict:
    if data.get("scope") != "failures":
        raise ValueError("autopsy gate requires scope=failures")
    processed = int(data.get("processed", 0))
    hard_pairs = int(data.get("hard_pairs", 0))
    rescue_rate = data.get("rescue_rate")
    recovery = data.get("rerank_recovery_rate")
    if rescue_rate is None or recovery is None:
        raise ValueError("autopsy lacks rescue measurements")
    passed = (processed >= args.min_n and hard_pairs >= args.min_pairs
              and float(rescue_rate) >= args.min_rescue_rate
              and float(recovery) >= args.min_recovery_rate)
    return {
        "schema": 1,
        "stage": "p3_autopsy",
        "verdict": "decision_signal" if passed else "no_actionable_sibling_signal",
        "pass": passed,
        "processed": processed,
        "hard_pairs": hard_pairs,
        "rescue_rate": float(rescue_rate),
        "rerank_recovery_rate": float(recovery),
        "gates": {
            "min_n": args.min_n,
            "min_pairs": args.min_pairs,
            "min_rescue_rate": args.min_rescue_rate,
            "min_recovery_rate": args.min_recovery_rate,
        },
    }


def screen(data: dict, args: argparse.Namespace) -> dict:
    if data.get("scope") != "all":
        raise ValueError("screen gate requires scope=all")
    paired = data.get("paired")
    if not isinstance(paired, dict):
        raise ValueError("missing paired result")
    n = int(paired.get("n", 0))
    delta = paired.get("delta")
    low = paired.get("ci95_low")
    if delta is None or low is None:
        raise ValueError("empty paired result")
    passed = n >= args.min_n and float(delta) >= args.min_delta and float(low) > 0.0
    return {
        "schema": 1,
        "stage": "conditional_second_pass",
        "verdict": "conditional_search_candidate" if passed else "second_pass_not_confirmed",
        "pass": passed,
        "n": n,
        "delta": float(delta),
        "ci95_low": float(low),
        "ci95_high": float(paired.get("ci95_high", 0.0)),
        "changed_move": int(data.get("changed_move", 0)),
        "regressions": int(data.get("regressions", 0)),
        "gates": {"min_n": args.min_n, "min_delta": args.min_delta, "lower_ci_above": 0.0},
    }


def ranker(data: dict, args: argparse.Namespace) -> dict:
    hold = data.get("holdout")
    if not isinstance(hold, dict):
        raise ValueError("missing holdout metrics")
    n = int(hold.get("n", 0))
    acc = float(hold.get("accuracy", 0.0))
    loss = float(hold.get("log_loss", 99.0))
    passed = bool(data.get("signal")) and n >= args.min_n and acc >= args.min_accuracy
    return {
        "schema": 1,
        "stage": "sibling_ranker",
        "verdict": "ranker_signal" if passed else "ranker_no_signal",
        "pass": passed,
        "holdout_n": n,
        "holdout_accuracy": acc,
        "holdout_log_loss": loss,
        "gates": {"min_n": args.min_n, "min_accuracy": args.min_accuracy},
    }


def _paired_from_conv(baseline: dict, candidate: dict) -> dict[str, float | int]:
    def rows(data: dict) -> dict[int, str]:
        if int(data.get("n_errors", 0)) != 0:
            raise ValueError("conversion result contains engine errors")
        out = {}
        for row in data.get("position_results", []):
            if isinstance(row, dict) and row.get("result") in {"win", "draw", "loss"}:
                index = int(row["index"])
                if index in out:
                    raise ValueError(f"duplicate position index {index}")
                out[index] = str(row["result"])
        return out
    b, c = rows(baseline), rows(candidate)
    common = sorted(set(b) & set(c))
    if not common:
        raise ValueError("empty paired conversion intersection")
    diffs = [(1 if c[i] == "win" else 0) - (1 if b[i] == "win" else 0) for i in common]
    n = len(diffs); mean = sum(diffs) / n
    if n > 1:
        var = sum((x - mean) ** 2 for x in diffs) / (n - 1)
        se = (var / n) ** 0.5
    else:
        se = 0.0
    return {"n": n, "delta": mean, "ci95_low": mean - 1.96 * se, "ci95_high": mean + 1.96 * se}


def candidate(data: dict, args: argparse.Namespace) -> dict:
    baseline = load(args.baseline)
    depth_gate = load(args.depth_gate)
    movetime_gate = load(args.movetime_gate)
    paired = _paired_from_conv(baseline, data)
    for label, gate in (("depth", depth_gate), ("movetime", movetime_gate)):
        if int(gate.get("n", 0)) < args.min_games:
            raise ValueError(f"{label} gate too small")
    strength_ok = (float(depth_gate.get("rate", 0.0)) >= args.min_rate
                   and float(depth_gate.get("ci_high", 0.0)) >= 0.5
                   and float(movetime_gate.get("rate", 0.0)) >= args.min_rate
                   and float(movetime_gate.get("ci_high", 0.0)) >= 0.5)
    passed = (int(paired["n"]) >= args.min_n
              and float(paired["delta"]) >= args.min_delta
              and float(paired["ci95_low"]) > 0.0
              and strength_ok)
    return {
        "schema": 1,
        "stage": "mmto_v2_candidate",
        "verdict": "candidate_for_confirmation" if passed else "mmto_v2_not_confirmed",
        "pass": passed,
        "paired_conversion": paired,
        "depth_gate": depth_gate,
        "movetime_gate": movetime_gate,
        "gates": {
            "min_n": args.min_n, "min_delta": args.min_delta,
            "min_games": args.min_games, "min_rate": args.min_rate,
            "lower_conversion_ci_above": 0.0, "strength_ci_high_at_least": 0.5,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("autopsy")
    a.add_argument("--input", type=Path, required=True)
    a.add_argument("--min-n", type=int, default=100)
    a.add_argument("--min-pairs", type=int, default=50)
    a.add_argument("--min-rescue-rate", type=float, default=0.10)
    a.add_argument("--min-recovery-rate", type=float, default=0.50)
    s = sub.add_parser("screen")
    s.add_argument("--input", type=Path, required=True)
    s.add_argument("--min-n", type=int, default=400)
    s.add_argument("--min-delta", type=float, default=0.02)
    r = sub.add_parser("ranker")
    r.add_argument("--input", type=Path, required=True)
    r.add_argument("--min-n", type=int, default=20)
    r.add_argument("--min-accuracy", type=float, default=0.55)
    c = sub.add_parser("candidate")
    c.add_argument("--input", type=Path, required=True, help="candidate conv_fixed_wdl JSON")
    c.add_argument("--baseline", type=Path, required=True)
    c.add_argument("--depth-gate", type=Path, required=True)
    c.add_argument("--movetime-gate", type=Path, required=True)
    c.add_argument("--min-n", type=int, default=400)
    c.add_argument("--min-delta", type=float, default=0.02)
    c.add_argument("--min-games", type=int, default=600)
    c.add_argument("--min-rate", type=float, default=0.49)
    for p in (a, s, r, c):
        p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = load(args.input)
        report = {"autopsy": autopsy, "screen": screen, "ranker": ranker, "candidate": candidate}[args.command](data, args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["pass"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
