// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Phase Pattern-2 Variant C — pattern eval avec encoding 5-state
// (empty/black_man/black_king/white_man/white_king).
//
// 8 patterns × 8 squares × 5^8 = 390 625 buckets / pattern = 3.125M
// buckets total. ~12 MB weight file. Kings INCLUS dans l'eval.
//
// Conventions :
//   * Cell encoding : 0 empty, 1 black_man, 2 black_king,
//                     3 white_man, 4 white_king
//   * Index : sum(cell[squares[i]] * 5^i) for i in [0, size).

#pragma once

#include <array>
#include <cstdint>
#include <string_view>

namespace pattern_jass_kings {

using Bitboard = std::uint64_t;
using Square   = std::uint8_t;   // FMJD 1..50

constexpr std::size_t PATTERN_SIZE  = 8;
constexpr std::size_t NUM_PATTERNS  = 8;

struct Pattern {
    std::array<Square, PATTERN_SIZE> squares;
    std::string_view name;
};

constexpr std::array<std::uint32_t, PATTERN_SIZE + 1> POW5 = {
    1, 5, 25, 125, 625, 3125, 15625, 78125, 390625,
};

constexpr std::uint32_t BUCKETS_PER_PATTERN = POW5[PATTERN_SIZE];   // 390625
constexpr std::uint32_t TOTAL_BUCKETS = BUCKETS_PER_PATTERN * NUM_PATTERNS;  // 3125000

// 8 patterns of 8 squares each. Mix : 4 row-segments (skip first 2 sq)
// + 4 column-segments (skip first 2 row-pairs).
inline constexpr std::array<Pattern, NUM_PATTERNS> PATTERNS = {{
    // Row segments (skip first 2 squares to keep size 8).
    {{ 1,  2,  3,  4,  5,  6,  7,  8}, "row_top_8"},
    {{11, 12, 13, 14, 15, 16, 17, 18}, "row_2_8"},
    {{21, 22, 23, 24, 25, 26, 27, 28}, "row_mid_8"},
    {{31, 32, 33, 34, 35, 36, 37, 38}, "row_4_8"},
    // Column segments (8 row-pairs worth).
    {{ 1,  6, 11, 16, 21, 26, 31, 36}, "col_left_8"},
    {{ 3,  8, 13, 18, 23, 28, 33, 38}, "col_mid_8"},
    {{ 5, 10, 15, 20, 25, 30, 35, 40}, "col_right_8"},
    {{ 2,  9, 12, 19, 22, 29, 32, 39}, "col_offset_8"},
}};

constexpr std::array<std::uint32_t, NUM_PATTERNS> pattern_offsets() noexcept {
    std::array<std::uint32_t, NUM_PATTERNS> out{};
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        out[i] = static_cast<std::uint32_t>(i * BUCKETS_PER_PATTERN);
    }
    return out;
}

// Compute the base-5 index for one pattern.
//   bm = black men   bb = black kings
//   wm = white men   wk = white kings
std::uint32_t extract_index(Bitboard bm, Bitboard bk,
                            Bitboard wm, Bitboard wk,
                            const Pattern& p) noexcept;

void extract_all(Bitboard bm, Bitboard bk,
                 Bitboard wm, Bitboard wk,
                 std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept;

}  // namespace pattern_jass_kings
