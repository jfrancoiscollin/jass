#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed record/WDL audit for CTX2-Intervention-v1 corpora."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
from typing import Any

import numpy as np

try:
    from l3_conditional_targets import JNNW_DTYPE
except ModuleNotFoundError:
    from jobs.tools.l3_conditional_targets import JNNW_DTYPE


HEADER = struct.Struct("<4sI")
EXPECTED_QUOTAS = {
    "BASE": 300_000,
    "ROP16": 600_000,
    "EPS16": 500_000,
    "DECAY120": 100_000,
    "TOPK3M30": 100_000,
    "DEPTH10": 400_000,
}


def _open(path: Path) -> tuple[int, np.memmap]:
    with path.open("rb") as handle:
        raw = handle.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise ValueError(f"{path}: truncated JNNW header")
    magic, count = HEADER.unpack(raw)
    if magic != b"JNNW":
        raise ValueError(f"{path}: JNNW magic expected")
    expected_size = HEADER.size + count * JNNW_DTYPE.itemsize
    if path.stat().st_size != expected_size:
        raise ValueError(
            f"{path}: size mismatch {path.stat().st_size} != {expected_size}"
        )
    rows = np.memmap(path, mode="r", offset=HEADER.size, dtype=JNNW_DTYPE, shape=(count,))
    return count, rows


def _rates(rows: np.ndarray) -> dict[str, float]:
    if len(rows) == 0:
        raise ValueError("empty JNNW corpus")
    rates = {str(value): float(np.mean(rows["wdl"] == value)) for value in (-1, 0, 1)}
    if not np.isclose(sum(rates.values()), 1.0, atol=1e-12):
        raise ValueError("WDL values outside {-1,0,1}")
    return rates


def audit(
    *,
    cells: dict[str, Path],
    unified: Path,
    code_sha: str,
    fresh_seed: int,
    expected_quotas: dict[str, int] = EXPECTED_QUOTAS,
    max_relative_draw_shift: float = 0.15,
    max_wdl_side_skew: float = 0.02,
) -> dict[str, Any]:
    if set(cells) != set(expected_quotas):
        raise ValueError("cell set drift")
    cell_rows: dict[str, Any] = {}
    base_draw: float | None = None
    for name, quota in expected_quotas.items():
        count, rows = _open(cells[name])
        if count != quota:
            raise ValueError(f"{name}: {count} records != {quota}")
        rates = _rates(rows)
        cell_rows[name] = {"records": count, "wdl_stm_rates": rates}
        if name == "BASE":
            base_draw = rates["0"]
    assert base_draw is not None
    count, rows = _open(unified)
    expected_total = sum(expected_quotas.values())
    if count != expected_total:
        raise ValueError(f"unified: {count} records != {expected_total}")
    rates = _rates(rows)
    draw_shift = (
        abs(rates["0"] - base_draw) / base_draw
        if base_draw
        else (0.0 if rates["0"] == 0.0 else float("inf"))
    )
    side_skew = abs(rates["1"] - rates["-1"])
    if draw_shift > max_relative_draw_shift:
        raise ValueError(f"unified relative draw shift {draw_shift} exceeds guard")
    if side_skew > max_wdl_side_skew:
        raise ValueError(f"unified WDL side skew {side_skew} exceeds guard")
    return {
        "schema": "jass.l3_context2_intervention_corpus.v1",
        "verdict": "JASS_CONTEXT2_INTERVENTION_CORPUS_READY",
        "code_sha": code_sha,
        "parent": "CURRICULUM",
        "fresh_seed": fresh_seed,
        "records": count,
        "cell_quotas": expected_quotas,
        "cells": cell_rows,
        "unified_wdl_stm_rates": rates,
        "relative_draw_shift_vs_base": draw_shift,
        "wdl_side_skew": side_skew,
        "same_opening_seeds_across_cells": True,
        "producers_per_cell": 12,
        "next_required_stage": "CTX2 activation/covariance audit before any fit",
        "fits_run": 0,
        "force_games_played": 0,
        "frozen_read": False,
        "promotion_authorized": False,
        "automatic_next_job": None,
    }


def _parse_cells(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--cell requires NAME=PATH")
        name, raw = value.split("=", 1)
        if not name or name in result:
            raise ValueError(f"invalid or duplicate cell {name!r}")
        result[name] = Path(raw)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell", action="append", required=True)
    parser.add_argument("--unified", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--fresh-seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = audit(
        cells=_parse_cells(args.cell),
        unified=args.unified,
        code_sha=args.code_sha,
        fresh_seed=args.fresh_seed,
    )
    if args.out.exists():
        raise ValueError(f"{args.out}: output exists (no-clobber)")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
