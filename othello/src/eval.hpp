// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Othello evaluation.
//
// Two flavours :
//   * eval_basic(b)         — hand-tuned baseline (mobility, corners,
//                             piece diff with phase blend). No weights.
//   * eval_pattern(b, w)    — linear pattern eval : sum(w[idx[i]]) over
//                             the 10 PATTERNS. Used after Day 5 training.
//
// All evals return a score in "centi-piece" units from the side-to-move's
// POV (positive = stm winning). Search uses negamax convention.

#pragma once

#include "board.hpp"
#include "pattern.hpp"

#include <array>
#include <cstdint>
#include <vector>

namespace othello {

// Bounds for terminal-game scoring. Any non-terminal eval result will
// be clamped inside (-WIN_SCORE+1000, WIN_SCORE-1000) to keep room
// for mate-distance differentiation in search.
constexpr int WIN_SCORE  = 1000000;
constexpr int DRAW_SCORE = 0;

// Hand-tuned baseline eval. Returns score from stm POV.
//
// Components :
//   - corner ownership : ±500 per corner
//   - mobility         : ±10 per legal move
//   - piece diff       : ±(phase × piece_diff)
// where phase ∈ [0, 100] grows from 0 (no pieces) to 100 (full board).
// Result : early game weights mobility/corner, late game weights piece count.
int eval_basic(const Board& b) noexcept;

// Linear pattern eval. weights[] must be at least total_pattern_buckets()
// long (default 39690 entries). Returns score from stm POV by combining
// stm-POV indices.
int eval_pattern(const Board& b, const std::int32_t* weights) noexcept;

// Convenience : vector overload (caller owns the vector).
inline int eval_pattern(const Board& b, const std::vector<std::int32_t>& w) noexcept {
    return eval_pattern(b, w.data());
}

// Terminal score for a finished game, from stm POV. Returns +WIN_SCORE
// if stm has more pieces, -WIN_SCORE if opponent has more, 0 if equal.
int terminal_score(const Board& b) noexcept;

}  // namespace othello
