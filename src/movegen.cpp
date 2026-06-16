// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Move generation for international (FMJD) draughts.
//
// Public entry point: `generate_legal_moves(pos, out)`. The implementation
// proceeds in two phases:
//
//   1. Generate every capture chain from the side-to-move's pieces. A capture
//      chain is *complete*: a man or king must keep capturing as long as
//      another (uncaptured) enemy can be jumped.  A captured piece stays on
//      the board until the chain ends, so it cannot be jumped twice and a
//      sliding king is blocked by it.
//
//   2. If at least one capture exists, apply the FMJD majority rule by
//      keeping only the chains that capture the maximum number of pieces.
//      Otherwise emit quiet moves (single-step for men, ray slides for
//      kings).
//
// Promotion happens iff a man *ends* its move on the opponent's home rank.
// While a man is in the middle of a chain it remains a man — even if it
// passes through the promotion row — so we keep the original piece type for
// the whole DFS and only set `Move::promotes` once the chain is committed.

#include "movegen.hpp"

#include "bd_time.hpp"
#include "bitboard.hpp"
#include "board.hpp"

#include <algorithm>
#include <array>

namespace jass {

namespace {

// Per-chain DFS state. `friend_bb`/`enemy_bb` are immutable for a single
// piece's exploration; `captured_bb`/`captured_list` track the running chain.
struct CaptureCtx {
    Color    us;
    Bitboard friend_bb;
    Bitboard enemy_bb;

    Bitboard occ;   // friend_bb | enemy_bb, cached (constant per piece chain)

    Square         from_sq{NO_SQUARE};
    Square         cur_sq{NO_SQUARE};
    Bitboard       captured_bb{0};
    std::uint8_t   captured_count{0};

    MoveList* out{nullptr};

