// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "nnue.hpp"

#include "bitboard.hpp"
#include "board.hpp"
#include "eval.hpp"

#include <cstring>
#include <fstream>
#include <string>

namespace jass {

namespace {

// Mirror of eval.cpp's hand-tuned constants. We duplicate them here on
// purpose: the network defines the effective evaluation once trained,
// and we don't want it to silently drift if eval.cpp's tables ever
// change without a corresponding NNUE refit.
constexpr int ADV_STEP        = 4;
constexpr int EDGE_PENALTY    = 3;
constexpr int BACKRANK_BONUS  = 5;

int file_of_sq(int s) noexcept {
    const int r = (s - 1) / 5;
    const int c = (s - 1) % 5;
    return (r % 2 == 0) ? (2 * c + 1) : (2 * c);
}

int iabs(int x) noexcept { return x < 0 ? -x : x; }

}  // namespace

LinearNetwork::LinearNetwork() {
    for (int s = FIRST_SQUARE; s <= LAST_SQUARE; ++s) {
        const int r        = (s - 1) / 5;
        const int file     = file_of_sq(s);
        const int edge     = (file == 0 || file == 9) ? -EDGE_PENALTY : 0;
        const int wman_psq = ADV_STEP * (9 - r) + (r == 9 ? BACKRANK_BONUS : 0) + edge;
        const int bman_psq = ADV_STEP * r       + (r == 0 ? BACKRANK_BONUS : 0) + edge;
        const int d2       = iabs(2 * r - 9) + iabs(2 * file - 9);
        const int king_psq = 16 - d2;

        const std::size_t idx = static_cast<std::size_t>(s - 1);
        weights_[idx][0] =  MAN_VALUE  + wman_psq;
        weights_[idx][1] =  KING_VALUE + king_psq;
        weights_[idx][2] = -(MAN_VALUE  + bman_psq);
        weights_[idx][3] = -(KING_VALUE + king_psq);
    }
}

namespace {

template <std::size_t Kind>
int sum_kind(const std::array<std::array<std::int32_t, 4>, NUM_SQUARES>& w,
             Bitboard bb) noexcept {
    int s = 0;
    while (bb) {
        const int bit = square_to_bit(pop_lsb(bb));
        s += w[static_cast<std::size_t>(bit)][Kind];
    }
    return s;
}

}  // namespace

int LinearNetwork::evaluate(const Position& pos) const noexcept {
    int score = 0;
    score += sum_kind<0>(weights_, pos.white_men());
    score += sum_kind<1>(weights_, pos.white_kings());
    score += sum_kind<2>(weights_, pos.black_men());
    score += sum_kind<3>(weights_, pos.black_kings());
    score += (pos.side_to_move() == Color::White) ? TEMPO_BONUS : -TEMPO_BONUS;
    return (pos.side_to_move() == Color::White) ? score : -score;
}

bool LinearNetwork::load(std::string_view path) {
    std::ifstream f(std::string{path}, std::ios::binary);
    if (!f) return false;
    decltype(weights_) tmp{};
    f.read(reinterpret_cast<char*>(tmp.data()),
           static_cast<std::streamsize>(sizeof(tmp)));
    if (!f || f.gcount() != static_cast<std::streamsize>(sizeof(tmp))) {
        return false;
    }
    weights_ = tmp;
    return true;
}

bool LinearNetwork::save(std::string_view path) const {
    std::ofstream f(std::string{path}, std::ios::binary);
    if (!f) return false;
    f.write(reinterpret_cast<const char*>(weights_.data()),
            static_cast<std::streamsize>(sizeof(weights_)));
    return f.good();
}

int evaluate_nnue(const Position& pos) {
    static const LinearNetwork net;
    return net.evaluate(pos);
}

}  // namespace jass
