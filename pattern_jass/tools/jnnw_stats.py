#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-Francois Collin
"""Inspect JNNW training datasets.

JNNW is the jass core self-play/master-data format:

  header: 4 bytes magic "JNNW" + uint32 record count, little-endian
  record: 38 bytes = 4 x uint64 bitboards (wm, wk, bm, bk), uint8 stm,
          int32 score, int8 wdl

The tool reports record-count consistency, phase/WDL distributions, and duplicate
position keys (bitboards + side-to-move), including WDL contradictions — counted as
distinct KEYS whose records carry mixed WDL (the record-level redundancy is reported
separately as duplicate_extra_records) — split between <=7-piece endgames and the
rest of the dataset.
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from pathlib import Path
from typing import Any

import numpy as np

JNNW_MAGIC = b"JNNW"
JNNW_HEADER_SIZE = 8
JNNW_RECORD_SIZE = 38

JNNW_DTYPE = np.dtype([
    ("wm", "<u8"),
    ("wk", "<u8"),
    ("bm", "<u8"),
    ("bk", "<u8"),
    ("stm", "u1"),
    ("score", "<i4"),
    ("wdl", "i1"),
])
KEY_DTYPE = np.dtype([
    ("wm", "<u8"),
    ("wk", "<u8"),
    ("bm", "<u8"),
    ("bk", "<u8"),
    ("stm", "u1"),
])
assert JNNW_DTYPE.itemsize == JNNW_RECORD_SIZE

_BYTE_POPCOUNT = np.array([int(i).bit_count() for i in range(256)],
                          dtype=np.uint8)


class JNNWFormatError(ValueError):
    """Raised when a JNNW file is unreadable or structurally invalid."""


def _fraction(count: int, total: int) -> float:
    return float(count / total) if total else 0.0


def _load_records(path: Path) -> tuple[int, int, np.ndarray]:
    """Return (header_count, file_derived_count, records).

    Header/file count mismatches are intentionally not fatal: this is an
    inspection tool, and reporting the mismatch is one of its jobs. Truncated
    headers, bad magic, and bodies whose size is not a multiple of 38 are fatal.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise JNNWFormatError(f"{path}: cannot stat file: {exc}") from exc

    if size < JNNW_HEADER_SIZE:
        raise JNNWFormatError(f"{path}: truncated header ({size} bytes)")

    try:
        with path.open("rb") as f:
            header = f.read(JNNW_HEADER_SIZE)
    except OSError as exc:
        raise JNNWFormatError(f"{path}: cannot read header: {exc}") from exc

    magic = header[:4]
    if magic != JNNW_MAGIC:
        raise JNNWFormatError(f"{path}: bad magic {magic!r}, expected {JNNW_MAGIC!r}")

    header_count = struct.unpack_from("<I", header, 4)[0]
    body_size = size - JNNW_HEADER_SIZE
    if body_size % JNNW_RECORD_SIZE:
        raise JNNWFormatError(
            f"{path}: body size {body_size} is not a multiple of "
            f"{JNNW_RECORD_SIZE}"
        )

    file_count = body_size // JNNW_RECORD_SIZE
    if file_count == 0:
        records = np.empty(0, dtype=JNNW_DTYPE)
    else:
        records = np.memmap(path, dtype=JNNW_DTYPE, mode="r",
                            offset=JNNW_HEADER_SIZE, shape=(file_count,))
    return header_count, file_count, records


def piece_counts(records: np.ndarray) -> np.ndarray:
    """Vectorised piece-count array from the union of the four bitboards."""
    if len(records) == 0:
        return np.empty(0, dtype=np.uint8)
    occupied = (records["wm"] | records["wk"] |
                records["bm"] | records["bk"]).astype("<u8", copy=False)
    by_byte = occupied.view(np.uint8).reshape(-1, 8)
    return _BYTE_POPCOUNT[by_byte].sum(axis=1, dtype=np.uint8)


def phase_stats(pieces: np.ndarray, total: int) -> dict[str, Any]:
    max_piece_count = int(pieces.max()) if len(pieces) else 0
    hist = np.bincount(pieces.astype(np.int64), minlength=max(65, max_piece_count + 1))
    thresholds = {}
    for limit in (7, 10, 12):
        count = int((pieces <= limit).sum())
        thresholds[f"le{limit}"] = {
            "count": count,
            "fraction": _fraction(count, total),
        }
    return {
        "histogram": {str(i): int(c) for i, c in enumerate(hist) if c},
        "thresholds": thresholds,
    }


def wdl_stats(wdl: np.ndarray, total: int) -> dict[str, Any]:
    values = {}
    for label, value in (("win", 1), ("draw", 0), ("loss", -1)):
        count = int((wdl == value).sum())
        values[label] = {
            "wdl": value,
            "count": count,
            "fraction": _fraction(count, total),
        }
    invalid = int((~np.isin(wdl, np.array([-1, 0, 1], dtype=np.int8))).sum())
    values["invalid"] = {
        "count": invalid,
        "fraction": _fraction(invalid, total),
    }
    return values


