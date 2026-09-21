// SPDX-License-Identifier: AGPL-3.0-or-later
#include "chinook_hybrid.hpp"

#include "bitboard.hpp"
#include "movegen.hpp"

namespace jass::chinook_hybrid {

bool gate_components(int total_pieces, std::size_t legal_moves,
                     int stm_material_margin) noexcept {
    return total_pieces >= 9 && total_pieces <= 19
        && legal_moves >= 5U && legal_moves <= 8U
        && stm_material_margin < 0;
}

bool gate(const Position& pos) noexcept {
    const int wm = popcount(pos.white_men());
    const int wk = popcount(pos.white_kings());
    const int bm = popcount(pos.black_men());
    const int bk = popcount(pos.black_kings());
    const int total = wm + wk + bm + bk;

    const int white_value = wm + 3 * wk;
    const int black_value = bm + 3 * bk;
    const int stm_margin = pos.side_to_move() == Color::White
        ? white_value - black_value
        : black_value - white_value;

    MoveList legal;
    generate_legal_moves(pos, legal);
    return gate_components(total, legal.size(), stm_margin);
}

int Network::evaluate(const Position& pos) const noexcept {
    if (gate(pos))
        return hier_->evaluate(pos);
    return curriculum_->evaluate(pos);
}

}  // namespace jass::chinook_hybrid
