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
}

bool TranspositionTable::probe(ZobristHash key, TTEntry& out) const noexcept {
    const TTCluster& c = cluster_table_[key & mask_];
    for (const TTEntry& e : c.entries) {
        if (e.bound != Bound::None && e.key == key) {
            out = e;
            return true;
        }
    }
    return false;
}

void TranspositionTable::store(ZobristHash key, PackedMove best_move,
                               int score, int depth, Bound bound) noexcept {
    TTCluster& c = cluster_table_[key & mask_];

    // Pick which of the four slots wins this write:
    //   1. an empty slot (Bound::None),
    //   2. the slot already holding this exact key (refresh in place),
    //   3. otherwise, the slot with the lowest stored depth.
    //
    // A same-key write only overwrites if the new entry was searched at
    // least as deep as the current one — same as the v0.1 single-slot
    // policy, just generalised over the cluster.
    TTEntry* dest = nullptr;
    int      min_depth_seen = std::numeric_limits<int>::max();
    TTEntry* shallowest    = &c.entries[0];

    for (TTEntry& e : c.entries) {
        if (e.bound == Bound::None) {            // empty slot wins
            dest = &e;
            break;
        }
        if (e.key == key) {                      // refresh in place
            if (depth >= e.depth) dest = &e;
            else                  return;        // never overwrite a deeper hit
            break;
        }
        if (e.depth < min_depth_seen) {
            min_depth_seen = e.depth;
            shallowest     = &e;
        }
    }
    if (!dest) dest = shallowest;

    dest->key       = key;
    dest->best_move = best_move;
    dest->score     = static_cast<std::int16_t>(score);
    dest->depth     = static_cast<std::int8_t>(depth);
    dest->bound     = bound;
}

std::size_t TranspositionTable::size() const noexcept {
    return cluster_table_.size() * TT_CLUSTER_SIZE;
}

}  // namespace jass
