#!/usr/bin/env python3
"""Measure pinned Scan conversion against the same fixed Jass defender.

The winning side is read from the certified JNNW WDL label.  Scan always
plays that side, while one immutable Jass model plays the disadvantaged side.
The output deliberately matches the schema consumed by
``aggregate_conv_shards.py`` so Scan and learned models can be paired by
source-position index.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    from conv_fixed_wdl import read_records, record_to_fen, winning_side
except ModuleNotFoundError:  # Imported as jobs.tools.conv_scan_fixed_wdl in tests.
    from jobs.tools.conv_fixed_wdl import read_records, record_to_fen, winning_side


def measure(args: argparse.Namespace) -> dict[str, object]:
    sys.path.insert(0, str(Path(args.calibrate_tool).resolve().parent))
    import calibrate_vs_scan as cv  # type: ignore

    pool_path = Path(args.pool_jnnw)
    records = read_records(pool_path)
    pool_sha256 = hashlib.sha256(pool_path.read_bytes()).hexdigest()

    def fresh():
        return (
            cv.ScanEngine(
                args.scan,
                label=f"Scan-d{args.scan_depth}",
                no_book=True,
                bb_size=0,
            ),
            cv.JassEngine(
                args.jass,
                label="fixed-defender",
                pattern_path=args.defender_pattern,
                search_params=args.defender_search_params,
            ),
            cv.Referee(args.jass),
        )

    champion, defender, referee = fresh()
    n_pos = n_win = n_draw = n_loss = n_skipped = n_errors = n_restarts = 0
    errors: list[str] = []
    position_results: list[dict[str, int | str]] = []
    try:
        for index, record in enumerate(records):
            if index % args.nshards != args.shard:
                continue
            winner = winning_side(record)
            if winner is None:
                n_skipped += 1
                position_results.append(
                    {"index": index, "result": "skipped_draw_label"}
                )
                continue

            fen = record_to_fen(record)
            white, black = (
                (champion, defender) if winner == "W" else (defender, champion)
            )
            try:
                result = cv.play_game(
                    white,
                    black,
                    referee,
                    fen,
                    jass_depth=args.defender_depth,
                    scan_depth=args.scan_depth,
                    max_plies=args.max_plies,
                    game_timeout_s=args.game_timeout,
                )
            except (BrokenPipeError, EOFError, OSError, TimeoutError) as exc:
                n_errors += 1
                errors.append(f"pos {index}: dead engine ({exc}) - restart")
                position_results.append({"index": index, "result": "error"})
                for engine in (champion, defender, referee):
                    try:
                        engine.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    champion, defender, referee = fresh()
                    n_restarts += 1
                except Exception as restart_exc:  # noqa: BLE001
                    errors.append(f"pos {index}: restart failed ({restart_exc})")
                    raise OSError("engine restart failed") from restart_exc
                continue
            except Exception as exc:  # noqa: BLE001
                n_errors += 1
                errors.append(f"pos {index}: {exc}")
                position_results.append({"index": index, "result": "error"})
                continue

            n_pos += 1
            champion_won = (
                (winner == "W" and result.outcome == "W")
                or (winner == "B" and result.outcome == "L")
            )
            if result.outcome == "D":
                n_draw += 1
                outcome = "draw"
            elif champion_won:
                n_win += 1
                outcome = "win"
            else:
                n_loss += 1
                outcome = "loss"
            position_results.append({"index": index, "result": outcome})
    finally:
        champion.close()
        defender.close()
        referee.close()

    return {
        "schema": 2,
        "conv_fixed_wdl": None if n_pos == 0 else round(n_win / n_pos, 6),
        "n_pos": n_pos,
        "n_win": n_win,
        "n_draw": n_draw,
        "n_loss": n_loss,
        "n_skipped_draw_label": n_skipped,
        "n_errors": n_errors,
        "n_restarts": n_restarts,
        "errors": errors[:20],
        "position_results": position_results,
        "depth": args.scan_depth,
        "movetime": None,
        "jass": args.scan,
        "defender_jass": args.jass,
        "pattern": f"SCAN_D{args.scan_depth}",
        "defender_pattern": args.defender_pattern,
        "search_params": (
            f"pinned_scan_runtime={args.scan_runtime_sha256};"
            "book=false;threads=1;tt-size=24;bb-size=0"
        ),
        "defender_search_params": args.defender_search_params,
        "scan_depth": args.scan_depth,
        "defender_depth": args.defender_depth,
        "scan_runtime_sha256": args.scan_runtime_sha256,
        "game_timeout": args.game_timeout,
        "pool_jnnw": str(pool_path),
        "pool_sha256": pool_sha256,
        "shard": args.shard,
        "nshards": args.nshards,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", required=True)
    parser.add_argument("--scan-runtime-sha256", required=True)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--defender-pattern", required=True)
    parser.add_argument("--defender-search-params", required=True)
    parser.add_argument("--pool-jnnw", required=True)
    parser.add_argument("--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py")
    parser.add_argument("--scan-depth", type=int, required=True)
    parser.add_argument("--defender-depth", type=int, default=10)
    parser.add_argument("--max-plies", type=int, default=260)
    parser.add_argument("--game-timeout", type=float, default=600.0)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.scan_depth <= 0 or args.defender_depth <= 0:
        parser.error("depths must be positive")
    if args.nshards <= 0 or not 0 <= args.shard < args.nshards:
        parser.error("require 0 <= shard < nshards")
    try:
        result = measure(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    Path(args.out).write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
