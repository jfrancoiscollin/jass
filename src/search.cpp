// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "search.hpp"

#include "eval.hpp"

namespace jass {

namespace {

struct Searcher {
    std::uint64_t nodes{0};

    int negamax(const Position& pos, int depth, int ply, int alpha, int beta);
};

int Searcher::negamax(const Position& pos, int depth, int ply,
                      int alpha, int beta) {
    ++nodes;

    MoveList moves;
    generate_legal_moves(pos, moves);
    if (moves.empty()) {
        // No legal moves: the side to move has lost. Prefer longer survival
        // / shorter wins by encoding distance-to-mate via the ply offset.
        return -MATE_SCORE + ply;
    }
    if (depth <= 0) {
        return evaluate(pos);
    }

    int best = -INF_SCORE;
    for (const auto& m : moves) {
        const Position next  = pos.after(m);
        const int      score = -negamax(next, depth - 1, ply + 1, -beta, -alpha);
        if (score > best) best = score;
        if (best > alpha) alpha = best;
        if (alpha >= beta) break;  // beta cut-off
    }
    return best;
}

}  // namespace

SearchResult search(const Position& pos, const SearchLimits& limits) {
    SearchResult res;

    MoveList root_moves;
    generate_legal_moves(pos, root_moves);
    if (root_moves.empty()) {
        res.score = -MATE_SCORE;
        return res;
    }

    Searcher s;
    Move     best_overall = root_moves[0];
    int      best_score   = -INF_SCORE;

    for (int depth = 1; depth <= limits.max_depth; ++depth) {
        Move iter_best  = root_moves[0];
        int  iter_score = -INF_SCORE;
        int  alpha      = -INF_SCORE;
        const int beta  =  INF_SCORE;

        // Try the previous-iteration best move first, when present in the
        // legal-move list, so the alpha-beta window tightens early.
        for (std::size_t i = 0; i < root_moves.size(); ++i) {
            if (depth > 1 && root_moves[i] == best_overall && i != 0) {
                std::swap(root_moves[0], root_moves[i]);
                break;
            }
        }

        for (const auto& m : root_moves) {
            const Position next  = pos.after(m);
            const int      score = -s.negamax(next, depth - 1, 1, -beta, -alpha);
            if (score > iter_score) {
                iter_score = score;
                iter_best  = m;
            }
            if (iter_score > alpha) alpha = iter_score;
        }

        best_overall = iter_best;
        best_score   = iter_score;
        res.depth    = depth;
    }

    res.best_move = best_overall;
    res.score     = best_score;
    res.nodes     = s.nodes;
    return res;
}

}  // namespace jass
