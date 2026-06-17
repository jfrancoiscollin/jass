#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-Francois Collin

import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pattern_jass.tools import jnnw_stats  # noqa: E402


def _bits(*squares):
    value = 0
    for square in squares:
        value |= 1 << square
    return value


def _record(wm, wk, bm, bk, stm, score, wdl):
    return struct.pack("<QQQQBib", wm, wk, bm, bk, stm, score, wdl)


def _write_jnnw(path, records, header_count=None):
    if header_count is None:
        header_count = len(records)
    path.write_bytes(b"JNNW" + struct.pack("<I", header_count) + b"".join(records))


def test_stats_for_synthetic_dataset():
    low_key = (_bits(0, 1), 0, _bits(2, 3), 0, 0)       # 4 pieces
    high_key = (_bits(0, 1, 2, 3, 4, 5), 0,
                _bits(6, 7, 8, 9, 10, 11, 12), 0, 1)   # 13 pieces
    low_unique = (_bits(0, 1, 2), 0, _bits(3, 4, 5, 6), 0, 0)  # 7 pieces
    high_unique = (_bits(0, 1, 2, 3, 4), 0,
                   _bits(5, 6, 7, 8, 9, 10), 0, 1)     # 11 pieces

    records = [
        _record(*low_key, score=10, wdl=1),
        _record(*low_key, score=20, wdl=-1),
        _record(*high_key, score=30, wdl=0),
        _record(*high_key, score=40, wdl=1),
        _record(*low_unique, score=50, wdl=0),
        _record(*high_unique, score=60, wdl=-1),
    ]

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "sample.jnnw"
        _write_jnnw(path, records)
        stats = jnnw_stats.compute_stats(path)

    assert stats["records"]["header_count"] == 6
    assert stats["records"]["file_count"] == 6
    assert stats["records"]["header_matches_file"] is True

    assert stats["phase"]["histogram"] == {"4": 2, "7": 1, "11": 1, "13": 2}
    assert stats["phase"]["thresholds"]["le7"]["count"] == 3
    assert stats["phase"]["thresholds"]["le7"]["fraction"] == 3 / 6
    assert stats["phase"]["thresholds"]["le10"]["count"] == 3
    assert stats["phase"]["thresholds"]["le10"]["fraction"] == 3 / 6
    assert stats["phase"]["thresholds"]["le12"]["count"] == 4
    assert stats["phase"]["thresholds"]["le12"]["fraction"] == 4 / 6

    assert stats["wdl"]["win"]["count"] == 2
    assert stats["wdl"]["win"]["fraction"] == 2 / 6
    assert stats["wdl"]["draw"]["count"] == 2
    assert stats["wdl"]["draw"]["fraction"] == 2 / 6
    assert stats["wdl"]["loss"]["count"] == 2
    assert stats["wdl"]["loss"]["fraction"] == 2 / 6
    assert stats["wdl"]["invalid"]["count"] == 0

    consistency = stats["consistency"]
    assert consistency["unique_keys"] == 4
    assert consistency["duplicate_keys"] == {"total": 2, "le7": 1, "gt7": 1}
    assert consistency["duplicate_extra_records"] == {
        "total": 2,
        "le7": 1,
        "gt7": 1,
    }
    assert consistency["wdl_contradictions"] == {
        "total": 2,
        "le7": 1,
        "gt7": 1,
    }


def test_header_mismatch_is_reported_but_not_fatal():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "mismatch.jnnw"
        _write_jnnw(path, [_record(1, 0, 2, 0, 0, 0, 0)], header_count=5)
        stats = jnnw_stats.compute_stats(path)

    assert stats["records"]["header_count"] == 5
    assert stats["records"]["file_count"] == 1
    assert stats["records"]["header_matches_file"] is False
    assert stats["records"]["mismatch"] == 4


def test_rejects_empty_header_and_truncated_body():
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "empty.jnnw"
        empty.write_bytes(b"")
        try:
            jnnw_stats.compute_stats(empty)
        except jnnw_stats.JNNWFormatError as exc:
            assert "truncated header" in str(exc)
        else:
            raise AssertionError("empty file should be rejected")

        truncated = Path(td) / "truncated.jnnw"
        truncated.write_bytes(b"JNNW" + struct.pack("<I", 1) + b"x")
        try:
            jnnw_stats.compute_stats(truncated)
        except jnnw_stats.JNNWFormatError as exc:
            assert "not a multiple" in str(exc)
        else:
            raise AssertionError("truncated body should be rejected")


if __name__ == "__main__":
    test_stats_for_synthetic_dataset()
    test_header_mismatch_is_reported_but_not_fatal()
    test_rejects_empty_header_and_truncated_body()
