// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Logistello-style pattern feature extraction for Othello.
//
// Conventions :
//   * Cell encoding : empty=0, black=1, white=2 (color-based, not
//     STM-POV). Color swap on the eval is handled at the eval layer
//     by remapping 1<->2 in the index.
//   * Index : sum(cell[squares[i]] * 3^i) for i in [0, size)
//   * num_buckets = 3^size — the number of distinct index values
//   * Patterns are canonical ; symmetry classes are NOT collapsed in
//     this POC (we just train weights per orientation). Future work :
//     dedup via equivalence classes (saves ~8× weight memory).
//
// 10 patterns total (~40K buckets) :
//   * 4 corners 2×2 :  4 × 81    =  324 buckets
//   * 4 edges   1×8 :  4 × 6561  = 26244 buckets
//   * 2 diagonals 8 : 2 × 6561  = 13122 buckets
//                                 ------
//                                  39690 buckets

#pragma once

#include "board.hpp"

#include <array>
#include <cstdint>
#include <string_view>

namespace othello {

constexpr std::size_t MAX_PATTERN_SIZE = 8;
constexpr std::size_t NUM_PATTERNS     = 10;

struct Pattern {
    std::array<Square, MAX_PATTERN_SIZE> squares;
    std::uint8_t   size;
    std::uint32_t  num_buckets;
    std::string_view name;
};

// Pre-computed 3^k for k in [0, MAX_PATTERN_SIZE].
constexpr std::array<std::uint32_t, MAX_PATTERN_SIZE + 1> POW3 = {
    1, 3, 9, 27, 81, 243, 729, 2187, 6561,
};

// All 10 canonical patterns. Squares are row-major (0 = a8, 63 = h1
// per board.hpp conventions). Padding entries past `size` are 0.
inline constexpr std::array<Pattern, NUM_PATTERNS> PATTERNS = {{
    // Corners 2×2 — 4 squares each, 81 buckets each.
    {{ 0,  1,  8,  9,  0,  0,  0,  0}, 4,   81, "corner_NW"},
    {{ 6,  7, 14, 15,  0,  0,  0,  0}, 4,   81, "corner_NE"},
    {{48, 49, 56, 57,  0,  0,  0,  0}, 4,   81, "corner_SW"},
    {{54, 55, 62, 63,  0,  0,  0,  0}, 4,   81, "corner_SE"},
    // Edges 1×8 — 8 squares each, 6561 buckets each.
    {{ 0,  1,  2,  3,  4,  5,  6,  7}, 8, 6561, "edge_top"},
    {{56, 57, 58, 59, 60, 61, 62, 63}, 8, 6561, "edge_bot"},
    {{ 0,  8, 16, 24, 32, 40, 48, 56}, 8, 6561, "edge_left"},
    {{ 7, 15, 23, 31, 39, 47, 55, 63}, 8, 6561, "edge_right"},
    // Main diagonals — 8 squares each, 6561 buckets each.
    {{ 0,  9, 18, 27, 36, 45, 54, 63}, 8, 6561, "diag_main"},
    {{ 7, 14, 21, 28, 35, 42, 49, 56}, 8, 6561, "diag_anti"},
}};

// Total number of feature buckets across all patterns. Used to size
// the weight vector for the linear eval.
constexpr std::size_t total_pattern_buckets() noexcept {
    std::size_t total = 0;
    for (const auto& p : PATTERNS) total += p.num_buckets;
    return total;
}

// Offset of pattern `i`'s buckets inside a flat weight array.
constexpr std::array<std::uint32_t, NUM_PATTERNS> pattern_offsets() noexcept {
    std::array<std::uint32_t, NUM_PATTERNS> out{};
    std::uint32_t acc = 0;
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        out[i] = acc;
        acc += PATTERNS[i].num_buckets;
    }
    return out;
}

// Compute the base-3 index of a single pattern given the board state.
// Cell value : 0 = empty, 1 = black, 2 = white.
std::uint32_t extract_index(const Board& b, const Pattern& p) noexcept;

// Compute indices for all PATTERNS at once. `out[i]` ∈ [0, PATTERNS[i].num_buckets).
void extract_all(const Board& b, std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept;

// Optional helper : same indices but with colors flipped (black<->white).
// Equivalent to extract_all on a board where black/white are swapped.
// Used by the eval layer to obtain "opponent-POV" indices without
// physically swapping the board.
void extract_all_flipped(const Board& b, std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept;

}  // namespace othello
