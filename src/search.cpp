// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "search.hpp"

#include "endgame.hpp"
#include "eval.hpp"
#include "nnue.hpp"
#include "tt.hpp"
#include "zobrist.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <thread>
#include <tuple>
#include <unordered_set>
#include <utility>
#include <vector>

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

    // Stack of Zobrist hashes representing the current path: the game
    // history prefix is loaded by `search()`, then negamax pushes/pops the
    // hash of each node as it descends and ascends.
    std::vector<ZobristHash> hash_path;

    // Time / external-stop control. `deadline` is meaningful only when
    // `has_deadline` is true; `stop_flag` may be null. Once `stopped` is
    // set, every subsequent search node short-circuits with a sentinel
    // value so the call stack unwinds quickly.
    std::chrono::steady_clock::time_point deadline{};
    bool                                  has_deadline{false};
    const std::atomic<bool>*              stop_flag{nullptr};
    bool                                  stopped{false};

    // Optional NNUE-style replacement for the handcrafted leaf evaluation.
    // Null means "use the static `evaluate()` function in eval.cpp".
    const INetwork*                       nnue{nullptr};

    // Set to true while a Null-Move Pruning probe is in progress, so
    // the recursive negamax doesn't try another null move on top
    // (which would converge to nonsense at deep enough chains).
    bool                                  was_null{false};

    int negamax    (const Position& pos, int depth, int ply, int alpha, int beta);
    int quiescence (const Position& pos,            int ply, int alpha, int beta);

    // Wrap the leaf eval so the rest of the code doesn't have to branch.
    int eval_leaf(const Position& pos) const noexcept {
        return nnue ? nnue->evaluate(pos) : evaluate(pos);
    }

    // Returns true if `h` already appears anywhere in `hash_path`.
    bool path_contains(ZobristHash h) const noexcept {
        for (auto x : hash_path) if (x == h) return true;
        return false;
    }

    // Polled at the start of every node; `stopped` becomes sticky.
    bool check_stop() noexcept {
        if (stopped) return true;
        if (stop_flag && stop_flag->load(std::memory_order_relaxed)) {
            stopped = true;
            return true;
        }
        if (has_deadline && std::chrono::steady_clock::now() >= deadline) {
            stopped = true;
            return true;
        }
        return false;
    }
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
    if (stopped) return 0;
    ++nodes;
    if ((nodes & 0x3FF) == 0 && check_stop()) return 0;

    MoveList moves;
    generate_legal_moves(pos, moves);
    if (moves.empty()) return -MATE_SCORE + ply;

    // generate_legal_moves either returns *all* maximum-length captures or
    // *all* quiet moves — never a mix. So a single check on the first move
    // tells us whether the position is calm.
    if (!moves[0].is_capture()) return eval_leaf(pos);

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
    if (stopped) return 0;
    // Hard ply cap so single-move extensions can't run off the end of the
    // killers / hash_path arrays.
    if (ply >= MAX_PLY) return eval_leaf(pos);
    ++nodes;
    // Polling time / external-stop is not free; throttle to once every
    // 1024 nodes. The first probe of every iteration also runs through
    // here because `nodes` was just bumped from 0 → 1 the very first time.
    if ((nodes & 0x3FF) == 0 && check_stop()) return 0;

    const ZobristHash hash = zobrist_hash(pos);

    // 0. Path-dependent draw detection. Path-dependent because it depends
    //    on which prior positions the search has visited, so we must not
    //    consult the TT for these answers.
    if (path_contains(hash))                        return 0;
    if (pos.halfmove_clock() >= FIFTY_MOVE_PLIES)   return 0;

    // 0bis. Endgame tablebase: positions with a known theoretical result
    //       skip the rest of the work. Like the path-dependent draws this
    //       answer is independent of the alpha-beta window.
    {
        const EndgameResult eg = probe_endgame(pos);
        if (eg == EndgameResult::Draw) return 0;
        if (eg == EndgameResult::WhiteWin) {
            return (pos.side_to_move() == Color::White)
                ?  (MATE_SCORE - MAX_PLY - 1)
                : -(MATE_SCORE - MAX_PLY - 1);
        }
        if (eg == EndgameResult::BlackWin) {
            return (pos.side_to_move() == Color::Black)
                ?  (MATE_SCORE - MAX_PLY - 1)
                : -(MATE_SCORE - MAX_PLY - 1);
        }
    }

    // 1. Probe TT.  A hit lets us cut the subtree if its stored bound is
    //    compatible with the current alpha-beta window; otherwise we still
    //    keep the suggested move for ordering.
    TTEntry tt_entry;
    bool    tt_hit  = tt->probe(hash, tt_entry);
    if (tt_hit && tt_entry.depth >= depth) {
        const int s = score_from_tt(tt_entry.score, ply);
        if (tt_entry.bound() == Bound::Exact)                    return s;
        if (tt_entry.bound() == Bound::Lower && s >= beta)       return s;
        if (tt_entry.bound() == Bound::Upper && s <= alpha)      return s;
    }

    // 2. Mate / leaf detection. At the horizon we hand off to quiescence
    //    so a forced capture pending at the leaf is not silently misvalued.
    MoveList moves;
    generate_legal_moves(pos, moves);
    if (moves.empty()) return -MATE_SCORE + ply;
    if (depth <= 0)    return quiescence(pos, ply, alpha, beta);

    // 2bis. Null-Move Pruning. If we can give the opponent a free
    //     move (no rule actually permits passing in draughts — this
    //     is purely a search technique) and the resulting reduced-
    //     depth search still beats beta, the current position is
    //     strong enough that we can cut without playing out its own
    //     subtree. Skipped in conditions where the technique is
    //     unsound or wasteful:
    //       - depth < 4: the saving is too small
    //       - already inside a null-move probe (no infinite chains)
    //       - beta is in the mate band (mate scores are absolute,
    //         not relative to the position's strength)
    //       - low material (<6 pieces): real zugzwang-like positions
    //         appear in king-and-pawn endgames where giving up a
    //         tempo legitimately loses
    //       - static eval already below beta: NMP can't possibly help
    {
        constexpr int NMP_MIN_DEPTH  = 4;
        constexpr int NMP_MIN_PIECES = 6;
        if (depth >= NMP_MIN_DEPTH
            && !was_null
            && !is_mate_score(beta)) {
            const Bitboard all = pos.white_men() | pos.white_kings()
                               | pos.black_men() | pos.black_kings();
            if (popcount(all) >= NMP_MIN_PIECES) {
                const int eval = eval_leaf(pos);
                if (eval >= beta) {
                    const int R          = 2 + depth / 4;
                    const int reduced    = depth - 1 - R;
                    const int safe_depth = reduced < 1 ? 1 : reduced;
                    const Position null_pos = pos.after_null();
                    was_null = true;
                    const int null_score = -negamax(null_pos, safe_depth, ply + 1,
                                                    -beta, -beta + 1);
                    was_null = false;
                    if (!stopped && null_score >= beta) {
                        return beta;
                    }
                }
            }
        }
    }

    // 3. Move ordering: TT-suggested move first, then killers, then a
    //    history-driven order on the remaining quiet moves. The TT only
    //    stores a `PackedMove`, so we resolve it against the actual
    //    legal-move list to recover the full move with its capture path.
    Move tt_move{};
    bool tt_move_valid = false;
    if (tt_hit) {
        for (const auto& m : moves) {
            if (same_packed_move(m, tt_entry.best_move)) {
                tt_move       = m;
                tt_move_valid = true;
                break;
            }
        }
    }
    order_moves(moves, *this, ply, tt_move, tt_move_valid);

    // 4. Search.
    const int alpha_orig = alpha;
    int       best       = -INF_SCORE;
    Move      best_move  = moves[0];

    hash_path.push_back(hash);

    // 4bis. Singular extension. If the TT entry says one move scores at
    //     least `tt_entry.score`, a quick verification search at half
    //     depth confirms whether the other moves can match it. When
    //     they all fall short by a margin, the TT move is "singular" —
    //     we extend its depth by one ply so the main loop spends more
    //     effort on what is likely the only good continuation.
    //
    // Constants chosen conservatively for draughts (tuned for chess
    // first, retuned by ear here):
    //   - Min depth 8 — extending shallow searches just bloats nodes
    //     without finding new tactics.
    //   - TT entry must be at least `depth - 3` so its score is
    //     trustworthy.
    //   - Margin scales with depth so cuts near mate scores still
    //     make sense.
    //   - Reduced depth = (depth - 1) / 2.
    constexpr int SINGULAR_MIN_DEPTH = 8;
    constexpr int SINGULAR_MARGIN    = 2;  // centipawns per ply of depth
    int  singular_ext = 0;
    if (tt_hit && tt_move_valid
        && depth >= SINGULAR_MIN_DEPTH
        && tt_entry.depth >= depth - 3
        && tt_entry.bound() != Bound::Upper
        && !is_mate_score(score_from_tt(tt_entry.score, ply))) {
        const int singular_beta  = score_from_tt(tt_entry.score, ply)
                                 - SINGULAR_MARGIN * depth;
        const int singular_depth = (depth - 1) / 2;

        int verify_best  = -INF_SCORE;
        int verify_alpha = singular_beta - 1;
        for (const auto& m : moves) {
            if (same_packed_move(m, tt_entry.best_move)) continue;  // exclude TT move
            const Position next = pos.after(m);
            const int      s    = -negamax(next, singular_depth - 1, ply + 1,
                                           -singular_beta, -verify_alpha);
            if (s > verify_best) verify_best = s;
            if (verify_best >= singular_beta) break;
            if (verify_best > verify_alpha)   verify_alpha = verify_best;
            if (stopped) break;
        }
        if (!stopped && verify_best < singular_beta) {
            singular_ext = 1;
        }
    }

    // 4bis. Late Move Reductions. After the first few moves (TT-move,
    //     killers, and the head of the history-sorted tail), search the
    //     remaining quiet moves at a reduced depth first. If the reduced
    //     search unexpectedly returns above alpha, re-search at full
    //     depth — same tree as without LMR but the reduction pre-empts
    //     unnecessary deep searches on uninteresting moves.
    //
    //     Skipped for:
    //       - the TT-move (always full depth — it's the best guess)
    //       - captures (in FMJD draughts the majority-capture rule
    //         already forces them when present; they are tactically
    //         decisive)
    //       - shallow nodes (depth < 3 — LMR overhead exceeds saving)
    //       - the first few moves of the ordering (i < 4)
    constexpr int LMR_MIN_DEPTH       = 3;
    constexpr int LMR_FIRST_FULL_MOVES = 4;
    auto lmr_reduction = [](int d, int move_idx) noexcept -> int {
        // Simple monotone formula: ~1 ply at low depth/index, ~3 plies
        // at depth ≥ 12 with index ≥ 16. Capped so the reduced depth
        // stays ≥ 1.
        if (d < LMR_MIN_DEPTH || move_idx < LMR_FIRST_FULL_MOVES) return 0;
        int r = 1 + d / 6 + move_idx / 8;
        return r < 1 ? 1 : (r > d - 2 ? d - 2 : r);
    };

    int move_idx = 0;
    for (const auto& m : moves) {
        const Position next      = pos.after(m);
        const bool     is_tt     = tt_move_valid
                                 && same_packed_move(m, tt_entry.best_move);
        const int      new_depth = depth - 1 + (singular_ext && is_tt ? 1 : 0);

        int score;
        const bool do_lmr = move_idx >= LMR_FIRST_FULL_MOVES
                         && depth >= LMR_MIN_DEPTH
                         && !is_tt
                         && !m.is_capture()
                         && !singular_ext;  // don't reduce when we just extended a singular line
        if (do_lmr) {
            const int r = lmr_reduction(depth, move_idx);
            const int reduced = new_depth - r;
            score = -negamax(next, reduced, ply + 1, -beta, -alpha);
            if (score > alpha && score < beta) {
                // Tail move surprised — re-search at full depth so its
                // exact score is established before we accept it.
                score = -negamax(next, new_depth, ply + 1, -beta, -alpha);
            }
        } else {
            score = -negamax(next, new_depth, ply + 1, -beta, -alpha);
        }

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
        ++move_idx;
    }

    hash_path.pop_back();

    // 5. Store back into the TT — but only if the result is real. An
    //    aborted search produced a placeholder score that would poison
    //    the table.
    if (!stopped) {
        Bound bound;
        if      (best >= beta)      bound = Bound::Lower;
        else if (best > alpha_orig) bound = Bound::Exact;
        else                        bound = Bound::Upper;

        tt->store(hash, pack_move(best_move),
                  score_to_tt(best, ply), depth, bound);
    }
    return best;
}

}  // namespace

