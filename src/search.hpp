// SPDX-License-Identifier: MIT
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
#include "zobrist.hpp"

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace jass { class TranspositionTable; }

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

struct SearchLimits {
    int         max_depth   = 6;
    std::size_t tt_mb       = 1;     // transposition table size in megabytes
    int         movetime_ms = 0;     // wall-clock cap; 0 = unlimited
    // External stop signal. If non-null and set to true while the search is
    // running, the current iteration is abandoned and the result of the
    // last completed iteration is returned.
    const std::atomic<bool>* stop_flag = nullptr;
    // Lazy SMP fan-out. `threads = N` spawns N-1 helper threads that run
    // independent iterative deepenings sharing the same TT — they
    // populate transposition entries for the main search to reuse. The
    // returned `SearchResult` is the main thread's only.
    int         threads     = 1;
};

struct SearchResult {
    Move              best_move{};
    int               score{0};
    int               depth{0};
    std::uint64_t     nodes{0};
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

}  // namespace jass
