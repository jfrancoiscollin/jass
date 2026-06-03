// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Othello move generation. A move = placing a piece on an empty square
// such that at least one bracketed enemy line gets flipped.
//
// 8 directions of bracketing : N, NE, E, SE, S, SW, W, NW. For each
// direction, we walk from the candidate square through enemy pieces
// until we hit an own piece (bracket closed → flip) or an empty/edge
// (bracket failed → no flip in this direction).
//
// Edge handling : mask out wrap-around. Files A (col 0) and H (col 7)
// need anti-wrap masks for E/W shifts ; row 0 and row 7 are handled by
// the shift itself going past edge.

#pragma once

#include "board.hpp"

#include <array>

namespace othello {

// Up to 60 legal moves in extreme positions (empty squares - 4 starting).
// 64 = safe upper bound + nice cache alignment.
constexpr std::size_t MAX_LEGAL_MOVES = 64;

struct MoveList {
    std::array<Square, MAX_LEGAL_MOVES> data{};
    std::size_t count{0};

    void clear() noexcept                       { count = 0; }
    void push(Square s) noexcept                { data[count++] = s; }
    std::size_t size() const noexcept           { return count; }
    bool empty() const noexcept                 { return count == 0; }
    Square operator[](std::size_t i) const noexcept { return data[i]; }
    Square* begin() noexcept                    { return data.data(); }
    Square* end()   noexcept                    { return data.data() + count; }
    const Square* begin() const noexcept        { return data.data(); }
    const Square* end()   const noexcept        { return data.data() + count; }
};

// Generate all legal moves for the side to move into `out`. If empty,
// the player must pass. After the function returns, `out.size()` is
// the number of legal squares.
void generate_legal_moves(const Board& b, MoveList& out) noexcept;

// Compute the bitboard of squares that would flip if `sq` is played.
// Empty bitboard means the move is illegal. Used both by movegen
// (legality check) and by apply_move (actual flipping).
Bitboard flips_for_move(const Board& b, Square sq) noexcept;

// Apply a legal move. Updates `b` in place : place own piece on `sq`,
// flip all bracketed enemy pieces, increment piece counts, switch stm,
// reset pass counter (or if move == pass, increment).
//
// Pass : pass by playing NO_SQUARE (or any illegal square). Increments
// pass counter without changing board.
//
// Returns true on success, false if the move was illegal AND
// not-a-pass (shouldn't happen if caller checks legality first).
bool apply_move(Board& b, Square sq) noexcept;

}  // namespace othello
