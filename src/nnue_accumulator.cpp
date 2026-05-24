// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// See nnue_accumulator.hpp for the full design notes (dual-accumulator
// HalfMen / Stockfish-HalfKP pattern). This file implements:
//   * the slow path (`refresh_from`) for `Accumulator` and
//     `AccumulatorPair`,
//   * the fast incremental update (`AccumulatorPair::apply_move`) for
//     HalfMen and V2 dense encodings. Returns false on anchor change
//     or unsupported encodings so the caller can fall back to
//     refresh_from.
// Both paths are wired into search via `SearchState::accumulators`
// (see src/search.cpp).

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

// Anchor shift: when one side's anchor changes between pos_before and
// pos_after, every anchor-relative feature for that side's accumulator
// needs to be moved from the old-anchor frame to the new-anchor frame.
// Walks the post-move pieces in `side`'s POV: for each piece, subtract
// its old-anchor rel contribution and add its new-anchor rel
// contribution. Finally swap the anchor one-hot (400 + old) → (400 + new).
//
// Cost: ~30 piece × (1 sub + 1 add) = ~60 column ops, plus 2 ops for
// the one-hot swap. Comparable to a full refresh for one side, but
// the OTHER side's accumulator (which didn't shift) is preserved →
// net ~½ refresh-equivalent cost across both sides for moves that
// shift one anchor only.
inline void shift_anchor(Accumulator&       acc,
                         const Position&    pos_after,
                         Color              side,
                         std::size_t        old_anchor,
                         std::size_t        new_anchor,
                         const MLPNetworkQ& net) noexcept {
    auto walk_bb = [&](Bitboard bb, std::size_t kind_pov) {
        while (bb) {
            const int bit = square_to_bit(pop_lsb(bb));
            const std::size_t b_pov = bit_in_pov(bit, side);
            const std::size_t rel_old = (b_pov + 50 - old_anchor) % 50;
            const std::size_t rel_new = (b_pov + 50 - new_anchor) % 50;
            if (rel_old != rel_new) {
                const std::size_t feat_old = 200 + rel_old * 4 + kind_pov;
                const std::size_t feat_new = 200 + rel_new * 4 + kind_pov;
                net.apply_column(acc.data.data(), feat_old, -1);
                net.apply_column(acc.data.data(), feat_new, +1);
            }
        }
    };

    if (side == Color::White) {
        walk_bb(pos_after.white_men(),   /*kind_pov=*/0);
        walk_bb(pos_after.white_kings(), /*kind_pov=*/1);
        walk_bb(pos_after.black_men(),   /*kind_pov=*/2);
        walk_bb(pos_after.black_kings(), /*kind_pov=*/3);
    } else {
        walk_bb(pos_after.black_men(),   /*kind_pov=*/0);
        walk_bb(pos_after.black_kings(), /*kind_pov=*/1);
        walk_bb(pos_after.white_men(),   /*kind_pov=*/2);
        walk_bb(pos_after.white_kings(), /*kind_pov=*/3);
    }
    // Anchor one-hot swap.
    net.apply_column(acc.data.data(), 400 + old_anchor, -1);
    net.apply_column(acc.data.data(), 400 + new_anchor, +1);
    acc.anchor = new_anchor;
}

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

// v3 incremental update. Handles every move shape (quiet, capture,
// promotion, combinations) including anchor shifts. The only remaining
// fallback case is an unsupported encoding (e.g. neither V2 nor
// HalfMen) — currently impossible because mlpq_dims_ok rejects any
// other input_dim at load time.
bool AccumulatorPair::apply_move(const Position&    pos_before,
                                 const Move&        m,
                                 const Position&    pos_after,
                                 const MLPNetworkQ& net) noexcept {
    if (!white.valid || !black.valid) return false;
    const bool halfmen  = (net.input_dim() == MLPNetworkQ::HALFMEN_INPUT_DIM);
    const bool v2_dense = (net.input_dim() == MLPNetworkQ::INPUT_DIM);
    if (!halfmen && !v2_dense) return false;

    if (m.from == NO_SQUARE || m.to == NO_SQUARE) return false;

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

    // Apply move-induced changes using the OLD anchor (acc.anchor
    // still holds the pre-move value).
    apply_changes(*this, changes.data(), n, halfmen, net);

    // Anchor handling. In HalfMen, if either side's anchor shifted as
    // a result of the move, shift the rel features + one-hot in that
    // accumulator now (the move-induced rel features added above were
    // computed against the OLD anchor; shift_anchor moves them to the
    // new frame and updates acc.anchor). In V2 we have no anchor-
    // relative features but still keep `acc.anchor` in sync so the
    // contract holds.
    const std::size_t new_w_anchor = anchor_for(pos_after, Color::White);
    const std::size_t new_b_anchor = anchor_for(pos_after, Color::Black);

    if (halfmen) {
        if (new_w_anchor != white.anchor) {
            shift_anchor(white, pos_after, Color::White,
                         white.anchor, new_w_anchor, net);
        }
        if (new_b_anchor != black.anchor) {
            shift_anchor(black, pos_after, Color::Black,
                         black.anchor, new_b_anchor, net);
        }
    } else {
        white.anchor = new_w_anchor;
        black.anchor = new_b_anchor;
    }

    return true;
}

}  // namespace jass
