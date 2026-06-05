# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# Mirror of pattern_jass/src/pattern.hpp (kept in sync manually).
# 8 patterns × 10 squares, ternary encoding, 472392 buckets total.

import numpy as np

# FMJD squares 1..50 per pattern. Match C++ PATTERNS exactly.
PATTERNS: list[list[int]] = [
    # Horizontal row-pairs.
    [ 1,  2,  3,  4,  5,  6,  7,  8,  9, 10],   # row_top
    [11, 12, 13, 14, 15, 16, 17, 18, 19, 20],   # row_2
    [21, 22, 23, 24, 25, 26, 27, 28, 29, 30],   # row_mid
    [31, 32, 33, 34, 35, 36, 37, 38, 39, 40],   # row_4
    [41, 42, 43, 44, 45, 46, 47, 48, 49, 50],   # row_bot
    # Vertical columns (sampling 1 sq per row-pair).
    [ 1,  6, 11, 16, 21, 26, 31, 36, 41, 46],   # col_left
    [ 3,  8, 13, 18, 23, 28, 33, 38, 43, 48],   # col_mid
    [ 5, 10, 15, 20, 25, 30, 35, 40, 45, 50],   # col_right
    # Variant B : diagonals + center
    [ 5,  9, 14, 18, 23, 27, 32, 36, 41, 46],   # diag_NE_a
    [ 1,  7, 12, 18, 23, 29, 34, 40, 45, 50],   # diag_SE_a
    [ 2,  8, 13, 19, 24, 30, 35, 41, 46, 49],   # diag_SE_b
    [12, 13, 17, 18, 19, 22, 23, 24, 28, 29],   # center_box
]

PATTERN_NAMES = [
    "row_top", "row_2", "row_mid", "row_4", "row_bot",
    "col_left", "col_mid", "col_right",
    "diag_NE_a", "diag_SE_a", "diag_SE_b", "center_box",
]

NUM_PATTERNS    = len(PATTERNS)   # 8
PATTERN_SIZE    = 10
BUCKETS_PER_PATTERN = 3 ** PATTERN_SIZE          # 59049
TOTAL_BUCKETS   = BUCKETS_PER_PATTERN * NUM_PATTERNS  # 472392

POW3 = np.array([3 ** k for k in range(PATTERN_SIZE + 1)], dtype=np.int64)

# Offsets cumulés (chaque pattern occupe BUCKETS_PER_PATTERN entrées
# consécutives dans le weight array).
PATTERN_OFFSETS = np.arange(NUM_PATTERNS, dtype=np.int64) * BUCKETS_PER_PATTERN


def extract_indices(black_men: np.ndarray, white_men: np.ndarray) -> np.ndarray:
    """Compute per-pattern indices for a batch of positions.

    Args :
        black_men, white_men : uint64 bitboards (N,). Kings are NOT used.
    Returns :
        int64 (N, NUM_PATTERNS) — for sample i pattern j, the bucket
        in the global weight array is PATTERN_OFFSETS[j] + indices[i, j].
    """
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
    """Per-pattern indices → global flat column indices (broadcast offsets)."""
    return indices + PATTERN_OFFSETS[np.newaxis, :]
