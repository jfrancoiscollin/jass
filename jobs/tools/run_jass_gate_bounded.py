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


LEGACY_SEARCH_PARAMS = "qs_forcing_depth=6,qs_promo_depth=6"


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


def resolve_search_params(args: argparse.Namespace) -> None:
    """Resolve legacy shared and explicit per-side fingerprints in one place."""
    shared = args.search_params or LEGACY_SEARCH_PARAMS
    args.search_params_a = args.search_params_a or shared
    args.search_params_b = args.search_params_b or shared


def command_for(args: argparse.Namespace, shard: int) -> list[str]:
    command = [
        sys.executable,
        args.harness,
        "--jass-a", args.jass_a,
        "--pattern-a", args.pattern_a,
        "--jass-b", args.jass_b,
        "--pattern-b", args.pattern_b,
        "--search-params-a", args.search_params_a,
        "--search-params-b", args.search_params_b,
        "--pairs", str(args.pairs),
        "--max-plies", str(args.max_plies),
        "--shard", str(shard),
        "--nshards", str(args.nshards),
        "--quiet",
        "--openings-file", args.openings_file,
    ]
    game_timeout = getattr(args, "game_timeout", None)
    if game_timeout is not None:
        command.extend(["--game-timeout", str(game_timeout)])
    if getattr(args, "paired_bootstrap_samples", 0) > 0:
        command.extend([
            "--results-jsonl",
            str(Path(args.work_dir) / f"games.{shard}.jsonl"),
        ])
    if getattr(args, "dump_games_dir", None):
        command.extend(["--dump-games-dir", str(Path(args.dump_games_dir))])
    if args.movetime is not None:
        command.extend(["--movetime", str(args.movetime)])
    else:
        command.extend(["--depth", str(args.depth)])
    return command


