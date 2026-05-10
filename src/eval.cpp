// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "eval.hpp"

#include "bitboard.hpp"
#include "board.hpp"

#include <array>
#include <cstdint>

namespace jass {

namespace {

constexpr int iabs(int x) noexcept { return x < 0 ? -x : x; }

// Man PSQT terms (all hand-set, no tuning data):
//
//   - advancement: each rank closer to the promotion row adds
//     ADVANCE_STEP points, so a man one square from promoting is worth
//     ~MAN_VALUE + 36.
//   - edge-column penalty: men on the leftmost / rightmost playable
//     files have fewer captures available and one less defender.
//   - back-rank guard bonus: men still on the home rank deny enemy
//     promotion squares for free.
inline constexpr int ADVANCE_STEP   = 4;
inline constexpr int EDGE_PENALTY   = 3;
inline constexpr int BACKRANK_BONUS = 5;

constexpr int file_of(int s) noexcept {
    const int r = (s - 1) / 5;
    const int c = (s - 1) % 5;
    return (r % 2 == 0) ? (2 * c + 1) : (2 * c);
}

constexpr int common_man_psqt_addons(int s) noexcept {
    const int file = file_of(s);
    const int edge = (file == 0 || file == 9) ? -EDGE_PENALTY : 0;
    return edge;
}

constexpr std::array<int, NUM_SQUARES + 1>
build_white_man_psqt() {
    std::array<int, NUM_SQUARES + 1> t{};
    for (int s = FIRST_SQUARE; s <= LAST_SQUARE; ++s) {
        const int r        = (s - 1) / 5;          // 0 = top, 9 = bottom
        const int adv      = ADVANCE_STEP * (9 - r);
        const int backrank = (r == 9) ? BACKRANK_BONUS : 0;
        t[static_cast<std::size_t>(s)] = adv + backrank + common_man_psqt_addons(s);
    }
    return t;
}

constexpr std::array<int, NUM_SQUARES + 1>
build_black_man_psqt() {
    std::array<int, NUM_SQUARES + 1> t{};
    for (int s = FIRST_SQUARE; s <= LAST_SQUARE; ++s) {
        const int r        = (s - 1) / 5;
        const int adv      = ADVANCE_STEP * r;
        const int backrank = (r == 0) ? BACKRANK_BONUS : 0;
        t[static_cast<std::size_t>(s)] = adv + backrank + common_man_psqt_addons(s);
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

// Bonus for men that have a friendly piece on the diagonal *behind* them
// — the classic "supported" or "defended" structure. A supported man can
// be replaced after a trade and is much harder to attack profitably.
//
// Backward diagonals are SW/SE for white men (rear-most squares are at
// row 9) and NW/NE for black men.
inline constexpr int SUPPORT_BONUS = 5;

int support_score(const Position& pos, Color c) noexcept {
    const Bitboard friends = pos.pieces_of(c);
    Bitboard       men     = pos.men_of(c);
    const Dir back1 = (c == Color::White) ? Dir::DownLeft  : Dir::UpLeft;
    const Dir back2 = (c == Color::White) ? Dir::DownRight : Dir::UpRight;

    int s = 0;
    while (men) {
        const Square sq = pop_lsb(men);
        const Square b1 = neighbour(sq, back1);
        const Square b2 = neighbour(sq, back2);
        if (b1 != NO_SQUARE && test(friends, b1)) s += SUPPORT_BONUS;
        if (b2 != NO_SQUARE && test(friends, b2)) s += SUPPORT_BONUS;
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

    // Structure: defended-piece bonus.
    score += support_score(pos, Color::White);
    score -= support_score(pos, Color::Black);

    // Tempo, computed from the white POV before the final flip.
    score += (pos.side_to_move() == Color::White) ? TEMPO_BONUS : -TEMPO_BONUS;

    return (pos.side_to_move() == Color::White) ? score : -score;
}

}  // namespace jass
