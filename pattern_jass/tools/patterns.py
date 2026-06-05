# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# Mirror of pattern_jass/src/pattern.hpp (v3 — Scan-style geometry).
# 8 patterns × 12 squares, ternary encoding, 4 251 528 buckets total.

import numpy as np

PATTERNS: list[list[int]] = [
    # Top half — 4 vertical bands (2 cols × 6 rows).
    [ 1,  2,  6,  7, 11, 12, 16, 17, 21, 22, 26, 27],   # top_band_0
    [ 2,  3,  7,  8, 12, 13, 17, 18, 22, 23, 27, 28],   # top_band_1
    [ 3,  4,  8,  9, 13, 14, 18, 19, 23, 24, 28, 29],   # top_band_2
    [ 4,  5,  9, 10, 14, 15, 19, 20, 24, 25, 29, 30],   # top_band_3
    # Bottom half — same 4 bands shifted to rows 4-9.
    [21, 22, 26, 27, 31, 32, 36, 37, 41, 42, 46, 47],   # bot_band_0
    [22, 23, 27, 28, 32, 33, 37, 38, 42, 43, 47, 48],   # bot_band_1
    [23, 24, 28, 29, 33, 34, 38, 39, 43, 44, 48, 49],   # bot_band_2
    [24, 25, 29, 30, 34, 35, 39, 40, 44, 45, 49, 50],   # bot_band_3
]

PATTERN_NAMES = [
    "top_band_0", "top_band_1", "top_band_2", "top_band_3",
    "bot_band_0", "bot_band_1", "bot_band_2", "bot_band_3",
]

NUM_PATTERNS         = len(PATTERNS)               # 8
PATTERN_SIZE         = 12
BUCKETS_PER_PATTERN  = 3 ** PATTERN_SIZE           # 531 441
TOTAL_BUCKETS        = BUCKETS_PER_PATTERN * NUM_PATTERNS  # 4 251 528

POW3 = np.array([3 ** k for k in range(PATTERN_SIZE + 1)], dtype=np.int64)
PATTERN_OFFSETS = np.arange(NUM_PATTERNS, dtype=np.int64) * BUCKETS_PER_PATTERN


def extract_indices(black_men: np.ndarray, white_men: np.ndarray) -> np.ndarray:
    n = len(black_men)
    out = np.zeros((n, NUM_PATTERNS), dtype=np.int64)
    for pi, sqs in enumerate(PATTERNS):
        idx = np.zeros(n, dtype=np.int64)
        for k, sq in enumerate(sqs):
            bit = np.uint64(1) << np.uint64(sq - 1)
            is_black = ((black_men & bit) != 0).astype(np.int64)
            is_white = ((white_men & bit) != 0).astype(np.int64)
            cell = is_black * 1 + is_white * 2
            idx += cell * int(POW3[k])
        out[:, pi] = idx
    return out


def flat_feature_columns(indices: np.ndarray) -> np.ndarray:
    return indices + PATTERN_OFFSETS[np.newaxis, :]
