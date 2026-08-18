#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fail-closed size and WDL audit for the CTX2 contribution-balanced pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jobs.tools.l3_context2_intervention_corpus_audit import _open, _rates


CELL_NAMES = (
    "blocked_man",
    "center_presence",
    "king_centrality",
    "king_safe_mobility",
    "legal_capture_option",
    "neutral",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def audit(
    *,
    cells: dict[str, Path],
    expected_per_cell: int,
    code_sha: str,
    fresh_seed: int,
    seed_source: str,
    unified: Path | None = None,
    max_relative_draw_shift: float = 0.15,
    max_wdl_side_skew: float = 0.02,
) -> dict[str, Any]:
    if set(cells) != set(CELL_NAMES):
        raise ValueError("cell set drift")
    if expected_per_cell <= 0:
        raise ValueError("expected_per_cell must be positive")

    rows: dict[str, Any] = {}
    for name in CELL_NAMES:
        count, records = _open(cells[name])
        if count != expected_per_cell:
            raise ValueError(f"{name}: {count} records != {expected_per_cell}")
        rates = _rates(records)
        side_skew = abs(rates["1"] - rates["-1"])
        if side_skew > max_wdl_side_skew + 1e-12:
            raise ValueError(f"{name}: WDL side skew {side_skew} exceeds guard")
        rows[name] = {
            "records": count,
            "sha256": _sha256(cells[name]),
            "wdl_stm_rates": rates,
            "wdl_side_skew": side_skew,
        }

    neutral_draw = float(rows["neutral"]["wdl_stm_rates"]["0"])
    for name in CELL_NAMES:
        draw = float(rows[name]["wdl_stm_rates"]["0"])
        shift = (
            abs(draw - neutral_draw) / neutral_draw
            if neutral_draw
            else (0.0 if draw == 0.0 else float("inf"))
        )
        if shift > max_relative_draw_shift + 1e-12:
            raise ValueError(
                f"{name}: relative draw shift {shift} versus neutral exceeds guard"
            )
        rows[name]["relative_draw_shift_vs_neutral"] = shift

    total = expected_per_cell * len(CELL_NAMES)
    unified_row = None
    if unified is not None:
        count, records = _open(unified)
        if count != total:
            raise ValueError(f"unified: {count} records != {total}")
        rates = _rates(records)
        side_skew = abs(rates["1"] - rates["-1"])
        if side_skew > max_wdl_side_skew + 1e-12:
            raise ValueError(f"unified: WDL side skew {side_skew} exceeds guard")
        unified_row = {
            "records": count,
            "sha256": _sha256(unified),
            "wdl_stm_rates": rates,
            "wdl_side_skew": side_skew,
        }

    completed = unified is not None
    return {
        "schema": "jass.l3_context2_contribution_balanced_corpus.v1",
        "verdict": (
            "JASS_CONTEXT2_CONTRIBUTION_BALANCED_CORPUS_READY"
            if completed
            else "JASS_CONTEXT2_CONTRIBUTION_BALANCED_PREFLIGHT_PASSED"
        ),
        "code_sha": code_sha,
        "parent": "CURRICULUM",
        "fresh_seed": int(fresh_seed),
        "seed_source": seed_source,
        "cell_order": list(CELL_NAMES),
        "expected_per_cell": expected_per_cell,
        "records": total,
        "cells": rows,
        "unified": unified_row,
        "guards": {
            "maximum_wdl_side_skew": max_wdl_side_skew,
            "maximum_relative_draw_shift_vs_neutral": max_relative_draw_shift,
            "all_cell_counts_exact": True,
            "all_cell_wdl_guards_passed": True,
            "unified_count_exact": completed,
        },
        "protocol": {
            "generator": "TOPK3M30",
            "seed_file_percent": 100,
            "producers_per_cell": 12,
            "fits_run": 0,
            "force_games_played": 0,
            "frozen_read": False,
            "promotion_authorized": False,
            "automatic_next_job": None,
        },
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
    parser.add_argument("--expected-per-cell", type=int, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--fresh-seed", type=int, required=True)
    parser.add_argument("--seed-source", required=True)
    parser.add_argument("--unified", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = audit(
        cells=_parse_cells(args.cell),
        expected_per_cell=args.expected_per_cell,
        code_sha=args.code_sha,
        fresh_seed=args.fresh_seed,
        seed_source=args.seed_source,
        unified=args.unified,
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
