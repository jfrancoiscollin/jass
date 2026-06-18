// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "search.hpp"

#include <cstdlib>

#include "bd_time.hpp"
#include "egdb_bridge.hpp"
#include "endgame.hpp"
#include "eval.hpp"
#include "nnue.hpp"
#include "nnue_accumulator.hpp"
#include "scan_eval.hpp"
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

void breakdown_reset() noexcept {
#ifdef JASS_TIME_BREAKDOWN
    bd::g_eval_ns.store(0,             std::memory_order_relaxed);
    bd::g_movegen_ns.store(0,          std::memory_order_relaxed);
    bd::g_apply_ns.store(0,            std::memory_order_relaxed);
    bd::g_accumulator_ns.store(0,      std::memory_order_relaxed);
    bd::g_tt_ns.store(0,               std::memory_order_relaxed);
    bd::g_zobrist_ns.store(0,          std::memory_order_relaxed);
    bd::g_movegen_capture_ns.store(0,  std::memory_order_relaxed);
    bd::g_movegen_quiet_ns.store(0,    std::memory_order_relaxed);
    bd::g_move_ordering_ns.store(0,    std::memory_order_relaxed);
    bd::g_path_check_ns.store(0,       std::memory_order_relaxed);
    bd::g_total_ns.store(0,            std::memory_order_relaxed);
    bd::g_total_started.store(bd::now_ns(), std::memory_order_relaxed);
#endif
}

BreakdownStats breakdown_snapshot() noexcept {
    BreakdownStats s;
#ifdef JASS_TIME_BREAKDOWN
    s.eval_ns             = bd::g_eval_ns.load(std::memory_order_relaxed);
    s.movegen_ns          = bd::g_movegen_ns.load(std::memory_order_relaxed);
    s.apply_ns            = bd::g_apply_ns.load(std::memory_order_relaxed);
    s.accumulator_ns      = bd::g_accumulator_ns.load(std::memory_order_relaxed);
    s.tt_ns               = bd::g_tt_ns.load(std::memory_order_relaxed);
    s.zobrist_ns          = bd::g_zobrist_ns.load(std::memory_order_relaxed);
    s.movegen_capture_ns  = bd::g_movegen_capture_ns.load(std::memory_order_relaxed);
    s.movegen_quiet_ns    = bd::g_movegen_quiet_ns.load(std::memory_order_relaxed);
    s.move_ordering_ns    = bd::g_move_ordering_ns.load(std::memory_order_relaxed);
    s.path_check_ns       = bd::g_path_check_ns.load(std::memory_order_relaxed);
    const auto t0 = bd::g_total_started.load(std::memory_order_relaxed);
    s.total_ns       = (t0 == 0) ? 0 : (bd::now_ns() - t0);
#endif
    return s;
}

namespace {

// Movegen wrapper, used in search call sites so the breakdown
// instrumentation captures movegen time. The handful of out-of-search
// movegen consumers (root setup, etc.) call `generate_legal_moves`
// directly so the timer doesn't account for non-search overhead.
inline void gen_moves(const Position& pos, MoveList& moves) noexcept {
    BD_TIME(movegen);
    generate_legal_moves(pos, moves);
}

// `pos.after(m)` is where pieces get moved/captured/promoted. It dominates
// the "apply move" bucket together with the accumulator push, which is
// timed at its own call sites below.
inline Position after_timed(const Position& pos, const Move& m) noexcept {
    BD_TIME(apply);
    return pos.after(m);
}

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

    // Tunable search constants + PVS toggle. Copied from SearchLimits at
    // the start of each top-level search (and into helper searchers).
    SearchParams        params{};

    std::array<std::array<Move, 2>, MAX_PLY + 1>                       killers{};
    std::array<std::array<int,  NUM_SQUARES + 1>, NUM_SQUARES + 1>     history{};
    // Countermove heuristic : best response to opponent's last move,
    // indexed by [opp_from][opp_to]. Reset between top-level searches
    // like killers/history. ~+20-40 ELO in typical alpha-beta engines.
    std::array<std::array<Move, NUM_SQUARES + 1>, NUM_SQUARES + 1>     countermove{};
    // Move stack : move_played[ply] is the move that brought us into
    // this ply (i.e., the parent's move when entering negamax at ply).
    // Used by countermove + LMP heuristics. Initialised to default
    // (invalid) Move at root.
    std::array<Move, MAX_PLY + 2>                                      move_played{};

