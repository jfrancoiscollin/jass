// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "tt.hpp"

#include <algorithm>
#include <bit>

namespace jass {

TranspositionTable::TranspositionTable() {
    resize_mb(16);  // sensible default
}

void TranspositionTable::resize_mb(std::size_t mb) {
    const std::size_t bytes = mb * std::size_t{1024} * std::size_t{1024};
    std::size_t count = bytes / sizeof(TTEntry);
    if (count == 0) count = 1;
    count = std::bit_floor(count);
    entries_.assign(count, TTEntry{});
    mask_ = count - 1;
}

void TranspositionTable::clear() {
    std::fill(entries_.begin(), entries_.end(), TTEntry{});
}

bool TranspositionTable::probe(ZobristHash key, TTEntry& out) const noexcept {
    const TTEntry& e = entries_[key & mask_];
    if (e.bound != Bound::None && e.key == key) {
        out = e;
        return true;
    }
    return false;
}

void TranspositionTable::store(ZobristHash  key,
                               const Move&  best_move,
                               int          score,
                               int          depth,
                               Bound        bound) noexcept {
    TTEntry& e = entries_[key & mask_];
    if (e.bound == Bound::None || depth >= e.depth) {
        e.key       = key;
        e.best_move = best_move;
        e.score     = static_cast<std::int16_t>(score);
        e.depth     = static_cast<std::int8_t>(depth);
        e.bound     = bound;
    }
}

}  // namespace jass
