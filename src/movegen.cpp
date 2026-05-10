// SPDX-License-Identifier: MIT
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

    Square         from_sq{NO_SQUARE};
    Square         cur_sq{NO_SQUARE};
    Bitboard       captured_bb{0};
    std::uint8_t   captured_count{0};
    std::array<Square, 20> captured_list{};

    MoveList* out{nullptr};
};

// A square is blocked for landing iff it currently holds another piece.
// The moving piece's *original* square counts as empty (the piece has left
// it for the duration of the chain); captured pieces still block until the
// chain commits.
constexpr bool landing_blocked(const CaptureCtx& ctx, Square s) noexcept {
    const Bitboard occ = ctx.friend_bb | ctx.enemy_bb;
    return test(occ, s) && s != ctx.from_sq;
}

void emit_chain(CaptureCtx& ctx) {
    Move m;
    m.from         = ctx.from_sq;
    m.to           = ctx.cur_sq;
    m.num_captures = ctx.captured_count;
    for (std::uint8_t i = 0; i < ctx.captured_count; ++i) {
        m.captures[i] = ctx.captured_list[i];
    }
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
        ctx.captured_list[ctx.captured_count++] = over;
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
        // Slide from cur_sq through empty squares until we hit a piece.
        Square scan = neighbour(ctx.cur_sq, d);
        while (scan != NO_SQUARE) {
            // Friend (other than the piece's vacated origin) blocks this ray.
            if (test(ctx.friend_bb, scan) && scan != ctx.from_sq) break;
            // An enemy: capturable iff not already in the chain.
            if (test(ctx.enemy_bb, scan)) {
                if (test(ctx.captured_bb, scan)) break;  // blocked, not re-capture

                const Square over = scan;
                set(ctx.captured_bb, over);
                ctx.captured_list[ctx.captured_count++] = over;

                // For each empty landing square strictly past `over`, recurse.
                Square land = neighbour(over, d);
                while (land != NO_SQUARE && !landing_blocked(ctx, land)) {
                    const Square saved = ctx.cur_sq;
                    ctx.cur_sq         = land;
                    extended           = true;

                    extend_king_captures(ctx);

                    ctx.cur_sq = saved;
                    land = neighbour(land, d);
                }

                --ctx.captured_count;
                clear(ctx.captured_bb, over);
                break;  // No more captures possible past `over` in this dir.
            }
            // Empty square (or our own vacated origin): keep sliding.
            scan = neighbour(scan, d);
        }
    }

    if (!extended && ctx.captured_count > 0) emit_chain(ctx);
}

void generate_captures(const Position& pos, MoveList& out) {
    CaptureCtx ctx{};
    ctx.us        = pos.side_to_move();
    ctx.friend_bb = pos.pieces_of(ctx.us);
    ctx.enemy_bb  = pos.pieces_of(opposite(ctx.us));
    ctx.out       = &out;

    Bitboard men = pos.men_of(ctx.us);
    while (men) {
        const Square s = pop_lsb(men);
        ctx.from_sq        = s;
        ctx.cur_sq         = s;
        ctx.captured_bb    = 0;
        ctx.captured_count = 0;
        extend_man_captures(ctx);
    }

    Bitboard kings = pos.kings_of(ctx.us);
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
    const Color    us  = pos.side_to_move();
    const Bitboard occ = pos.occupied();

    // Men step one square in their two forward directions.
    Bitboard men = pos.men_of(us);
    const auto fwd = man_forward_dirs(us);
    while (men) {
        const Square from = pop_lsb(men);
        for (Dir d : fwd) {
            const Square to = neighbour(from, d);
            if (to == NO_SQUARE) continue;
            if (test(occ, to)) continue;
            Move m;
            m.from     = from;
            m.to       = to;
            m.promotes = is_promotion_square(to, us);
            out.push(m);
        }
    }

    // Kings slide arbitrarily far along any of the four diagonals.
    Bitboard kings = pos.kings_of(us);
    while (kings) {
        const Square from = pop_lsb(kings);
        for (Dir d : ALL_DIRS) {
            Square cur = neighbour(from, d);
            while (cur != NO_SQUARE && !test(occ, cur)) {
                Move m;
                m.from = from;
                m.to   = cur;
                out.push(m);
                cur = neighbour(cur, d);
            }
        }
    }
}

}  // namespace

void generate_legal_moves(const Position& pos, MoveList& out) {
    out.clear();

    MoveList captures;
    generate_captures(pos, captures);

    if (!captures.empty()) {
        std::uint8_t max_n = 0;
        for (const auto& m : captures) {
            if (m.num_captures > max_n) max_n = m.num_captures;
        }
        for (const auto& m : captures) {
            if (m.num_captures == max_n) out.push(m);
        }
        return;
    }

    generate_quiet_moves(pos, out);
}

}  // namespace jass
