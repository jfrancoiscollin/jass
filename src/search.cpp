// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "search.hpp"

#include "eval.hpp"
#include "tt.hpp"
#include "zobrist.hpp"

#include <algorithm>
#include <array>

namespace jass {

namespace {

// Mate-score handling for the transposition table.
//
// Inside the search a "mate-loss for STM at distance d" is encoded as
// `-MATE_SCORE + ply + d` and "mate-win in d plies" as
// `MATE_SCORE - (ply + d)`. The `ply` term is search-tree relative and would
// poison cross-iteration reuse, so before storing we strip it and add it
// back on probe.
inline constexpr int MATE_BOUND = MATE_SCORE - MAX_PLY;

inline int score_to_tt(int score, int ply) noexcept {
    if (score >  MATE_BOUND) return score + ply;
    if (score < -MATE_BOUND) return score - ply;
    return score;
}

inline int score_from_tt(int score, int ply) noexcept {
    if (score >  MATE_BOUND) return score - ply;
    if (score < -MATE_BOUND) return score + ply;
    return score;
}

// Hoist `priority` to the front of `moves` if present, so it is searched
// first. Used both at the root (previous-iteration best) and inside the
// recursion (TT-suggested move).
inline void hoist_move(MoveList& moves, const Move& priority) {
    for (std::size_t i = 0; i < moves.size(); ++i) {
        if (moves[i] == priority) {
            if (i != 0) std::swap(moves[0], moves[i]);
            return;
        }
    }
}

// Move-ordering aids reset between top-level searches.
//
// Killer moves: at each ply we remember up to two *quiet* moves that
// recently caused a beta cutoff. They are tried right after the TT-suggested
// move because they tend to refute many sibling positions too.
//
// History heuristic: a flat from/to table accumulates a depth^2 bonus every
// time a quiet move causes a beta cutoff. Quiet moves with the highest
// history are tried first among the rest.
struct Searcher {
    TranspositionTable* tt{nullptr};
    std::uint64_t       nodes{0};

    std::array<std::array<Move, 2>, MAX_PLY + 1>                       killers{};
    std::array<std::array<int,  NUM_SQUARES + 1>, NUM_SQUARES + 1>     history{};

