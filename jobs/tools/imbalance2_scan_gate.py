#!/usr/bin/env python3
"""Final plateau-only benchmark for L3-IMBALANCE2 against Gen2-MMTO and Scan.

Each engine plays both colours against itself from the same fixed positions. The
outcome is folded to the side that started with the two-man material advantage.
Gen2-MMTO is the lower reference; Scan is the upper/stop reference.
"""
from __future__ import annotations

import argparse
import json
import random
import struct
import sys
from collections import defaultdict
from pathlib import Path

REC = 38
CATS = ("win", "draw", "loss")
COST = {"win": 0.0, "draw": 1.0, "loss": 2.0}


def read_records(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError(f"{path}: invalid JNNW")
    n = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != n * REC:
        raise ValueError(f"{path}: truncated JNNW")
    return [body[i * REC:(i + 1) * REC] for i in range(n)]


def record_to_fen(rec: bytes) -> str:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", rec, 0)
    stm = rec[32]
    if wk or bk:
        raise ValueError("benchmark record contains kings")

    def sqs(bits: int) -> str:
        return ",".join(str(i) for i in range(1, 51) if bits & (1 << (i - 1)))

    return f"{'B' if stm else 'W'}:W{sqs(wm)}:B{sqs(bm)}"


def material_up_pov(result: object, side: str) -> str:
    outcome = result.outcome
    if outcome == "D":
        return "draw"
    won = (side == "W" and outcome == "W") or (side == "B" and outcome == "L")
    return "win" if won else "loss"


def make_players(cv, args):
    if args.engine in ("candidate", "gen2"):
        if not args.pattern:
            raise ValueError("--pattern is required for a Jass engine")
        white = cv.JassEngine(
            args.jass, label=f"{args.engine}-W", pattern_path=args.pattern,
            search_params=args.search_params,
        )
        black = cv.JassEngine(
            args.jass, label=f"{args.engine}-B", pattern_path=args.pattern,
            search_params=args.search_params,
        )
    else:
        if not args.scan:
            raise ValueError("--scan is required for engine=scan")
        white = cv.ScanEngine(args.scan, label="Scan-W", no_book=True, bb_size=args.scan_bb_size)
        black = cv.ScanEngine(args.scan, label="Scan-B", no_book=True, bb_size=args.scan_bb_size)
    return white, black


def run(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(Path(args.calibrate_tool).resolve().parent))
    import calibrate_vs_scan as cv  # type: ignore

    records = read_records(Path(args.pool))
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    if len(records) != len(meta):
        raise ValueError("pool and metadata length mismatch")

    white, black = make_players(cv, args)
    referee = cv.Referee(args.jass)
    rows: list[dict[str, object]] = []
    try:
        for index, (rec, item) in enumerate(zip(records, meta, strict=True)):
            if index % args.nshards != args.shard:
                continue
            low, high = sorted((int(item["white_men"]), int(item["black_men"])))
            if high - low != 2 or not 1 <= low <= 18:
                raise ValueError(f"index {index}: invalid stratum")
            advantaged = str(item["advantaged_side"])
            fen = record_to_fen(rec)
            budget = {"movetime": args.movetime} if args.movetime is not None else {"depth": args.depth}
            try:
                result = cv.play_game(white, black, referee, fen, max_plies=args.max_plies, **budget)
                rows.append({
                    "index": index,
                    "stratum": item["stratum"],
                    "advantaged_side": advantaged,
                    "outcome": material_up_pov(result, advantaged),
                    "reason": result.reason,
                })
            except Exception as exc:  # noqa: BLE001
                rows.append({"index": index, "stratum": item["stratum"], "error": str(exc)})
    finally:
        for engine in (white, black, referee):
            try:
                engine.close()
            except Exception:  # noqa: BLE001
                pass

    payload = {
        "schema": 3,
        "protocol": "fixed-position-engine-selfplay",
        "engine": args.engine,
        "perspective": "material_up_side",
        "pool": args.pool,
        "shard": args.shard,
        "nshards": args.nshards,
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


def load_rows(paths: list[str], expected_engine: str) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("engine") != expected_engine:
            raise ValueError(f"{path}: expected engine {expected_engine}")
        for row in payload["rows"]:
            index = int(row["index"])
            if index in result:
                raise ValueError(f"duplicate index {index} for {expected_engine}")
            result[index] = row
    return result


def rates(rows: list[dict[str, object]], key: str) -> dict[str, float]:
    n = len(rows)
    return {cat: sum(row[key] == cat for row in rows) / n for cat in CATS}


def bootstrap(rows: list[dict[str, object]], key_a: str, key_b: str, reps: int, seed: int):
    rng = random.Random(seed)
    n = len(rows)
    category_samples = {cat: [] for cat in CATS}
    cost_samples: list[float] = []
    for _ in range(reps):
        selected = [rows[rng.randrange(n)] for _ in range(n)]
        ar, br = rates(selected, key_a), rates(selected, key_b)
        for cat in CATS:
            category_samples[cat].append(ar[cat] - br[cat])
        cost_samples.append(
            sum(COST[row[key_a]] - COST[row[key_b]] for row in selected) / n
        )

    def interval(values: list[float]) -> list[float]:
        values.sort()
        return [values[int(0.025 * (reps - 1))], values[int(0.975 * (reps - 1))]]

    return {cat: interval(values) for cat, values in category_samples.items()}, interval(cost_samples)


def aggregate(args: argparse.Namespace) -> int:
    candidate = load_rows(args.candidate_inputs, "candidate")
    gen2 = load_rows(args.gen2_inputs, "gen2")
    scan = load_rows(args.scan_inputs, "scan")
    all_indices = sorted(set(candidate) | set(gen2) | set(scan))
    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    for index in all_indices:
        triplet = [candidate.get(index), gen2.get(index), scan.get(index)]
        if any(item is None or "error" in item for item in triplet):
            errors.append({"index": index, "candidate": triplet[0], "gen2": triplet[1], "scan": triplet[2]})
            continue
        c, g, s = triplet
        rows.append({
            "index": index,
            "stratum": c["stratum"],
            "candidate": c["outcome"],
            "gen2": g["outcome"],
            "scan": s["outcome"],
        })
    if not rows:
        raise ValueError("no valid triplets")

    cr, gr, sr = rates(rows, "candidate"), rates(rows, "gen2"), rates(rows, "scan")
    scan_delta = {cat: cr[cat] - sr[cat] for cat in CATS}
    scan_ci, _ = bootstrap(rows, "candidate", "scan", args.bootstrap, args.seed)
    _, gen2_cost_ci = bootstrap(rows, "candidate", "gen2", args.bootstrap, args.seed + 1)
    candidate_cost = sum(COST[row["candidate"]] for row in rows) / len(rows)
    gen2_cost = sum(COST[row["gen2"]] for row in rows) / len(rows)
    lower_delta = candidate_cost - gen2_cost

    scan_global_pass = all(abs(scan_delta[cat]) <= args.global_point_margin for cat in CATS) and all(
        scan_ci[cat][0] >= -args.global_ci_margin and scan_ci[cat][1] <= args.global_ci_margin
        for cat in CATS
    )
    gen2_pass = lower_delta <= args.gen2_cost_margin and gen2_cost_ci[1] <= args.gen2_ci_margin

    strata: dict[str, object] = {}
    strata_pass = True
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["stratum"])].append(row)
    for name in sorted(grouped, key=lambda value: int(value.split("v", 1)[0])):
        group = grouped[name]
        c, g, s = rates(group, "candidate"), rates(group, "gen2"), rates(group, "scan")
        delta = {cat: c[cat] - s[cat] for cat in CATS}
        passed = len(group) >= args.min_per_stratum and all(
            abs(delta[cat]) <= args.stratum_point_margin for cat in CATS
        )
        strata_pass &= passed
        strata[name] = {"n": len(group), "candidate": c, "gen2": g, "scan": s, "candidate_minus_scan": delta, "pass": passed}

    passed = scan_global_pass and gen2_pass and strata_pass and len(errors) <= args.max_errors
    payload = {
        "schema": 3,
        "protocol": "candidate_gen2_scan_fixed_position_selfplay",
        "perspective": "material_up_side",
        "decision": "scan_equivalent_above_gen2" if passed else "plateau_below_target",
        "pass": passed,
        "n": len(rows),
        "errors": errors,
        "candidate": cr,
        "gen2": gr,
        "scan": sr,
        "candidate_minus_scan": scan_delta,
        "candidate_minus_scan_bootstrap_95": scan_ci,
        "failure_cost_2loss_plus_draw": {
            "candidate": candidate_cost,
            "gen2": gen2_cost,
            "delta": lower_delta,
            "bootstrap_95": gen2_cost_ci,
        },
        "scan_global_pass": scan_global_pass,
        "gen2_lower_reference_pass": gen2_pass,
        "strata_pass": strata_pass,
        "strata": strata,
        "margins": {
            "global_point": args.global_point_margin,
            "global_ci": args.global_ci_margin,
            "stratum_point": args.stratum_point_margin,
            "min_per_stratum": args.min_per_stratum,
            "gen2_cost": args.gen2_cost_margin,
            "gen2_ci": args.gen2_ci_margin,
        },
    }
    Path(args.out).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["decision"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("--engine", choices=("candidate", "gen2", "scan"), required=True)
    runner.add_argument("--jass", required=True)
    runner.add_argument("--scan", default="")
    runner.add_argument("--pattern", default="")
    runner.add_argument("--pool", required=True)
    runner.add_argument("--meta", required=True)
    runner.add_argument("--search-params")
    runner.add_argument("--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py")
    budget = runner.add_mutually_exclusive_group()
    budget.add_argument("--depth", type=int, default=10)
    budget.add_argument("--movetime", type=float)
    runner.add_argument("--max-plies", type=int, default=400)
    runner.add_argument("--scan-bb-size", type=int, default=0)
    runner.add_argument("--shard", type=int, default=0)
    runner.add_argument("--nshards", type=int, default=1)
    runner.add_argument("--out", required=True)
    runner.set_defaults(func=run)

    agg = sub.add_parser("aggregate")
    agg.add_argument("--candidate-inputs", nargs="+", required=True)
    agg.add_argument("--gen2-inputs", nargs="+", required=True)
    agg.add_argument("--scan-inputs", nargs="+", required=True)
    agg.add_argument("--out", required=True)
    agg.add_argument("--bootstrap", type=int, default=5000)
    agg.add_argument("--seed", type=int, default=271828)
    agg.add_argument("--global-point-margin", type=float, default=0.03)
    agg.add_argument("--global-ci-margin", type=float, default=0.05)
    agg.add_argument("--stratum-point-margin", type=float, default=0.10)
    agg.add_argument("--min-per-stratum", type=int, default=20)
    agg.add_argument("--gen2-cost-margin", type=float, default=0.02)
    agg.add_argument("--gen2-ci-margin", type=float, default=0.05)
    agg.add_argument("--max-errors", type=int, default=0)
    agg.set_defaults(func=aggregate)

    args = parser.parse_args()
    if getattr(args, "nshards", 1) <= 0 or not 0 <= getattr(args, "shard", 0) < getattr(args, "nshards", 1):
        parser.error("require 0 <= shard < nshards")
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
