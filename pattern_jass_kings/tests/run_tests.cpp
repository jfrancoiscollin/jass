// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "pattern.hpp"
#include "weights.hpp"

#include <cstdio>
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

using namespace pattern_jass_kings;

void test_layout_constants() {
    REQUIRE_EQ(PATTERN_SIZE, std::size_t{8});
    REQUIRE_EQ(NUM_PATTERNS, std::size_t{8});
    REQUIRE_EQ(BUCKETS_PER_PATTERN, std::uint32_t{390625});  // 5^8
    REQUIRE_EQ(TOTAL_BUCKETS, std::uint32_t{3125000});       // 8 * 390625
}

void test_extract_empty() {
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(0, 0, 0, 0, idx);
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        REQUIRE_EQ(idx[i], std::uint32_t{0});
    }
}

void test_extract_each_cell_value() {
    // Black man on sq 1 (pos 0 of row_top_8) → cell 1, idx 0 = 1
    {
        std::array<std::uint32_t, NUM_PATTERNS> idx{};
        extract_all(Bitboard{1} << 0, 0, 0, 0, idx);
        REQUIRE_EQ(idx[0], std::uint32_t{1});
    }
    // Black king on sq 1 → cell 2, idx 0 = 2
    {
        std::array<std::uint32_t, NUM_PATTERNS> idx{};
        extract_all(0, Bitboard{1} << 0, 0, 0, idx);
        REQUIRE_EQ(idx[0], std::uint32_t{2});
    }
    // White man on sq 1 → cell 3, idx 0 = 3
    {
        std::array<std::uint32_t, NUM_PATTERNS> idx{};
        extract_all(0, 0, Bitboard{1} << 0, 0, idx);
        REQUIRE_EQ(idx[0], std::uint32_t{3});
    }
    // White king on sq 1 → cell 4, idx 0 = 4
    {
        std::array<std::uint32_t, NUM_PATTERNS> idx{};
        extract_all(0, 0, 0, Bitboard{1} << 0, idx);
        REQUIRE_EQ(idx[0], std::uint32_t{4});
    }
}

void test_extract_max_bound() {
    // Fill all squares with white kings → max cell value 4 everywhere.
    Bitboard wk = 0;
    for (int s = 1; s <= 50; ++s) wk |= Bitboard{1} << (s - 1);
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(0, 0, 0, wk, idx);
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        REQUIRE(idx[i] < BUCKETS_PER_PATTERN);
    }
}

void test_weights_loader_roundtrip() {
    const char* path = "/tmp/pattern_jass_kings_test.pjtw";
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
    for (std::uint32_t i = 0; i < TOTAL_BUCKETS; ++i) {
        std::int32_t v = (i == 0) ? 99 : 0;
        write_u32(f, static_cast<std::uint32_t>(v));
    }
    std::fclose(f);

    std::string err;
    auto loaded = load_weights(path, &err);
    REQUIRE(loaded.has_value());
    if (!loaded) { std::cerr << "  err: " << err << "\n"; return; }
    REQUIRE_EQ(loaded->w.size(), static_cast<std::size_t>(TOTAL_BUCKETS));
    REQUIRE_EQ(loaded->w[0], std::int32_t{99});
    REQUIRE_EQ(loaded->scale, std::uint32_t{1000});
    std::remove(path);
}

}  // namespace

int main() {
    test_layout_constants();
    test_extract_empty();
    test_extract_each_cell_value();
    test_extract_max_bound();
    test_weights_loader_roundtrip();

    std::cerr << "passed: " << g_passed << "  failed: " << g_failed << '\n';
    return g_failed == 0 ? 0 : 1;
}