    int negamax    (const Position& pos, int depth, int ply, int alpha, int beta);
    int quiescence (const Position& pos,            int ply, int alpha, int beta);
};

// Score used to sort the move list. Larger = tried first.
inline int order_score(const Searcher& s, const Move& m, int ply,
                       const Move& tt_move, bool tt_hit) noexcept {
    if (tt_hit && m == tt_move) return 1'000'000;
    if (m.is_capture())          return 0;            // captures: keep generation order
    if (m == s.killers[static_cast<std::size_t>(ply)][0])  return   800'000;
    if (m == s.killers[static_cast<std::size_t>(ply)][1])  return   700'000;
    return s.history[m.from][m.to];
}

// Sort moves in place, descending by `order_score`. Selection sort: the move
// list is small (~30 in the worst case) and an in-place ordering keeps the
// hot loop cache-friendly.
inline void order_moves(MoveList& moves, const Searcher& s, int ply,
                        const Move& tt_move, bool tt_hit) {
    std::array<int, 256> scores;  // populated for [0, n) before any read
    const std::size_t n = moves.size();
    for (std::size_t i = 0; i < n; ++i) {
        scores[i] = order_score(s, moves[i], ply, tt_move, tt_hit);
    }
    for (std::size_t i = 0; i < n; ++i) {
        std::size_t best = i;
        for (std::size_t j = i + 1; j < n; ++j) {
            if (scores[j] > scores[best]) best = j;
        }
        if (best != i) {
            std::swap(moves[i],  moves[best]);
            std::swap(scores[i], scores[best]);
        }
    }
}

// Quiescence: at the search horizon, only mandatory capture chains are
// played out. International draughts forbids "stand pat with a capture
// available" by rule, so the implementation is unusually direct: if there
// are captures we must play one; otherwise the position is calm and we
// return the static eval.
int Searcher::quiescence(const Position& pos, int ply, int alpha, int beta) {
    ++nodes;

    MoveList moves;
    generate_legal_moves(pos, moves);
    if (moves.empty()) return -MATE_SCORE + ply;

    // generate_legal_moves either returns *all* maximum-length captures or
    // *all* quiet moves — never a mix. So a single check on the first move
    // tells us whether the position is calm.
    if (!moves[0].is_capture()) return evaluate(pos);

    int best = -INF_SCORE;
    for (const auto& m : moves) {
        const Position next  = pos.after(m);
        const int      score = -quiescence(next, ply + 1, -beta, -alpha);
        if (score > best) best = score;
        if (best > alpha) alpha = best;
        if (alpha >= beta) break;  // beta cut-off
    }
    return best;
}

int Searcher::negamax(const Position& pos, int depth, int ply,
                      int alpha, int beta) {
    ++nodes;

    const ZobristHash hash = zobrist_hash(pos);

    // 1. Probe TT.  A hit lets us cut the subtree if its stored bound is
    //    compatible with the current alpha-beta window; otherwise we still
    //    keep the suggested move for ordering.
    TTEntry tt_entry;
    bool    tt_hit  = tt->probe(hash, tt_entry);
    Move    tt_move{};
    if (tt_hit) {
        tt_move = tt_entry.best_move;
        if (tt_entry.depth >= depth) {
            const int s = score_from_tt(tt_entry.score, ply);
            if (tt_entry.bound == Bound::Exact)                    return s;
            if (tt_entry.bound == Bound::Lower && s >= beta)       return s;
            if (tt_entry.bound == Bound::Upper && s <= alpha)      return s;
        }
    }

    // 2. Mate / leaf detection. At the horizon we hand off to quiescence
    //    so a forced capture pending at the leaf is not silently misvalued.
    MoveList moves;
    generate_legal_moves(pos, moves);
    if (moves.empty()) return -MATE_SCORE + ply;
    if (depth <= 0)    return quiescence(pos, ply, alpha, beta);

    // 3. Move ordering: TT-suggested move first, then killers, then a
    //    history-driven order on the remaining quiet moves.
    order_moves(moves, *this, ply, tt_move, tt_hit);

    // 4. Search.
    const int alpha_orig = alpha;
    int       best       = -INF_SCORE;
    Move      best_move  = moves[0];

    for (const auto& m : moves) {
        const Position next  = pos.after(m);
        const int      score = -negamax(next, depth - 1, ply + 1, -beta, -alpha);
        if (score > best) {
            best      = score;
            best_move = m;
        }
        if (best > alpha) alpha = best;
        if (alpha >= beta) {
            // Beta cutoff: reward the move that produced it. Captures aren't
            // tracked because the legal-move generator already orders them
            // implicitly (every legal move at a capture node has the same
            // length under the FMJD majority rule).
            if (!m.is_capture() && ply <= MAX_PLY) {
                if (!(m == killers[static_cast<std::size_t>(ply)][0])) {
                    killers[static_cast<std::size_t>(ply)][1] = killers[static_cast<std::size_t>(ply)][0];
                    killers[static_cast<std::size_t>(ply)][0] = m;
                }
                history[m.from][m.to] += depth * depth;
            }
            break;
        }
    }

    // 5. Store back into the TT with the appropriate bound flag.
    Bound bound;
    if      (best >= beta)      bound = Bound::Lower;
    else if (best > alpha_orig) bound = Bound::Exact;
    else                        bound = Bound::Upper;

    tt->store(hash, best_move, score_to_tt(best, ply), depth, bound);
    return best;
}

}  // namespace

SearchResult search(const Position& pos, const SearchLimits& limits) {
    TranspositionTable tt;
    tt.resize_mb(limits.tt_mb);
    return search(pos, limits, tt);
}

SearchResult search(const Position& pos, const SearchLimits& limits,
                    TranspositionTable& tt) {
    SearchResult res;

    MoveList root_moves;
    generate_legal_moves(pos, root_moves);
    if (root_moves.empty()) {
        res.score = -MATE_SCORE;
        return res;
    }

    Searcher s;
    s.tt = &tt;

    Move best_overall = root_moves[0];
    int  best_score   = -INF_SCORE;

    const ZobristHash root_hash = zobrist_hash(pos);

    for (int depth = 1; depth <= limits.max_depth; ++depth) {
        if (depth > 1) hoist_move(root_moves, best_overall);

        Move      iter_best  = root_moves[0];
        int       iter_score = -INF_SCORE;
        int       alpha      = -INF_SCORE;
        const int beta       =  INF_SCORE;

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

        // The root window is full so the iteration result is exact; this
        // primes the TT so the next iteration starts with the prior best
        // move directly via the standard probe path.
        tt.store(root_hash, iter_best,
                 score_to_tt(iter_score, /*ply=*/0),
                 depth, Bound::Exact);
    }

    res.best_move = best_overall;
    res.score     = best_score;
    res.nodes     = s.nodes;
    return res;
}

}  // namespace jass
