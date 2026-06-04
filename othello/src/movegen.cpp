// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "movegen.hpp"

namespace othello {

namespace {

// File masks to prevent horizontal wrap-around on shifts.
constexpr Bitboard FILE_A = 0x0101010101010101ULL;  // col 0
constexpr Bitboard FILE_H = 0x8080808080808080ULL;  // col 7
constexpr Bitboard NOT_FILE_A = ~FILE_A;
constexpr Bitboard NOT_FILE_H = ~FILE_H;

// 8 direction shifts. row-major sq = row*8 + col, row 0 = top.
// North = decreasing row = bb >> 8. South = increasing row = bb << 8.
inline Bitboard shift_n (Bitboard bb) noexcept { return  bb >> 8; }
inline Bitboard shift_s (Bitboard bb) noexcept { return  bb << 8; }
inline Bitboard shift_e (Bitboard bb) noexcept { return (bb & NOT_FILE_H) << 1; }
inline Bitboard shift_w (Bitboard bb) noexcept { return (bb & NOT_FILE_A) >> 1; }
inline Bitboard shift_ne(Bitboard bb) noexcept { return (bb & NOT_FILE_H) >> 7; }
inline Bitboard shift_nw(Bitboard bb) noexcept { return (bb & NOT_FILE_A) >> 9; }
inline Bitboard shift_se(Bitboard bb) noexcept { return (bb & NOT_FILE_H) << 9; }
inline Bitboard shift_sw(Bitboard bb) noexcept { return (bb & NOT_FILE_A) << 7; }

// Compute legal-target squares in one direction. Walk from own pieces
// through opp pieces ; final shift onto empty = legal move.
template <typename Shift>
inline Bitboard legal_dir(Bitboard own, Bitboard opp,
                          Bitboard empty, Shift shift) noexcept {
    Bitboard x = shift(own) & opp;
    x |= shift(x) & opp;
    x |= shift(x) & opp;
    x |= shift(x) & opp;
    x |= shift(x) & opp;
    x |= shift(x) & opp;  // up to 6 consecutive opp between two own
    return shift(x) & empty;
}

// Compute the flips a play at `from` would cause in one direction,
// walking through opp until we hit an own piece (bracket closes).
template <typename Shift>
inline Bitboard flips_dir(Bitboard from, Bitboard own,
                          Bitboard opp, Shift shift) noexcept {
    Bitboard line = 0;
    Bitboard cur  = shift(from);
    while (cur & opp) {
        line |= cur;
        cur = shift(cur);
    }
    return (cur & own) ? line : Bitboard{0};
}

}  // namespace

Bitboard flips_for_move(const Board& b, Square sq) noexcept {
    if (sq >= BOARD_SIZE) return 0;
    const Bitboard from = Bitboard{1} << sq;
    if (b.occupied() & from) return 0;

    const Bitboard own = b.own_pieces();
    const Bitboard opp = b.opp_pieces();
    Bitboard flips = 0;
    flips |= flips_dir(from, own, opp, shift_n);
    flips |= flips_dir(from, own, opp, shift_s);
    flips |= flips_dir(from, own, opp, shift_e);
    flips |= flips_dir(from, own, opp, shift_w);
    flips |= flips_dir(from, own, opp, shift_ne);
    flips |= flips_dir(from, own, opp, shift_nw);
    flips |= flips_dir(from, own, opp, shift_se);
    flips |= flips_dir(from, own, opp, shift_sw);
    return flips;
}

void generate_legal_moves(const Board& b, MoveList& out) noexcept {
    out.clear();
    const Bitboard own   = b.own_pieces();
    const Bitboard opp   = b.opp_pieces();
    const Bitboard empty = ~(own | opp);

    Bitboard moves = 0;
    moves |= legal_dir(own, opp, empty, shift_n);
    moves |= legal_dir(own, opp, empty, shift_s);
    moves |= legal_dir(own, opp, empty, shift_e);
    moves |= legal_dir(own, opp, empty, shift_w);
    moves |= legal_dir(own, opp, empty, shift_ne);
    moves |= legal_dir(own, opp, empty, shift_nw);
    moves |= legal_dir(own, opp, empty, shift_se);
    moves |= legal_dir(own, opp, empty, shift_sw);

    while (moves) {
        const Square sq = static_cast<Square>(__builtin_ctzll(moves));
        out.push(sq);
        moves &= moves - 1;
    }
}

bool apply_move(Board& b, Square sq) noexcept {
    // Pass : sq == NO_SQUARE (or out of range). Only legal if no
    // legal moves exist for stm — caller is expected to enforce that.
    if (sq >= BOARD_SIZE) {
        ++b.passes;
        b.stm = ~b.stm;
        return true;
    }

    const Bitboard flips = flips_for_move(b, sq);
    if (flips == 0) return false;  // illegal

    const Bitboard placed = Bitboard{1} << sq;
    if (b.stm == Color::Black) {
        b.black |=  placed | flips;
        b.white &= ~flips;
    } else {
        b.white |=  placed | flips;
        b.black &= ~flips;
    }
    b.passes = 0;
    b.stm = ~b.stm;
    return true;
}

}  // namespace othello
