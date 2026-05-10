// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Zobrist hashing for `Position`. The hash collapses (white men, white kings,
// black men, black kings, side-to-move) into a single 64-bit value with
// negligible collision probability for any realistic search.
//
// Currently the hash is recomputed from scratch on every probe — a
// deliberate simplification while the engine is small. If profiling later
// shows hashing as a bottleneck, the same XOR keys can be applied
// incrementally inside `Position::after`.

#pragma once

#include "position.hpp"

#include <cstdint>

namespace jass {

using ZobristHash = std::uint64_t;

ZobristHash zobrist_hash(const Position& pos) noexcept;

}  // namespace jass
