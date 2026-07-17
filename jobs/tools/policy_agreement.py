#!/usr/bin/env python3
"""Measure paired root-policy agreement between two pattern evaluations.

This is the cheap C0 diagnostic for fork C.  A scalar weak bootstrap can be
byte-different while inducing almost the same fixed-depth policy; this probe
measures the behaviour directly on one frozen FEN set before a full tour.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import calibrate_vs_scan as cv  # noqa: E402


def move_key(move: cv.Move | None) -> tuple | None:
    if move is None:
        return None
    return move.frm, move.to, tuple(sorted(move.captures))


def summarize(rows: list[dict], *, requested: int) -> dict:
    complete = [row for row in rows if row.get("move_a") and row.get("move_b")]
    agree = sum(row["move_a"] == row["move_b"] for row in complete)
    n = len(complete)
    return {
        "schema": 1,
        "requested": requested,
        "complete": n,
        "errors": len(rows) - n,
        "agree": agree,
        "disagree": n - agree,
        "agreement": None if not n else round(agree / n, 6),
        "divergence": None if not n else round((n - agree) / n, 6),
        "rows": rows,
    }


def load_fens(path: Path, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        fen = line.split("#", 1)[0].strip()
        if not fen or fen in seen:
            continue
        seen.add(fen)
        result.append(fen)
        if len(result) >= limit:
            break
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--pattern-a", required=True)
    parser.add_argument("--pattern-b", required=True)
    parser.add_argument("--fens", type=Path, required=True)
    parser.add_argument("--depth", type=int, default=9)
    parser.add_argument("--limit", type=int, default=600)
    parser.add_argument("--min-complete", type=int, default=100)
    parser.add_argument("--search-params", default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    fens = load_fens(args.fens, args.limit)
    if not fens:
        raise SystemExit("no FEN to probe")
    a = cv.JassEngine(
        args.jass,
        label="policy-a",
        pattern_path=args.pattern_a,
        search_params=args.search_params,
    )
    b = cv.JassEngine(
        args.jass,
        label="policy-b",
        pattern_path=args.pattern_b,
        search_params=args.search_params,
    )
    rows: list[dict] = []
    try:
        for index, fen in enumerate(fens):
            row = {
                "index": index,
                "fen_sha256": hashlib.sha256(fen.encode()).hexdigest(),
                "move_a": None,
                "move_b": None,
            }
            try:
                a.set_position_fen(fen)
                b.set_position_fen(fen)
                ma = a.go(depth=args.depth)
                mb = b.go(depth=args.depth)
                ka, kb = move_key(ma), move_key(mb)
                row["move_a"] = list(ka) if ka is not None else None
                row["move_b"] = list(kb) if kb is not None else None
            except Exception as exc:  # one bad position must remain visible
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)
    finally:
        a.close()
        b.close()

    report = summarize(rows, requested=len(fens))
    report.update({"depth": args.depth, "fen_file": str(args.fens)})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in (
        "requested", "complete", "agree", "disagree", "agreement", "divergence"
    )}))
    return 0 if report["complete"] >= args.min_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
