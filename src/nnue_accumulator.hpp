// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// =============================================================================
// HalfMen incremental NNUE accumulator — SCAFFOLD ONLY (not yet wired up)
// =============================================================================
//
// PURPOSE
// -------
// Companion to MLPNetworkQ (src/nnue.hpp). Targets the Layer-1 input sum
// that, even after the column-major + AVX2 refactor (PR #72), is still
// the bulk of evaluate() cost — and is rebuilt from scratch on every
// search node. With ~150K nodes per depth-20 search, that's ~150K full
// Layer-1 sums per move. Incremental update reduces that to a small
// delta (1-2 piece moves + maybe an anchor change) per node.
//
// STATUS (this commit):
//   * Slow path (refresh_from) is IMPLEMENTED — Accumulator and
//     AccumulatorPair fully refresh from a Position by delegating to
//     MLPNetworkQ::build_layer1 (new public method). Covered by a
//     parity test against build_layer1 output.
//   * Fast path (apply_move) is a stub returning false: callers must
//     refresh_from on the post-move position. Wiring in Engine is
//     deferred until the Cycle-9 pilot validates the training
//     direction (no point optimising eval if the architecture or
//     labelling is wrong).
//   * Estimated remaining work: ~1-2 weeks of careful C++ for the
//     incremental update + Engine integration + extensive parity
//     testing against the refresh-each-time path.
//
//
// DESIGN — TWO ACCUMULATORS, ONE PER COLOUR
// -----------------------------------------
// HalfMen has a structural problem for naïve incremental update: every
// STM swap (i.e. every ply in draughts) changes the *anchor* — the
// rear-most STM piece — which the entire 200 anchor-relative columns
// + 50 anchor one-hot columns depend on. A single-accumulator scheme
// would have to recompute ~250/450 features on every move, defeating
// the point.
//
// Stockfish's HalfKP solves the analogous problem (king-relative
// features change when the king moves) by maintaining TWO accumulators
// in parallel, one anchored to each side's reference (king, in their
// case). On every move, BOTH accumulators are updated. Evaluating in
// STM-POV just reads from STM's accumulator; the opponent's is kept
// up-to-date for the next ply.
//
// We mirror that here. Two `Accumulator` objects live alongside the
// `Position`:
//
//   * `acc_white` — STM-POV from White's perspective, no mirror,
//                   anchor = MSB of (white_men | white_kings).
//   * `acc_black` — STM-POV from Black's perspective, mirrored bits
//                   (b -> 49-b), anchor = 49 - LSB(black_men | black_kings).
//
// `evaluate(pos)` reads the accumulator matching `pos.side_to_move()`,
// finishes the forward pass (ReLU + Layer-2 + Layer-3 + scale), done.
// The Layer-1 sum becomes a `memcpy` from the cached accumulator —
// no per-feature work.
//
//
// UPDATE PATH — INCREMENTAL DELTAS
// --------------------------------
// On `Engine::apply_move(m)`, we know:
//   * The set of squares whose occupancy changes (move origin, move
//     target, plus captured squares).
//   * For each such square, the (old_kind, new_kind) tuple (men/king,
//     white/black, or empty).
//   * Whether the move promoted (man -> king).
//
// For each affected square (b, old_kind, new_kind), in each accumulator
// (acc_white, acc_black) — note: each accumulator sees the WHOLE board
// in its own POV, so both must be updated:
//
//   Remove old_kind contribution at square b:
//     acc -= W1_col[ b_in_pov * 4 + old_kind_in_pov ]    (absolute)
//     acc -= W1_col[ 200 + rel(b_in_pov, anchor_pov) * 4 + old_kind_in_pov ]
//
//   Add new_kind contribution at square b:
//     acc += W1_col[ b_in_pov * 4 + new_kind_in_pov ]
//     acc += W1_col[ 200 + rel(b_in_pov, anchor_pov) * 4 + new_kind_in_pov ]
//
// Empty -> kind and kind -> empty are handled by treating "empty"
// as a no-op (no column add/sub). Kind change (promotion) is two
// passes: remove (b, man) then add (b, king).
//
//
// ANCHOR INVALIDATION
// -------------------
// The anchor for accumulator X is X's own MSB/LSB-of-pieces. It only
// changes when X-side's piece set changes such that the rear-most
// piece of X moves or is captured:
//
//   * If acc_white's anchor changes:
//       — All 50 anchor-relative slots in acc_white shift. Cheap to
//         recompute: 50 column-subtracts (old rel positions) + 50
//         column-adds (new rel positions) + 1 anchor-one-hot swap.
//       — acc_black is unaffected by acc_white's anchor change.
//   * Symmetric for acc_black.
//
// Most moves don't change the anchor (only the rear-most piece's
// removal does). So this expensive path is rare.
//
//
// API SHAPE
// ---------
// Engine holds a stack of Accumulator pairs (one per ply, for undo
// support during search). On apply_move:
//   1. Push current pair onto undo stack.
//   2. Update top pair in place with the move's delta.
// On undo_move: pop the undo stack.
//
// `Accumulator::refresh_from(const Position&, const MLPNetworkQ&)` is
// the slow path: rebuild the accumulator from scratch by iterating
// pieces. Used to seed at search start (Engine::new_game / set_position)
// and after rare events that would require complex delta logic (e.g.
// a multi-jump capture chain hitting >K squares — fall back to refresh
// if cheaper).
//
//
// MEMORY LAYOUT
// -------------
// Accumulator stores `hidden1` int32 values aligned to 32 bytes (AVX2
// load/store alignment). MAX_HIDDEN=1024 → 4 KB per accumulator,
// 8 KB per pair (white+black), ~8 MB for a 1000-ply undo stack. The
// search rarely needs >100 plies of undo, so the stack can be capped
// at ~128 entries (1 MB) without trouble.
//
//
// WIRING-UP PLAN (when this gets implemented)
// -------------------------------------------
//   1. Position exposes "delta info" from `pos.after(m)`: which squares
//      changed and how. Either compute by diffing pos / pos.after(m)
//      bitboards or extend Move with the info. The latter is cleaner.
//   2. Engine owns an `AccumulatorPair` and an undo stack.
//   3. Engine::new_game / set_position refreshes the pair from scratch.
//   4. Engine::apply_move pushes undo + applies delta to the pair.
//   5. Engine::undo_move pops undo.
//   6. MLPNetworkQ::evaluate_with_accumulator(pos, acc_pair) is the
//      fast path; the existing evaluate(pos) becomes a wrapper that
//      builds a fresh AccumulatorPair from pos for callers that don't
//      have one (tests, one-off positions).
//
// Estimated effort once we commit: 1-2 weeks of focused C++, including
// extensive parity testing against the current refresh-each-time path
// (the test should run a full search, log every evaluate() output, and
// compare against a search of the same position with incremental
// disabled — they must match bit-for-bit modulo accumulator round-off,
// which there isn't any here since everything is integer-stable).
//
// =============================================================================

