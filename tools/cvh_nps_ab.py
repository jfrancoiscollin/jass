#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Paired fixed-depth speed benchmark for CVH cells A/Z/C10.

All cells search the same deterministic JNNW positions at the same depths.  The
report includes nodes/s, seconds/position, node counts and A/Z move mismatches.
The ``offgate`` filter excludes root positions where the P3 head is active;
``p3`` keeps exactly margin=1 and 8<=pieces<20.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import struct
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import calibrate_vs_scan as cv  # noqa: E402

REC = 38
NODES_RE = re.compile(r"\bnodes=(\d+)\b")
MOVE_RE = re.compile(r"^bestmove\s+(\S+)")


@dataclass(frozen=True)
class Sample:
    index: int
    fen: str
    pieces: int
    margin: int


def _squares(bits: int, king: bool) -> list[str]:
    prefix = "K" if king else ""
    return [f"{prefix}{sq}" for sq in range(1, 51) if bits & (1 << (sq - 1))]


def _record_sample(index: int, rec: bytes) -> Sample:
    wm, wk, bm, bk = struct.unpack_from("<QQQQ", rec, 0)
    stm = rec[32]
    if stm not in (0, 1):
        raise ValueError(f"record {index}: bad stm={stm}")
    planes = (wm, wk, bm, bk)
    if any(x >> 50 for x in planes):
        raise ValueError(f"record {index}: bits outside board")
    if any(planes[i] & planes[j] for i in range(4) for j in range(i + 1, 4)):
        raise ValueError(f"record {index}: overlapping planes")
    nwm, nwk, nbm, nbk = (x.bit_count() for x in planes)
    pieces = nwm + nwk + nbm + nbk
    margin = abs((nbm + 3 * nbk) - (nwm + 3 * nwk))
    white = _squares(wm, False) + _squares(wk, True)
    black = _squares(bm, False) + _squares(bk, True)
    fen = f"{'B' if stm else 'W'}:W{','.join(white)}:B{','.join(black)}"
    return Sample(index=index, fen=fen, pieces=pieces, margin=margin)


def load_samples(path: Path, n: int, seed: int, mode: str,
                 min_pieces: int = 8) -> list[Sample]:
    raw = path.read_bytes()
    if len(raw) < 8 or raw[:4] != b"JNNW":
        raise ValueError(f"{path}: invalid JNNW")
    count = struct.unpack_from("<I", raw, 4)[0]
    body = raw[8:]
    if len(body) != count * REC:
        raise ValueError(f"{path}: truncated JNNW")
    indices = list(range(count))
    random.Random(seed).shuffle(indices)
    out: list[Sample] = []
    for index in indices:
        sample = _record_sample(index, body[index * REC:(index + 1) * REC])
        active = sample.margin == 1 and 8 <= sample.pieces < 20
        keep = (
            mode == "all"
            or (mode == "p3" and active)
            or (mode == "offgate" and sample.pieces >= min_pieces and not active)
        )
        if keep:
            out.append(sample)
        if len(out) >= n:
            break
    if len(out) < n:
        raise ValueError(f"{path}: requested {n} {mode} samples, found {len(out)}")
    return out


class BenchJass(cv.JassEngine):
    def go_stats(self, depth: int) -> tuple[str, int, float]:
        self._drain()
        self._send(f"go depth {depth}")
        t0 = time.perf_counter()
        lines = self._read_until(
            lambda line: line.startswith("bestmove") or line.startswith("error"),
            timeout_s=120.0,
        )
        elapsed = time.perf_counter() - t0
        last = lines[-1]
        if last.startswith("error"):
            raise RuntimeError(last)
        nm = NODES_RE.search(last)
        mm = MOVE_RE.search(last)
        if nm is None or mm is None:
            raise ValueError(f"cannot parse benchmark line: {last!r}")
        return mm.group(1), int(nm.group(1)), elapsed


