// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// 10×10 board geometry: FMJD square numbering, row/column conversion and
// precomputed diagonal-neighbour tables.

#pragma once

#include "types.hpp"

#include <array>

namespace jass {

// Diagonal directions, encoded so that bit 0 = "going down" (row increasing,
// i.e. toward Black's home rank) and bit 1 = "going right" (file increasing).
enum class Dir : std::uint8_t {
    UpLeft    = 0,  //  row-1, col-1
    UpRight   = 1,  //  row-1, col+1
    DownLeft  = 2,  //  row+1, col-1
    DownRight = 3,  //  row+1, col+1
};

inline constexpr int NUM_DIRS = 4;

// All four directions, in a deterministic order (NW, NE, SW, SE).
inline constexpr std::array<Dir, NUM_DIRS> ALL_DIRS = {
    Dir::UpLeft, Dir::UpRight, Dir::DownLeft, Dir::DownRight};

// Forward directions for men of a given colour.
// Whites move "up" (toward row 0); blacks move "down" (toward row 9).
inline constexpr std::array<Dir, 2> man_forward_dirs(Color c) noexcept {
    return (c == Color::White)
        ? std::array<Dir, 2>{Dir::UpLeft, Dir::UpRight}
        : std::array<Dir, 2>{Dir::DownLeft, Dir::DownRight};
}

// -----------------------------------------------------------------------------
// Row / column helpers — operate on FMJD squares 1..50.
// -----------------------------------------------------------------------------
constexpr int row_of(Square s) noexcept {
    // 0 = top row (Black's home), 9 = bottom row (White's home).
    return (static_cast<int>(s) - 1) / 5;
}

constexpr int col_of(Square s) noexcept {
    // 0 = leftmost file, 9 = rightmost file.
    const int r = row_of(s);
    const int c = (static_cast<int>(s) - 1) % 5;
    // Even rows (0,2,4,6,8) host dark squares at odd columns 1,3,5,7,9.
    // Odd rows host them at even columns 0,2,4,6,8.
    return (r % 2 == 0) ? (2 * c + 1) : (2 * c);
}

constexpr bool is_white_promotion_row(int row) noexcept { return row == 0; }
constexpr bool is_black_promotion_row(int row) noexcept { return row == 9; }

constexpr bool is_promotion_square(Square s, Color mover) noexcept {
    const int r = row_of(s);
    return (mover == Color::White) ? is_white_promotion_row(r)
                                   : is_black_promotion_row(r);
}

// -----------------------------------------------------------------------------
// Diagonal-neighbour table.
// -----------------------------------------------------------------------------
// `neighbour(s, d)` returns the immediate diagonal neighbour of `s` in
// direction `d`, or `NO_SQUARE` if `s` is on the board edge in that direction.
// Indexed by FMJD square 1..50 (slot 0 is filled with NO_SQUARE).
struct NeighbourTable {
    std::array<std::array<Square, NUM_DIRS>, NUM_SQUARES + 1> data{};
};

const NeighbourTable& neighbours();

inline Square neighbour(Square s, Dir d) noexcept {
    return neighbours().data[s][static_cast<std::size_t>(d)];
}

// Walk `n` steps from `s` in direction `d`, returning NO_SQUARE if the ray
// leaves the board. Useful for king moves and capture rays.
Square ray_step(Square s, Dir d, int n) noexcept;

}  // namespace jass
