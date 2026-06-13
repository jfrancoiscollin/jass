// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern.hpp"
#include "weights.hpp"

#include <cstdio>
#include <iostream>
#include <random>
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
    REQUIRE_EQ(PATTERN_SIZE, std::size_t{12});
    REQUIRE_EQ(NUM_PATTERNS, std::size_t{32});                 // v4 (enriched geometry)
    REQUIRE_EQ(BUCKETS_PER_PATTERN, std::uint32_t{531441});    // 3^12
    REQUIRE_EQ(TOTAL_BUCKETS, std::uint32_t{32 * 531441});     // 17 006 112
    REQUIRE_EQ(TOTAL_BUCKETS, BUCKETS_PER_PATTERN * static_cast<std::uint32_t>(NUM_PATTERNS));

    constexpr auto offsets = pattern_offsets();
    REQUIRE_EQ(offsets[0], std::uint32_t{0});
    REQUIRE_EQ(offsets[NUM_PATTERNS - 1], std::uint32_t{(NUM_PATTERNS - 1) * 531441});
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
    // Black man on square 1 → bit 0. Only top_band_0 (idx 0) contains
    // sq 1 (at position 0). Other top_bands start at sq 2/3/4. Bottom
    // bands cover rows 4-9, exclude sq 1.
    const Bitboard b1 = Bitboard{1} << 0;
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(b1, 0, idx);

    REQUIRE_EQ(idx[0], std::uint32_t{1});  // top_band_0 (sq 1 at pos 0)
    REQUIRE_EQ(idx[1], std::uint32_t{0});  // top_band_1 (no sq 1)
    REQUIRE_EQ(idx[2], std::uint32_t{0});
    REQUIRE_EQ(idx[3], std::uint32_t{0});
    REQUIRE_EQ(idx[4], std::uint32_t{0});  // bot_band_0
    REQUIRE_EQ(idx[5], std::uint32_t{0});
    REQUIRE_EQ(idx[6], std::uint32_t{0});
    REQUIRE_EQ(idx[7], std::uint32_t{0});
}

