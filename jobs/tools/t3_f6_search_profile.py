#!/usr/bin/env python3
"""R0 HUB-level OFF regression and 0.1 s/move search-cost profile."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from calibrate_vs_scan import JassEngine  # noqa: E402
from calibrate_vs_scan import parse_jass_fen  # noqa: E402


def fens(path: Path) -> list[str]:
    rows = [line.split("#", 1)[0].strip()
            for line in path.read_text(encoding="utf-8").splitlines()]
    return [row for row in rows if row]


def phase(fen: str) -> str:
    _, wm, wk, bm, bk = parse_jass_fen(fen)
    pieces = len(wm) + len(wk) + len(bm) + len(bk)
    if 30 <= pieces <= 40:
        return "P0"
    if 20 <= pieces <= 29:
        return "P1"
    if 12 <= pieces <= 19:
        return "P2"
    if 9 <= pieces <= 11:
        return "P3"
    raise ValueError(f"R0 position outside phase contract: pieces={pieces}")


def stratified(corpus: list[str], per_phase: int, seed: int) -> list[str]:
    out: list[str] = []
    for name in ("P0", "P1", "P2", "P3"):
        rows = [fen for fen in corpus if phase(fen) == name]
        rows.sort(key=lambda fen: hashlib.sha256(f"{seed}:{fen}".encode()).digest())
        if len(rows) < per_phase:
            raise ValueError(f"R0 support below {per_phase} for {name}")
        out.extend(rows[:per_phase])
    out.sort(key=lambda fen: hashlib.sha256(f"{seed}:all:{fen}".encode()).digest())
    return out


def neteval(engine: JassEngine, fen: str) -> int:
    engine.new_game()
    engine.set_position_fen(fen)
    engine._send("neteval")
    lines = engine._read_until(lambda line: line.startswith("neteval ")
                               or line.startswith("error"))
    if lines[-1].startswith("error"):
        raise RuntimeError(f"{engine.label}: {lines[-1]}")
    return int(lines[-1].split()[1])


def bestmove_record(engine: JassEngine, fen: str, *, depth: int | None = None,
                    movetime: float | None = None) -> dict[str, object]:
    engine.new_game()
    engine.set_position_fen(fen)
    move, lines = engine.go_verbose(depth=depth, movetime=movetime)
    line = lines[-1]
    fields = {key: int(value) for key, value in
              re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)=(-?\d+)\b", line)}
    return {
        "move": move.jass_apply_str() if move else None,
        "score": fields.get("score"),
        "depth": fields.get("depth"),
        "nodes": fields.get("nodes"),
        "eval_calls": fields.get("evalcalls", 0),
    }


def telemetry_report(engine: JassEngine) -> dict[str, object]:
    values = engine.telemetry_snapshot()
    searches = int(values["searches"])
    wall = float(values["wall_seconds"])
    histogram = dict(values.get("depth_histogram", {}))
    ordered = [int(depth) for depth, count in histogram.items() for _ in range(int(count))]
    def quantile(q: float) -> float:
        if not ordered:
            return 0.0
        ordered.sort()
        index = q * (len(ordered) - 1)
        lo = int(index)
        hi = min(lo + 1, len(ordered) - 1)
        return ordered[lo] + (index - lo) * (ordered[hi] - ordered[lo])
    return {
        **values,
        "mean_depth": float(values["depth_sum"]) / searches if searches else 0.0,
        "depth_quantiles": {"p05": quantile(0.05), "p50": quantile(0.50),
                            "p95": quantile(0.95)},
        "nodes_per_search": int(values["nodes"]) / searches if searches else 0.0,
        "eval_calls_per_search": int(values["eval_calls"]) / searches if searches else 0.0,
        "nps": int(values["nodes"]) / wall if wall > 0 else 0.0,
    }


def run(args: argparse.Namespace) -> dict[str, object]:
    corpus = fens(args.corpus)
    if len(corpus) != 4096:
        raise ValueError(f"R0 corpus must contain 4096 FENs, got {len(corpus)}")
    env_off = {"JASS_T3_F6_MODEL": None}
    current = JassEngine(args.exe, label="current-OFF", pattern_path=str(args.curriculum),
                         search_params=args.search_params, env_overrides=env_off,
                         enforce_no_book=True)
    prereg = JassEngine(args.prereg_exe, label="prereg-OFF", pattern_path=str(args.curriculum),
                        search_params=args.search_params, env_overrides=env_off,
                        enforce_no_book=True)
    static_mismatches = 0
    q00_mismatches: list[dict[str, object]] = []
    try:
        for fen in corpus:
            static_mismatches += neteval(current, fen) != neteval(prereg, fen)
        q00_roots = stratified(corpus, 16, 2026090904)
        for index, fen in enumerate(q00_roots):
            new = bestmove_record(current, fen, depth=9)
            old = bestmove_record(prereg, fen, depth=9)
            comparable = {key: new[key] for key in ("move", "score", "depth", "nodes")}
            if comparable != {key: old[key] for key in comparable}:
                q00_mismatches.append({"row": index, "current": new, "prereg": old})
    finally:
        current.close()
        prereg.close()
    if static_mismatches or q00_mismatches:
        raise ValueError("OFF functional regression gate failed")

    off = JassEngine(args.exe, label="profile-OFF", pattern_path=str(args.curriculum),
                     search_params=args.search_params, env_overrides=env_off,
                     enforce_no_book=True)
    on = JassEngine(args.exe, label="profile-ON", pattern_path=str(args.curriculum),
                    search_params=args.search_params,
                    env_overrides={"JASS_T3_F6_MODEL": str(args.model)},
                    enforce_no_book=True)
    try:
        # Fixed target-blind order; alternate which arm searches first.
        ordered = stratified(corpus, 32, 2026090904)
        for index, fen in enumerate(ordered):
            arms = (off, on) if index % 2 == 0 else (on, off)
            for engine in arms:
                bestmove_record(engine, fen, movetime=0.1)
        search_profile = {"curriculum_off": telemetry_report(off),
                          "t3_f6_on": telemetry_report(on)}
    finally:
        off.close()
        on.close()
    return {
        "schema": "jass.t3_f6_search_profile.v1",
        "passed": True,
        "off_regression": {
            "static_positions": 4096,
            "static_mismatches": static_mismatches,
            "q00_depth9_roots": 64,
            "q00_move_score_depth_nodes_mismatches": len(q00_mismatches),
        },
        "search_profile": search_profile,
        "profile_roots": 128,
        "profile_roots_by_phase": {name: 32 for name in ("P0", "P1", "P2", "P3")},
        "movetime_seconds": 0.1,
        "order_seed": 2026090904,
        "same_executable_on_off": True,
        "deep_label_reads": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True)
    parser.add_argument("--prereg-exe", required=True)
    parser.add_argument("--curriculum", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--search-params", default="qs_forcing_depth=6,qs_promo_depth=6")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
