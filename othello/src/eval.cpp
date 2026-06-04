// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "eval.hpp"
#include "movegen.hpp"

namespace othello {

namespace {

constexpr Bitboard CORNER_MASK =
      (Bitboard{1} << 0)  | (Bitboard{1} << 7)
    | (Bitboard{1} << 56) | (Bitboard{1} << 63);

inline int count_legal_moves(const Board& b) noexcept {
    MoveList ml;
    generate_legal_moves(b, ml);
    return static_cast<int>(ml.size());
}

}  // namespace

int eval_basic(const Board& b) noexcept {
    const Bitboard own = b.own_pieces();
    const Bitboard opp = b.opp_pieces();

    const int own_pc = __builtin_popcountll(own);
    const int opp_pc = __builtin_popcountll(opp);
    const int total  = own_pc + opp_pc;

    // Phase : 0 = empty board, 100 = full board. Scales piece diff.
    const int phase = (total * 100) / 64;

    // Corner ownership : huge bonus, stable across phases.
    const int own_corners = __builtin_popcountll(own & CORNER_MASK);
    const int opp_corners = __builtin_popcountll(opp & CORNER_MASK);
    const int corner_term = (own_corners - opp_corners) * 500;

    // Mobility : count moves for both sides. stm = current, opp move
    // count requires a temporary board with flipped stm.
    const int own_moves = count_legal_moves(b);
    Board flipped = b;
    flipped.stm = ~flipped.stm;
    const int opp_moves = count_legal_moves(flipped);
    const int mobility_term = (own_moves - opp_moves) * 10;

    // Piece diff : weighted by phase. In endgame, piece count dominates.
    const int piece_term = ((own_pc - opp_pc) * phase) / 10;

    return corner_term + mobility_term + piece_term;
}

int eval_pattern(const Board& b, const std::int32_t* weights) noexcept {
    // Sum weights[index_i] over the 10 patterns. The indices are
    // computed from the raw board ; eval is from "black POV" by
    // convention, then sign-flipped if stm is white.
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(b, idx);
    constexpr auto offsets = pattern_offsets();
    std::int64_t sum = 0;
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        sum += weights[offsets[i] + idx[i]];
    }
    // Indices were color-based ; convert to stm POV.
    return (b.stm == Color::Black) ? static_cast<int>(sum)
                                   : static_cast<int>(-sum);
}

int terminal_score(const Board& b) noexcept {
    const int own_pc = __builtin_popcountll(b.own_pieces());
    const int opp_pc = __builtin_popcountll(b.opp_pieces());
    if (own_pc > opp_pc) return  WIN_SCORE;
    if (own_pc < opp_pc) return -WIN_SCORE;
    return DRAW_SCORE;
}

}  // namespace othello
