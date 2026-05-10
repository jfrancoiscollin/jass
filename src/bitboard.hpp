// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// 50-bit Bitboard type for the 50 playable squares of the 10×10 draughts
// board. Bit `i` of the underlying `uint64_t` corresponds to FMJD square
// `i + 1` (so bits 0..49 are the playable squares; bits 50..63 are unused).

#pragma once

#include "types.hpp"

#include <bit>
#include <cstdint>

namespace jass {

using Bitboard = std::uint64_t;

inline constexpr Bitboard EMPTY_BB    = 0ULL;
inline constexpr Bitboard FULL_BB     = (1ULL << NUM_SQUARES) - 1ULL;
inline constexpr Bitboard PLAYABLE_BB = FULL_BB;

constexpr Bitboard square_bb(Square s) noexcept {
    return 1ULL << square_to_bit(s);
}

constexpr bool test(Bitboard b, Square s) noexcept {
    return (b & square_bb(s)) != 0;
}

constexpr void set(Bitboard& b, Square s) noexcept {
    b |= square_bb(s);
}

constexpr void clear(Bitboard& b, Square s) noexcept {
    b &= ~square_bb(s);
}

constexpr void toggle(Bitboard& b, Square s) noexcept {
    b ^= square_bb(s);
}

constexpr int popcount(Bitboard b) noexcept {
    return std::popcount(b);
}

// Returns the FMJD square number of the lowest set bit (1..50) and clears it
// in `b`. Calling on an empty bitboard is undefined behaviour.
constexpr Square pop_lsb(Bitboard& b) noexcept {
    const int bit = std::countr_zero(b);
    b &= b - 1;
    return bit_to_square(bit);
}

constexpr Square lsb(Bitboard b) noexcept {
    return bit_to_square(std::countr_zero(b));
}

}  // namespace jass
