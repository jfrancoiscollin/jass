// SPDX-License-Identifier: AGPL-3.0-or-later
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

#include <array>
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

// Compact 4-byte move record stored inside the transposition table.  The
// full `Move` (with the 20-square capture path) is reconstructed on demand
// by re-running `generate_legal_moves` for the current position and matching
// on (from, to, num_captures, promotes); this is cheap because the search
// has to generate moves anyway.
struct PackedMove {
    std::uint8_t from{0};
    std::uint8_t to{0};
    std::uint8_t num_captures{0};
    std::uint8_t promotes{0};   // 0 / 1
};
static_assert(sizeof(PackedMove) == 4);

inline PackedMove pack_move(const Move& m) noexcept {
    return {m.from, m.to, m.num_captures,
            static_cast<std::uint8_t>(m.promotes ? 1 : 0)};
}

// True when `m` matches `p` on the four "identity" fields. The capture-
// path of `m` is not consulted; `p` does not carry it.
inline bool same_packed_move(const Move& m, PackedMove p) noexcept {
    return m.from == p.from
        && m.to   == p.to
        && m.num_captures == p.num_captures
        && (m.promotes ? 1 : 0) == p.promotes;
}

struct TTEntry {
    ZobristHash  key{0};         // 8 bytes
    PackedMove   best_move{};    // 4 bytes
    std::int16_t score{0};       // 2 bytes
    std::int8_t  depth{-1};      // 1 byte
    // Packed byte:
    //   bits [0..1]  Bound  (2 bits — 4 values, 2 actually used + None)
    //   bits [2..7]  generation (6 bits — wraps every 64 top-level searches)
    // Generation lets the replacement policy de-prioritise entries left
    // over from earlier searches: a current-generation deep entry is
    // protected from being overwritten by a shallow one, but an old-
    // generation entry of any depth is fair game.
    std::uint8_t bound_gen{0};

    Bound bound() const noexcept {
        return static_cast<Bound>(bound_gen & 0x03);
    }
    std::uint8_t gen() const noexcept {
        return static_cast<std::uint8_t>((bound_gen >> 2) & 0x3F);
    }
    void set_bound_gen(Bound b, std::uint8_t g) noexcept {
        bound_gen = static_cast<std::uint8_t>(
            ((g & 0x3F) << 2) | (static_cast<std::uint8_t>(b) & 0x03));
    }
};
static_assert(sizeof(TTEntry) == 16);

// Each cluster groups four entries; on collision we look at all four
// before giving up. Sized to fit a single 64-byte cache line.
inline constexpr std::size_t TT_CLUSTER_SIZE = 4;
struct TTCluster {
    std::array<TTEntry, TT_CLUSTER_SIZE> entries{};
};
static_assert(sizeof(TTCluster) == TT_CLUSTER_SIZE * 16);

class TranspositionTable {
public:
    TranspositionTable();

    // Resize to roughly `mb` megabytes. The internal cluster count is
    // rounded down to a power of two so the index can be computed with
    // a mask.
    void resize_mb(std::size_t mb);

    // Reset every entry to "empty".
    void clear();

    // Bump the generation counter — call once at the start of every
    // top-level search. Entries written by older searches become
    // preferred replacement targets even if they sit at deeper
    // residual depths. The counter is 6 bits and wraps benignly.
    void new_search() noexcept;
    std::uint8_t current_generation() const noexcept { return current_gen_; }

    // Look up a key.  Returns true if a valid entry with this exact key
    // is present, in which case `out` is filled.
    bool probe(ZobristHash key, TTEntry& out) const noexcept;

    // Store an entry. The cluster's four entries are scanned: an empty
    // slot or the slot already holding this key wins, otherwise the
    // replacement targets the entry with the highest (old-gen, low-depth)
    // priority. New stores never overwrite a strictly deeper entry of
    // the same key.
    void store(ZobristHash key, PackedMove best_move,
               int score, int depth, Bound bound) noexcept;

    std::size_t size()     const noexcept;            // total entry slots
    std::size_t clusters() const noexcept { return cluster_table_.size(); }

private:
    std::vector<TTCluster> cluster_table_;
    std::size_t            mask_{0};                  // cluster mask
    std::uint8_t           current_gen_{0};
};

}  // namespace jass