def consistency_stats(records: np.ndarray, pieces: np.ndarray) -> dict[str, Any]:
    if len(records) == 0:
        zero_split = {"total": 0, "le7": 0, "gt7": 0}
        return {
            "duplicate_keys": dict(zero_split),
            "duplicate_extra_records": dict(zero_split),
            "wdl_contradictions": dict(zero_split),
            "unique_keys": 0,
        }

    keys = np.empty(len(records), dtype=KEY_DTYPE)
    for field in ("wm", "wk", "bm", "bk", "stm"):
        keys[field] = records[field]

    order = np.argsort(keys, order=("wm", "wk", "bm", "bk", "stm"), kind="stable")
    sorted_keys = keys[order]
    sorted_pieces = pieces[order]
    sorted_wdl = records["wdl"][order]

    same_as_previous = (
        (sorted_keys["wm"][1:] == sorted_keys["wm"][:-1]) &
        (sorted_keys["wk"][1:] == sorted_keys["wk"][:-1]) &
        (sorted_keys["bm"][1:] == sorted_keys["bm"][:-1]) &
        (sorted_keys["bk"][1:] == sorted_keys["bk"][:-1]) &
        (sorted_keys["stm"][1:] == sorted_keys["stm"][:-1])
    )
    starts = np.empty(len(records), dtype=bool)
    starts[0] = True
    starts[1:] = ~same_as_previous
    start_idx = np.flatnonzero(starts)
    end_idx = np.r_[start_idx[1:], len(records)]
    counts = end_idx - start_idx

    duplicate = counts > 1
    group_le7 = sorted_pieces[start_idx] <= 7

    wdl_min = np.minimum.reduceat(sorted_wdl, start_idx)
    wdl_max = np.maximum.reduceat(sorted_wdl, start_idx)
    contradictory = duplicate & (wdl_min != wdl_max)
    extra_records = counts - 1

    def split_sum(mask: np.ndarray, weights: np.ndarray | None = None) -> dict[str, int]:
        if weights is None:
            values = mask.astype(np.int64)
        else:
            values = np.where(mask, weights, 0).astype(np.int64)
        total = int(values.sum())
        le7 = int(values[group_le7].sum())
        return {"total": total, "le7": le7, "gt7": total - le7}

    return {
        "duplicate_keys": split_sum(duplicate),
        "duplicate_extra_records": split_sum(duplicate, extra_records),
        "wdl_contradictions": split_sum(contradictory),
        "unique_keys": int(len(start_idx)),
    }


def compute_stats(path: str | Path) -> dict[str, Any]:
    """Compute all JNNW stats for `path` and return JSON-serialisable data."""
    path = Path(path)
    header_count, file_count, records = _load_records(path)
    total = int(file_count)
    pieces = piece_counts(records)
    return {
        "path": os.fspath(path),
        "records": {
            "header_count": int(header_count),
            "file_count": total,
            "header_matches_file": int(header_count) == total,
            "mismatch": int(header_count) - total,
        },
        "phase": phase_stats(pieces, total),
        "wdl": wdl_stats(records["wdl"], total),
        "consistency": consistency_stats(records, pieces),
    }


def _fmt_fraction(value: float) -> str:
    return f"{value * 100:6.2f}%"


def format_text(stats: dict[str, Any]) -> str:
    lines = []
    records = stats["records"]
    lines.append(f"JNNW stats: {stats['path']}")
    lines.append("")
    lines.append("Records")
    lines.append(f"  header count : {records['header_count']}")
    lines.append(f"  file records : {records['file_count']}")
    if records["header_matches_file"]:
        lines.append("  count check  : OK")
    else:
        lines.append(f"  count check  : MISMATCH ({records['mismatch']:+d})")

    lines.append("")
    lines.append("Phase distribution")
    for key, label in (("le7", "<=7p"), ("le10", "<=10p"), ("le12", "<=12p")):
        item = stats["phase"]["thresholds"][key]
        lines.append(
            f"  {label:6s}: {item['count']:8d} "
            f"({_fmt_fraction(item['fraction'])})"
        )
    lines.append("  histogram:")
    for pieces, count in stats["phase"]["histogram"].items():
        lines.append(f"    {int(pieces):2d} pieces: {count}")

    lines.append("")
    lines.append("WDL distribution")
    for key, label in (("win", "+1"), ("draw", " 0"), ("loss", "-1")):
        item = stats["wdl"][key]
        lines.append(
            f"  {label}: {item['count']:8d} "
            f"({_fmt_fraction(item['fraction'])})"
        )
    invalid = stats["wdl"]["invalid"]
    if invalid["count"]:
        lines.append(
            f"  invalid: {invalid['count']:8d} "
            f"({_fmt_fraction(invalid['fraction'])})"
        )

    lines.append("")
    lines.append("Consistency")
    cons = stats["consistency"]
    lines.append(f"  unique keys             : {cons['unique_keys']}")
    for key, label in (
        ("duplicate_keys", "duplicated keys"),
        ("duplicate_extra_records", "duplicate extra records"),
        ("wdl_contradictions", "WDL contradictions (keys)"),
    ):
        item = cons[key]
        lines.append(
            f"  {label:24s}: {item['total']} "
            f"(<=7p {item['le7']}, >7p {item['gt7']})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("jnnw", help="JNNW dataset to inspect")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of human-readable text")
    args = ap.parse_args(argv)

    try:
        stats = compute_stats(args.jnnw)
    except (JNNWFormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(stats, indent=2, sort_keys=True))
    else:
        print(format_text(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
