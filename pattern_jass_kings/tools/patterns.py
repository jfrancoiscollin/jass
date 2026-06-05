# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# Mirror of pattern_jass_kings/src/pattern.hpp. 8 patterns × 8 squares,
# 5-state encoding (empty, bm, bk, wm, wk).

import numpy as np

PATTERNS: list[list[int]] = [
    # Row segments.
    [ 1,  2,  3,  4,  5,  6,  7,  8],   # row_top_8
    [11, 12, 13, 14, 15, 16, 17, 18],   # row_2_8
    [21, 22, 23, 24, 25, 26, 27, 28],   # row_mid_8
    [31, 32, 33, 34, 35, 36, 37, 38],   # row_4_8
    # Column segments.
    [ 1,  6, 11, 16, 21, 26, 31, 36],   # col_left_8
    [ 3,  8, 13, 18, 23, 28, 33, 38],   # col_mid_8
    [ 5, 10, 15, 20, 25, 30, 35, 40],   # col_right_8
    [ 2,  9, 12, 19, 22, 29, 32, 39],   # col_offset_8
]

PATTERN_NAMES = [
    "row_top_8", "row_2_8", "row_mid_8", "row_4_8",
    "col_left_8", "col_mid_8", "col_right_8", "col_offset_8",
]

NUM_PATTERNS         = len(PATTERNS)               # 8
PATTERN_SIZE         = 8
BUCKETS_PER_PATTERN  = 5 ** PATTERN_SIZE           # 390625
TOTAL_BUCKETS        = BUCKETS_PER_PATTERN * NUM_PATTERNS  # 3 125 000

POW5 = np.array([5 ** k for k in range(PATTERN_SIZE + 1)], dtype=np.int64)
PATTERN_OFFSETS = np.arange(NUM_PATTERNS, dtype=np.int64) * BUCKETS_PER_PATTERN


def extract_indices(bm: np.ndarray, bk: np.ndarray,
                    wm: np.ndarray, wk: np.ndarray) -> np.ndarray:
    """5-state index per pattern. cell = 0/1/2/3/4."""
    n = len(bm)
    out = np.zeros((n, NUM_PATTERNS), dtype=np.int64)
    for pi, sqs in enumerate(PATTERNS):
        idx = np.zeros(n, dtype=np.int64)
        for k, sq in enumerate(sqs):
            bit = np.uint64(1) << np.uint64(sq - 1)
            is_bm = ((bm & bit) != 0).astype(np.int64)
            is_bk = ((bk & bit) != 0).astype(np.int64)
            is_wm = ((wm & bit) != 0).astype(np.int64)
            is_wk = ((wk & bit) != 0).astype(np.int64)
            cell = is_bm * 1 + is_bk * 2 + is_wm * 3 + is_wk * 4
            idx += cell * int(POW5[k])
        out[:, pi] = idx
    return out


def flat_feature_columns(indices: np.ndarray) -> np.ndarray:
    return indices + PATTERN_OFFSETS[np.newaxis, :]
