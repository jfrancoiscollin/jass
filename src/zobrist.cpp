// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "zobrist.hpp"

#include "zobrist_keys.hpp"

namespace jass {

namespace {

// SplitMix64 — a public-domain finalizer used to produce well-distributed
// 64-bit pseudo-random values from a deterministic seed. Implementation:
// see https://prng.di.unimi.it/splitmix64.c.
constexpr std::uint64_t splitmix64(std::uint64_t z) noexcept {
    z += 0x9E3779B97F4A7C15ULL;
    z ^= z >> 30;
    z *= 0xBF58476D1CE4E5B9ULL;
    z ^= z >> 27;
    z *= 0x94D049BB133111EBULL;
    z ^= z >> 31;
    return z;
}

constexpr ZobristKeys build_keys() {
    ZobristKeys t{};
    std::uint64_t seed = 0x0123456789ABCDEFULL;
    auto next = [&seed]() {
        seed = splitmix64(seed);
        return seed;
    };
    for (int k = 0; k < 4; ++k) {
        for (int b = 0; b < NUM_SQUARES; ++b) {
            t.piece[static_cast<std::size_t>(k)]
                   [static_cast<std::size_t>(b)] = next();
        }
    }
    t.side_to_move = next();
    return t;
}

}  // namespace

constinit const ZobristKeys ZOBRIST = build_keys();

ZobristHash zobrist_hash(const Position& pos) noexcept {
    return pos.hash();
}

}  // namespace jass