std::vector<Move> extract_pv(const Position& start,
                             const TranspositionTable& tt,
                             int max_len) {
    std::vector<Move> pv;
    pv.reserve(static_cast<std::size_t>(max_len));

    Position pos = start;
    std::unordered_set<ZobristHash> seen;
    seen.reserve(static_cast<std::size_t>(max_len));

    while (static_cast<int>(pv.size()) < max_len) {
        const ZobristHash h = zobrist_hash(pos);
        if (!seen.insert(h).second) break;  // cycle

        TTEntry e;
        if (!tt.probe(h, e))            break;
        if (e.bound() != Bound::Exact)  break;

        // Defensive: confirm the stored move is still legal in the current
        // position (a hash collision on a stale entry could otherwise have
        // us emit nonsense). The TT only carries a `PackedMove`, so we
        // also recover the full Move with its capture path here.
        MoveList legal;
        generate_legal_moves(pos, legal);
        const Move* found = nullptr;
        for (const auto& m : legal) {
            if (same_packed_move(m, e.best_move)) { found = &m; break; }
        }
        if (!found) break;

        pv.push_back(*found);
        pos = pos.after(*found);
    }
    return pv;
}

SearchResult search(const Position& pos, const SearchLimits& limits) {
    TranspositionTable tt;
    tt.resize_mb(limits.tt_mb);
    return search(pos, limits, tt, {});
}

