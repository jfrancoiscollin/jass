// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// A small power-of-two transposition table.
//
// Each slot stores: the position's Zobrist key, the best move found at that
// depth, the score, the depth at which the score was computed, and a bound
// flag (Exact / Lower / Upper). The replacement scheme is depth-preferred:
// a probe collision overwrites the existing slot only if the new entry was
// searched at least as deeply.

#pragma once

#include "types.hpp"
#include "zobrist.hpp"

#include <cstddef>
#include <cstdint>
#include <vector>

namespace jass {

enum class Bound : std::uint8_t {
    None  = 0,
    Exact = 1,  // exact score
    Lower = 2,  // fail-high: actual score >= stored score (we cut on beta)
    Upper = 3,  // fail-low : actual score <= stored score (no move beat alpha)
};

struct TTEntry {
    ZobristHash  key{0};
    Move         best_move{};
    std::int16_t score{0};
    std::int8_t  depth{-1};
    Bound        bound{Bound::None};
};

class TranspositionTable {
public:
    TranspositionTable();

    // Resize to roughly `mb` megabytes. The internal slot count is rounded
    // down to a power of two so the index can be computed with a mask.
    void resize_mb(std::size_t mb);

    // Reset every slot to "empty". Cheap because TTEntry is trivially-
    // copyable; intended to be called between independent searches.
    void clear();

    // Look up a key. Returns true if a valid entry with this exact key is
    // present, in which case `out` is filled.
    bool probe(ZobristHash key, TTEntry& out) const noexcept;

    // Store an entry. The current slot is overwritten only if its existing
    // contents are stale (no key) or were searched at a lower depth.
    void store(ZobristHash  key,
               const Move&  best_move,
               int          score,
               int          depth,
               Bound        bound) noexcept;

    std::size_t size() const noexcept { return entries_.size(); }

private:
    std::vector<TTEntry> entries_;
    std::size_t          mask_{0};
};

}  // namespace jass
