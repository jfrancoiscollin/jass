// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Pattern feature extraction for jass (50-square draughts).
//
// v3 (Option D — Scan-style geometry) : 8 patterns × 12 squares,
// ternary encoding. Inspired by Scan's column-shift × top/bottom-half
// approach (cf docs/SCAN_ARCHITECTURE_NOTES.md §3) but with from-scratch
// FMJD-layout-aware geometry (no bit-magic reuse).
//
// Each pattern is a 2-column × 6-row "vertical band" covering 12 squares.
// 4 bands × 2 halves (top: rows 0-5, bottom: rows 4-9) = 8 patterns,
// with the middle rows (4-5) shared across halves for redundancy.
//
// Conventions :
//   * Bit `i` of the uint64 bitboard = FMJD square (i+1)
//   * Cell encoding : 0 = empty, 1 = black_man, 2 = white_man
//   * Kings are NOT in patterns (matches Scan §3)
//   * Index : sum(cell[squares[i]] * 3^i) for i in [0, size)

#pragma once

#include <array>
#include <cstdint>
#include <string_view>

namespace pattern_jass {

using Bitboard = std::uint64_t;
using Square   = std::uint8_t;   // FMJD 1..50

constexpr std::size_t PATTERN_SIZE  = 12;
constexpr std::size_t NUM_PATTERNS  = 8;

struct Pattern {
    std::array<Square, PATTERN_SIZE> squares;
    std::string_view name;
};

constexpr std::array<std::uint32_t, PATTERN_SIZE + 1> POW3 = {
    1, 3, 9, 27, 81, 243, 729, 2187, 6561, 19683, 59049, 177147, 531441,
};

constexpr std::uint32_t BUCKETS_PER_PATTERN = POW3[PATTERN_SIZE];  // 531 441
constexpr std::uint32_t TOTAL_BUCKETS       = BUCKETS_PER_PATTERN * NUM_PATTERNS;
                                                                   // 4 251 528

// 8 patterns of 12 squares. "Vertical bands" 2 cols × 6 rows, taken
// in top half (rows 0-5) and bottom half (rows 4-9). The two halves
// overlap on rows 4-5 so middle-board patterns get learned twice.
inline constexpr std::array<Pattern, NUM_PATTERNS> PATTERNS = {{
    // Top half, 4 vertical bands of width-2 columns × 6 rows.
    {{ 1,  2,  6,  7, 11, 12, 16, 17, 21, 22, 26, 27}, "top_band_0"},
    {{ 2,  3,  7,  8, 12, 13, 17, 18, 22, 23, 27, 28}, "top_band_1"},
    {{ 3,  4,  8,  9, 13, 14, 18, 19, 23, 24, 28, 29}, "top_band_2"},
    {{ 4,  5,  9, 10, 14, 15, 19, 20, 24, 25, 29, 30}, "top_band_3"},
    // Bottom half, same 4 bands shifted to rows 4-9.
    {{21, 22, 26, 27, 31, 32, 36, 37, 41, 42, 46, 47}, "bot_band_0"},
    {{22, 23, 27, 28, 32, 33, 37, 38, 42, 43, 47, 48}, "bot_band_1"},
    {{23, 24, 28, 29, 33, 34, 38, 39, 43, 44, 48, 49}, "bot_band_2"},
    {{24, 25, 29, 30, 34, 35, 39, 40, 44, 45, 49, 50}, "bot_band_3"},
}};

constexpr std::array<std::uint32_t, NUM_PATTERNS> pattern_offsets() noexcept {
    std::array<std::uint32_t, NUM_PATTERNS> out{};
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        out[i] = static_cast<std::uint32_t>(i * BUCKETS_PER_PATTERN);
    }
    return out;
}

std::uint32_t extract_index(Bitboard black_men, Bitboard white_men,
                            const Pattern& p) noexcept;

void extract_all(Bitboard black_men, Bitboard white_men,
                 std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept;

}  // namespace pattern_jass
