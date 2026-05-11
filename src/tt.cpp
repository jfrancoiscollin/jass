// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "tt.hpp"

#include <algorithm>
#include <bit>
#include <limits>

namespace jass {

TranspositionTable::TranspositionTable() {
    resize_mb(16);  // sensible default
}

void TranspositionTable::resize_mb(std::size_t mb) {
    const std::size_t bytes = mb * std::size_t{1024} * std::size_t{1024};
    std::size_t count = bytes / sizeof(TTCluster);
    if (count == 0) count = 1;
    count = std::bit_floor(count);
    cluster_table_.assign(count, TTCluster{});
    mask_ = count - 1;
}

void TranspositionTable::clear() {
    std::fill(cluster_table_.begin(), cluster_table_.end(), TTCluster{});
    current_gen_ = 0;
}

void TranspositionTable::new_search() noexcept {
    current_gen_ = static_cast<std::uint8_t>((current_gen_ + 1) & 0x3F);
}

bool TranspositionTable::probe(ZobristHash key, TTEntry& out) const noexcept {
    const TTCluster& c = cluster_table_[key & mask_];
    for (const TTEntry& e : c.entries) {
        if (e.bound() != Bound::None && e.key == key) {
            out = e;
            return true;
        }
    }
    return false;
}

void TranspositionTable::store(ZobristHash key, PackedMove best_move,
                               int score, int depth, Bound bound) noexcept {
    TTCluster& c = cluster_table_[key & mask_];

    // Find the destination:
    //   1. An empty slot (Bound::None) wins immediately.
    //   2. A slot already holding this exact key refreshes in place,
    //      but only when the new entry was searched at least as deep.
    //   3. Otherwise pick the entry with the highest replacement
    //      priority, computed as `(is_old ? OLD_BONUS : 0) - e.depth`.
    //      Old-generation entries dominate young ones regardless of
    //      their stored depth; among entries of the same age, the
    //      shallowest one loses.
    constexpr int OLD_BONUS = 1000;

    TTEntry* dest      = nullptr;
    TTEntry* fallback  = nullptr;
    int      best_pri  = std::numeric_limits<int>::min();

    for (TTEntry& e : c.entries) {
        if (e.bound() == Bound::None) {
            dest = &e;
            break;
        }
        if (e.key == key) {
            if (depth >= e.depth) dest = &e;
            else                  return;  // never overwrite a deeper hit
            break;
        }
        const bool is_old = (e.gen() != current_gen_);
        const int  pri    = (is_old ? OLD_BONUS : 0) - static_cast<int>(e.depth);
        if (pri > best_pri) {
            best_pri = pri;
            fallback = &e;
        }
    }
    if (!dest) dest = fallback;

    dest->key       = key;
    dest->best_move = best_move;
    dest->score     = static_cast<std::int16_t>(score);
    dest->depth     = static_cast<std::int8_t>(depth);
    dest->set_bound_gen(bound, current_gen_);
}

std::size_t TranspositionTable::size() const noexcept {
    return cluster_table_.size() * TT_CLUSTER_SIZE;
}

}  // namespace jass
