// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Pattern feature extraction for jass (50-square draughts).
//
// 8 patterns, 10 squares each, ternary encoding. Cf README §"Géométrie
// pattern v1" for the per-pattern square layout.
//
// Conventions :
//   * Bit `i` of the uint64 bitboard = FMJD square (i+1). Match
//     src/bitboard.hpp:5 in the jass core.
//   * Cell encoding : 0 = empty, 1 = black_man, 2 = white_man.
//   * Kings are NOT in patterns (cf Scan §3 ; v1 design).
//   * Index : sum(cell[squares[i]] * 3^i) for i in [0, size).

#pragma once

#include <array>
#include <cstdint>
#include <string_view>

namespace pattern_jass {

using Bitboard = std::uint64_t;
using Square   = std::uint8_t;   // FMJD 1..50

constexpr std::size_t PATTERN_SIZE  = 10;
constexpr std::size_t NUM_PATTERNS  = 12;   // v2 (Variant B) : +4 diagonal/center patterns

struct Pattern {
    std::array<Square, PATTERN_SIZE> squares;  // FMJD square numbers, 1..50
    std::string_view name;
};

constexpr std::array<std::uint32_t, PATTERN_SIZE + 1> POW3 = {
    1, 3, 9, 27, 81, 243, 729, 2187, 6561, 19683, 59049,
};

constexpr std::uint32_t BUCKETS_PER_PATTERN = POW3[PATTERN_SIZE];  // 59049
constexpr std::uint32_t TOTAL_BUCKETS = BUCKETS_PER_PATTERN * NUM_PATTERNS;  // 472392

// FMJD square layout for the 8 patterns. Squares are stored 1-based
// (FMJD convention). The extractor converts to bit positions (sq - 1).
inline constexpr std::array<Pattern, NUM_PATTERNS> PATTERNS = {{
    // Horizontal row-pairs.
    {{ 1,  2,  3,  4,  5,  6,  7,  8,  9, 10}, "row_top"},
    {{11, 12, 13, 14, 15, 16, 17, 18, 19, 20}, "row_2"},
    {{21, 22, 23, 24, 25, 26, 27, 28, 29, 30}, "row_mid"},
    {{31, 32, 33, 34, 35, 36, 37, 38, 39, 40}, "row_4"},
    {{41, 42, 43, 44, 45, 46, 47, 48, 49, 50}, "row_bot"},
    // Vertical "columns" (one per row-pair, sampling 1 sq per row).
    {{ 1,  6, 11, 16, 21, 26, 31, 36, 41, 46}, "col_left"},
    {{ 3,  8, 13, 18, 23, 28, 33, 38, 43, 48}, "col_mid"},
    {{ 5, 10, 15, 20, 25, 30, 35, 40, 45, 50}, "col_right"},
    // Variant B additions : diagonal-flavoured + central regions to
    // diversify the geometric correlations beyond rows/cols.
    {{ 5,  9, 14, 18, 23, 27, 32, 36, 41, 46}, "diag_NE_a"},
    {{ 1,  7, 12, 18, 23, 29, 34, 40, 45, 50}, "diag_SE_a"},
    {{ 2,  8, 13, 19, 24, 30, 35, 41, 46, 49}, "diag_SE_b"},
    {{12, 13, 17, 18, 19, 22, 23, 24, 28, 29}, "center_box"},
}};

// Offset of pattern `i`'s buckets inside the flat weight array.
constexpr std::array<std::uint32_t, NUM_PATTERNS> pattern_offsets() noexcept {
    std::array<std::uint32_t, NUM_PATTERNS> out{};
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        out[i] = static_cast<std::uint32_t>(i * BUCKETS_PER_PATTERN);
    }
    return out;
}

// Compute the base-3 index of a single pattern.
// Inputs : `black_men`, `white_men` bitboards (kings NOT included).
std::uint32_t extract_index(Bitboard black_men, Bitboard white_men,
                            const Pattern& p) noexcept;

// Compute indices for all 8 patterns.
void extract_all(Bitboard black_men, Bitboard white_men,
                 std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept;

}  // namespace pattern_jass
