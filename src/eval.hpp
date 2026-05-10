// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Static evaluation of a draughts position.
//
// This first iteration is intentionally trivial: a flat material count with
// fixed values for men and kings. The score is returned from the side-to-move
// point of view (positive = good for the side to move), as expected by the
// negamax search.
//
// More elaborate terms — piece-square tables, mobility, advancement, tempo,
// king safety, … — will be layered on top later without changing the
// signature.

#pragma once

#include "position.hpp"

namespace jass {

inline constexpr int MAN_VALUE  = 100;
inline constexpr int KING_VALUE = 300;

int evaluate(const Position& pos) noexcept;

}  // namespace jass
