// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Lightweight test harness for the Othello POC. No external framework.
// Each REQUIRE failure prints and increments a counter ; main() returns
// non-zero if any failed.

#include "board.hpp"
#include "movegen.hpp"

#include <cstdint>
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
        } else {                                                       \
            ++g_passed;                                                \
        }                                                              \
    } while (0)

#define REQUIRE_EQ(a, b)                                               \
    do {                                                               \
        const auto av = (a);                                           \
        const auto bv = (b);                                           \
        if (!(av == bv)) {                                             \
            ++g_failed;                                                \
            std::cerr << "FAIL " << __FILE__ << ':' << __LINE__        \
                      << "  " << #a << " == " << #b                    \
                      << "  got " << av << " expected " << bv << '\n'; \
        } else {                                                       \
            ++g_passed;                                                \
        }                                                              \
    } while (0)

namespace {

using namespace othello;

void test_start_position() {
    const Board b = Board::start_position();
    REQUIRE_EQ(b.black_count(), 2);
    REQUIRE_EQ(b.white_count(), 2);
    REQUIRE(b.stm == Color::Black);
    REQUIRE(!b.is_game_over());
    // Black on e4(28), d5(35). White on d4(27), e5(36).
    REQUIRE_EQ(b.black, (Bitboard{1} << 28) | (Bitboard{1} << 35));
    REQUIRE_EQ(b.white, (Bitboard{1} << 27) | (Bitboard{1} << 36));
}

void test_to_string_roundtrip() {
    const Board b = Board::start_position();
    const std::string s = b.to_string();
    REQUIRE_EQ(s, std::string("B:28,35:27,36"));
    const auto parsed = Board::from_string(s);
    REQUIRE(parsed.has_value());
    REQUIRE(*parsed == b);

    // White-to-move, with explicit passes suffix.
    Board b2;
    b2.black = Bitboard{1} << 0;
    b2.white = Bitboard{1} << 63;
    b2.stm = Color::White;
    b2.passes = 1;
    const std::string s2 = b2.to_string();
    REQUIRE_EQ(s2, std::string("W:0:63:p1"));
    const auto parsed2 = Board::from_string(s2);
    REQUIRE(parsed2.has_value());
    REQUIRE(*parsed2 == b2);
}

void test_from_string_invalid() {
    REQUIRE(!Board::from_string("").has_value());
    REQUIRE(!Board::from_string("X:0:1").has_value());          // bad stm
    REQUIRE(!Board::from_string("B:64:0").has_value());         // out of range
    REQUIRE(!Board::from_string("B:0:0").has_value());          // overlap
    REQUIRE(!Board::from_string("B::").has_value() == false);   // both empty IS valid
}

void test_legal_moves_start() {
    const Board b = Board::start_position();
    MoveList ml;
    generate_legal_moves(b, ml);
    REQUIRE_EQ(ml.size(), std::size_t{4});

    // Standard start position : Black can play d3(19), c4(26), f5(37), e6(44).
    std::uint64_t got = 0;
    for (std::size_t i = 0; i < ml.size(); ++i) {
        got |= Bitboard{1} << ml[i];
    }
    const std::uint64_t expected = (Bitboard{1} << 19)
                                 | (Bitboard{1} << 26)
                                 | (Bitboard{1} << 37)
                                 | (Bitboard{1} << 44);
    REQUIRE_EQ(got, expected);
}

void test_apply_move_flips() {
    Board b = Board::start_position();
    // Black plays d3 (square 19). Flips d4 (square 27).
    const Bitboard flips = flips_for_move(b, 19);
    REQUIRE_EQ(flips, Bitboard{1} << 27);
    REQUIRE(apply_move(b, 19));
    REQUIRE_EQ(b.black_count(), 4);
    REQUIRE_EQ(b.white_count(), 1);
    REQUIRE(b.stm == Color::White);
    REQUIRE_EQ(b.passes, std::uint8_t{0});
}

void test_apply_illegal() {
    Board b = Board::start_position();
    // (0,0) is not a legal move from start.
    REQUIRE_EQ(flips_for_move(b, 0), Bitboard{0});
    REQUIRE(!apply_move(b, 0));
    // Board unchanged.
    REQUIRE_EQ(b.black_count(), 2);
    REQUIRE_EQ(b.white_count(), 2);
    REQUIRE(b.stm == Color::Black);
}

void test_pass_then_pass_terminates() {
    // Construct a contrived position where neither side has a move.
    // Empty board with one black and one white piece, isolated.
    Board b;
    b.black = Bitboard{1} << 0;
    b.white = Bitboard{1} << 63;
    b.stm = Color::Black;
    MoveList ml;
    generate_legal_moves(b, ml);
    REQUIRE(ml.empty());

    REQUIRE(apply_move(b, NO_SQUARE));
    REQUIRE_EQ(b.passes, std::uint8_t{1});
    REQUIRE(!b.is_game_over());

    generate_legal_moves(b, ml);
    REQUIRE(ml.empty());
    REQUIRE(apply_move(b, NO_SQUARE));
    REQUIRE_EQ(b.passes, std::uint8_t{2});
    REQUIRE(b.is_game_over());
}

// Standard Othello perft values from the initial position. Source :
// reversi/edax-style perft (no special pass handling required at these
// depths since both players have legal moves throughout).
//   depth 1: 4
//   depth 2: 12
//   depth 3: 56
//   depth 4: 244
//   depth 5: 1396
//   depth 6: 8200
std::uint64_t perft(Board b, int depth) {
    if (depth == 0) return 1;
    MoveList ml;
    generate_legal_moves(b, ml);
    if (ml.empty()) {
        if (b.passes >= 1) return 1;
        Board after = b;
        apply_move(after, NO_SQUARE);
        return perft(after, depth - 1);
    }
    std::uint64_t total = 0;
    for (std::size_t i = 0; i < ml.size(); ++i) {
        Board after = b;
        apply_move(after, ml[i]);
        total += perft(after, depth - 1);
    }
    return total;
}

void test_perft_known_values() {
    const Board start = Board::start_position();
    REQUIRE_EQ(perft(start, 1), std::uint64_t{4});
    REQUIRE_EQ(perft(start, 2), std::uint64_t{12});
    REQUIRE_EQ(perft(start, 3), std::uint64_t{56});
    REQUIRE_EQ(perft(start, 4), std::uint64_t{244});
    REQUIRE_EQ(perft(start, 5), std::uint64_t{1396});
    REQUIRE_EQ(perft(start, 6), std::uint64_t{8200});
}

}  // namespace

int main() {
    test_start_position();
    test_to_string_roundtrip();
    test_from_string_invalid();
    test_legal_moves_start();
    test_apply_move_flips();
    test_apply_illegal();
    test_pass_then_pass_terminates();
    test_perft_known_values();

    std::cerr << "passed: " << g_passed << "  failed: " << g_failed << '\n';
    return g_failed == 0 ? 0 : 1;
}
