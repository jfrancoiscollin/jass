// SPDX-License-Identifier: AGPL-3.0-or-later
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

// -----------------------------------------------------------------------------
// Directional neighbour batch shifts.
// -----------------------------------------------------------------------------
// `reach_all_dirs(bb)` returns the bitboard of all squares that are an
// immediate diagonal neighbour (any of 4 directions) of any bit set in `bb`.
//
// O(1) bitboard operations — replaces the iterate-and-set loop that
// otherwise costs ~4 × popcount(bb) ops. Used by the man-capture
// pre-filter and other "is there an enemy nearby ?" queries.
//
// Brick layout : 50 squares numbered 1..50, row-major. Row r contains
// FMJD (5r+1)..(5r+5) at bits (5r)..(5r+4). Even rows (r=0,2,4,6,8)
// have their dark squares at physical columns 1,3,5,7,9 ; odd rows at
// 0,2,4,6,8. Diagonal shifts therefore have different bit deltas per
// row parity :
//   dir   even-row delta   odd-row delta   constraint
//   NW    -5               -6              odd row : c > 0
//   NE    -4               -5              even row : c < 4
//   SW    +5               +4              odd row : c > 0
//   SE    +6               +5              even row : c < 4
inline constexpr Bitboard EVEN_ROW_MASK =
    (0x1FULL <<  0) | (0x1FULL << 10) | (0x1FULL << 20)
  | (0x1FULL << 30) | (0x1FULL << 40);
inline constexpr Bitboard ODD_ROW_MASK = FULL_BB & ~EVEN_ROW_MASK;

// Bits where (bit_idx mod 5) == 0 : column 0 within each row.
inline constexpr Bitboard COL_FIRST_MASK =
    (1ULL <<  0) | (1ULL <<  5) | (1ULL << 10) | (1ULL << 15) | (1ULL << 20)
  | (1ULL << 25) | (1ULL << 30) | (1ULL << 35) | (1ULL << 40) | (1ULL << 45);
inline constexpr Bitboard COL_LAST_MASK  = COL_FIRST_MASK << 4;  // (mod 5) == 4
inline constexpr Bitboard NOT_COL_FIRST  = FULL_BB & ~COL_FIRST_MASK;
inline constexpr Bitboard NOT_COL_LAST   = FULL_BB & ~COL_LAST_MASK;

// Single-step directional shifts (brick layout). `shift_dir(bb)` returns the
// set of squares that are the `dir` neighbour of some bit in `bb`; off-board
// neighbours are masked out. Dir mapping: nw=UpLeft, ne=UpRight, sw=DownLeft,
// se=DownRight. (Same deltas as reach_all_dirs / scan_eval's mobility.)
constexpr Bitboard shift_nw(Bitboard bb) noexcept {
    const Bitboard even = bb & EVEN_ROW_MASK, odd = bb & ODD_ROW_MASK;
    return ((even >> 5) | ((odd & NOT_COL_FIRST) >> 6)) & FULL_BB;
}
constexpr Bitboard shift_ne(Bitboard bb) noexcept {
    const Bitboard even = bb & EVEN_ROW_MASK, odd = bb & ODD_ROW_MASK;
    return (((even & NOT_COL_LAST) >> 4) | (odd >> 5)) & FULL_BB;
}
constexpr Bitboard shift_sw(Bitboard bb) noexcept {
    const Bitboard even = bb & EVEN_ROW_MASK, odd = bb & ODD_ROW_MASK;
    return ((even << 5) | ((odd & NOT_COL_FIRST) << 4)) & FULL_BB;
}
constexpr Bitboard shift_se(Bitboard bb) noexcept {
    const Bitboard even = bb & EVEN_ROW_MASK, odd = bb & ODD_ROW_MASK;
    return (((even & NOT_COL_LAST) << 6) | (odd << 5)) & FULL_BB;
}

constexpr Bitboard reach_all_dirs(Bitboard bb) noexcept {
    const Bitboard even = bb & EVEN_ROW_MASK;
    const Bitboard odd  = bb & ODD_ROW_MASK;
    const Bitboard nw   = (even >> 5)
                        | ((odd & NOT_COL_FIRST) >> 6);
    const Bitboard ne   = ((even & NOT_COL_LAST) >> 4)
                        | (odd >> 5);
    const Bitboard se   = ((even & NOT_COL_LAST) << 6)
                        | (odd << 5);
    const Bitboard sw   = (even << 5)
                        | ((odd & NOT_COL_FIRST) << 4);
    return (nw | ne | se | sw) & FULL_BB;
}

// Promotion rows as bitboards (bit i = FMJD square i+1). White promotes on the
// top row (FMJD 1..5 = bits 0..4) ; Black on the bottom row (FMJD 46..50 = bits
// 45..49). Lets the quiet man generator decide `promotes` by masking the whole
// destination set once instead of calling is_promotion_square() per move.
inline constexpr Bitboard WHITE_PROMO_BB = 0x1FULL;          // bits 0..4
inline constexpr Bitboard BLACK_PROMO_BB = 0x1FULL << 45;    // bits 45..49

}  // namespace jass
