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

#include <cstdint>

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
    int max_depth = 6;
};

struct SearchResult {
    Move          best_move{};
    int           score{0};
    int           depth{0};
    std::uint64_t nodes{0};
};

// Search the given position. Iterative deepening from 1 up to
// `limits.max_depth`; the result holds the best move and score from the
// final iteration. If the side to move has no legal moves, `best_move`
// stays default-constructed and the score is `-MATE_SCORE`.
SearchResult search(const Position& pos, const SearchLimits& limits);

}  // namespace jass
