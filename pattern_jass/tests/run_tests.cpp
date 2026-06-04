// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern.hpp"

#include <iostream>
#include <string>

static int g_failed = 0;
static int g_passed = 0;

#define REQUIRE(cond)                                                  \
    do {                                                               \
        if (!(cond)) {                                                 \
            ++g_failed;                                                \
            std::cerr << "FAIL " << __FILE__ << ':' << __LINE__        \
                      << "  " << #cond << '\n';                        \
        } else { ++g_passed; }                                         \
    } while (0)

#define REQUIRE_EQ(a, b)                                               \
    do {                                                               \
        const auto av = (a); const auto bv = (b);                      \
        if (!(av == bv)) {                                             \
            ++g_failed;                                                \
            std::cerr << "FAIL " << __FILE__ << ':' << __LINE__        \
                      << "  " << #a << " == " << #b                    \
                      << "  got " << av << " expected " << bv << '\n'; \
        } else { ++g_passed; }                                         \
    } while (0)

namespace {

using namespace pattern_jass;

void test_layout_constants() {
    REQUIRE_EQ(PATTERN_SIZE, std::size_t{10});
    REQUIRE_EQ(NUM_PATTERNS, std::size_t{8});
    REQUIRE_EQ(BUCKETS_PER_PATTERN, std::uint32_t{59049});  // 3^10
    REQUIRE_EQ(TOTAL_BUCKETS, std::uint32_t{472392});       // 8 * 59049

    constexpr auto offsets = pattern_offsets();
    REQUIRE_EQ(offsets[0], std::uint32_t{0});
    REQUIRE_EQ(offsets[7], std::uint32_t{7 * 59049});
}

void test_pattern_square_count() {
    // Sanity : every pattern has exactly PATTERN_SIZE squares, all in
    // 1..50, all distinct within a pattern.
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        const auto& p = PATTERNS[i];
        std::uint64_t seen = 0;
        for (Square sq : p.squares) {
            REQUIRE(sq >= 1 && sq <= 50);
            const std::uint64_t bit = std::uint64_t{1} << (sq - 1);
            REQUIRE((seen & bit) == 0);  // no duplicates
            seen |= bit;
        }
    }
}

void test_extract_empty() {
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(0, 0, idx);
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        REQUIRE_EQ(idx[i], std::uint32_t{0});
    }
}

void test_extract_single_black() {
    // Black man on square 1 → bit 0. In pattern row_top (idx 0), sq 1
    // is at position 0 → idx = 1 * 3^0 = 1. In col_left (idx 5), sq 1
    // is at position 0 → idx = 1. Others = 0.
    const Bitboard b1 = Bitboard{1} << 0;
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(b1, 0, idx);

    REQUIRE_EQ(idx[0], std::uint32_t{1});  // row_top
    REQUIRE_EQ(idx[1], std::uint32_t{0});  // row_2
    REQUIRE_EQ(idx[2], std::uint32_t{0});
    REQUIRE_EQ(idx[3], std::uint32_t{0});
    REQUIRE_EQ(idx[4], std::uint32_t{0});
    REQUIRE_EQ(idx[5], std::uint32_t{1});  // col_left
    REQUIRE_EQ(idx[6], std::uint32_t{0});  // col_mid
    REQUIRE_EQ(idx[7], std::uint32_t{0});  // col_right
}

void test_extract_single_white_far() {
    // White man on square 50 → bit 49. In row_bot (idx 4), sq 50 is at
    // position 9 → cell=2, idx = 2 * 3^9 = 2 * 19683 = 39366.
    // In col_right (idx 7), sq 50 is at position 9 → 39366.
    const Bitboard w50 = Bitboard{1} << 49;
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(0, w50, idx);

    for (std::size_t i = 0; i < 4; ++i) REQUIRE_EQ(idx[i], std::uint32_t{0});
    REQUIRE_EQ(idx[4], std::uint32_t{39366});   // row_bot
    REQUIRE_EQ(idx[5], std::uint32_t{0});
    REQUIRE_EQ(idx[6], std::uint32_t{0});
    REQUIRE_EQ(idx[7], std::uint32_t{39366});   // col_right
}

void test_extract_index_within_bounds() {
    // Fill all squares with alternating colors, check all indices stay
    // inside BUCKETS_PER_PATTERN.
    Bitboard b = 0, w = 0;
    for (int s = 1; s <= 50; ++s) {
        const Bitboard bit = Bitboard{1} << (s - 1);
        if (s % 2 == 0) b |= bit; else w |= bit;
    }
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(b, w, idx);
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        REQUIRE(idx[i] < BUCKETS_PER_PATTERN);
    }
}

void test_color_swap() {
    // Swap black<->white : every cell `1` becomes `2` and vice versa.
    // For a pattern with `k` non-empty cells (cells with values in
    // {1,2}), swap changes idx in a predictable way : new_cell = 3 -
    // old_cell. So new_idx = sum((3 - old_cell) * 3^i) over occupied i.
    // We just check the indices change (≠ 0 → ≠ swap-of-0) when there
    // are any pieces in the pattern.
    Bitboard b = Bitboard{1} << 0;  // black on sq 1
    Bitboard w = Bitboard{1} << 1;  // white on sq 2
    std::array<std::uint32_t, NUM_PATTERNS> a{}, s{};
    extract_all(b, w, a);
    extract_all(w, b, s);  // colors swapped

    // row_top contains both sq 1 and sq 2.
    // Original : black sq 1 → cell 1 at pos 0 ; white sq 2 → cell 2 at pos 1
    //   idx_a = 1*1 + 2*3 = 7
    // Swapped : black sq 2 → cell 1 at pos 1 ; white sq 1 → cell 2 at pos 0
    //   idx_s = 2*1 + 1*3 = 5
    REQUIRE_EQ(a[0], std::uint32_t{7});
    REQUIRE_EQ(s[0], std::uint32_t{5});
}

}  // namespace

int main() {
    test_layout_constants();
    test_pattern_square_count();
    test_extract_empty();
    test_extract_single_black();
    test_extract_single_white_far();
    test_extract_index_within_bounds();
    test_color_swap();

    std::cerr << "passed: " << g_passed << "  failed: " << g_failed << '\n';
    return g_failed == 0 ? 0 : 1;
}
