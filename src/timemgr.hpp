// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Tiny time-management helper for the search.
//
// Given the time budget reported by a tournament-style protocol
// (`wtime`, `btime`, `winc`, `binc`, optionally `movestogo`), this
// returns how many milliseconds the next search should be allowed to
// spend so the engine doesn't lose on time.

#pragma once

#include "types.hpp"

namespace jass {

struct TimeBudget {
    int wtime_ms   = 0;  // remaining time, white
    int btime_ms   = 0;  // remaining time, black
    int winc_ms    = 0;  // increment per move, white
    int binc_ms    = 0;  // increment per move, black
    int movestogo  = 0;  // moves until next time control; 0 = open-ended
};

// Returns the recommended budget for the side currently to move. A
// returned value of 0 means "no time information given — use whatever
// other limits the caller specified".
int compute_movetime_ms(const TimeBudget& tb, Color stm) noexcept;

}  // namespace jass
