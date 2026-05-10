// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Public access to the Zobrist hashing keys.
//
// Split out from `zobrist.hpp` so `Position` can perform incremental
// hash updates inside `after`, `add_piece` and `remove_piece` without
// pulling in the Position-aware bulk hashing function (which would
// create a circular include).

#pragma once

#include "types.hpp"

#include <array>
#include <cstdint>

namespace jass {

using ZobristHash = std::uint64_t;

struct ZobristKeys {
    // Indexed by [piece-kind 0..3][bit 0..49]. Piece-kind: 0 = white
    // man, 1 = white king, 2 = black man, 3 = black king.
    std::array<std::array<std::uint64_t, NUM_SQUARES>, 4> piece;
    std::uint64_t                                         side_to_move;
};

extern const ZobristKeys ZOBRIST;

// Key for a single (piece, square) pair. `Piece::None` returns 0 so it
// is a no-op when XORed into a running hash.
inline ZobristHash key_for_piece(Piece p, Square s) noexcept {
    int kind = -1;
    switch (p) {
        case Piece::WhiteMan:  kind = 0; break;
        case Piece::WhiteKing: kind = 1; break;
        case Piece::BlackMan:  kind = 2; break;
        case Piece::BlackKing: kind = 3; break;
        case Piece::None:      return 0;
    }
    return ZOBRIST.piece[static_cast<std::size_t>(kind)]
                        [static_cast<std::size_t>(square_to_bit(s))];
}

inline ZobristHash key_for_side_to_move() noexcept {
    return ZOBRIST.side_to_move;
}

}  // namespace jass