    // Continuation history (1b, gated by params.use_conthist). Keyed by
    // [opp_prev_to][m.from][m.to] — "after the opponent moved to square X,
    // this quiet reply was good". Accumulated like `history` on beta
    // cutoffs, added to the quiet-move ordering score. Heap-allocated
    // (51³ ints ≈ 0.5 MB) so the per-thread Searcher stays off the stack.
    static constexpr std::size_t CH_DIM  = NUM_SQUARES + 1;
    static constexpr std::size_t CH_SIZE = CH_DIM * CH_DIM * CH_DIM;
    std::vector<std::int32_t> cont_hist = std::vector<std::int32_t>(CH_SIZE, 0);

    std::int32_t& ch(int prev_to, int from, int to) noexcept {
        return cont_hist[(static_cast<std::size_t>(prev_to) * CH_DIM
                          + static_cast<std::size_t>(from)) * CH_DIM
                         + static_cast<std::size_t>(to)];
    }
    std::int32_t ch(int prev_to, int from, int to) const noexcept {
        return cont_hist[(static_cast<std::size_t>(prev_to) * CH_DIM
                          + static_cast<std::size_t>(from)) * CH_DIM
                         + static_cast<std::size_t>(to)];
    }

    // Per-ply static eval, for the "improving" heuristic (1b). EVAL_NONE at
    // tactical nodes (forced capture) where a static eval is meaningless.
    static constexpr int EVAL_NONE = INF_SCORE;
    std::array<int, MAX_PLY + 2> static_eval_stack{};

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

    // Wall time at which the current root iteration started, used by the
    // iterative-deepening loop to decide whether to skip the next iteration
    // when it would obviously not finish before the deadline.
    std::chrono::steady_clock::time_point iter_started_at{};

    // Optional NNUE-style replacement for the handcrafted leaf evaluation.
    // Null means "use the static `evaluate()` function in eval.cpp".
    const INetwork*                       nnue{nullptr};

    // Fast-path accumulator support. When `nnue` is an `MLPNetworkQ`,
    // we cache the concrete pointer here and maintain a per-ply
    // `AccumulatorPair` so each leaf eval skips the Layer-1 rebuild.
    // Otherwise `mlpq_nnue` is null and `eval_leaf` falls back to the
    // generic `nnue->evaluate(pos)` path, which any concrete INetwork
    // supports.
    //
    // The +1 covers the case ply == MAX_PLY (the hard cap branch in
    // negamax still calls eval_leaf at that level).
    const MLPNetworkQ*                    mlpq_nnue{nullptr};
    std::array<AccumulatorPair, MAX_PLY + 2> accumulators{};

    // Same idea for the Scan/pattern eval (v3/v4) : when `nnue` is a
    // ScanEvalNetwork, maintain the 32 base-3 pattern indices per ply so each
    // leaf skips the full extract_all rebuild. One accumulator per ply (the
    // index is side-to-move-independent).
    const scan_eval::ScanEvalNetwork*     scan_nnue{nullptr};
    std::array<scan_eval::ScanAccumulator, MAX_PLY + 2> scan_accs{};

    // Set to true while a Null-Move Pruning probe is in progress, so
    // the recursive negamax doesn't try another null move on top
    // (which would converge to nonsense at deep enough chains).
    bool                                  was_null{false};

    int negamax    (const Position& pos, int depth, int ply, int alpha, int beta);
    int quiescence (const Position& pos,            int ply, int alpha, int beta);

    // Wrap the leaf eval so the rest of the code doesn't have to branch.
    // When `mlpq_nnue` is set, the per-ply accumulator is up-to-date
    // for `pos` (the caller maintains the invariant via
    // `push_accumulator` at every recursion) and we can skip the
    // Layer-1 rebuild via `evaluate_with_accumulator`. Otherwise we
    // dispatch to whatever INetwork was provided (or to the static
    // handcrafted eval if none).
    int eval_leaf(const Position& pos, int ply) const noexcept {
        BD_TIME(eval);
        if (mlpq_nnue) {
            const auto& acc = (pos.side_to_move() == Color::White)
                ? accumulators[ply].white
                : accumulators[ply].black;
            return mlpq_nnue->evaluate_with_accumulator(pos, acc.data.data());
        }
        if (scan_nnue) {
            return scan_nnue->evaluate_with_idx(
                pos, scan_accs[static_cast<std::size_t>(ply)].idx.data());
        }
        return nnue ? nnue->evaluate(pos) : evaluate(pos);
    }

