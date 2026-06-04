// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "search.hpp"
#include "eval.hpp"

#include <algorithm>
#include <chrono>
#include <limits>

namespace othello {

namespace {

constexpr int INF = std::numeric_limits<int>::max() / 2;

struct SearchCtx {
    std::function<int(const Board&)> evaluator;
    std::uint64_t nodes = 0;
    std::chrono::steady_clock::time_point deadline;
    bool time_limited = false;
    bool aborted = false;

    bool past_deadline() noexcept {
        if (!time_limited) return false;
        // Check every 1024 nodes to amortise the clock call.
        if ((nodes & 1023) != 0) return aborted;
        if (std::chrono::steady_clock::now() >= deadline) aborted = true;
        return aborted;
    }
};

// Simple move ordering : try corners first, then non-X squares, then
// the rest. X-squares (adjacent diagonals to empty corners) and C-squares
// are typically bad ; we don't penalise yet but corners-first is cheap
// and useful.
inline int move_order_key(Square sq) noexcept {
    const Bitboard bit = Bitboard{1} << sq;
    constexpr Bitboard CORNERS =
          (Bitboard{1} << 0)  | (Bitboard{1} << 7)
        | (Bitboard{1} << 56) | (Bitboard{1} << 63);
    if (bit & CORNERS) return 0;   // try first
    // Edge squares next (excluding corners).
    constexpr Bitboard EDGES =
          0x00000000000000FFULL | 0xFF00000000000000ULL    // top + bot rows
        | 0x0101010101010101ULL | 0x8080808080808080ULL;   // left + right cols
    if (bit & EDGES) return 1;
    return 2;
}

int negamax(Board b, int depth, int alpha, int beta, SearchCtx& ctx) {
    ++ctx.nodes;

    if (b.is_game_over()) {
        return terminal_score(b);
    }
    if (depth <= 0) {
        return ctx.evaluator(b);
    }
    if (ctx.past_deadline()) return ctx.evaluator(b);

    MoveList ml;
    generate_legal_moves(b, ml);

    if (ml.empty()) {
        // Pass : flip side, recurse with same depth (no work done by stm).
        Board after = b;
        apply_move(after, NO_SQUARE);
        if (after.is_game_over()) return terminal_score(after);
        return -negamax(after, depth, -beta, -alpha, ctx);
    }

    // Move ordering : sort copy of move list by static key.
    std::array<Square, MAX_LEGAL_MOVES> ordered{};
    for (std::size_t i = 0; i < ml.size(); ++i) ordered[i] = ml[i];
    std::sort(ordered.begin(), ordered.begin() + ml.size(),
              [](Square a, Square c) {
                  return move_order_key(a) < move_order_key(c);
              });

    int best = -INF;
    for (std::size_t i = 0; i < ml.size(); ++i) {
        Board after = b;
        apply_move(after, ordered[i]);
        const int score = -negamax(after, depth - 1, -beta, -alpha, ctx);
        if (ctx.aborted) return best == -INF ? ctx.evaluator(b) : best;
        if (score > best) best = score;
        if (best > alpha) alpha = best;
        if (alpha >= beta) break;  // beta cutoff
    }
    return best;
}

}  // namespace

SearchResult search(const Board& root, const SearchConfig& cfg) {
    SearchCtx ctx;
    ctx.evaluator = cfg.evaluator ? cfg.evaluator
                                  : [](const Board& b) { return eval_basic(b); };
    if (cfg.max_time_ms > 0) {
        ctx.time_limited = true;
        ctx.deadline = std::chrono::steady_clock::now()
                     + std::chrono::milliseconds(cfg.max_time_ms);
    }

    SearchResult result;
    if (root.is_game_over()) {
        result.score = terminal_score(root);
        return result;
    }

    MoveList ml;
    generate_legal_moves(root, ml);
    if (ml.empty()) {
        // Root must pass.
        result.best_move = NO_SQUARE;
        Board after = root;
        apply_move(after, NO_SQUARE);
        result.score = -ctx.evaluator(after);
        return result;
    }

    // Iterative deepening : 1..max_depth. Best move from the deepest
    // completed iteration. If time runs out mid-iteration, fall back
    // to the last completed.
    Square best_completed = ml[0];
    int    score_completed = -INF;

    for (int depth = 1; depth <= cfg.max_depth; ++depth) {
        std::array<Square, MAX_LEGAL_MOVES> ordered{};
        for (std::size_t i = 0; i < ml.size(); ++i) ordered[i] = ml[i];
        std::sort(ordered.begin(), ordered.begin() + ml.size(),
                  [](Square a, Square c) {
                      return move_order_key(a) < move_order_key(c);
                  });

        int    iter_best  = -INF;
        Square iter_move  = ml[0];
        int    alpha      = -INF;
        int    beta       =  INF;
        bool   incomplete = false;

        for (std::size_t i = 0; i < ml.size(); ++i) {
            Board after = root;
            apply_move(after, ordered[i]);
            const int score = -negamax(after, depth - 1, -beta, -alpha, ctx);
            if (ctx.aborted) { incomplete = true; break; }
            if (score > iter_best) {
                iter_best = score;
                iter_move = ordered[i];
            }
            if (iter_best > alpha) alpha = iter_best;
        }

        if (!incomplete) {
            best_completed  = iter_move;
            score_completed = iter_best;
            result.depth_reached = depth;
        } else {
            break;
        }
    }

    result.best_move = best_completed;
    result.score     = score_completed;
    result.nodes     = ctx.nodes;
    return result;
}

}  // namespace othello
