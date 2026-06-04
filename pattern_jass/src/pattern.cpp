// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern.hpp"

namespace pattern_jass {

std::uint32_t extract_index(Bitboard black_men, Bitboard white_men,
                            const Pattern& p) noexcept {
    std::uint32_t idx = 0;
    for (std::size_t i = 0; i < PATTERN_SIZE; ++i) {
        const Square sq = p.squares[i];        // FMJD 1..50
        const Bitboard bit = Bitboard{1} << (sq - 1);
        std::uint32_t cell = 0;
        if      (black_men & bit) cell = 1;
        else if (white_men & bit) cell = 2;
        idx += cell * POW3[i];
    }
    return idx;
}

void extract_all(Bitboard black_men, Bitboard white_men,
                 std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept {
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        out[i] = extract_index(black_men, white_men, PATTERNS[i]);
    }
}

}  // namespace pattern_jass
