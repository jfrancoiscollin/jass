#!/usr/bin/env python3
"""Run and aggregate the Scan-equivalence stop gate for L3-IMBALANCE2.

The protocol intentionally matches the existing material-selfplay benchmark:
Scan plays both colours against itself, and the candidate plays both colours
against itself, from exactly the same fixed positions and at the same search
budget. Outcomes are folded to the side holding the two-man material edge.
"""
from __future__ import annotations

import argparse
import json
import random
import struct
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

REC = 38
CATS = ("win", "draw", "loss")


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


def run(args: argparse.Namespace) -> int:
    sys.path.insert(0, str(Path(args.calibrate_tool).resolve().parent))
    import calibrate_vs_scan as cv  # type: ignore

    records = read_records(Path(args.pool))
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    if len(records) != len(meta):
        raise ValueError("pool and metadata length mismatch")

    candidate_white = cv.JassEngine(
        args.jass, label="candidate-W", pattern_path=args.candidate,
        search_params=args.search_params,
    )
    candidate_black = cv.JassEngine(
        args.jass, label="candidate-B", pattern_path=args.candidate,
        search_params=args.search_params,
    )
    scan_white = cv.ScanEngine(
        args.scan, label="Scan-W", no_book=True, bb_size=args.scan_bb_size,
    )
    scan_black = cv.ScanEngine(
        args.scan, label="Scan-B", no_book=True, bb_size=args.scan_bb_size,
    )
    referee = cv.Referee(args.jass)
    rows: list[dict[str, object]] = []
    try:
        for index, (rec, m) in enumerate(zip(records, meta, strict=True)):
            if index % args.nshards != args.shard:
                continue
            low, high = sorted((int(m["white_men"]), int(m["black_men"])))
            if high - low != 2 or not 1 <= low <= 18:
                raise ValueError(f"index {index}: invalid stratum")
            advantaged = str(m["advantaged_side"])
            fen = record_to_fen(rec)
            play = (
                {"movetime": args.movetime}
                if args.movetime is not None
                else {"depth": args.depth}
            )
            try:
                candidate_result = cv.play_game(
                    candidate_white, candidate_black, referee, fen,
                    max_plies=args.max_plies, **play,
                )
                scan_result = cv.play_game(
                    scan_white, scan_black, referee, fen,
                    max_plies=args.max_plies, **play,
                )
                rows.append({
                    "index": index,
                    "stratum": m["stratum"],
                    "advantaged_side": advantaged,
                    "candidate": material_up_pov(candidate_result, advantaged),
                    "scan": material_up_pov(scan_result, advantaged),
                    "candidate_reason": candidate_result.reason,
                    "scan_reason": scan_result.reason,
                })
            except Exception as exc:
                rows.append({
                    "index": index, "stratum": m["stratum"], "error": str(exc)
                })
    finally:
        for engine in (
            candidate_white, candidate_black, scan_white, scan_black, referee,
        ):
            try:
                engine.close()
            except Exception:
                pass

    payload = {
        "schema": 2,
        "protocol": "candidate-selfplay_vs_scan-selfplay",
        "perspective": "material_up_side",
        "pool": args.pool,
        "shard": args.shard,
        "nshards": args.nshards,
        "rows": rows,
    }
    Path(args.out).write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return 0


def rates(rows: Iterable[dict[str, object]], key: str) -> dict[str, float]:
    rows = list(rows)
    n = len(rows)
    return {cat: sum(r[key] == cat for r in rows) / n for cat in CATS}


def paired_bootstrap(
    rows: list[dict[str, object]], reps: int, seed: int
) -> dict[str, list[float]]:
    rng = random.Random(seed)
    n = len(rows)
    samples = {cat: [] for cat in CATS}
    for _ in range(reps):
        draw = [rows[rng.randrange(n)] for _ in range(n)]
        cr, sr = rates(draw, "candidate"), rates(draw, "scan")
        for cat in CATS:
            samples[cat].append(cr[cat] - sr[cat])
    out: dict[str, list[float]] = {}
    for cat, values in samples.items():
        values.sort()
        out[cat] = [
            values[int(0.025 * (reps - 1))],
            values[int(0.975 * (reps - 1))],
        ]
    return out


