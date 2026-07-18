#!/usr/bin/env python3
"""Measure conversion against a fixed defender on deeply labelled JNNW positions.

Unlike the historical ``tools/conv_self.py`` heuristic, this runner does not
infer the advantaged side from piece counts. The winning side comes from the
record's d14+EGDB WDL label, so equal-material and king-heavy positions are
measured correctly. Schema 2 retains one outcome per source index so downstream
comparisons can use paired confidence intervals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

MAGIC = b"JNNW"
REC = 38


def read_records(path: str | Path) -> list[bytes]:
    raw = Path(path).read_bytes()
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise ValueError(f"{path}: invalid JNNW")
    n = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != n * REC:
        raise ValueError(f"{path}: truncated JNNW body")
    return [body[i * REC:(i + 1) * REC] for i in range(n)]


def record_to_fen(rec: bytes) -> str:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", rec, 0)
    stm = rec[32]

    def squares(bits: int, king: bool) -> list[str]:
        prefix = "K" if king else ""
        return [f"{prefix}{sq}" for sq in range(1, 51) if bits & (1 << (sq - 1))]

    white = squares(wm, False) + squares(wk, True)
    black = squares(bm, False) + squares(bk, True)
    return f"{'B' if stm else 'W'}:W{','.join(white)}:B{','.join(black)}"


def winning_side(rec: bytes) -> str | None:
    """Return W/B from STM-POV WDL, or None for a draw."""
    stm = rec[32]
    wdl = struct.unpack_from("<b", rec, 37)[0]
    if wdl == 0:
        return None
    stm_side = "B" if stm else "W"
    if wdl > 0:
        return stm_side
    return "W" if stm_side == "B" else "B"


def measure(args: argparse.Namespace) -> dict[str, object]:
    # Lazy import keeps pure record helpers unit-testable without engine tools.
    sys.path.insert(0, str(Path(args.calibrate_tool).resolve().parent))
    import calibrate_vs_scan as cv  # type: ignore

    pool_path = Path(args.pool_jnnw)
    records = read_records(pool_path)
    pool_sha256 = hashlib.sha256(pool_path.read_bytes()).hexdigest()
    defender_jass = args.defender_jass or args.jass

    def _fresh():
        return (
            cv.JassEngine(
                args.jass,
                pattern_path=args.pattern,
                search_params=args.search_params,
            ),
            cv.JassEngine(
                defender_jass,
                pattern_path=args.defender_pattern,
                search_params=args.defender_search_params,
            ),
            cv.Referee(args.jass),
        )

    champion, defender, referee = _fresh()
    n_pos = n_win = n_draw = n_loss = n_skipped = n_errors = n_restarts = 0
    errors: list[str] = []
    position_results: list[dict[str, int | str]] = []
    try:
        for index, rec in enumerate(records):
            if index % args.nshards != args.shard:
                continue
            winner = winning_side(rec)
            if winner is None:
                n_skipped += 1
                position_results.append({"index": index, "result": "skipped_draw_label"})
                continue
            fen = record_to_fen(rec)
            white, black = (champion, defender) if winner == "W" else (defender, champion)
            try:
                play_args = (
                    {"movetime": args.movetime}
                    if args.movetime is not None
                    else {"depth": args.depth}
                )
                result = cv.play_game(
                    white, black, referee, fen, max_plies=args.max_plies, **play_args
                )
            except (BrokenPipeError, EOFError, OSError, TimeoutError) as exc:
                # Restart all engines so one failure costs exactly one source position.
                n_errors += 1
                errors.append(f"pos {index}: moteur mort ({exc}) - restart")
                position_results.append({"index": index, "result": "error"})
                for engine in (champion, defender, referee):
                    try:
                        engine.close()
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    champion, defender, referee = _fresh()
                    n_restarts += 1
                except Exception as restart_exc:  # noqa: BLE001
                    errors.append(f"pos {index}: restart FAIL ({restart_exc})")
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
        "depth": None if args.movetime is not None else args.depth,
        "movetime": args.movetime,
        "jass": args.jass,
        "defender_jass": defender_jass,
        "pattern": args.pattern,
        "defender_pattern": args.defender_pattern,
        "search_params": args.search_params,
        "defender_search_params": args.defender_search_params,
        "pool_jnnw": str(pool_path),
        "pool_sha256": pool_sha256,
        "shard": args.shard,
        "nshards": args.nshards,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jass", required=True)
    parser.add_argument(
        "--defender-jass",
        help="optional second binary when the fixed defender uses another pattern geometry",
    )
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--defender-pattern", required=True)
    parser.add_argument("--search-params", help="candidate's fully resolved fingerprint")
    parser.add_argument(
        "--defender-search-params", help="fixed defender's fully resolved fingerprint"
    )
    parser.add_argument("--pool-jnnw", required=True)
    parser.add_argument("--calibrate-tool", default="jobs/tools/calibrate_vs_scan.py")
    budget = parser.add_mutually_exclusive_group()
    budget.add_argument("--depth", type=int, default=10)
    budget.add_argument("--movetime", type=float)
    parser.add_argument("--max-plies", type=int, default=260)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--nshards", type=int, default=1)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.nshards <= 0 or not 0 <= args.shard < args.nshards:
        parser.error("require 0 <= shard < nshards")
    try:
        result = measure(args)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    Path(args.out).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