    // Running max length of any emitted chain. FMJD prise majoritaire
    // forces play of the longest capture, so emit_chain filters lazily :
    // a chain shorter than `max_captures` is dropped; a longer one wipes
    // the accumulated list and resets the bar. Saves the second pass that
    // `generate_legal_moves` used to do (sub-bucket "wrapper" = 8.1% of
    // total search at 0099).
    std::uint8_t   max_captures{0};
};

// A square is blocked for landing iff it currently holds another piece.
// The moving piece's *original* square counts as empty (the piece has left
// it for the duration of the chain); captured pieces still block until the
// chain commits.
constexpr bool landing_blocked(const CaptureCtx& ctx, Square s) noexcept {
    return test(ctx.occ, s) && s != ctx.from_sq;
}

void emit_chain(CaptureCtx& ctx) {
    if (ctx.captured_count < ctx.max_captures) return;
    if (ctx.captured_count > ctx.max_captures) {
        ctx.out->clear();
        ctx.max_captures = ctx.captured_count;
    }
    Move m;
    m.from         = ctx.from_sq;
    m.to           = ctx.cur_sq;
    m.num_captures = ctx.captured_count;
    m.captured     = ctx.captured_bb;   // already maintained during the chain
    m.promotes = is_promotion_square(ctx.cur_sq, ctx.us);
    ctx.out->push(m);
}

void extend_man_captures(CaptureCtx& ctx) {
    bool extended = false;

    for (Dir d : ALL_DIRS) {
        const Square over = neighbour(ctx.cur_sq, d);
        if (over == NO_SQUARE) continue;
        if (!test(ctx.enemy_bb, over)) continue;
        if (test(ctx.captured_bb, over)) continue;

        const Square land = neighbour(over, d);
        if (land == NO_SQUARE) continue;
        if (landing_blocked(ctx, land)) continue;

        // Mark the capture, recurse, then undo.
        set(ctx.captured_bb, over);
        ++ctx.captured_count;
        const Square saved = ctx.cur_sq;
        ctx.cur_sq         = land;
        extended           = true;

        extend_man_captures(ctx);

        ctx.cur_sq = saved;
        --ctx.captured_count;
        clear(ctx.captured_bb, over);
    }

    if (!extended && ctx.captured_count > 0) emit_chain(ctx);
}

void extend_king_captures(CaptureCtx& ctx) {
    bool extended = false;

    for (Dir d : ALL_DIRS) {
        // Slide from cur_sq through empty squares until we hit a piece,
        // using the pre-computed king ray table.
        const KingRay& scan_ray = king_ray(ctx.cur_sq, d);
        for (std::uint8_t si = 0; si < scan_ray.length; ++si) {
            const Square scan = scan_ray.squares[si];
            // Friend (other than the piece's vacated origin) blocks this ray.
            if (test(ctx.friend_bb, scan) && scan != ctx.from_sq) break;
            // An enemy: capturable iff not already in the chain.
            if (test(ctx.enemy_bb, scan)) {
                if (test(ctx.captured_bb, scan)) break;  // blocked, not re-capture

                const Square over = scan;
                set(ctx.captured_bb, over);
                ++ctx.captured_count;

                // For each empty landing square strictly past `over`, recurse.
                const KingRay& land_ray = king_ray(over, d);
                for (std::uint8_t li = 0; li < land_ray.length; ++li) {
                    const Square land = land_ray.squares[li];
                    if (landing_blocked(ctx, land)) break;
                    const Square saved = ctx.cur_sq;
                    ctx.cur_sq         = land;
                    extended           = true;

                    extend_king_captures(ctx);

                    ctx.cur_sq = saved;
                }

                --ctx.captured_count;
                clear(ctx.captured_bb, over);
                break;  // No more captures possible past `over` in this dir.
            }
            // Empty square (or our own vacated origin): keep sliding.
        }
    }

    if (!extended && ctx.captured_count > 0) emit_chain(ctx);
}

void generate_captures(const Position& pos, MoveList& out) {
    BD_TIME(movegen_capture);
    CaptureCtx ctx{};
    ctx.us        = pos.side_to_move();
    ctx.friend_bb = pos.pieces_of(ctx.us);
    ctx.enemy_bb  = pos.pieces_of(opposite(ctx.us));
    ctx.occ       = ctx.friend_bb | ctx.enemy_bb;
    ctx.out       = &out;

    const Bitboard kings_us = pos.kings_of(ctx.us);

    // Pre-filter for man captures : compute the mask of squares that
    // are 1-step adjacent to at least one enemy piece. A friend man can
    // only START a capture from such a square, so iterating only over
    // `friend_men & enemy_reach` skips the dead-end extend_man_captures
    // calls that would just iterate over their 4 directions and find
    // nothing. Computed as O(1) bitboard ops via brick-layout-aware
    // `reach_all_dirs` (cf bitboard.hpp), replacing the iterate-and-set
    // loop that was ~4×popcount(enemy) ops.
    const Bitboard enemy_reach = reach_all_dirs(ctx.enemy_bb);

    Bitboard threat_men = pos.men_of(ctx.us) & enemy_reach;

    // Early-skip : when we have no kings and no man is adjacent to any
    // enemy, there is no possible capture in this position. Skip the
    // entire capture machinery.
    if (threat_men == 0 && kings_us == 0) return;

    while (threat_men) {
        const Square s = pop_lsb(threat_men);
        ctx.from_sq        = s;
        ctx.cur_sq         = s;
        ctx.captured_bb    = 0;
        ctx.captured_count = 0;
        extend_man_captures(ctx);
    }

    Bitboard kings = kings_us;
    while (kings) {
        const Square s = pop_lsb(kings);
        ctx.from_sq        = s;
        ctx.cur_sq         = s;
        ctx.captured_bb    = 0;
        ctx.captured_count = 0;
        extend_king_captures(ctx);
    }
}

void generate_quiet_moves(const Position& pos, MoveList& out) {
    BD_TIME(movegen_quiet);
    const Color    us  = pos.side_to_move();
    const Bitboard occ = pos.occupied();

    // Men step one square in their two forward directions. Bitboard-parallel :
    // shift the whole men set by each forward direction & empties to get ALL
    // destinations at once (skipping blocked/edge candidates), then recover the
    // source per move via the inverse-direction neighbour (UpLeft<->DownRight,
    // UpRight<->DownLeft). Equivalent moves to the per-piece loop (perft-exact).
    const Bitboard men   = pos.men_of(us);
    const Bitboard empty = ~occ & PLAYABLE_BB;
    const bool white = (us == Color::White);
    // (dest set, inverse dir to recover `from`) for the two forward directions.
    const Bitboard d0 = (white ? shift_nw(men) : shift_sw(men)) & empty;
    const Bitboard d1 = (white ? shift_ne(men) : shift_se(men)) & empty;
    const Dir inv0 = white ? Dir::DownRight : Dir::UpRight;   // inverse of NW / SW
    const Dir inv1 = white ? Dir::DownLeft  : Dir::UpLeft;    // inverse of NE / SE
    // Whole-set promotion split : a destination promotes iff it lands on the
    // mover's far row, so AND the dest set with the promo-row mask once and the
    // inner loop carries a constant `promotes` flag (no per-move row divide).
    const Bitboard promo = white ? WHITE_PROMO_BB : BLACK_PROMO_BB;
    auto emit_dests = [&](Bitboard dests, Dir inv) noexcept {
        for (Bitboard p = dests & promo; p; ) {
            const Square to = pop_lsb(p);
            Move m; m.from = neighbour(to, inv); m.to = to; m.promotes = true;
            out.push(m);
        }
        for (Bitboard q = dests & ~promo; q; ) {
            const Square to = pop_lsb(q);
            Move m; m.from = neighbour(to, inv); m.to = to; m.promotes = false;
            out.push(m);
        }
    };
    emit_dests(d0, inv0);
    emit_dests(d1, inv1);

    // Kings slide arbitrarily far along any of the four diagonals.
    // Uses the pre-computed king ray table to avoid the per-step
    // `neighbour()` lookup and NO_SQUARE check in the inner loop.
    Bitboard kings = pos.kings_of(us);
    while (kings) {
        const Square from = pop_lsb(kings);
        for (Dir d : ALL_DIRS) {
            const KingRay& ray = king_ray(from, d);
            for (std::uint8_t i = 0; i < ray.length; ++i) {
                const Square to = ray.squares[i];
                if (test(occ, to)) break;
                Move m;
                m.from = from;
                m.to   = to;
                out.push(m);
            }
        }
    }
}

}  // namespace

void generate_legal_moves(const Position& pos, MoveList& out) {
    out.clear();

    // generate_captures writes directly into `out`, keeping only max-length
    // chains via emit_chain's max_captures tracking. No second pass needed.
    generate_captures(pos, out);
    if (!out.empty()) return;

    generate_quiet_moves(pos, out);
}

}  // namespace jass
