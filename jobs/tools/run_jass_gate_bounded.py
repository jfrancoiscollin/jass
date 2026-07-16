#!/usr/bin/env python3
"""Run the existing sharded Jass gate with bounded process concurrency.

The scientific inputs, shard count and aggregation are identical to
run_jass_gate.py. Only the number of simultaneously running shard processes is
limited so the same experiment can run safely on a lower-memory host.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path


def parse_result_files(paths: list[Path], expected_shards: int) -> dict:
    if len(paths) != expected_shards:
        raise ValueError(f"got {len(paths)} shard logs, expected {expected_shards}")
    wins = draws = losses = 0
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing/empty gate log: {path}")
        found = 0
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("RESULT"):
                parts = line.split()
                if len(parts) != 4:
                    raise ValueError(f"{path}: malformed RESULT line")
                wins += int(parts[1])
                draws += int(parts[2])
                losses += int(parts[3])
                found += 1
        if found != 1:
            raise ValueError(f"{path}: expected exactly one RESULT line, got {found}")
    n = wins + draws + losses
    if n <= 0:
        raise ValueError("gate produced zero games")
    rate = (wins + 0.5 * draws) / n
    variance = max(0.0, (wins + 0.25 * draws) / n - rate * rate)
    se = math.sqrt(variance / n)
    ci_low = max(0.0, rate - 1.96 * se)
    ci_high = min(1.0, rate + 1.96 * se)
    elo = -400 * math.log10(1 / rate - 1) if 0 < rate < 1 else 0.0
    return {
        "wins_a": wins,
        "draws": draws,
        "wins_b": losses,
        "n": n,
        "rate": round(rate, 6),
        "ci_low": round(ci_low, 6),
        "ci_high": round(ci_high, 6),
        "elo": round(elo, 2),
        "complete": True,
    }


def command_for(args: argparse.Namespace, shard: int) -> list[str]:
    return [
        sys.executable,
        args.harness,
        "--jass-a", args.jass,
        "--pattern-a", args.pattern_a,
        "--jass-b", args.jass,
        "--pattern-b", args.pattern_b,
        "--search-params-a", args.search_params,
        "--search-params-b", args.search_params,
        "--depth", str(args.depth),
        "--pairs", str(args.pairs),
        "--max-plies", str(args.max_plies),
        "--shard", str(shard),
        "--nshards", str(args.nshards),
        "--quiet",
        "--openings-file", args.openings_file,
    ]


def run_gate(args: argparse.Namespace) -> dict:
    out_dir = Path(args.work_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    max_parallel = max(1, min(args.max_parallel, args.nshards))
    active: dict[int, tuple[subprocess.Popen, object, Path, float]] = {}
    next_shard = 0
    failures: list[str] = []

    while next_shard < args.nshards or active:
        while next_shard < args.nshards and len(active) < max_parallel:
            shard = next_shard
            next_shard += 1
            log_path = out_dir / f"gate.{shard}.log"
            handle = log_path.open("w", encoding="utf-8")
            process = subprocess.Popen(
                command_for(args, shard),
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
            active[shard] = (process, handle, log_path, time.monotonic())

        progressed = False
        for shard, (process, handle, log_path, started) in list(active.items()):
            return_code = process.poll()
            if return_code is None and time.monotonic() - started > args.timeout:
                process.kill()
                process.wait()
                return_code = 124
            if return_code is None:
                continue
            handle.close()
            del active[shard]
            progressed = True
            if return_code != 0:
                failures.append(f"shard {shard} rc={return_code} log={log_path}")
        if failures:
            for process, handle, _, _ in active.values():
                process.kill()
                process.wait()
                handle.close()
            raise ValueError("; ".join(failures))
        if active and not progressed:
            time.sleep(0.2)

    logs = [out_dir / f"gate.{shard}.log" for shard in range(args.nshards)]
    result = parse_result_files(logs, args.nshards)
    result.update({
        "pattern_a": args.pattern_a,
        "pattern_b": args.pattern_b,
        "depth": args.depth,
        "pairs": args.pairs,
        "nshards": args.nshards,
        "max_parallel": max_parallel,
        "openings_file": args.openings_file,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--pattern-a", required=True)
    parser.add_argument("--pattern-b", required=True)
    parser.add_argument("--openings-file", required=True)
    parser.add_argument("--harness", default="tools/jass_vs_jass_arch.py")
    parser.add_argument("--search-params", default="qs_forcing_depth=6,qs_promo_depth=6")
    parser.add_argument("--depth", type=int, default=9)
    parser.add_argument("--pairs", type=int, default=1)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--nshards", type=int, default=16)
    parser.add_argument("--max-parallel", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=7000)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = run_gate(args)
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 4
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
