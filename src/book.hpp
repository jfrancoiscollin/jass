// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Tiny opening book: a map from Zobrist hash to a single recommended
// move, populated from a hand-coded list of opening lines.
//
// This is enough to take the engine out of the early opening with
// reasonable moves rather than burning search effort on it. A larger
// book read from a file is a future refinement; the public API does
// not need to change for that.

#pragma once

#include "position.hpp"
#include "types.hpp"
#include "zobrist.hpp"

#include <cstddef>
#include <optional>
#include <unordered_map>

namespace jass {

class Book {
public:
    Book();

    // Probe the book for a move applicable in `pos`. Returns nullopt on
    // miss, on hash collision (the stored move isn't legal here) or if
    // the book is disabled.
    std::optional<Move> probe(const Position& pos) const;

    std::size_t size() const noexcept { return entries_.size(); }

private:
    std::unordered_map<ZobristHash, Move> entries_;

    void populate();
};

}  // namespace jass
