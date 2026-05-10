// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Core scalar types of the Jass engine: colours, pieces, squares and moves.

#pragma once

#include <array>
#include <cstdint>

namespace jass {

// -----------------------------------------------------------------------------
// Colour
// -----------------------------------------------------------------------------
enum class Color : std::uint8_t {
    White = 0,
    Black = 1,
};

constexpr Color opposite(Color c) noexcept {
    return (c == Color::White) ? Color::Black : Color::White;
}

constexpr int color_index(Color c) noexcept {
    return static_cast<int>(c);
}

// -----------------------------------------------------------------------------
// Piece
// -----------------------------------------------------------------------------
// `None` is reserved for "no piece on this square" in 8-bit board arrays.
enum class Piece : std::uint8_t {
    None      = 0,
    WhiteMan  = 1,
    BlackMan  = 2,
    WhiteKing = 3,
    BlackKing = 4,
};

constexpr bool is_white(Piece p) noexcept {
    return p == Piece::WhiteMan || p == Piece::WhiteKing;
}
constexpr bool is_black(Piece p) noexcept {
    return p == Piece::BlackMan || p == Piece::BlackKing;
}
constexpr bool is_king(Piece p) noexcept {
    return p == Piece::WhiteKing || p == Piece::BlackKing;
}
constexpr bool is_man(Piece p) noexcept {
    return p == Piece::WhiteMan || p == Piece::BlackMan;
}
constexpr Color color_of(Piece p) noexcept {
    // Caller's responsibility not to pass `None`.
    return is_white(p) ? Color::White : Color::Black;
}

// -----------------------------------------------------------------------------
// Square — FMJD numbering (1..50). 0 is reserved as a "no square" sentinel.
// -----------------------------------------------------------------------------
using Square = std::uint8_t;

inline constexpr Square NO_SQUARE       = 0;
inline constexpr Square FIRST_SQUARE    = 1;
inline constexpr Square LAST_SQUARE     = 50;
inline constexpr int    NUM_SQUARES     = 50;
inline constexpr int    BOARD_SIDE      = 10;

constexpr bool square_is_valid(Square s) noexcept {
    return s >= FIRST_SQUARE && s <= LAST_SQUARE;
}

// Convert FMJD square (1..50) to a 0-based bitboard bit index (0..49).
constexpr int square_to_bit(Square s) noexcept {
    return static_cast<int>(s) - 1;
}
constexpr Square bit_to_square(int b) noexcept {
    return static_cast<Square>(b + 1);
}

// -----------------------------------------------------------------------------
// Move
// -----------------------------------------------------------------------------
// In international draughts a single move can chain many captures. The FMJD
// theoretical maximum for a king move is 19 captures; we round up to 20 for
// safety. `captures` lists the *captured* squares (in capture order) — useful
// to remove pieces lazily during make/unmake. `path` lists the squares the
// moving piece traverses (excluding the start square). For a quiet move,
// `path = { to }` and `num_captures = 0`.
struct Move {
    Square                  from{NO_SQUARE};
    Square                  to{NO_SQUARE};
    std::uint8_t            num_captures{0};
    bool                    promotes{false};
    std::array<Square, 20>  captures{};

    constexpr bool is_capture() const noexcept { return num_captures > 0; }
    constexpr bool is_quiet()   const noexcept { return num_captures == 0; }

    friend constexpr bool operator==(const Move& a, const Move& b) noexcept {
        if (a.from != b.from || a.to != b.to ||
            a.num_captures != b.num_captures || a.promotes != b.promotes) {
            return false;
        }
        for (std::uint8_t i = 0; i < a.num_captures; ++i) {
            if (a.captures[i] != b.captures[i]) return false;
        }
        return true;
    }
};

}  // namespace jass
