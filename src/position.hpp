// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// `Position` — the immutable-on-disk representation of a draughts game state.
//
// Internally we keep four bitboards (white men, white kings, black men, black
// kings) plus the side to move. This is enough to reconstruct the full board
// state. A separate `mailbox` accessor reconstitutes a Piece for any square.

#pragma once

#include "bitboard.hpp"
#include "types.hpp"
#include "zobrist_keys.hpp"

#include <optional>
#include <string>
#include <string_view>

namespace jass {

class Position {
public:
    // -------------------------------------------------------------------------
    // Construction
    // -------------------------------------------------------------------------
    Position() = default;

    // Standard FMJD opening setup: white men on 31..50, black men on 1..20,
    // white to move.
    static Position start_position() noexcept;

    // Parse a Hub-style FEN string. Returns std::nullopt on syntax errors or
    // any conflict (e.g. two pieces on the same square).
    //
    // Accepted form, whitespace insensitive:
    //
    //     <stm> ":" <colour-list> ":" <colour-list>
    //
    // where <stm> is "W" or "B", and <colour-list> is
    //
    //     ("W"|"B") (<entry> ("," <entry>)*)?
    //
    // Each <entry> is either a single square ("31") or a range ("31-50"),
    // optionally preceded by "K" to denote a king ("K33" or "K30-32").
    //
    // The two colour-lists must use different colour letters; missing pieces
    // are simply absent from the lists.
    static std::optional<Position> from_fen(std::string_view fen);

    // -------------------------------------------------------------------------
    // Accessors
    // -------------------------------------------------------------------------
    Bitboard white_men()   const noexcept { return white_men_;   }
    Bitboard white_kings() const noexcept { return white_kings_; }
    Bitboard black_men()   const noexcept { return black_men_;   }
    Bitboard black_kings() const noexcept { return black_kings_; }

    Bitboard whites()   const noexcept { return white_men_ | white_kings_; }
    Bitboard blacks()   const noexcept { return black_men_ | black_kings_; }
    Bitboard occupied() const noexcept { return whites() | blacks(); }
    Bitboard empties()  const noexcept { return ~occupied() & PLAYABLE_BB; }

    Bitboard pieces_of(Color c) const noexcept {
        return (c == Color::White) ? whites() : blacks();
    }
    Bitboard men_of(Color c) const noexcept {
        return (c == Color::White) ? white_men_ : black_men_;
    }
    Bitboard kings_of(Color c) const noexcept {
        return (c == Color::White) ? white_kings_ : black_kings_;
    }

    Color side_to_move() const noexcept { return stm_; }

    // Half-move counter for the FMJD 25-move rule: incremented on a
    // reversible move (king quiet), reset on captures or man moves. A
    // game where the counter reaches 50 plies (i.e. 25 full moves) is
    // declared drawn.
    int  halfmove_clock() const noexcept { return halfmove_clock_; }
    void set_halfmove_clock(int c) noexcept { halfmove_clock_ = c; }

    // Cached Zobrist hash of the position. Maintained incrementally by
    // `add_piece` / `remove_piece` / `set_side_to_move` and by
    // `Position::after`. Returns 0 only for a fully empty default-
    // constructed Position with white to move.
    ZobristHash hash() const noexcept { return hash_; }

    Piece piece_at(Square s) const noexcept;

    // -------------------------------------------------------------------------
    // Mutators (low-level — `Position` does not yet implement make/unmake)
    // -------------------------------------------------------------------------
    void clear() noexcept;
    void set_side_to_move(Color c) noexcept {
        if (c != stm_) hash_ ^= key_for_side_to_move();
        stm_ = c;
    }

    // Place / remove a piece on a square. The square must be empty before
    // `add_piece`; `remove_piece` requires that the matching piece is there.
    void add_piece(Square s, Piece p) noexcept;
    void remove_piece(Square s, Piece p) noexcept;

    // -------------------------------------------------------------------------
    // Move application
    // -------------------------------------------------------------------------
    // Return a new Position obtained by playing `m` in `*this`. Side to move
    // is flipped, captured pieces are removed and a man that ends on the
    // promotion row is upgraded to a king.
    //
    // Behaviour is undefined if `m` was not produced by `generate_legal_moves`
    // for `*this` (or an equivalent legal-move source).
    Position after(const Move& m) const noexcept;

    // -------------------------------------------------------------------------
    // Serialisation
    // -------------------------------------------------------------------------
    std::string to_fen() const;

    // ASCII diagram of the board, useful for tests and the smoke-test main.
    std::string to_ascii() const;

    // -------------------------------------------------------------------------
    // Equality (bit-exact, ignoring move-counter metadata which we don't yet
    // track).
    // -------------------------------------------------------------------------
    friend bool operator==(const Position& a, const Position& b) noexcept {
        return a.white_men_   == b.white_men_   &&
               a.white_kings_ == b.white_kings_ &&
               a.black_men_   == b.black_men_   &&
               a.black_kings_ == b.black_kings_ &&
               a.stm_         == b.stm_;
    }

private:
    Bitboard    white_men_{0};
    Bitboard    white_kings_{0};
    Bitboard    black_men_{0};
    Bitboard    black_kings_{0};
    Color       stm_{Color::White};
    int         halfmove_clock_{0};
    ZobristHash hash_{0};  // 0 matches the bulk hash of an empty white-to-move
};

}  // namespace jass