void test_extract_single_white_far() {
    // White man on square 50 → bit 49. Only bot_band_3 (idx 7) contains
    // sq 50 at position 11 → cell=2, idx = 2 * 3^11 = 2 * 177147 = 354294.
    const Bitboard w50 = Bitboard{1} << 49;
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(0, w50, idx);

    for (std::size_t i = 0; i < 7; ++i) REQUIRE_EQ(idx[i], std::uint32_t{0});
    REQUIRE_EQ(idx[7], std::uint32_t{354294});   // bot_band_3 (sq 50 at pos 11)
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

void test_weights_loader_roundtrip() {
    const char* path = "/tmp/pattern_jass_weights_test.pjtw";
    FILE* f = std::fopen(path, "wb");
    REQUIRE(f != nullptr);
    if (!f) return;

    auto write_u32 = [](FILE* fp, std::uint32_t v) {
        unsigned char b[4] = {
            static_cast<unsigned char>( v        & 0xFF),
            static_cast<unsigned char>((v >>  8) & 0xFF),
            static_cast<unsigned char>((v >> 16) & 0xFF),
            static_cast<unsigned char>((v >> 24) & 0xFF),
        };
        std::fwrite(b, 1, 4, fp);
    };

    write_u32(f, WEIGHTS_MAGIC);
    write_u32(f, WEIGHTS_VERSION);
    write_u32(f, TOTAL_BUCKETS);
    write_u32(f, 1000);
    // weight[0] = 42, weight[BUCKETS_PER_PATTERN] = -7 (offset for pattern 1)
    for (std::uint32_t i = 0; i < TOTAL_BUCKETS; ++i) {
        std::int32_t v = 0;
        if      (i == 0)                       v = 42;
        else if (i == BUCKETS_PER_PATTERN)     v = -7;
        write_u32(f, static_cast<std::uint32_t>(v));
    }
    std::fclose(f);

    std::string err;
    auto loaded = pattern_jass::load_weights(path, &err);
    REQUIRE(loaded.has_value());
    if (!loaded) { std::cerr << "  load err: " << err << "\n"; return; }
    REQUIRE_EQ(loaded->scale, std::uint32_t{1000});
    REQUIRE_EQ(loaded->w.size(), static_cast<std::size_t>(TOTAL_BUCKETS));
    REQUIRE_EQ(loaded->w[0], std::int32_t{42});
    REQUIRE_EQ(loaded->w[BUCKETS_PER_PATTERN], std::int32_t{-7});

    std::remove(path);
}

void test_weights_loader_bad_magic() {
    const char* path = "/tmp/pattern_jass_weights_bad.pjtw";
    FILE* f = std::fopen(path, "wb");
    REQUIRE(f != nullptr);
    if (!f) return;
    const unsigned char hdr[16] = {0xDE, 0xAD, 0xBE, 0xEF};
    std::fwrite(hdr, 1, 16, f);
    std::fclose(f);

    std::string err;
    auto loaded = pattern_jass::load_weights(path, &err);
    REQUIRE(!loaded.has_value());
    std::remove(path);
}

void test_eval_pattern_zero_weights() {
    std::vector<std::int32_t> w(TOTAL_BUCKETS, 0);
    // Any position should return 0 with zero weights.
    Bitboard b = Bitboard{1} << 0;
    Bitboard wt = Bitboard{1} << 49;
    REQUIRE_EQ(eval_pattern(b, wt, w.data()), std::int64_t{0});
    REQUIRE_EQ(eval_pattern(0, 0, w.data()),  std::int64_t{0});
}

void test_eval_pattern_one_hot() {
    // Set weight at offset 0 (row_top, idx 0) = 123. Empty board has
    // all indices = 0, so eval = sum of weights[off_i + 0] for all i.
    // With only weights[0] set, eval = 123.
    std::vector<std::int32_t> w(TOTAL_BUCKETS, 0);
    w[0] = 123;
    REQUIRE_EQ(eval_pattern(0, 0, w.data()), std::int64_t{123});

    // Place black on sq 1 → row_top idx becomes 1, col_left idx becomes 1.
    // The weight at offset(row_top) + 1 = 0, and weights[off(col_left)+1] = 0.
    // But w[0] (offset(row_top) + 0) no longer contributes since idx > 0.
    // So eval = 0 now (for row_top, col_left), and 0 from other patterns.
    REQUIRE_EQ(eval_pattern(Bitboard{1} << 0, 0, w.data()), std::int64_t{0});
}

void test_update_all_matches_extract() {
    // Incremental update_all(before→after) must equal a from-scratch
    // extract_all(after), for ARBITRARY men reconfigurations (stronger than a
    // single move). Random disjoint black/white men placements.
    std::mt19937_64 rng(0xC0FFEEu);
    auto gen = [&](Bitboard& bm, Bitboard& wm) {
        bm = 0; wm = 0;
        for (int b = 0; b < 50; ++b) {
            const unsigned r = static_cast<unsigned>(rng() % 3u);
            if      (r == 1) bm |= Bitboard{1} << b;
            else if (r == 2) wm |= Bitboard{1} << b;
        }
    };
    for (int trial = 0; trial < 3000; ++trial) {
        Bitboard bm0, wm0, bm1, wm1;
        gen(bm0, wm0); gen(bm1, wm1);
        std::array<std::uint32_t, NUM_PATTERNS> idx{}, ref{};
        extract_all(bm0, wm0, idx);            // before
        update_all(bm0, wm0, bm1, wm1, idx);   // incremental → after
        extract_all(bm1, wm1, ref);            // from scratch after
        for (std::size_t i = 0; i < NUM_PATTERNS; ++i) REQUIRE_EQ(idx[i], ref[i]);
    }
    // No-op update (before == after) must leave indices untouched.
    Bitboard bm, wm; gen(bm, wm);
    std::array<std::uint32_t, NUM_PATTERNS> a{}, b{};
    extract_all(bm, wm, a); b = a;
    update_all(bm, wm, bm, wm, a);
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) REQUIRE_EQ(a[i], b[i]);
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
    test_weights_loader_roundtrip();
    test_weights_loader_bad_magic();
    test_eval_pattern_zero_weights();
    test_eval_pattern_one_hot();
    test_update_all_matches_extract();

    std::cerr << "passed: " << g_passed << "  failed: " << g_failed << '\n';
    return g_failed == 0 ? 0 : 1;
}
