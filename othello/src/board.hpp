// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Othello board representation for Phase Pattern-1 POC.
//
// Pure bitboard 8×8 : 64 squares numbered row-major 0-63.
// Square 0 = top-left (a8 in algebraic notation if we wanted it),
// square 63 = bottom-right.
//
// State :
//   * `black` : bitmap of squares with a black piece
//   * `white` : bitmap of squares with a white piece
//   * black & white == 0  (no square can hold both)
//   * `stm`   : side to move (Black or White)
//   * `passes` : consecutive passes (game ends at 2)
//
// Standard Othello starting position : 4 pieces in center.
//   d4 = white, e4 = black, d5 = black, e5 = white
//   Square indices : 27, 28, 35, 36 (row-major 0-based)

#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

namespace othello {

using Square   = std::uint8_t;     // 0..63
using Bitboard = std::uint64_t;

enum class Color : std::uint8_t {
    Black = 0,
    White = 1,
};

inline Color operator~(Color c) noexcept {
    return c == Color::Black ? Color::White : Color::Black;
}

constexpr Square NO_SQUARE = 64;   // sentinel
constexpr int    BOARD_SIZE = 64;

struct Board {
    Bitboard black{0};
    Bitboard white{0};
    Color    stm{Color::Black};
    std::uint8_t passes{0};         // ≥ 2 → game over

    // Default constructor is empty board (used for tests). Use
    // `start_position()` for a real game.
    Board() = default;

    static Board start_position() noexcept {
        Board b;
        b.white = (Bitboard{1} << 27) | (Bitboard{1} << 36);  // d4, e5
        b.black = (Bitboard{1} << 28) | (Bitboard{1} << 35);  // e4, d5
        b.stm = Color::Black;  // Black moves first in Othello
        return b;
    }

    // Bitmap of squares with any piece.
    constexpr Bitboard occupied() const noexcept {
        return black | white;
    }

    // Pieces of the side to move.
    constexpr Bitboard own_pieces() const noexcept {
        return stm == Color::Black ? black : white;
    }

    constexpr Bitboard opp_pieces() const noexcept {
        return stm == Color::Black ? white : black;
    }

    // Piece count (used for terminal eval and feature extraction).
    int black_count() const noexcept;
    int white_count() const noexcept;

    // Game over: both players passed in a row, OR board is full.
    constexpr bool is_game_over() const noexcept {
        return passes >= 2 || occupied() == ~Bitboard{0};
    }

    // ASCII rendering for debug / tests. 8 rows × 8 cols, '.', 'X' (black),
    // 'O' (white). Returns multi-line string ending in '\n'.
    std::string to_ascii() const;

    // FEN-like roundtrip. Format : "stm:black-squares:white-squares" with
    // squares as comma-separated 0-based indices.
    // E.g. start position = "B:28,35:27,36".
    std::string to_string() const;
    static std::optional<Board> from_string(std::string_view s);

    // Equality (used by tests).
    constexpr bool operator==(const Board& o) const noexcept {
        return black == o.black && white == o.white
            && stm == o.stm && passes == o.passes;
    }
};

// Square <-> (row, col) helpers. row 0 = top, col 0 = left.
constexpr int  sq_row(Square s) noexcept { return s / 8; }
constexpr int  sq_col(Square s) noexcept { return s % 8; }
constexpr Square make_square(int row, int col) noexcept {
    return static_cast<Square>(row * 8 + col);
}

}  // namespace othello
