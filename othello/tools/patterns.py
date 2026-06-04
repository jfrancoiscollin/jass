# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 Jean-François Collin
#
# Pattern definitions mirroring othello/src/pattern.hpp. Kept in sync
# manually for now (10 patterns, base-3 encoding, 39690 buckets total).

import numpy as np

# Each entry : list of board square indices (row-major 0..63).
PATTERNS: list[list[int]] = [
    # Corners 2×2 (4 squares, 81 buckets each)
    [ 0,  1,  8,  9],            # corner_NW
    [ 6,  7, 14, 15],            # corner_NE
    [48, 49, 56, 57],            # corner_SW
    [54, 55, 62, 63],            # corner_SE
    # Edges 1×8 (8 squares, 6561 buckets each)
    [ 0,  1,  2,  3,  4,  5,  6,  7],   # edge_top
    [56, 57, 58, 59, 60, 61, 62, 63],   # edge_bot
    [ 0,  8, 16, 24, 32, 40, 48, 56],   # edge_left
    [ 7, 15, 23, 31, 39, 47, 55, 63],   # edge_right
    # Diagonals
    [ 0,  9, 18, 27, 36, 45, 54, 63],   # diag_main
    [ 7, 14, 21, 28, 35, 42, 49, 56],   # diag_anti
]

PATTERN_NAMES = [
    "corner_NW", "corner_NE", "corner_SW", "corner_SE",
    "edge_top",  "edge_bot",  "edge_left", "edge_right",
    "diag_main", "diag_anti",
]

NUM_PATTERNS = len(PATTERNS)

# 3^size buckets per pattern.
PATTERN_BUCKETS = [3 ** len(p) for p in PATTERNS]
TOTAL_BUCKETS = sum(PATTERN_BUCKETS)

# Pow-3 lookups (per-position multipliers within a pattern).
POW3 = np.array([3 ** k for k in range(9)], dtype=np.int64)

# Cumulative offset of each pattern inside the flat weight array.
PATTERN_OFFSETS = np.cumsum([0] + PATTERN_BUCKETS[:-1], dtype=np.int64)


def extract_indices(black: np.ndarray, white: np.ndarray) -> np.ndarray:
    """Compute pattern indices for a batch of positions.

    Args:
        black, white : uint64 bitboards (N,)
    Returns:
        indices : int64 (N, NUM_PATTERNS) — for sample i pattern j,
                  flat-offset bucket = PATTERN_OFFSETS[j] + indices[i, j].
    """
    n = len(black)
    out = np.zeros((n, NUM_PATTERNS), dtype=np.int64)
    # For each pattern, compute the index as sum(cell[sq[k]] * 3^k).
    for pi, sqs in enumerate(PATTERNS):
        idx = np.zeros(n, dtype=np.int64)
        for k, sq in enumerate(sqs):
            bit = np.uint64(1) << np.uint64(sq)
            is_black = ((black & bit) != 0).astype(np.int64)
            is_white = ((white & bit) != 0).astype(np.int64)
            # cell value : 0 empty, 1 black, 2 white
            cell = is_black * 1 + is_white * 2
            idx += cell * int(POW3[k])
        out[:, pi] = idx
    return out


def flat_feature_columns(indices: np.ndarray) -> np.ndarray:
    """Convert per-pattern indices to flat column indices into the
    global weight array.

    Args:
        indices : int64 (N, NUM_PATTERNS) from extract_indices.
    Returns:
        cols : int64 (N, NUM_PATTERNS) — global column index per sample.
    """
    return indices + PATTERN_OFFSETS[np.newaxis, :]
