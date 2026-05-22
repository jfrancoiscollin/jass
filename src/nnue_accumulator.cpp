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

#include "bitboard.hpp"
#include "nnue.hpp"
#include "position.hpp"

#include <bit>

namespace jass {

namespace {

// Translate a "piece" (color + type) into the side-POV kind index.
// `mover` is the colour of the piece being placed/removed; `side` is
// the accumulator's POV. Own-side pieces map to kinds 0/1 (man/king);
// opp-side pieces map to kinds 2/3.
inline std::size_t kind_in_pov(Color piece_color, bool is_king,
                               Color side) noexcept {
    const bool is_own = (piece_color == side);
    const std::size_t base = is_own ? 0 : 2;
    return base + (is_king ? 1 : 0);
}

// Side-POV bit index: black mirrors (49 - b).
inline std::size_t bit_in_pov(int b, Color side) noexcept {
    return (side == Color::Black)
        ? static_cast<std::size_t>(49 - b)
        : static_cast<std::size_t>(b);
}

// Compute the anchor (same definition as compute_anchor_q_for in nnue.cpp,
// duplicated here so apply_move can detect anchor changes without a
// dependency on nnue.cpp internals).
inline std::size_t anchor_for(const Position& pos, Color side) noexcept {
    if (side == Color::White) {
        const Bitboard bb = pos.white_men() | pos.white_kings();
        if (bb == 0) return 49;
        return static_cast<std::size_t>(std::bit_width(bb)) - 1;
    } else {
        const Bitboard bb = pos.black_men() | pos.black_kings();
        if (bb == 0) return 49;
        const int lsb = std::countr_zero(bb);
        return static_cast<std::size_t>(49 - lsb);
    }
}

// Apply the (b, kind) delta (sign = +1 to add the piece, -1 to remove
// it) to ONE accumulator. In HalfMen mode (`halfmen == true`) we apply
// both the absolute and the anchor-relative columns; in V2 mode we
// apply just the absolute one (V2 has no anchor-relative features).
inline void apply_piece_delta(Accumulator&       acc,
                              std::size_t        b_pov,
                              std::size_t        kind_pov,
                              int                sign,
                              bool               halfmen,
                              const MLPNetworkQ& net) noexcept {
    const std::size_t abs_feat = b_pov * 4 + kind_pov;
    net.apply_column(acc.data.data(), abs_feat, sign);
    if (halfmen) {
        const std::size_t rel  = (b_pov + 50 - acc.anchor) % 50;
        const std::size_t feat = 200 + rel * 4 + kind_pov;
        net.apply_column(acc.data.data(), feat, sign);
    }
}

}  // namespace

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

// v1 incremental update. Conservative: handles only the simple shape
// (quiet move, no promotion, no anchor change). Captures, promotions,
// or anchor invalidation cause an early return so the caller falls
// back to refresh_from.
//
// On the supported shape, the delta is:
//   * remove the moving piece at `from` (sub abs + rel columns) in both
//     accumulators (white-POV and black-POV)
//   * add the moving piece at `to` (add abs + rel columns) in both
//     accumulators
// V2 (input_dim=200) is NOT supported yet — return false so the slow
// path handles it. HalfMen is the only encoding we ship trained
// networks for in practice.
bool AccumulatorPair::apply_move(const Position&    pos_before,
                                 const Move&        m,
                                 const MLPNetworkQ& net) noexcept {
    // Pre-conditions: both accumulators must already be valid (i.e.
    // refresh_from has been called for pos_before).
    if (!white.valid || !black.valid) return false;
    const bool halfmen = (net.input_dim() == MLPNetworkQ::HALFMEN_INPUT_DIM);
    const bool v2_dense = (net.input_dim() == MLPNetworkQ::INPUT_DIM);
    if (!halfmen && !v2_dense) return false;  // unsupported encoding

    // Bail on captures and promotions (handled by refresh in v1).
    if (m.num_captures != 0) return false;
    if (m.promotes)          return false;
    // Bail if either endpoint is invalid (shouldn't happen on legal
    // moves but guards against null/sentinel Move values).
    if (m.from == NO_SQUARE || m.to == NO_SQUARE) return false;

    // Compute pos_after so we can check anchor invariance (HalfMen
    // only — V2 has no anchor). For V2 the call to pos.after() is
    // still useful as a defensive correctness check.
    const Position pos_after = pos_before.after(m);

    if (halfmen) {
        if (anchor_for(pos_after, Color::White) != white.anchor ||
            anchor_for(pos_after, Color::Black) != black.anchor) {
            return false;
        }
    }

    // Identify the mover. For a quiet, non-promoting move:
    //   * `from` had the mover's piece (man or king); now empty.
    //   * `to`   was empty;                            now has the mover's piece.
    // Determine the kind from the bitboards at `from` in pos_before.
    const Color mover_colour = pos_before.side_to_move();
    const int   from_bit     = static_cast<int>(m.from) - 1;
    const int   to_bit       = static_cast<int>(m.to)   - 1;
    const Bitboard from_mask = Bitboard{1} << from_bit;
    const bool is_king = (mover_colour == Color::White)
        ? ((pos_before.white_kings() & from_mask) != 0)
        : ((pos_before.black_kings() & from_mask) != 0);

    // Apply the delta to both accumulators.
    for (Color side : {Color::White, Color::Black}) {
        Accumulator& acc      = (side == Color::White) ? white : black;
        const std::size_t b_from = bit_in_pov(from_bit, side);
        const std::size_t b_to   = bit_in_pov(to_bit,   side);
        const std::size_t kind   = kind_in_pov(mover_colour, is_king, side);
        // Remove from `b_from`, add at `b_to`.
        apply_piece_delta(acc, b_from, kind, -1, halfmen, net);
        apply_piece_delta(acc, b_to,   kind, +1, halfmen, net);
    }

    return true;
}

}  // namespace jass
