// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "eval.hpp"

#include "bitboard.hpp"
#include "board.hpp"

#include <array>

namespace jass {

namespace {

constexpr int iabs(int x) noexcept { return x < 0 ? -x : x; }

// Per-rank advancement bonus for a man, in points.
//
// White's promotion row is row 0; black's is row 9. Each step closer to
// promotion adds `ADVANCE_STEP` points so a man that has not yet moved is
// worth its raw material value while a man one square from promotion is
// worth roughly +36.
inline constexpr int ADVANCE_STEP = 4;

constexpr std::array<int, NUM_SQUARES + 1>
build_white_man_psqt() {
    std::array<int, NUM_SQUARES + 1> t{};
    for (int s = FIRST_SQUARE; s <= LAST_SQUARE; ++s) {
        const int r = (s - 1) / 5;          // 0 = top  (white promotion)
        t[static_cast<std::size_t>(s)] = ADVANCE_STEP * (9 - r);
    }
    return t;
}

constexpr std::array<int, NUM_SQUARES + 1>
build_black_man_psqt() {
    std::array<int, NUM_SQUARES + 1> t{};
    for (int s = FIRST_SQUARE; s <= LAST_SQUARE; ++s) {
        const int r = (s - 1) / 5;          // 9 = bottom (black promotion)
        t[static_cast<std::size_t>(s)] = ADVANCE_STEP * r;
    }
    return t;
}

// Centralisation bonus for kings. We measure twice the L1 distance from
// the geometric centre (4.5, 4.5) — i.e. |2r - 9| + |2f - 9| ∈ [2, 16] —
// and reward smaller distances. Range: a king at the centre gets +14, a
// king at a far corner gets 0.
constexpr std::array<int, NUM_SQUARES + 1>
build_king_psqt() {
    std::array<int, NUM_SQUARES + 1> t{};
    for (int s = FIRST_SQUARE; s <= LAST_SQUARE; ++s) {
        const int r = (s - 1) / 5;
        const int row_even = (r % 2 == 0);
        const int c_in_row = (s - 1) % 5;
        const int file = row_even ? (2 * c_in_row + 1) : (2 * c_in_row);
        const int d2 = iabs(2 * r - 9) + iabs(2 * file - 9);
        // d2 ∈ [2, 16]; centre best.
        t[static_cast<std::size_t>(s)] = 16 - d2;
    }
    return t;
}

constinit const std::array<int, NUM_SQUARES + 1> WHITE_MAN_PSQT
    = build_white_man_psqt();
constinit const std::array<int, NUM_SQUARES + 1> BLACK_MAN_PSQT
    = build_black_man_psqt();
constinit const std::array<int, NUM_SQUARES + 1> KING_PSQT
    = build_king_psqt();

int score_men(Bitboard men, const std::array<int, NUM_SQUARES + 1>& psqt) noexcept {
    int s = 0;
    for (Bitboard b = men; b; ) {
        const Square sq = pop_lsb(b);
        s += MAN_VALUE + psqt[static_cast<std::size_t>(sq)];
    }
    return s;
}

int score_kings(Bitboard kings) noexcept {
    int s = 0;
    for (Bitboard b = kings; b; ) {
        const Square sq = pop_lsb(b);
        s += KING_VALUE + KING_PSQT[static_cast<std::size_t>(sq)];
    }
    return s;
}

}  // namespace

int evaluate(const Position& pos) noexcept {
    int score = 0;

    // Material + per-piece positional terms.
    score += score_men  (pos.white_men(),   WHITE_MAN_PSQT);
    score += score_kings(pos.white_kings());
    score -= score_men  (pos.black_men(),   BLACK_MAN_PSQT);
    score -= score_kings(pos.black_kings());

    // Tempo, computed from the white POV before the final flip.
    score += (pos.side_to_move() == Color::White) ? TEMPO_BONUS : -TEMPO_BONUS;

    return (pos.side_to_move() == Color::White) ? score : -score;
}

}  // namespace jass
