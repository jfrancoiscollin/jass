// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Static evaluation of a draughts position.
//
// The score is returned from the side-to-move point of view (positive =
// good for the side to move), as expected by the negamax search.
//
// Current terms (all values handcrafted, not tuned yet):
//   - material: man = 100, king = 300
//   - advancement PSQT for men (bonus growing toward the promotion row)
//   - centralisation PSQT for kings (bonus near the centre)
//   - tempo: a small bonus for the side to move
//
// Further terms — mobility, safe-square tactics, structure, …  — will be
// added iteratively without changing the signature.

#pragma once

#include "position.hpp"

namespace jass {

inline constexpr int MAN_VALUE    = 100;
inline constexpr int KING_VALUE   = 300;
inline constexpr int TEMPO_BONUS  = 5;

int evaluate(const Position& pos) noexcept;

}  // namespace jass