def aggregate(args: argparse.Namespace) -> int:
    rows: list[dict[str, object]] = []
    for path in args.inputs:
        rows.extend(json.loads(Path(path).read_text(encoding="utf-8"))["rows"])
    valid = [r for r in rows if "error" not in r]
    errors = [r for r in rows if "error" in r]
    if not valid:
        raise ValueError("no valid paired results")

    cr, sr = rates(valid, "candidate"), rates(valid, "scan")
    delta = {cat: cr[cat] - sr[cat] for cat in CATS}
    ci = paired_bootstrap(valid, args.bootstrap, args.seed)
    global_pass = all(
        abs(delta[c]) <= args.global_point_margin for c in CATS
    ) and all(
        ci[c][0] >= -args.global_ci_margin
        and ci[c][1] <= args.global_ci_margin
        for c in CATS
    )

    strata: dict[str, object] = {}
    strata_pass = True
    by_stratum: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in valid:
        by_stratum[str(row["stratum"])].append(row)
    for name in sorted(by_stratum, key=lambda s: int(s.split("v", 1)[0])):
        group = by_stratum[name]
        c, s = rates(group, "candidate"), rates(group, "scan")
        d = {cat: c[cat] - s[cat] for cat in CATS}
        passed = len(group) >= args.min_per_stratum and all(
            abs(d[cat]) <= args.stratum_point_margin for cat in CATS
        )
        strata_pass &= passed
        strata[name] = {
            "n": len(group),
            "candidate": c,
            "scan": s,
            "delta": d,
            "pass": passed,
        }

    passed = global_pass and strata_pass and len(errors) <= args.max_errors
    payload = {
        "schema": 2,
        "protocol": "candidate-selfplay_vs_scan-selfplay",
        "perspective": "material_up_side",
        "decision": "scan_equivalent" if passed else "continue_training",
        "pass": passed,
        "n": len(valid),
        "errors": errors,
        "candidate": cr,
        "scan": sr,
        "delta": delta,
        "paired_bootstrap_95": ci,
        "global_pass": global_pass,
        "strata_pass": strata_pass,
        "strata": strata,
        "margins": {
            "global_point": args.global_point_margin,
            "global_ci": args.global_ci_margin,
            "stratum_point": args.stratum_point_margin,
            "min_per_stratum": args.min_per_stratum,
        },
    }
    Path(args.out).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(payload["decision"])
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--jass", required=True)
    r.add_argument("--scan", required=True)
    r.add_argument("--candidate", required=True)
    r.add_argument("--pool", required=True)
    r.add_argument("--meta", required=True)
    r.add_argument("--search-params")
    r.add_argument("--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py")
    budget = r.add_mutually_exclusive_group()
    budget.add_argument("--depth", type=int, default=10)
    budget.add_argument("--movetime", type=float)
    r.add_argument("--max-plies", type=int, default=400)
    r.add_argument("--scan-bb-size", type=int, default=0)
    r.add_argument("--shard", type=int, default=0)
    r.add_argument("--nshards", type=int, default=1)
    r.add_argument("--out", required=True)
    r.set_defaults(func=run)

    a = sub.add_parser("aggregate")
    a.add_argument("--inputs", nargs="+", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--bootstrap", type=int, default=5000)
    a.add_argument("--seed", type=int, default=271828)
    a.add_argument("--global-point-margin", type=float, default=0.03)
    a.add_argument("--global-ci-margin", type=float, default=0.05)
    a.add_argument("--stratum-point-margin", type=float, default=0.10)
    a.add_argument("--min-per-stratum", type=int, default=20)
    a.add_argument("--max-errors", type=int, default=0)
    a.set_defaults(func=aggregate)
    args = p.parse_args()
    if getattr(args, "nshards", 1) <= 0 or not (
        0 <= getattr(args, "shard", 0) < getattr(args, "nshards", 1)
    ):
        p.error("require 0 <= shard < nshards")
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