def parse_cells(values: list[str]) -> list[tuple[str, str]]:
    cells: list[tuple[str, str]] = []
    seen: set[str] = set()
    for value in values:
        if "=" not in value:
            raise ValueError(f"bad --cell {value!r}; expected NAME=PATH")
        name, path = value.split("=", 1)
        if not name or not path or name in seen:
            raise ValueError(f"bad or duplicate cell {value!r}")
        seen.add(name)
        cells.append((name, path))
    if "A" not in seen or "Z" not in seen or "C10" not in seen:
        raise ValueError("cells A, Z and C10 are mandatory")
    return cells


def benchmark(args: argparse.Namespace) -> dict[str, object]:
    cells = parse_cells(args.cell)
    samples = load_samples(args.positions, args.n, args.seed, args.filter,
                           args.min_pieces)
    depths = [int(x) for x in args.depths.split(",") if x.strip()]
    if not depths or any(d <= 0 for d in depths):
        raise ValueError("--depths must contain positive integers")

    engines = {
        name: BenchJass(args.jass, label=name, pattern_path=path,
                        search_params=args.search_params)
        for name, path in cells
    }
    totals = {
        name: {"nodes": 0, "seconds": 0.0, "searches": 0, "errors": 0}
        for name, _ in cells
    }
    moves: dict[tuple[int, int, str], str] = {}
    try:
        # Warm caches without recording the timings.
        for name, _ in cells:
            for sample in samples[:args.warmup]:
                engines[name].new_game()
                engines[name].set_position_fen(sample.fen)
                engines[name].go_stats(depths[0])

        for depth in depths:
            for pos_i, sample in enumerate(samples):
                order = cells[pos_i % len(cells):] + cells[:pos_i % len(cells)]
                for name, _ in order:
                    engine = engines[name]
                    try:
                        engine.new_game()
                        engine.set_position_fen(sample.fen)
                        move, nodes, seconds = engine.go_stats(depth)
                    except Exception:  # noqa: BLE001
                        totals[name]["errors"] += 1
                        continue
                    totals[name]["nodes"] += nodes
                    totals[name]["seconds"] += seconds
                    totals[name]["searches"] += 1
                    moves[(sample.index, depth, name)] = move
    finally:
        for engine in engines.values():
            try:
                engine.close()
            except Exception:  # noqa: BLE001
                pass

    cell_report: dict[str, dict[str, float | int]] = {}
    for name, _ in cells:
        t = totals[name]
        searches = int(t["searches"])
        seconds = float(t["seconds"])
        nodes = int(t["nodes"])
        cell_report[name] = {
            "searches": searches,
            "errors": int(t["errors"]),
            "nodes": nodes,
            "seconds": round(seconds, 6),
            "nps": round(nodes / seconds, 3) if seconds > 0 else 0.0,
            "seconds_per_search": round(seconds / searches, 6) if searches else 0.0,
        }

    az_common = az_mismatch = 0
    for sample in samples:
        for depth in depths:
            a = moves.get((sample.index, depth, "A"))
            z = moves.get((sample.index, depth, "Z"))
            if a is not None and z is not None:
                az_common += 1
                az_mismatch += int(a != z)

    a_nps = float(cell_report["A"]["nps"])
    for name in cell_report:
        cell_report[name]["nps_ratio_vs_a"] = (
            round(float(cell_report[name]["nps"]) / a_nps, 6) if a_nps else 0.0
        )

    return {
        "schema": 1,
        "filter": args.filter,
        "positions": str(args.positions),
        "n_positions": len(samples),
        "depths": depths,
        "seed": args.seed,
        "search_params": args.search_params,
        "cells": cell_report,
        "az_common_searches": az_common,
        "az_move_mismatches": az_mismatch,
        "sample_indices": [sample.index for sample in samples],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jass", required=True)
    parser.add_argument("--cell", action="append", required=True,
                        help="repeat NAME=PATTERN; A/Z/C10 mandatory")
    parser.add_argument("--positions", required=True, type=Path)
    parser.add_argument("--filter", choices=("offgate", "p3", "all"),
                        default="offgate")
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--depths", default="9,12")
    parser.add_argument("--seed", type=int, default=314159)
    parser.add_argument("--min-pieces", type=int, default=8)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--search-params")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.n <= 0 or args.warmup < 0:
        parser.error("--n must be positive and --warmup non-negative")
    try:
        report = benchmark(args)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
