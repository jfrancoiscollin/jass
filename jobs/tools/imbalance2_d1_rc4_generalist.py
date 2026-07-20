#!/usr/bin/env python3
"""Run a small paired control-vs-RC4 generalist guard.

The guard is secondary and can only veto the pilot.  It uses deterministic fixed
FENs, swaps colours within each pair, and declares a regression established only
when the paired bootstrap interval lies wholly below 50%.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
import sys


def interval(values: list[float]) -> list[float]:
    values = sorted(values)
    n = len(values)
    return [values[int(0.025 * (n - 1))], values[int(0.975 * (n - 1))]]


def pair_bootstrap(pair_scores: list[float], reps: int, seed: int) -> list[float]:
    rng = random.Random(seed)
    n = len(pair_scores)
    samples = []
    for _ in range(reps):
        samples.append(sum(pair_scores[rng.randrange(n)] for _ in range(n)) / n)
    return interval(samples)


def load_fens(path: Path) -> list[str]:
    fens = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line[0] not in "WB" or ":W" not in line or ":B" not in line:
            continue
        fens.append(line)
    if not fens:
        raise ValueError(f"{path}: no usable FENs")
    return fens


def rc4_points(outcome: str, rc4_is_white: bool) -> float:
    if outcome == "D":
        return 0.5
    rc4_won = (rc4_is_white and outcome == "W") or ((not rc4_is_white) and outcome == "L")
    return 1.0 if rc4_won else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-jass", required=True)
    parser.add_argument("--control-pattern", required=True)
    parser.add_argument("--rc4-jass", required=True)
    parser.add_argument("--rc4-pattern", required=True)
    parser.add_argument("--openings", required=True)
    parser.add_argument("--search-params", required=True)
    parser.add_argument("--pairs", type=int, default=64)
    parser.add_argument("--depth", type=int, default=8)
    parser.add_argument("--max-plies", type=int, default=200)
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=314159)
    parser.add_argument("--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.pairs != 64 or args.depth != 8 or args.max_plies != 200:
        parser.error("generalist guard contract is fixed at 64 pairs, d8, maxplies 200")
    if args.bootstrap < 10000:
        parser.error("generalist guard requires at least 10000 bootstrap replicates")
    if len(args.search_params.split(",")) != 63:
        parser.error("generalist guard requires 63 pinned search keys")

    tool = Path(args.calibrate_tool).resolve()
    sys.path.insert(0, str(tool.parent))
    import calibrate_vs_scan as cv  # type: ignore

    fens = load_fens(Path(args.openings))
    rng = random.Random(args.seed)
    if len(fens) < args.pairs:
        parser.error(f"need at least {args.pairs} fixed FENs, found {len(fens)}")
    chosen = rng.sample(fens, args.pairs)

    control = cv.JassEngine(
        args.control_jass,
        label="D1-control-generalist",
        pattern_path=args.control_pattern,
        search_params=args.search_params,
    )
    rc4 = cv.JassEngine(
        args.rc4_jass,
        label="D1-RC4-generalist",
        pattern_path=args.rc4_pattern,
        search_params=args.search_params,
    )
    referee = cv.Referee(args.control_jass)
    games: list[dict[str, object]] = []
    pair_scores: list[float] = []
    try:
        for pair_index, fen in enumerate(chosen):
            a = cv.play_game(rc4, control, referee, fen, depth=args.depth, max_plies=args.max_plies)
            b = cv.play_game(control, rc4, referee, fen, depth=args.depth, max_plies=args.max_plies)
            score_a = rc4_points(a.outcome, True)
            score_b = rc4_points(b.outcome, False)
            pair_score = (score_a + score_b) / 2.0
            pair_scores.append(pair_score)
            games.extend([
                {"pair": pair_index, "rc4_colour": "white", "outcome_white_pov": a.outcome, "rc4_points": score_a, "plies": a.plies, "reason": a.reason},
                {"pair": pair_index, "rc4_colour": "black", "outcome_white_pov": b.outcome, "rc4_points": score_b, "plies": b.plies, "reason": b.reason},
            ])
    finally:
        for engine in (control, rc4, referee):
            try:
                engine.close()
            except Exception:
                pass

    score_rate = sum(pair_scores) / len(pair_scores)
    ci = pair_bootstrap(pair_scores, args.bootstrap, args.seed + 1)
    regression_established = ci[1] < 0.5
    guard_pass = (not regression_established) and score_rate >= 0.45
    payload = {
        "schema": 1,
        "protocol": "d1-rc4-paired-generalist-guard",
        "pairs": len(pair_scores),
        "games": len(games),
        "depth": args.depth,
        "max_plies": args.max_plies,
        "seed": args.seed,
        "rc4_score_rate": score_rate,
        "paired_bootstrap_95": ci,
        "regression_established": regression_established,
        "minimum_point_guard": 0.45,
        "pass": guard_pass,
        "game_rows": games,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("D1_RC4_GENERALIST_PASS" if guard_pass else "D1_RC4_GENERALIST_FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