#pragma once

#include "nnue.hpp"     // for MLPNetworkQ, MAX_HIDDEN
#include "position.hpp"
#include "types.hpp"

#include <array>
#include <cstdint>

namespace jass {

// One accumulator = Layer-1 partial sum for one side's POV.
// `data` mirrors what `MLPNetworkQ::evaluate` builds in its scratch
// `acc1[]`: hidden1 int32 values, anchored to this side's reference.
//
// `valid` is set false on construction and after invalidating ops
// (anchor change, refresh requested); the eval path falls back to
// the slow refresh when it sees an invalid accumulator. This lets
// the implementation roll out lazily — anything we haven't coded
// incremental support for can just mark the accumulator invalid
// and the slow path handles it correctly.
struct alignas(32) Accumulator {
    std::array<std::int32_t, MLPNetworkQ::MAX_HIDDEN> data{};
    std::size_t                                       hidden1 = 0;
    std::size_t                                       anchor  = 0;
    bool                                              valid   = false;

    // Slow path: rebuild from scratch. Delegates to
    // MLPNetworkQ::build_layer1, which walks active pieces in `pos`
    // from `side`'s POV and sums absolute + anchor-relative columns +
    // anchor one-hot. O(active_pieces × hidden1) — same cost as the
    // current MLPNetworkQ::evaluate Layer 1. Sets `valid = true`.
    void refresh_from(const Position&    pos,
                      Color              side,
                      const MLPNetworkQ& net) noexcept;
};

// One pair = (white-POV accumulator, black-POV accumulator). Engine
// holds one of these as "current" and a stack of saved pairs for undo.
struct AccumulatorPair {
    Accumulator white;
    Accumulator black;

    // Reset both to invalid (forces refresh on next eval).
    void invalidate() noexcept {
        white.valid = false;
        black.valid = false;
    }

    // Rebuild both from scratch from `pos` + `net`. Slow path; used at
    // Engine::new_game / set_position, and as the fallback whenever
    // apply_move() reports it couldn't update incrementally.
    void refresh_from(const Position& pos, const MLPNetworkQ& net) noexcept;

    // Incremental update: `pos_before` and `m` together describe one
    // move; the function mutates *this from "matching pos_before" to
    // "matching pos_before.after(m)". Returns true on incremental
    // success; false if it bailed out (caller must then refresh_from
    // on the new position).
    //
    // STATUS: returns false unconditionally (stub). The actual
    // incremental logic — per-affected-square column subtract/add +
    // anchor-invalidation handling — is the larger remaining piece
    // of work.
    bool apply_move(const Position&    pos_before,
                    const Move&        m,
                    const MLPNetworkQ& net) noexcept;
};

}  // namespace jass
