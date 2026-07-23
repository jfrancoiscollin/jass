#!/usr/bin/env python3
"""Select and confirm a C0/P1 convex PJTW meta-evaluation."""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def combined(reports: list[dict]) -> dict:
    wins = sum(int(r["wins_a"]) for r in reports)
    draws = sum(int(r["draws"]) for r in reports)
    losses = sum(int(r["wins_b"]) for r in reports)
    n = wins + draws + losses
    if n <= 0:
        raise ValueError("empty combined gate")
    rate = (wins + 0.5 * draws) / n
    variance = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(variance / n)
    ci_low = max(0.0, rate - 1.96 * se)
    ci_high = min(1.0, rate + 1.96 * se)
    elo = -400 * math.log10(1 / rate - 1) if 0 < rate < 1 else 0.0
    return {
        "wins_meta": wins,
        "draws": draws,
        "wins_parent": losses,
        "n": n,
        "meta_score_rate": round(rate, 6),
        "ci_low": round(ci_low, 6),
        "ci_high": round(ci_high, 6),
        "meta_elo_vs_parent": round(elo, 2),
    }


def alpha_tag(alpha: float) -> str:
    return f"c0w{round(alpha * 1000):04d}"


def select(args: argparse.Namespace) -> dict:
    rows = []
    for alpha in args.alphas:
        tag = alpha_tag(alpha)
        vs_c0 = load(args.screen_dir / f"screen-{tag}-vs-c0.json")
        vs_p1 = load(args.screen_dir / f"screen-{tag}-vs-p1.json")
        row = {
            "alpha_c0": alpha,
            "alpha_p1": 1.0 - alpha,
            "tag": tag,
            "vs_c0": vs_c0,
            "vs_p1": vs_p1,
            "worst_score_rate": min(float(vs_c0["rate"]), float(vs_p1["rate"])),
            "mean_score_rate": (float(vs_c0["rate"]) + float(vs_p1["rate"])) / 2.0,
        }
        rows.append(row)
    winner = max(rows, key=lambda r: (r["worst_score_rate"], r["mean_score_rate"], -abs(r["alpha_c0"] - 0.5)))
    return {
        "schema": 1,
        "protocol": "l3-pure-c0-p1-meta-blend-screen",
        "selection_rule": "maximize min(score_vs_c0,score_vs_p1), then mean, then closeness_to_50_50",
        "candidates": rows,
        "selected": {k: winner[k] for k in ("alpha_c0", "alpha_p1", "tag", "worst_score_rate", "mean_score_rate")},
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def confirm(args: argparse.Namespace) -> dict:
    selection = load(args.selection)
    selected = selection["selected"]
    depth_c0 = load(args.depth_vs_c0)
    time_c0 = load(args.movetime_vs_c0)
    depth_p1 = load(args.depth_vs_p1)
    time_p1 = load(args.movetime_vs_p1)
    c0 = combined([depth_c0, time_c0])
    p1 = combined([depth_p1, time_p1])
    all_point_positive = all(float(r["rate"]) > 0.5 for r in (depth_c0, time_c0, depth_p1, time_p1))
    proven_c0 = c0["meta_score_rate"] >= 0.505 and c0["ci_low"] > 0.5
    proven_p1 = p1["meta_score_rate"] >= 0.505 and p1["ci_low"] > 0.5
    directional_c0 = c0["meta_score_rate"] > 0.5
    directional_p1 = p1["meta_score_rate"] > 0.5
    if all_point_positive and proven_c0 and proven_p1:
        decision = "META_SUPERIOR_TO_BOTH"
    elif directional_c0 and directional_p1:
        decision = "META_DIRECTIONALLY_BETTER_NOT_PROVEN"
    elif directional_c0 != directional_p1:
        decision = "META_TRADEOFF_ONLY"
    else:
        decision = "META_NOT_BETTER_THAN_BOTH"
    payload = {
        "schema": 1,
        "protocol": "l3-pure-c0-p1-meta-blend-confirmation",
        "decision": decision,
        "selected": selected,
        "screen": selection,
        "views": {
            "depth9_vs_c0": depth_c0,
            "movetime_vs_c0": time_c0,
            "depth9_vs_p1": depth_p1,
            "movetime_vs_p1": time_p1,
        },
        "combined_vs_c0": c0,
        "combined_vs_p1": p1,
        "criteria": {
            "all_four_point_estimates_above_50pct": all_point_positive,
            "combined_score_min": 0.505,
            "combined_ci_low_must_exceed": 0.5,
            "proven_vs_c0": proven_c0,
            "proven_vs_p1": proven_p1,
        },
        "training_records": 0,
        "self_play_games_for_training": 0,
        "promotion_authorized": False,
        "training_continuation_authorized": False,
        "automatic_next_job": None,
    }
    return payload


def write(payload: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_select = sub.add_parser("select")
    p_select.add_argument("--screen-dir", required=True, type=Path)
    p_select.add_argument("--alphas", required=True, nargs="+", type=float)
    p_select.add_argument("--out", required=True, type=Path)
    p_confirm = sub.add_parser("confirm")
    p_confirm.add_argument("--selection", required=True, type=Path)
    p_confirm.add_argument("--depth-vs-c0", required=True, type=Path)
    p_confirm.add_argument("--movetime-vs-c0", required=True, type=Path)
    p_confirm.add_argument("--depth-vs-p1", required=True, type=Path)
    p_confirm.add_argument("--movetime-vs-p1", required=True, type=Path)
    p_confirm.add_argument("--out", required=True, type=Path)
    p_confirm.add_argument("--summary-out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "select":
            payload = select(args)
        else:
            payload = confirm(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"l3_pure_meta_blend: {exc}", file=__import__("sys").stderr)
        return 2
    write(payload, args.out)
    if args.command == "confirm" and args.summary_out:
        summary = {
            "job_class": "l3-pure-meta-blend",
            "decision": payload["decision"],
            "selected_alpha_c0": payload["selected"]["alpha_c0"],
            "selected_alpha_p1": payload["selected"]["alpha_p1"],
            "meta_elo_vs_c0": payload["combined_vs_c0"]["meta_elo_vs_parent"],
            "meta_elo_vs_p1": payload["combined_vs_p1"]["meta_elo_vs_parent"],
            "promotion_authorized": False,
            "automatic_next_job": None,
        }
        write(summary, args.summary_out)
    print(payload.get("decision", f"selected={payload['selected']['tag']}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
