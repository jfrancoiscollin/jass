// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern.hpp"

namespace pattern_jass_kings {

std::uint32_t extract_index(Bitboard bm, Bitboard bk,
                            Bitboard wm, Bitboard wk,
                            const Pattern& p) noexcept {
    std::uint32_t idx = 0;
    for (std::size_t i = 0; i < PATTERN_SIZE; ++i) {
        const Square sq = p.squares[i];
        const Bitboard bit = Bitboard{1} << (sq - 1);
        std::uint32_t cell = 0;
        if      (bm & bit) cell = 1;
        else if (bk & bit) cell = 2;
        else if (wm & bit) cell = 3;
        else if (wk & bit) cell = 4;
        idx += cell * POW5[i];
    }
    return idx;
}

void extract_all(Bitboard bm, Bitboard bk,
                 Bitboard wm, Bitboard wk,
                 std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept {
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        out[i] = extract_index(bm, bk, wm, wk, PATTERNS[i]);
    }
}

}  // namespace pattern_jass_kings