def paired_opening_report(
    paths: list[Path],
    *,
    expected_shards: int,
    expected_openings: int,
    pairs: int,
    bootstrap_samples: int,
    seed: int,
) -> dict:
    """Cluster bootstrap over openings after colour-swapped paired games."""
    import numpy as np
    if len(paths) != expected_shards:
        raise ValueError("paired result shard count mismatch")
    rows = []
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing/empty paired result file: {path}")
        rows.extend(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    expected_games = expected_openings * pairs * 2
    if len(rows) != expected_games:
        raise ValueError(f"paired results contain {len(rows)} games, expected {expected_games}")
    indices = [int(row["game_index"]) for row in rows]
    if len(set(indices)) != expected_games or set(indices) != set(range(expected_games)):
        raise ValueError("paired game indices are not a complete unique range")
    by_opening: dict[int, list[dict]] = {}
    for row in rows:
        opening = int(row["opening_index"])
        score = float(row["score_a"])
        if opening < 0 or opening >= expected_openings or score not in (0.0, 0.5, 1.0):
            raise ValueError("paired result row outside contract")
        by_opening.setdefault(opening, []).append(row)
    if set(by_opening) != set(range(expected_openings)):
        raise ValueError("paired results do not cover every opening")
    per_opening = np.empty(expected_openings, dtype=np.float64)
    errors = 0
    for opening, opening_rows in by_opening.items():
        if len(opening_rows) != pairs * 2:
            raise ValueError(f"opening {opening} has {len(opening_rows)} games")
        colours = [bool(row["a_is_white"]) for row in opening_rows]
        if colours.count(True) != pairs or colours.count(False) != pairs:
            raise ValueError(f"opening {opening} colour pairing drift")
        per_opening[opening] = np.mean([float(row["score_a"]) for row in opening_rows])
        errors += sum(row.get("error") is not None for row in opening_rows)
    rng = np.random.default_rng(seed)
    draws = np.empty(bootstrap_samples, dtype=np.float64)
    batch = 4096
    for start in range(0, bootstrap_samples, batch):
        stop = min(start + batch, bootstrap_samples)
        sampled = rng.integers(0, expected_openings, size=(stop - start, expected_openings))
        draws[start:stop] = per_opening[sampled].mean(axis=1)
    ci_low, ci_high = np.quantile(draws, [0.025, 0.975])
    return {
        "method": "paired_colour_opening_cluster_bootstrap",
        "n_openings": expected_openings,
        "games_per_opening": pairs * 2,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
        "rate": float(per_opening.mean()),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "probability_rate_gt_half": float(np.mean(draws > 0.5)),
        "positive_opening_fraction": float(np.mean(per_opening > 0.5)),
        "per_opening_scores": per_opening.tolist(),
        "error_draws": errors,
    }


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
    if args.dump_games_dir:
        dump_dir = Path(args.dump_games_dir)
        with open(args.openings_file, encoding="utf-8") as stream:
            opening_count = sum(
                1 for line in stream if line.split("#", 1)[0].strip()
            )
        expected_games = opening_count * args.pairs * 2
        dumps = sorted(dump_dir.glob("game-*.json"))
        if len(dumps) != expected_games:
            raise ValueError(
                f"complete game dumps contain {len(dumps)} files, expected {expected_games}"
            )
        indices = []
        for path in dumps:
            row = json.loads(path.read_text(encoding="utf-8"))
            if row.get("schema") != "jass.complete_game_dump.v1":
                raise ValueError(f"{path}: complete game dump schema drift")
            if len(row.get("fens", [])) != len(row.get("moves", [])) + 1:
                raise ValueError(f"{path}: incomplete game trajectory")
            indices.append(int(row["game_id"]))
        if set(indices) != set(range(expected_games)) or len(indices) != len(set(indices)):
            raise ValueError("complete game dump indices are not a unique complete range")
        result["complete_game_dumps"] = {
            "schema": "jass.complete_game_dump_set.v1",
            "directory": str(dump_dir),
            "games": expected_games,
            "trajectory_contract_valid": True,
        }
    if args.paired_bootstrap_samples > 0:
        with open(args.openings_file, encoding="utf-8") as stream:
            openings = [
                line.split("#", 1)[0].strip()
                for line in stream
                if line.split("#", 1)[0].strip()
            ]
        paired_paths = [out_dir / f"games.{shard}.jsonl" for shard in range(args.nshards)]
        result["paired_opening"] = paired_opening_report(
            paired_paths,
            expected_shards=args.nshards,
            expected_openings=len(openings),
            pairs=args.pairs,
            bootstrap_samples=args.paired_bootstrap_samples,
            seed=args.paired_bootstrap_seed,
        )
    result.update({
        "jass_a": args.jass_a,
        "jass_b": args.jass_b,
        "pattern_a": args.pattern_a,
        "pattern_b": args.pattern_b,
        "search_params_a": args.search_params_a,
        "search_params_b": args.search_params_b,
        "depth": None if args.movetime is not None else args.depth,
        "movetime": args.movetime,
        "pairs": args.pairs,
        "nshards": args.nshards,
        "max_parallel": max_parallel,
        "openings_file": args.openings_file,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jass",
        help="single binary for same-architecture matches (backward-compatible shorthand)",
    )
    parser.add_argument("--jass-a", help="side A binary for cross-architecture matches")
    parser.add_argument("--jass-b", help="side B binary for cross-architecture matches")
    parser.add_argument("--pattern-a", required=True)
    parser.add_argument("--pattern-b", required=True)
    parser.add_argument("--openings-file", required=True)
    parser.add_argument("--harness", default="jobs/tools/jass_vs_jass_arch.py")
    parser.add_argument(
        "--search-params",
        help="shared fingerprint (legacy shorthand; defaults to historical 6/6)",
    )
    parser.add_argument("--search-params-a", help="resolved fingerprint for side A")
    parser.add_argument("--search-params-b", help="resolved fingerprint for side B")
    budget = parser.add_mutually_exclusive_group()
    budget.add_argument("--depth", type=int, default=9)
    budget.add_argument("--movetime", type=float, help="equal seconds per move on both sides")
    parser.add_argument("--pairs", type=int, default=1)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--nshards", type=int, default=16)
    parser.add_argument("--max-parallel", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=7000)
    parser.add_argument("--game-timeout", type=float, default=None,
                        help="forwarded to the harness: per-game wall-clock cap (s), exceeded → draw.")
    parser.add_argument("--paired-bootstrap-samples", type=int, default=0,
                        help="when positive, retain per-game results and cluster-bootstrap openings")
    parser.add_argument("--paired-bootstrap-seed", type=int, default=20260814)
    parser.add_argument("--dump-games-dir",
                        help="retain and validate immutable complete trajectories for every game")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    args.jass_a = args.jass_a or args.jass
    args.jass_b = args.jass_b or args.jass
    if not args.jass_a or not args.jass_b:
        parser.error("provide --jass, or both --jass-a and --jass-b")
    resolve_search_params(args)
    if args.paired_bootstrap_samples < 0:
        parser.error("--paired-bootstrap-samples must be non-negative")
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
