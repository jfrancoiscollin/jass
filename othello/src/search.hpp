// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Basic alpha-beta negamax search for Othello.
//
// No TT, no LMR, no killer moves yet — focus correctness for Day 3.
// Iterative deepening at the driver level so the caller can cap depth
// or time.

#pragma once

#include "board.hpp"
#include "movegen.hpp"

#include <cstdint>
#include <functional>

namespace othello {

struct SearchConfig {
    int           max_depth   = 6;       // hard depth cap per iteration
    int           max_time_ms = 0;       // 0 = depth-only
    // Eval functor : returns score from stm POV. Defaults to eval_basic.
    std::function<int(const Board&)> evaluator;
};

struct SearchResult {
    Square          best_move    = NO_SQUARE;
    int             score        = 0;
    std::uint64_t   nodes        = 0;
    int             depth_reached = 0;
};

SearchResult search(const Board& root, const SearchConfig& cfg);

}  // namespace othello
