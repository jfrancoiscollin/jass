// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Minimal game-tree search: negamax alpha-beta with iterative deepening,
// fed by `generate_legal_moves` and the material `evaluate`.
//
// The interface is deliberately small so callers (the CLI front-end, the
// future HUB driver, the WASM bindings) can drive the engine the same way.

#pragma once

#include "movegen.hpp"
#include "position.hpp"
#include "search_params.hpp"
#include "zobrist.hpp"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace jass { class TranspositionTable; }
namespace jass { class INetwork; }

namespace jass {

// Score conventions. `MATE_SCORE` is the (positive) value of an immediately
// winning position for the side to move; mates further away are slightly
// smaller in magnitude so the search prefers shorter wins / longer losses.
inline constexpr int MATE_SCORE = 30000;
inline constexpr int INF_SCORE  = 31000;
inline constexpr int MAX_PLY    = 64;

constexpr bool is_mate_score(int s) noexcept {
    return s > (MATE_SCORE - MAX_PLY) || s < -(MATE_SCORE - MAX_PLY);
}

enum class NodeLimitMode : std::uint8_t {
    // Historical SearchLimits::max_nodes semantics: poll with the existing
    // time/external-stop cadence (every 1024 nodes) and at iteration bounds.
    Periodic,
    // Experimental self-play contract: check the authoritative counter at
    // every node and never expose a partially searched root iteration.
    Exact,
};

// Passive depth-1 diagnostics.  These records are populated only when a
// caller supplies SearchLimits::depth_one_trace; the production/default path
// keeps the pointer null and performs no diagnostic work.  Scores follow the
// engine's normal side-to-move convention: child_return is the value returned
// by negamax(child, 0), while root_negated_return is its single negation at
// the root.
struct DepthOneMoveTrace {
    Move          move{};
    int           alpha_before{0};
    int           beta{0};
    int           child_depth{0};
    int           child_return{0};
    int           root_negated_return{0};
    std::uint64_t nodes_before{0};
    std::uint64_t nodes_after{0};
    std::uint64_t eval_calls_before{0};
    std::uint64_t eval_calls_after{0};

    bool          entered_quiescence{false};
    int           qsearch_alpha{0};
    int           qsearch_beta{0};
    std::size_t   qsearch_legal_moves{0};
    bool          qsearch_forced_capture{false};
    bool          qsearch_opponent_threat{false};
    bool          qsearch_stand_pat_valid{false};
    int           qsearch_stand_pat{0};
    std::size_t   qsearch_selective_sacs{0};
    std::size_t   qsearch_moves_searched{0};
    int           qsearch_return{0};

