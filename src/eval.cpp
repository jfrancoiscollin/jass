// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "eval.hpp"

#include "bitboard.hpp"

namespace jass {

int evaluate(const Position& pos) noexcept {
    int score = 0;
    score += MAN_VALUE  * popcount(pos.white_men());
    score += KING_VALUE * popcount(pos.white_kings());
    score -= MAN_VALUE  * popcount(pos.black_men());
    score -= KING_VALUE * popcount(pos.black_kings());
    return (pos.side_to_move() == Color::White) ? score : -score;
}

}  // namespace jass
