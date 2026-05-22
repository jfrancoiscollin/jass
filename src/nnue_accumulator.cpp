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

// One piece change in the canonical (Position-level) frame:
//   * `bit` is the bitboard bit (0..49, same as square - 1).
//   * `colour` is the piece's colour.
//   * `is_king` is the piece's type (king vs man).
//   * `sign` is +1 (piece appears here in the post-move position)
//     or -1 (piece disappears from here).
// The accumulator-side mapping (POV bit + POV kind) happens later
// in apply_changes() — once per POV — so the same change is reused
// for both white-POV and black-POV updates.
struct PieceChange {
    int   bit;
    Color colour;
    bool  is_king;
    int   sign;
};

inline void apply_changes(AccumulatorPair&        pair,
                          const PieceChange*      changes,
                          std::size_t             n_changes,
                          bool                    halfmen,
                          const MLPNetworkQ&      net) noexcept {
    for (Color side : {Color::White, Color::Black}) {
        Accumulator& acc = (side == Color::White) ? pair.white : pair.black;
        for (std::size_t i = 0; i < n_changes; ++i) {
            const PieceChange& ch = changes[i];
            const std::size_t b_pov    = bit_in_pov(ch.bit, side);
            const std::size_t kind_pov = kind_in_pov(ch.colour, ch.is_king, side);
            apply_piece_delta(acc, b_pov, kind_pov, ch.sign, halfmen, net);
        }
    }
}

// v2 incremental update. Handles quiet, capture, and promotion moves
// (any combination) as long as no anchor shifts. Anchor invalidation
// still triggers a refresh fallback (the per-anchor-shift delta path
// is meaningful future work but not implemented yet).
bool AccumulatorPair::apply_move(const Position&    pos_before,
                                 const Move&        m,
                                 const MLPNetworkQ& net) noexcept {
    if (!white.valid || !black.valid) return false;
    const bool halfmen  = (net.input_dim() == MLPNetworkQ::HALFMEN_INPUT_DIM);
    const bool v2_dense = (net.input_dim() == MLPNetworkQ::INPUT_DIM);
    if (!halfmen && !v2_dense) return false;

    if (m.from == NO_SQUARE || m.to == NO_SQUARE) return false;

    // Compute pos_after so we can check anchor invariance (HalfMen
    // only). Cheap relative to a full Layer-1 refresh.
    const Position pos_after = pos_before.after(m);
    if (halfmen) {
        if (anchor_for(pos_after, Color::White) != white.anchor ||
            anchor_for(pos_after, Color::Black) != black.anchor) {
            return false;
        }
    }

    // Build the change list. Worst case: from + to + 20 captures = 22.
    const Color    mover    = pos_before.side_to_move();
    const Color    opponent = (mover == Color::White) ? Color::Black : Color::White;
    const int      from_bit = static_cast<int>(m.from) - 1;
    const int      to_bit   = static_cast<int>(m.to)   - 1;
    const Bitboard from_msk = Bitboard{1} << from_bit;
    const bool mover_was_king = (mover == Color::White)
        ? ((pos_before.white_kings() & from_msk) != 0)
        : ((pos_before.black_kings() & from_msk) != 0);
    const bool mover_is_king_after = mover_was_king || m.promotes;

    std::array<PieceChange, 22> changes{};
    std::size_t n = 0;

    // Remove mover from `from` (its pre-move kind).
    changes[n++] = PieceChange{from_bit, mover, mover_was_king, -1};
    // Add mover at `to` (its post-move kind — same as pre unless promotes).
    changes[n++] = PieceChange{to_bit,   mover, mover_is_king_after, +1};
    // Remove each captured opponent piece.
    for (std::uint8_t i = 0; i < m.num_captures; ++i) {
        const int cap_bit = static_cast<int>(m.captures[i]) - 1;
        const Bitboard cap_msk = Bitboard{1} << cap_bit;
        const bool cap_was_king = (opponent == Color::White)
            ? ((pos_before.white_kings() & cap_msk) != 0)
            : ((pos_before.black_kings() & cap_msk) != 0);
        changes[n++] = PieceChange{cap_bit, opponent, cap_was_king, -1};
    }

    apply_changes(*this, changes.data(), n, halfmen, net);

    // Keep the anchor cache in sync with the position even in V2 mode
    // (where the anchor doesn't affect features but the contract that
    // `acc.anchor` reflects the current position still applies).
    white.anchor = anchor_for(pos_after, Color::White);
    black.anchor = anchor_for(pos_after, Color::Black);

    return true;
}

}  // namespace jass
