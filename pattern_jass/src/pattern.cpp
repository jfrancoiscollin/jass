// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern.hpp"

#include <bit>
#include <cstdint>

namespace pattern_jass {

namespace {

// Reverse map : square-bit b (0..49) → the (pattern, position) pairs whose
// pattern contains FMJD square (b+1). Built once from PATTERNS at static init.
// Flat layout : refs for bit b live in flat[off[b] .. off[b+1]).
struct PatRef { std::uint8_t p; std::uint8_t i; };

struct ReverseMap {
    std::array<std::uint16_t, 51> off{};
    std::array<PatRef, NUM_PATTERNS * PATTERN_SIZE> flat{};

    ReverseMap() noexcept {
        std::array<std::uint16_t, 50> cnt{};
        for (std::size_t p = 0; p < NUM_PATTERNS; ++p)
            for (std::size_t i = 0; i < PATTERN_SIZE; ++i)
                ++cnt[PATTERNS[p].squares[i] - 1u];
        std::uint16_t acc = 0;
        for (int b = 0; b < 50; ++b) { off[b] = acc; acc = static_cast<std::uint16_t>(acc + cnt[b]); }
        off[50] = acc;
        std::array<std::uint16_t, 50> cur{};
        for (int b = 0; b < 50; ++b) cur[b] = off[b];
        for (std::size_t p = 0; p < NUM_PATTERNS; ++p)
            for (std::size_t i = 0; i < PATTERN_SIZE; ++i) {
                const int b = PATTERNS[p].squares[i] - 1;
                flat[cur[b]++] = PatRef{static_cast<std::uint8_t>(p),
                                        static_cast<std::uint8_t>(i)};
            }
    }
};

const ReverseMap g_revmap;

}  // namespace

std::uint32_t extract_index(Bitboard black_men, Bitboard white_men,
                            const Pattern& p) noexcept {
    std::uint32_t idx = 0;
    for (std::size_t i = 0; i < PATTERN_SIZE; ++i) {
        const Square sq = p.squares[i];        // FMJD 1..50
        const Bitboard bit = Bitboard{1} << (sq - 1);
        std::uint32_t cell = 0;
        if      (black_men & bit) cell = 1;
        else if (white_men & bit) cell = 2;
        idx += cell * POW3[i];
    }
    return idx;
}

void extract_all(Bitboard black_men, Bitboard white_men,
                 std::array<std::uint32_t, NUM_PATTERNS>& out) noexcept {
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        out[i] = extract_index(black_men, white_men, PATTERNS[i]);
    }
}

void update_all(Bitboard bm_before, Bitboard wm_before,
                Bitboard bm_after,  Bitboard wm_after,
                std::array<std::uint32_t, NUM_PATTERNS>& idx) noexcept {
    // Squares whose men-occupancy changed (a captured/moved/promoted man flips
    // a bit in bm or wm). Kings are not in patterns, so king bits don't matter.
    Bitboard changed = (bm_before ^ bm_after) | (wm_before ^ wm_after);
    while (changed) {
        const int b = std::countr_zero(changed);
        changed &= changed - 1;                       // clear lowest set bit
        const Bitboard bit = Bitboard{1} << b;
        const int oldc = (bm_before & bit) ? 1 : (wm_before & bit) ? 2 : 0;
        const int newc = (bm_after  & bit) ? 1 : (wm_after  & bit) ? 2 : 0;
        const int d = newc - oldc;
        if (d == 0) continue;                         // safety (shouldn't occur)
        for (std::uint16_t k = g_revmap.off[b]; k < g_revmap.off[b + 1]; ++k) {
            const PatRef r = g_revmap.flat[k];
            idx[r.p] = static_cast<std::uint32_t>(
                static_cast<std::int32_t>(idx[r.p])
                + d * static_cast<std::int32_t>(POW3[r.i]));
        }
    }
}

}  // namespace pattern_jass
