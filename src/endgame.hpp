// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Endgame knowledge: a small probe that recognises positions whose
// theoretical result is known and returns it directly so the search does
// not waste nodes re-deriving them.
//
// The current implementation contains the simplest such case:
//
//   - K vs K (one king on each side, no men): always a draw under FMJD
//     rules — neither king can ever capture and both can always move.
//
// More elaborate cases (KK vs K, K vs KK, …) belong in a real
// retrograde-analysis bitbase. The probe interface here is sized to
// accept those without changing its callers.

#pragma once

#include "position.hpp"

#include <cstdint>

namespace jass {

enum class EndgameResult : std::uint8_t {
    Unknown   = 0,  // not in the tablebase — let the normal search run
    Draw      = 1,
    WhiteWin  = 2,
    BlackWin  = 3,
};

EndgameResult probe_endgame(const Position& pos) noexcept;

}  // namespace jass