    // Populate `accumulators[ply+1]` to reflect `pos_after` given that
    // `accumulators[ply]` already reflects `pos_before` and `m` was
    // played from pos_before. Fast path: copy + `apply_move`. Slow
    // fallback: full `refresh_from`. No-op when the accumulator path
    // is inactive (mlpq_nnue == nullptr).
    void push_accumulator(int ply,
                          const Position& pos_before,
                          const Move& m,
                          const Position& pos_after) noexcept {
        if (!mlpq_nnue && !scan_nnue) return;
        BD_TIME(accumulator);
        const std::size_t pi  = static_cast<std::size_t>(ply);
        const std::size_t pi1 = pi + 1;
        if (pi1 >= accumulators.size()) return;  // ply cap, no descent
        if (mlpq_nnue) {
            accumulators[pi1] = accumulators[pi];
            if (!accumulators[pi1].apply_move(pos_before, m, pos_after, *mlpq_nnue)) {
                accumulators[pi1].refresh_from(pos_after, *mlpq_nnue);
            }
        }
        if (scan_nnue) {
            scan_accs[pi1] = scan_accs[pi];
            scan_accs[pi1].apply_move(pos_before, pos_after);
        }
    }

    // Null move: piece positions unchanged → both accumulators are
    // bit-identical to the previous ply's. Just copy.
    void push_accumulator_null(int ply) noexcept {
        if (!mlpq_nnue && !scan_nnue) return;
        BD_TIME(accumulator);
        const std::size_t pi  = static_cast<std::size_t>(ply);
        const std::size_t pi1 = pi + 1;
        if (pi1 >= accumulators.size()) return;
        if (mlpq_nnue) accumulators[pi1] = accumulators[pi];
        if (scan_nnue) scan_accs[pi1]    = scan_accs[pi];
    }

