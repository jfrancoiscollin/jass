// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// See nnue_accumulator.hpp for the full design notes (dual-accumulator
// HalfMen / Stockfish-HalfKP pattern). This file implements the slow
// path (`refresh_from`) for both `Accumulator` and `AccumulatorPair`.
// The fast incremental update (`AccumulatorPair::apply_move`) is still
// a TODO — it's the larger piece of work and depends on `Position`
// exposing per-move delta information (which squares changed and how).

#include "nnue_accumulator.hpp"

#include "nnue.hpp"
#include "position.hpp"

namespace jass {

void Accumulator::refresh_from(const Position&    pos,
                               Color              side,
                               const MLPNetworkQ& net) noexcept {
    hidden1 = net.hidden1();
    // Reuse the network's Layer-1 builder. `build_layer1` writes to
    // the first `hidden1` slots — leaving the rest of `data` as junk
    // is fine because nothing else looks at it.
    net.build_layer1(pos, side, data.data());

    // Cache the anchor we built against so apply_move() can later
    // detect "did the anchor change?" without re-deriving from pos.
    if (side == Color::White) {
        const Bitboard bb = pos.white_men() | pos.white_kings();
        anchor = (bb == 0) ? 49
                           : static_cast<std::size_t>(std::bit_width(bb)) - 1;
    } else {
        const Bitboard bb = pos.black_men() | pos.black_kings();
        if (bb == 0) {
            anchor = 49;
        } else {
            const int lsb = std::countr_zero(bb);
            anchor = static_cast<std::size_t>(49 - lsb);
        }
    }

    valid = true;
}

void AccumulatorPair::refresh_from(const Position&    pos,
                                   const MLPNetworkQ& net) noexcept {
    white.refresh_from(pos, Color::White, net);
    black.refresh_from(pos, Color::Black, net);
}

bool AccumulatorPair::apply_move(const Position&    /*pos_before*/,
                                 const Move&        /*m*/,
                                 const MLPNetworkQ& /*net*/) noexcept {
    // TODO: implement the incremental update. See nnue_accumulator.hpp
    // for the design (per-affected-square (b, old_kind, new_kind)
    // column subtract/add in each accumulator; ~50 column ops + full
    // anchor refresh when the rear-most piece moves).
    //
    // For now, we always return false → caller must refresh_from(pos_after).
    // That keeps the API contract honest while the fast path is
    // built incrementally: the slow path is correct, the fast path
    // when ready will be a strict speedup.
    return false;
}

}  // namespace jass
