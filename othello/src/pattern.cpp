// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern.hpp"

namespace othello {

std::uint32_t extract_index(const Board& b, const Pattern& p) noexcept {
    std::uint32_t idx = 0;
    for (std::uint8_t i = 0; i < p.size; ++i) {
        const Square sq = p.squares[i];
        const Bitboard bit = Bitboard{1} << sq;
        std::uint32_t cell = 0;
        if      (b.black & bit) cell = 1;
        else if (b.white & bit) cell = 2;
        idx += cell * POW3[i];
    }
    return idx;
}

void extract_all(const Board& b,
                 std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept {
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        out[i] = extract_index(b, PATTERNS[i]);
    }
}

void extract_all_flipped(const Board& b,
                         std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept {
    Board flipped = b;
    std::swap(flipped.black, flipped.white);
    flipped.stm = ~flipped.stm;
    extract_all(flipped, out);
}

}  // namespace othello