    // Returns true if `h` repeats an ancestor on the current search path. A
    // repetition requires the SAME side to move (even plies back) and can only
    // involve positions since the last irreversible move (a man move/capture
    // changes material or structure irreversibly) — i.e. the trailing
    // `halfmove` entries. So scan back by 2, capped at `halfmove`, instead of
    // the whole path : O(reversible run) per node, not O(depth).
    bool path_contains(ZobristHash h, int halfmove) const noexcept {
        BD_TIME(path_check);
        const std::size_t n = hash_path.size();
        const std::size_t cap = static_cast<std::size_t>(halfmove);
        for (std::size_t back = 2; back <= n && back <= cap; back += 2) {
            if (hash_path[n - back] == h) return true;
        }
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
                       const Move& tt_move, bool tt_hit,
                       const Move& prev_move) noexcept {
    if (tt_hit && m == tt_move) return 1'000'000;
    if (m.is_capture())          return 0;            // captures: keep generation order
    if (m == s.killers[static_cast<std::size_t>(ply)][0])  return   800'000;
    if (m == s.killers[static_cast<std::size_t>(ply)][1])  return   700'000;
    // Countermove heuristic : if this move was the best response to the
    // opponent's last move on a prior beta cutoff, try it early.
    if (prev_move.from != 0) {
        const Move& cm = s.countermove
            [static_cast<std::size_t>(prev_move.from)]
            [static_cast<std::size_t>(prev_move.to)];
        if (cm.from != 0 && m == cm) return 650'000;
    }
    // History tail, optionally boosted by continuation history (1b).
    int hist = s.history[m.from][m.to];
    if (s.params.use_conthist && prev_move.from != 0) {
        hist += s.ch(prev_move.to, m.from, m.to);
    }
    return hist;
}

// Sort moves in place, descending by `order_score`. Selection sort: the move
// list is small (~30 in the worst case) and an in-place ordering keeps the
// hot loop cache-friendly.
inline void order_moves(MoveList& moves, const Searcher& s, int ply,
                        const Move& tt_move, bool tt_hit,
                        const Move& prev_move) {
    BD_TIME(move_ordering);
    std::array<int, 256> scores;  // populated for [0, n) before any read
    const std::size_t n = moves.size();
    for (std::size_t i = 0; i < n; ++i) {
        scores[i] = order_score(s, moves[i], ply, tt_move, tt_hit, prev_move);
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
    gen_moves(pos, moves);
    if (moves.empty()) return -MATE_SCORE + ply;

    // generate_legal_moves either returns *all* maximum-length captures or
    // *all* quiet moves — never a mix. So a single check on the first move
    // tells us whether the position is calm.
    if (!moves[0].is_capture()) return eval_leaf(pos, ply);

    int best = -INF_SCORE;
    for (const auto& m : moves) {
        const Position next  = after_timed(pos, m);
        push_accumulator(ply, pos, m, next);
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
    if (ply >= MAX_PLY) return eval_leaf(pos, ply);
    ++nodes;
    // Polling time / external-stop is not free; throttle to once every
    // 1024 nodes. The first probe of every iteration also runs through
    // here because `nodes` was just bumped from 0 → 1 the very first time.
    if ((nodes & 0x3FF) == 0 && check_stop()) return 0;

    ZobristHash hash;
    { BD_TIME(zobrist); hash = zobrist_hash(pos); }

    // Kick off the TT cluster fetch now so its cache line is in flight while
    // the node does the repetition / 50-move checks below (hides the random-
    // access memory latency that dominates the probe at step 1).
    if (tt) tt->prefetch(hash);

    // 0. Path-dependent draw detection. Path-dependent because it depends
    //    on which prior positions the search has visited, so we must not
    //    consult the TT for these answers.
    if (path_contains(hash, pos.halfmove_clock()))  return 0;
    if (pos.halfmove_clock() >= FIFTY_MOVE_PLIES)   return 0;

    // 0bis. Endgame tablebase: positions with a known theoretical result
    //       skip the rest of the work. Like the path-dependent draws this
    //       answer is independent of the alpha-beta window.
    {
        const EndgameResult eg = probe_endgame(pos);
        if (eg == EndgameResult::Draw) return 0;
        if (eg == EndgameResult::WhiteWin || eg == EndgameResult::BlackWin) {
            // Distance-aware TB terminal. A flat win score gave the search no
            // reason to PROGRESS in a won endgame: every winning move tied, so
            // it could shuffle until the FMJD draw rule and throw the win (and,
            // in self-play, mislabel the won line as a draw). Subtracting `ply`
            // makes a SHORTER win score higher and a LONGER loss score higher
            // (less negative) → the search prefers to convert sooner / resist
            // longer, shedding pieces toward a simpler win. Stays one ply-band
            // below MATE_BOUND so it outranks any eval but is never mistaken for
            // a real forced mate. (TB nodes are re-probed here BEFORE the TT, so
            // the ply-relative value is never served from a stale TT entry; a
            // proper MTC database would make the within-TB distance exact.)
            const bool stm_wins = (eg == EndgameResult::WhiteWin)
                ? (pos.side_to_move() == Color::White)
                : (pos.side_to_move() == Color::Black);
            // Distance = search plies to reach here (`ply`) PLUS the exact
            // moves-to-conversion from the MTC database when loaded (Kingsrow
            // has it, Scan does not — this plays the FASTEST conversion, not
            // just *a* conversion). probe_mtc returns 1 in the flat <10-ply zone
            // and the true value >=10 (the band where dawdling is a real risk),
            // or <=0 when the position is outside the MTC db; gate on a
            // confirmed WLD win (we are in the win branch). Capped so the TB-win
            // band stays well above any eval and below MATE_BOUND.
            int dist = ply;
            if (egdb::available_mtc()) {
                const int m = egdb::probe_mtc(pos);
                if (m > 0) dist += (m < 500 ? m : 500);
            }
            const int v = (MATE_SCORE - MAX_PLY - 1) - dist;
            return stm_wins ? v : -v;
        }
    }

    // 1. Probe TT.  A hit lets us cut the subtree if its stored bound is
    //    compatible with the current alpha-beta window; otherwise we still
    //    keep the suggested move for ordering.
    TTEntry tt_entry;
    bool    tt_hit;
    { BD_TIME(tt); tt_hit = tt->probe(hash, tt_entry); }
    if (tt_hit && tt_entry.depth >= depth) {
        const int s = score_from_tt(tt_entry.score, ply);
        if (tt_entry.bound() == Bound::Exact)                    return s;
        if (tt_entry.bound() == Bound::Lower && s >= beta)       return s;
        if (tt_entry.bound() == Bound::Upper && s <= alpha)      return s;
    }

    // 2. Mate / leaf detection. At the horizon we hand off to quiescence
    //    so a forced capture pending at the leaf is not silently misvalued.
    MoveList moves;
    gen_moves(pos, moves);
    if (moves.empty()) return -MATE_SCORE + ply;
    if (depth <= 0)    return quiescence(pos, ply, alpha, beta);

    // Shared, lazily-computed static eval for this node. RFP / NMP / razoring
    // all want it; compute at most once. A "tactical" node (a forced capture
    // is pending) has no meaningful static eval. NB: lazy → when every 1b
    // flag is off the call pattern matches the pre-1b behaviour exactly.
    const bool tactical = moves[0].is_capture();
    bool have_eval = false;
    int  node_eval = 0;
    auto static_eval = [&]() noexcept -> int {
        if (!have_eval) { node_eval = eval_leaf(pos, ply); have_eval = true; }
        return node_eval;
    };

    // Improving heuristic (1b, gated). Record this node's static eval and
    // compare to the same side's eval 2 plies up.
    static_eval_stack[static_cast<std::size_t>(ply)] = EVAL_NONE;
    bool improving = false;
    if (params.use_improving && !tactical) {
        const int se = static_eval();
        static_eval_stack[static_cast<std::size_t>(ply)] = se;
        if (ply >= 2
            && static_eval_stack[static_cast<std::size_t>(ply - 2)] != EVAL_NONE) {
            improving = se > static_eval_stack[static_cast<std::size_t>(ply - 2)];
        }
    }

    // Endgame search regime (gated; eg_pieces=0 disables → ZERO cost on the
    // default path: the && short-circuits before the popcount). When few pieces
    // remain the node is SEARCH-BOUND (job 0252: deep search rescues a weak
    // endgame eval) yet tactically sharp with low branching, so aggressive
    // reductions/pruning risk discarding the single precise winning line for
    // little node saving. The gated flags let an A/B disable NMP (zugzwang),
    // LMP and/or LMR below `eg_pieces` pieces (same popcount phase axis as
    // pattern_jass --phase-weight). Cf docs/ROADMAP.md (VERDICT FINALES).
    const bool eg = params.eg_pieces > 0
                 && popcount(pos.occupied()) <= params.eg_pieces;

    // 2bis. Reverse Futility Pruning (a.k.a. static null move). When the
    //   position is quiet (no forced captures — recall draughts mandates
    //   the longest capture chain, so `moves[0].is_capture()` is reliable
    //   as a "tactical position" signal), shallow, not in the mate band,
    //   and the static eval beats beta by a margin that scales with the
    //   remaining depth, the subtree almost certainly fails high.
    //
    //   Cheaper than the recursive NMP probe below and covers the depth
    //   1-5 range where NMP doesn't fire (NMP_MIN_DEPTH=4) or its overhead
    //   isn't amortised by the saving.
    //
    //   Margin = 100 cp * depth is conservative; over-aggressive RFP
    //   loses ELO by pruning critical lines whose static eval looks safe
    //   but where the opponent has a deep tactical resource.
    {
        const int RFP_MAX_DEPTH = params.rfp_max_depth;
        const int RFP_MARGIN    = params.rfp_margin;  // cp per remaining ply
        if (depth <= RFP_MAX_DEPTH
            && !was_null
            && !is_mate_score(beta)
            && !tactical) {
            const int eval   = static_eval();
            const int margin = RFP_MARGIN * depth;
            if (eval - margin >= beta) return eval - margin;
        }
    }

    // 2bis-b. Razoring (gated; default off via razor_max_depth=0).
    //   Symmetric to RFP on the alpha side: at a shallow non-PV quiet
    //   node whose static eval is far below alpha, verify with quiescence
    //   and prune if qsearch confirms the node can't raise alpha. Placed
    //   before the hash_path push so the early return needs no pop.
    if (params.razor_max_depth > 0
        && depth <= params.razor_max_depth
        && (beta - alpha) == 1
        && !was_null
        && !is_mate_score(alpha)
        && !tactical) {
        const int eval   = static_eval();
        const int margin = params.razor_margin * depth;
        if (eval + margin <= alpha) {
            const int q = quiescence(pos, ply, alpha, beta);
            if (q <= alpha) return q;
        }
    }

    // 2ter. Null-Move Pruning. If we can give the opponent a free
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
        const int NMP_MIN_DEPTH  = params.nmp_min_depth;
        const int NMP_MIN_PIECES = params.nmp_min_pieces;
        if (depth >= NMP_MIN_DEPTH
            && !was_null
            && !is_mate_score(beta)
            && !(eg && params.eg_no_nmp)) {     // endgame regime: NMP off (zugzwang)
            const Bitboard all = pos.white_men() | pos.white_kings()
                               | pos.black_men() | pos.black_kings();
            if (popcount(all) >= NMP_MIN_PIECES) {
                const int eval = static_eval();
                if (eval >= beta) {
                    const int R          = params.nmp_r_base + depth / params.nmp_r_div;
                    const int reduced    = depth - 1 - R;
                    const int safe_depth = reduced < 1 ? 1 : reduced;
                    const Position null_pos = pos.after_null();
                    push_accumulator_null(ply);
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

    // 2quater. Internal Iterative Deepening (1b, gated). With no usable TT
    //   move at a deep quiet node, a reduced-depth search of THIS position
    //   first fills the TT with a best move, so the full search isn't run on
    //   a blind move order. Runs before hash_path push (pos is not yet its
    //   own ancestor) and re-probes the TT for the move it produced.
    if (params.iid_min_depth > 0
        && !tt_move_valid
        && depth >= params.iid_min_depth
        && !tactical) {
        const int iid_depth = depth - params.iid_reduction;
        if (iid_depth >= 1) {
            (void)negamax(pos, iid_depth, ply, alpha, beta);
            if (!stopped) {
                TTEntry e2;
                bool h2;
                { BD_TIME(tt); h2 = tt->probe(hash, e2); }
                if (h2) {
                    for (const auto& m : moves) {
                        if (same_packed_move(m, e2.best_move)) {
                            tt_entry      = e2;
                            tt_move       = m;
                            tt_move_valid = true;
                            tt_hit        = true;
                            break;
                        }
                    }
                }
            }
            if (stopped) return 0;
        }
    }

    const Move prev_move = move_played[static_cast<std::size_t>(ply)];
    order_moves(moves, *this, ply, tt_move, tt_move_valid, prev_move);

    // 4. Search.
    const int alpha_orig = alpha;
    int       best       = -INF_SCORE;
    Move      best_move  = moves[0];

    { BD_TIME(path_check); hash_path.push_back(hash); }

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
    const int SINGULAR_MIN_DEPTH = params.singular_min_depth;
    const int SINGULAR_MARGIN    = params.singular_margin;  // cp per ply of depth
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
            const Position next = after_timed(pos, m);
            push_accumulator(ply, pos, m, next);
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

    // 4ter. ProbCut (gated; default off via probcut_min_depth=0). At a
    //   high-depth non-PV node, if a forced capture leads to a
    //   reduced-depth score >= beta + probcut_margin, the node almost
    //   certainly fails high — cut. Mirrors the singular verification's
    //   move application; the early return must pop the hash_path pushed
    //   above. NB: draughts captures are forced, so this only fires at
    //   tactical nodes (value uncertain — measured via A/B before ship).
    if (params.probcut_min_depth > 0
        && depth >= params.probcut_min_depth
        && (beta - alpha) == 1
        && !was_null
        && !is_mate_score(beta)) {
        const int rbeta  = beta + params.probcut_margin;
        const int rdepth = depth - params.probcut_reduction;
        if (rdepth >= 1 && !is_mate_score(rbeta)) {
            for (const auto& m : moves) {
                if (!m.is_capture()) continue;
                const Position next = after_timed(pos, m);
                push_accumulator(ply, pos, m, next);
                const int sc = -negamax(next, rdepth - 1, ply + 1,
                                        -rbeta, -rbeta + 1);
                if (stopped) break;
                if (sc >= rbeta) {
                    { BD_TIME(path_check); hash_path.pop_back(); }
                    return sc;
                }
            }
        }
    }

    // 4quater. Multi-cut pruning (1b, gated). At a deep non-PV quiet node,
    //   scout the first `multicut_moves` ordered moves at reduced depth; if
    //   at least `multicut_cuts` of them fail high, the node almost certainly
    //   fails high — cut. Speculative; the early return pops the hash_path
    //   pushed above (mirror of ProbCut).
    if (params.multicut_min_depth > 0
        && depth >= params.multicut_min_depth
        && (beta - alpha) == 1
        && !was_null
        && !is_mate_score(beta)
        && !tactical) {
        const int rdepth = depth - params.multicut_reduction;
        if (rdepth >= 1) {
            int cuts = 0, tried = 0;
            for (const auto& m : moves) {
                if (tried >= params.multicut_moves) break;
                ++tried;
                const Position next = after_timed(pos, m);
                push_accumulator(ply, pos, m, next);
                if (ply + 1 < static_cast<int>(move_played.size())) {
                    move_played[static_cast<std::size_t>(ply + 1)] = m;
                }
                const int sc = -negamax(next, rdepth - 1, ply + 1,
                                        -beta, -beta + 1);
                if (stopped) break;
                if (sc >= beta && ++cuts >= params.multicut_cuts) {
                    { BD_TIME(path_check); hash_path.pop_back(); }
                    return beta;
                }
            }
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
    const int LMR_MIN_DEPTH        = params.lmr_min_depth;
    const int LMR_FIRST_FULL_MOVES = params.lmr_first_full_moves;
    auto lmr_reduction = [&params = params, LMR_MIN_DEPTH, LMR_FIRST_FULL_MOVES,
                          improving]
                         (int d, int move_idx) noexcept -> int {
        // Simple monotone formula: ~1 ply at low depth/index, ~3 plies
        // at depth ≥ 12 with index ≥ 16. Capped so the reduced depth
        // stays ≥ 1. When the improving heuristic is on and we are not
        // improving, reduce one extra ply.
        if (d < LMR_MIN_DEPTH || move_idx < LMR_FIRST_FULL_MOVES) return 0;
        int r = params.lmr_base + d / params.lmr_depth_div
              + move_idx / params.lmr_idx_div;
        if (params.use_improving && !improving) r += 1;
        return r < 1 ? 1 : (r > d - 2 ? d - 2 : r);
    };

    // Late Move Pruning : at shallow depth on non-PV nodes, skip late
    // quiet moves entirely. They're statistically unlikely to raise
    // alpha given move ordering has already sorted them. Captures are
    // never pruned (FMJD majority rule forces them anyway). ~+10-20 ELO.
    // LMP applies for depth <= lmp_max_depth (param ; default 3 = legacy).
    // first-move-index to skip at depth d : tuned d1/d2/d3 for the shallow
    // nodes, then a quadratic move-count tail (2 + d + d*d) that continues the
    // d1/d2/d3 trend exactly (4,8,14,22,32,44…) for the deepened range.
    const int LMP_MAX_DEPTH = params.lmp_max_depth;
    auto lmp_threshold_for = [&params = params](int d) noexcept -> int {
        switch (d) {
            case 1:  return params.lmp_d1;
            case 2:  return params.lmp_d2;
            case 3:  return params.lmp_d3;
            default: return 2 + d + d * d;   // depths >= 4 (only when lmp_max_depth>3)
        }
    };
    const bool is_pv_node = (beta - alpha) > 1;

    int move_idx = 0;
    for (const auto& m : moves) {
        // LMP : skip late quiet moves at shallow non-PV nodes. When the
        // improving heuristic is on and we are NOT improving, prune one step
        // earlier (the position is already trending the wrong way).
        int lmp_threshold = (depth >= 1 && depth <= LMP_MAX_DEPTH)
                          ? lmp_threshold_for(depth) : 0;
        if (params.use_improving && !improving && lmp_threshold > 0) {
            lmp_threshold = (lmp_threshold + 1) / 2;
        }
        if (!is_pv_node
            && depth >= 1 && depth <= LMP_MAX_DEPTH
            && move_idx >= lmp_threshold
            && !m.is_capture()
            && !(eg && params.eg_no_lmp)   // endgame regime: don't prune late quiets
            && best > -INF_SCORE / 2) {  // already have a real score → safe to skip
            ++move_idx;
            continue;
        }
        const Position next      = after_timed(pos, m);
        push_accumulator(ply, pos, m, next);
        // Record the move being played so the child node (ply+1) can
        // consult it as `prev_move` for countermove ordering.
        if (ply + 1 < static_cast<int>(move_played.size())) {
            move_played[static_cast<std::size_t>(ply + 1)] = m;
        }
        const bool     is_tt     = tt_move_valid
                                 && same_packed_move(m, tt_entry.best_move);
        const int      promo_ext = (params.ext_promotion && m.promotes) ? 1 : 0;
        const int      new_depth = depth - 1
                                 + (singular_ext && is_tt ? 1 : 0)
                                 + promo_ext;

        int score;
        const bool do_lmr = move_idx >= LMR_FIRST_FULL_MOVES
                         && depth >= LMR_MIN_DEPTH
                         && !is_tt
                         && !m.is_capture()
                         && !(eg && params.eg_no_lmr)  // endgame regime: full-depth, no reductions
                         && !singular_ext;  // don't reduce when we just extended a singular line
        if (params.use_pvs && move_idx > 0) {
            // Principal Variation Search: once a PV move has raised alpha,
            // scout the remaining moves with a zero-width window (optionally
            // LMR-reduced). Only moves that beat alpha pay for an exact
            // full-window re-search.
            const int r = do_lmr ? lmr_reduction(depth, move_idx) : 0;
            score = -negamax(next, new_depth - r, ply + 1, -alpha - 1, -alpha);
            if (score > alpha && r > 0) {
                // The reduction alone may have caused the fail-high; verify
                // at full depth with the same zero window before paying for
                // a full-window search.
                score = -negamax(next, new_depth, ply + 1, -alpha - 1, -alpha);
            }
            if (score > alpha && score < beta) {
                // Genuine PV candidate — establish its exact score.
                score = -negamax(next, new_depth, ply + 1, -beta, -alpha);
            }
        } else if (do_lmr) {
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
                const int hbonus = depth * depth;
                // History aging (gated) : gravity rule caps the table at
                // ~history_max and decays large OLD cutoffs toward it, so stale
                // history stops dominating the ordering. history_max=0 = legacy
                // unbounded += bonus (byte-identical default).
                {
                    int& h = history[m.from][m.to];
                    h += (params.history_max > 0)
                       ? hbonus - h * hbonus / params.history_max
                       : hbonus;
                }
                // Countermove : record `m` as the best response to the
                // opponent's previous move (if any). Stored regardless
                // of ply so siblings further up the tree also benefit.
                if (prev_move.from != 0) {
                    countermove
                        [static_cast<std::size_t>(prev_move.from)]
                        [static_cast<std::size_t>(prev_move.to)] = m;
                    // Continuation history (1b) : same cutoff signal, keyed
                    // by the opponent's landing square × this reply.
                    if (params.use_conthist) {
                        int& c = ch(prev_move.to, m.from, m.to);
                        c += (params.history_max > 0)
                           ? hbonus - c * hbonus / params.history_max
                           : hbonus;
                    }
                }
            }
            break;
        }
        ++move_idx;
    }

    { BD_TIME(path_check); hash_path.pop_back(); }

    // 5. Store back into the TT — but only if the result is real. An
    //    aborted search produced a placeholder score that would poison
    //    the table.
    if (!stopped) {
        Bound bound;
        if      (best >= beta)      bound = Bound::Lower;
        else if (best > alpha_orig) bound = Bound::Exact;
        else                        bound = Bound::Upper;

        { BD_TIME(tt); tt->store(hash, pack_move(best_move),
                                 score_to_tt(best, ply), depth, bound); }
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
// barely move, which is the common case in quiet positions. The initial
// half-width is tunable via SearchParams::aspiration_initial.

}  // namespace

SearchResult search(const Position& pos, const SearchLimits& limits,
                    TranspositionTable& tt,
                    const std::vector<ZobristHash>& game_history) {
    SearchResult res;
    breakdown_reset();

    // One-time bootstrap of the external endgame DB (Kingsrow egdb_intl) from
    // JASS_EGDB_PATH. No-op (and free thereafter) in the default build; here
    // rather than per-node so probe_endgame's gate stays a single atomic load.
    egdb::ensure_initialised();

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
    gen_moves(pos, root_moves);
    if (root_moves.empty()) {
        res.score = -MATE_SCORE;
        return res;
    }

    Searcher s;
    s.tt        = &tt;
    s.params    = limits.params;
    s.hash_path = game_history;
    s.hash_path.push_back(root_hash);  // root is an ancestor for its children
    s.stop_flag = limits.stop_flag;
    s.nnue      = limits.nnue;
    // Activate the accumulator fast path when the supplied INetwork is
    // the quantised MLP. Other concrete types (LinearNetwork, the
    // float MLPNetwork) fall through to the generic
    // `nnue->evaluate(pos)` slow path.
    s.mlpq_nnue = dynamic_cast<const MLPNetworkQ*>(limits.nnue);
    if (s.mlpq_nnue) {
        s.accumulators[0].refresh_from(pos, *s.mlpq_nnue);
    }
    // Same fast path for the Scan/pattern eval (v3/v4). `JASS_NO_SCAN_ACC`
    // forces the recompute path (extract_all every leaf) for A/B benchmarking.
    static const bool scan_acc_off = std::getenv("JASS_NO_SCAN_ACC") != nullptr;
    s.scan_nnue = scan_acc_off
        ? nullptr
        : dynamic_cast<const scan_eval::ScanEvalNetwork*>(limits.nnue);
    if (s.scan_nnue) {
        s.scan_accs[0].refresh_from(pos);
    }
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
        const SearchParams params_for_helpers = limits.params;
        for (int i = 1; i < limits.threads; ++i) {
            helpers.emplace_back([&pos, &game_history, &tt, &helper_stop,
                                  max_depth = limits.max_depth,
                                  nnue_for_helpers, params_for_helpers]() {
                SearchLimits hlim;
                hlim.max_depth = max_depth;
                hlim.stop_flag = &helper_stop;
                hlim.threads   = 1;  // critical: helpers must not fork further
                hlim.nnue      = nnue_for_helpers;
                hlim.params    = params_for_helpers;
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
            const Position next  = after_timed(pos, m);
            s.push_accumulator(0, pos, m, next);
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

        // Time-management iteration skip: when running under a deadline,
        // estimate whether the next iteration has any chance of finishing
        // before we'd be stopped mid-search. Iteration times in iterative
        // deepening with TT typically grow ~1.5-3x per ply for draughts;
        // we use 2x as a conservative midpoint. If the previous iteration
        // already consumed more than half the remaining budget, skip the
        // next one and keep the deeper-than-required result we have.
        //
        // Threshold tuned to fire only at depth >= 4 because shallow
        // iterations are too noisy to extrapolate from (single-ply timing
        // is dominated by overhead, not real work).
        if (s.has_deadline && depth >= s.params.tm_min_depth) {
            const auto now      = std::chrono::steady_clock::now();
            if (now >= s.deadline) break;
            const auto remaining = std::chrono::duration_cast<
                std::chrono::milliseconds>(s.deadline - now).count();
            const auto last_iter = std::chrono::duration_cast<
                std::chrono::milliseconds>(now - s.iter_started_at).count();
            // Projected next-iteration cost = last_iter × tm_next_iter_pct/100.
            // If even half of that exceeds the remaining time, the next
            // iteration would be aborted mid-flight (wasted work). The factor
            // is tunable because a fast eval's high-depth branching factor
            // differs from the NNUE regime these were set for.
            const auto projected = last_iter * s.params.tm_next_iter_pct / 100;
            if (last_iter > 0 && projected > remaining) break;
        }
        s.iter_started_at = std::chrono::steady_clock::now();

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
            delta = std::max(s.params.aspiration_initial, 2 * volatility);
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