SearchResult search(const Position& pos, const SearchLimits& limits,
                    TranspositionTable& tt) {
    return search(pos, limits, tt, {});
}

namespace {

// Aspiration windows: from depth 3 onward we frame the next search with a
// narrow window centred on the previous iteration's score, then widen
// progressively on every fail-high or fail-low until the search returns a
// score inside the window. Saves nodes when iteration-to-iteration scores
// barely move, which is the common case in quiet positions.
inline constexpr int ASPIRATION_INITIAL = 50;

}  // namespace

SearchResult search(const Position& pos, const SearchLimits& limits,
                    TranspositionTable& tt,
                    const std::vector<ZobristHash>& game_history) {
    SearchResult res;

    // Bump the TT generation so entries written during this search are
    // protected from being clobbered by stale data left over from
    // previous moves of the same game (the engine keeps the TT alive
    // across `apply_move`). Old-generation entries become preferred
    // replacement targets without losing their probe usefulness.
    tt.new_search();

    // Top-level draw checks: they short-circuit the entire iterative
    // deepening because the same draw would otherwise be re-derived inside
    // negamax for every depth.
    const ZobristHash root_hash = zobrist_hash(pos);
    for (auto h : game_history) {
        if (h == root_hash) {
            res.score = 0;
            return res;
        }
    }
    if (pos.halfmove_clock() >= FIFTY_MOVE_PLIES) {
        res.score = 0;
        return res;
    }
    {
        const EndgameResult eg = probe_endgame(pos);
        if (eg == EndgameResult::Draw) {
            res.score = 0;
            return res;
        }
        // For WIN/LOSS at the root we still need to actually pick a move,
        // so we don't short-circuit; the search will propagate the
        // bitbase value up from the children at depth >= 1.
    }

    MoveList root_moves;
    generate_legal_moves(pos, root_moves);
    if (root_moves.empty()) {
        res.score = -MATE_SCORE;
        return res;
    }

    Searcher s;
    s.tt        = &tt;
    s.hash_path = game_history;
    s.hash_path.push_back(root_hash);  // root is an ancestor for its children
    s.stop_flag = limits.stop_flag;
    s.nnue      = limits.nnue;
    if (limits.movetime_ms > 0) {
        s.has_deadline = true;
        s.deadline = std::chrono::steady_clock::now()
                   + std::chrono::milliseconds(limits.movetime_ms);
    }

    // ---------------------------------------------------------------------
    // Lazy SMP fan-out
    // ---------------------------------------------------------------------
    // Helper threads run an independent single-threaded `search` against
    // the same shared `tt`. They never report a result; their job is to
    // keep transposition entries flowing in for the main search. The TT
    // is accessed without locks: races may yield the occasional stale
    // entry but the search is self-correcting (move-legality is verified
    // on use, scores are merely hints).
    std::atomic<bool>          helper_stop{false};
    std::vector<std::thread>   helpers;
    if (limits.threads > 1) {
        helpers.reserve(static_cast<std::size_t>(limits.threads - 1));
        const INetwork* nnue_for_helpers = limits.nnue;
        for (int i = 1; i < limits.threads; ++i) {
            helpers.emplace_back([&pos, &game_history, &tt, &helper_stop,
                                  max_depth = limits.max_depth,
                                  nnue_for_helpers]() {
                SearchLimits hlim;
                hlim.max_depth = max_depth;
                hlim.stop_flag = &helper_stop;
                hlim.threads   = 1;  // critical: helpers must not fork further
                hlim.nnue      = nnue_for_helpers;
                (void)::jass::search(pos, hlim, tt, game_history);
            });
        }
    }
    auto stop_helpers = [&]() {
        helper_stop.store(true, std::memory_order_relaxed);
        for (auto& t : helpers) if (t.joinable()) t.join();
    };

    Move best_overall = root_moves[0];
    int  best_score   = -INF_SCORE;

    // Recent score history (max 4 last iterations), used for *adaptive*
    // aspiration: the next iteration's initial window width adapts to
    // the volatility of the last few iteration scores.
    std::vector<int> score_history;

    // One iteration of the root loop, run inside the aspiration retry loop
    // below. Returns (best move, best score) found within [alpha, beta].
    auto run_root_window = [&](int depth, int alpha, int beta)
        -> std::pair<Move, int> {
        Move iter_best  = root_moves[0];
        int  iter_score = -INF_SCORE;
        int  cur_alpha  = alpha;

        for (const auto& m : root_moves) {
            if (s.stopped) break;
            const Position next  = pos.after(m);
            const int      score = -s.negamax(next, depth - 1, 1,
                                              -beta, -cur_alpha);
            if (score > iter_score) {
                iter_score = score;
                iter_best  = m;
            }
            if (iter_score > cur_alpha) cur_alpha = iter_score;
            if (cur_alpha >= beta) break;  // beta cut-off (narrow window)
        }
        return {iter_best, iter_score};
    };

    for (int depth = 1; depth <= limits.max_depth; ++depth) {
        // Honour an early stop request before spending any work on this
        // iteration. The previous iteration's `best_overall` is returned.
        if (depth > 1 && s.check_stop()) break;

        if (depth > 1) hoist_move(root_moves, best_overall);

        // Pick the initial [alpha, beta] window. Shallow depths and any
        // iteration following a mate score fall back to the full window
        // because narrow aspiration is unhelpful there.  When we do use a
        // narrow window, its half-width adapts to the largest absolute
        // score swing across the recent iterations: if scores have been
        // stable, we open a tight window; if they've been jumpy, we
        // pre-emptively widen it.
        int alpha, beta, delta;
        if (depth < 3 || is_mate_score(best_score)) {
            alpha = -INF_SCORE;
            beta  =  INF_SCORE;
            delta =  INF_SCORE;
        } else {
            int volatility = 0;
            for (std::size_t i = 1; i < score_history.size(); ++i) {
                const int diff = std::abs(score_history[i] - score_history[i - 1]);
                if (diff > volatility) volatility = diff;
            }
            delta = std::max(ASPIRATION_INITIAL, 2 * volatility);
            alpha = best_score - delta;
            beta  = best_score + delta;
        }

        Move iter_best;
        int  iter_score = 0;
        while (true) {
            std::tie(iter_best, iter_score) = run_root_window(depth, alpha, beta);
            if (s.stopped) break;  // discard incomplete window

            if (iter_score <= alpha && alpha > -INF_SCORE) {
                alpha = std::max(alpha - delta, -INF_SCORE);
                if (delta < INF_SCORE / 2) delta *= 2;
                continue;
            }
            if (iter_score >= beta && beta < INF_SCORE) {
                beta = std::min(beta + delta, INF_SCORE);
                if (delta < INF_SCORE / 2) delta *= 2;
                continue;
            }
            break;
        }

        // Discard any iteration that didn't finish; the previous
        // `best_overall` / `best_score` / `res.depth` remain in effect.
        if (s.stopped && depth > 1) break;

        best_overall = iter_best;
        best_score   = iter_score;
        res.depth    = depth;

        tt.store(root_hash, pack_move(iter_best),
                 score_to_tt(iter_score, /*ply=*/0),
                 depth, Bound::Exact);

        // Track recent scores for the adaptive-aspiration heuristic above.
        score_history.push_back(iter_score);
        constexpr std::size_t HISTORY_LEN = 4;
        if (score_history.size() > HISTORY_LEN) {
            score_history.erase(score_history.begin());
        }
    }

    stop_helpers();

    res.best_move = best_overall;
    res.score     = best_score;
    res.nodes     = s.nodes;
    res.pv        = extract_pv(pos, tt, std::max(res.depth, 1));
    return res;
}

}  // namespace jass