    bool          path_draw{false};
    bool          fifty_move_draw{false};
    bool          tablebase_hit{false};
    bool          tt_cutoff{false};
    bool          terminal_hit{false};
    std::string   first_resolution_stage;
};

// Every static leaf actually reached below the active depth-one root move.
// Position is copied only in diagnostic mode; the production path keeps the
// owning trace pointer null and performs no copy or allocation.
struct LeafEvalTrace {
    Position position{};
    Move     root_move{};
    int      ply{0};
    int      score{0};
};

struct DepthOneSearchTrace {
    static constexpr std::size_t MAX_LEAF_EVALS = 16384;
    std::vector<DepthOneMoveTrace> moves;
    std::vector<LeafEvalTrace> leaf_evals;
    bool leaf_eval_overflow{false};
    std::uint64_t qnodes{0};
    std::uint64_t tablebase_probes{0};
    std::uint64_t tablebase_hits{0};
    std::uint64_t tt_probes{0};
    std::uint64_t tt_hits{0};
    std::uint64_t terminal_hits{0};
};

struct SearchLimits {
    int         max_depth   = 6;
    std::size_t tt_mb       = 1;     // transposition table size in megabytes
    int         movetime_ms = 0;     // wall-clock cap; 0 = unlimited
    // Hard node cap: abandon the search once this many nodes are visited.
    // 0 = unlimited. Unlike `movetime_ms` this is DETERMINISTIC (no wall-clock,
    // no endgame movetime-overshoot) — the right bound for a flat/near-zero eval
    // where alpha-beta pruning collapses and a fixed-depth search would explode
    // (e.g. from-scratch self-play with a zero-weights eval).
    // Periodic is the historical ~1024-node polling contract. Callers that
    // need a zero-overshoot cap must opt into Exact explicitly.
    std::uint64_t max_nodes = 0;
    NodeLimitMode node_limit_mode = NodeLimitMode::Periodic;
    // External stop signal. If non-null and set to true while the search is
    // running, the current iteration is abandoned and the result of the
    // last completed iteration is returned.
    const std::atomic<bool>* stop_flag = nullptr;
    // Lazy SMP fan-out. `threads = N` spawns N-1 helper threads that run
    // independent iterative deepenings sharing the same TT — they
    // populate transposition entries for the main search to reuse. The
    // returned `SearchResult` is the main thread's only.
    int         threads     = 1;
    // Optional NNUE-style network used at every leaf instead of the
    // handcrafted `evaluate(pos)`. Default null = use handcrafted.
    // Any concrete `INetwork` (Linear, MLP, …) is accepted.
    const INetwork* nnue = nullptr;
    // Tunable search parameters (pruning/reduction/extension constants +
    // PVS toggle). Default = behaviour-neutral baseline.
    SearchParams params{};
    // Optional passive instrumentation for a completed depth-1 root
    // iteration. Null is the byte/behaviour-identical production default.
    DepthOneSearchTrace* depth_one_trace = nullptr;
    // Diagnostic-only root ordering schedule. Format:
    // "1:31-26,31-27;2:31-27,31-26". Every depth must list every
    // legal root move exactly once. Empty preserves production ordering.
    std::string root_order_schedule;
};

enum class SearchStopReason : std::uint8_t {
    None,
    Nodes,
    Time,
    External,
};

inline const char* search_stop_reason_name(SearchStopReason reason) noexcept {
    switch (reason) {
        case SearchStopReason::Nodes:    return "nodes";
        case SearchStopReason::Time:     return "time";
        case SearchStopReason::External: return "external";
        case SearchStopReason::None:     return "none";
    }
    return "none";
}

struct SearchResult {
    Move              best_move{};
    int               score{0};
    int               depth{0};
    // `depth` keeps its historical meaning: last fully completed iterative
    // depth. `effective_depth` is the deepest iteration started, including an
    // iteration interrupted by a node/time/external limit.
    int               effective_depth{0};
    int               completed_depth{0};
    bool              aborted_iteration{false};
    SearchStopReason  stop_reason{SearchStopReason::None};
    std::uint64_t     nodes{0};
    std::uint64_t     cutoffs{0};            // DIAG #1
    std::uint64_t     first_move_cutoffs{0}; // DIAG #1
    std::uint64_t     pvs_researches{0};     // DIAG #1
    std::uint64_t     moves_searched{0};     // DIAG #1
    std::uint64_t     eval_calls{0};
    std::uint64_t     scan_verify_probes{0};
    std::uint64_t     scan_verify_cutoffs{0};
    std::uint64_t     scan_threat_reentries{0};
    // Passive deterministic V4 plumbing counters. They are maintained for
    // every search arm and never participate in a search decision.
    std::uint64_t     qnodes{0};
    std::uint64_t     qsearch_calls{0};
    std::uint64_t     tablebase_probes{0};
    std::uint64_t     tablebase_hits{0};
    std::uint64_t     tt_probes{0};
    std::uint64_t     tt_hits{0};
    std::uint64_t     terminal_hits{0};
    std::uint64_t     reductions{0};
    std::uint64_t     extensions{0};
    std::uint64_t     root_order_applications{0};
    std::uint64_t     root_order_failures{0};
    // Principal variation: the line of play the engine expects from this
    // point. `pv[0] == best_move`. Length is bounded by `MAX_PLY` and may
    // be shorter than the search depth if the TT walk terminates early
    // (TT miss, illegal move from a hash collision, or cycle).
    std::vector<Move> pv;
    // True when `best_move` came from the opening book, in which case
    // `depth` and `nodes` are 0 and `pv` only contains the book move.
    bool              from_book{false};
};

// Search the given position. Iterative deepening from 1 up to
// `limits.max_depth`; the result holds the best move and score from the
// final iteration. If the side to move has no legal moves, `best_move`
// stays default-constructed and the score is `-MATE_SCORE`.
//
// The two-argument overload allocates a fresh transposition table sized
// according to `limits.tt_mb` for each call; callers that drive several
// searches in sequence (a game, a HUB session, …) should instead pass an
// explicit, reused table to the three-argument overload.
// `game_history` holds the Zobrist hashes of every position the game has
// already visited *before* `pos` (predecessors only — `pos` itself must not
// be in there). It is consulted for 3-fold-repetition detection together
// with the search-tree path the recursion builds itself.
SearchResult search(const Position& pos, const SearchLimits& limits);
SearchResult search(const Position& pos, const SearchLimits& limits,
                    TranspositionTable& tt);
SearchResult search(const Position& pos, const SearchLimits& limits,
                    TranspositionTable& tt,
                    const std::vector<ZobristHash>& game_history);

// FMJD draws checked by the search (besides the no-legal-move case which
// is a loss for the side to move):
//   - 25-move rule: 50 plies without an irreversible move → draw 0
//   - 2-fold repetition (we treat the first repeat as drawish, an accepted
//     simplification): the current hash is in `game_history` or the search
//     path → draw 0.
inline constexpr int FIFTY_MOVE_PLIES = 50;

// Walk the principal variation by repeated TT probes from `start`. Stops
// at a TT miss, a non-Exact entry, an illegal stored move (hash collision)
// or a position cycle. The returned vector is bounded by `max_len`.
std::vector<Move> extract_pv(const Position&            start,
                             const TranspositionTable&  tt,
                             int                        max_len = MAX_PLY);

// Time-breakdown instrumentation. When the binary is built with
// `-DJASS_TIME_BREAKDOWN`, the search wraps the calls to eval / movegen /
// position-application in chrono samplers and accumulates the time in
// thread-shared atomic counters. Otherwise these helpers are no-ops and
// the counters are not touched. ~5-10% overhead when active.
void breakdown_reset() noexcept;
struct BreakdownStats {
    std::uint64_t eval_ns             = 0;
    std::uint64_t movegen_ns          = 0;
    std::uint64_t apply_ns            = 0;
    std::uint64_t accumulator_ns      = 0;
    std::uint64_t tt_ns               = 0;
    std::uint64_t zobrist_ns          = 0;
    std::uint64_t movegen_capture_ns  = 0;
    std::uint64_t movegen_quiet_ns    = 0;
    std::uint64_t move_ordering_ns    = 0;
    std::uint64_t path_check_ns       = 0;
    std::uint64_t total_ns            = 0;
};
BreakdownStats breakdown_snapshot() noexcept;

}  // namespace jass
