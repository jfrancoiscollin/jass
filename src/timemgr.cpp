// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "timemgr.hpp"

namespace jass {

namespace {

// Average draughts game length used as the "moves left" estimate when
// the protocol doesn't volunteer one. Standard rule-of-thumb.
constexpr int DEFAULT_MOVES_LEFT = 30;

// Spend at most this fraction of the remaining time on a single move.
// (We divide by `SAFETY_DENOM` to derive a hard cap.)
constexpr int SAFETY_DENOM = 4;

// Use this fraction of the increment up-front (the rest is kept as a
// reserve for the next moves). 4/5 is a conservative compromise.
constexpr int INC_NUM = 4;
constexpr int INC_DEN = 5;

// Floor: never claim less than this so we always make some search
// progress even when the clock is nearly drained.
constexpr int MIN_BUDGET_MS = 5;

}  // namespace

int compute_movetime_ms(const TimeBudget& tb, Color stm) noexcept {
    const int total = (stm == Color::White) ? tb.wtime_ms : tb.btime_ms;
    const int inc   = (stm == Color::White) ? tb.winc_ms  : tb.binc_ms;

    if (total <= 0 && inc <= 0) return 0;  // no time data → caller decides
    if (total <  0) return MIN_BUDGET_MS;

    int moves_left = DEFAULT_MOVES_LEFT;
    if (tb.movestogo > 0 && tb.movestogo < DEFAULT_MOVES_LEFT) {
        moves_left = tb.movestogo;
    }

    int budget = (total / moves_left) + (inc * INC_NUM) / INC_DEN;
    if (total > 0) {
        const int cap = total / SAFETY_DENOM;
        if (budget > cap) budget = cap;
    }
    if (budget < MIN_BUDGET_MS) budget = MIN_BUDGET_MS;
    return budget;
}

}  // namespace jass
