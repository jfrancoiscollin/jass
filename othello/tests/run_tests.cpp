// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Lightweight test harness for the Othello POC. No external framework.
// Each REQUIRE failure prints and increments a counter ; main() returns
// non-zero if any failed.

#include "board.hpp"
#include "eval.hpp"
#include "gen_data.hpp"
#include "movegen.hpp"
#include "pattern.hpp"
#include "search.hpp"

#include <vector>

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

// ---------------------------------------------------------------------------
// Pattern tests
// ---------------------------------------------------------------------------

void test_pattern_layout() {
    // 4 corners × 81 + 4 edges × 6561 + 2 diagonals × 6561 = 39690.
    REQUIRE_EQ(total_pattern_buckets(), std::size_t{39690});

    // Each PATTERNS[i].num_buckets should equal 3^size.
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        const auto& p = PATTERNS[i];
        REQUIRE_EQ(p.num_buckets, POW3[p.size]);
    }

    // Offsets cumulative + monotonic, starting at 0.
    const auto offsets = pattern_offsets();
    REQUIRE_EQ(offsets[0], std::uint32_t{0});
    for (std::size_t i = 1; i < NUM_PATTERNS; ++i) {
        REQUIRE_EQ(offsets[i], offsets[i-1] + PATTERNS[i-1].num_buckets);
    }
}

void test_pattern_empty_board() {
    const Board empty;  // all zero
    std::array<std::uint32_t, NUM_PATTERNS> indices{};
    extract_all(empty, indices);
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        REQUIRE_EQ(indices[i], std::uint32_t{0});
    }
}

void test_pattern_single_black_corner() {
    // Single black piece at square 0 (NW corner). Should set the
    // first cell of corner_NW pattern AND edge_top AND edge_left AND
    // diag_main. Others unaffected.
    Board b;
    b.black = Bitboard{1} << 0;

    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(b, idx);

    // corner_NW : squares[0]=0, so cell 0 = black = 1, idx = 1 * 3^0 = 1
    REQUIRE_EQ(idx[0], std::uint32_t{1});
    // corner_NE/SW/SE : sq 0 not in pattern → 0
    REQUIRE_EQ(idx[1], std::uint32_t{0});
    REQUIRE_EQ(idx[2], std::uint32_t{0});
    REQUIRE_EQ(idx[3], std::uint32_t{0});
    // edge_top : squares[0]=0 → idx 1
    REQUIRE_EQ(idx[4], std::uint32_t{1});
    // edge_bot : no overlap → 0
    REQUIRE_EQ(idx[5], std::uint32_t{0});
    // edge_left : squares[0]=0 → idx 1
    REQUIRE_EQ(idx[6], std::uint32_t{1});
    // edge_right : no overlap → 0
    REQUIRE_EQ(idx[7], std::uint32_t{0});
    // diag_main : squares[0]=0 → idx 1
    REQUIRE_EQ(idx[8], std::uint32_t{1});
    // diag_anti : no overlap → 0
    REQUIRE_EQ(idx[9], std::uint32_t{0});
}

void test_pattern_single_white_corner() {
    // Same but white piece. Cell value = 2 → idx = 2.
    Board b;
    b.white = Bitboard{1} << 0;

    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(b, idx);

    REQUIRE_EQ(idx[0], std::uint32_t{2});  // corner_NW
    REQUIRE_EQ(idx[4], std::uint32_t{2});  // edge_top
    REQUIRE_EQ(idx[6], std::uint32_t{2});  // edge_left
    REQUIRE_EQ(idx[8], std::uint32_t{2});  // diag_main
}

void test_pattern_index_max_value() {
    // Full board with alternating black/white maxing out each
    // pattern's index. Easier check : sanity that no index ever
    // exceeds num_buckets - 1.
    Board b;
    // Fill all 64 squares with checkerboard.
    for (Square s = 0; s < BOARD_SIZE; ++s) {
        const Bitboard bit = Bitboard{1} << s;
        if ((sq_row(s) + sq_col(s)) % 2 == 0) b.black |= bit;
        else                                  b.white |= bit;
    }
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(b, idx);
    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        REQUIRE(idx[i] < PATTERNS[i].num_buckets);
    }
}

void test_pattern_start_position() {
    const Board b = Board::start_position();
    // Black on e4(28), d5(35). White on d4(27), e5(36).
    // None of these are in corner 2x2 patterns or edges (all in
    // central 4×4 region), so corner/edge indices = 0.
    // diag_main covers d5(35), e4(28) ? Let's check :
    //   diag_main squares = {0, 9, 18, 27, 36, 45, 54, 63}
    //     27 = white → cell 2 at position 3
    //     36 = white → cell 2 at position 4
    //     others empty
    //   idx = 2*81 + 2*243 = 162 + 486 = 648
    // diag_anti squares = {7, 14, 21, 28, 35, 42, 49, 56}
    //     28 = black → cell 1 at position 3
    //     35 = black → cell 1 at position 4
    //   idx = 1*27 + 1*81 = 27 + 81 = ... wait pos 3 = POW3[3] = 27
    //                                       pos 4 = POW3[4] = 81
    //   idx = 27 + 81 = 108
    std::array<std::uint32_t, NUM_PATTERNS> idx{};
    extract_all(b, idx);

    REQUIRE_EQ(idx[0], std::uint32_t{0});  // corner_NW empty
    REQUIRE_EQ(idx[1], std::uint32_t{0});  // corner_NE empty
    REQUIRE_EQ(idx[2], std::uint32_t{0});  // corner_SW empty
    REQUIRE_EQ(idx[3], std::uint32_t{0});  // corner_SE empty
    REQUIRE_EQ(idx[4], std::uint32_t{0});  // edge_top empty
    REQUIRE_EQ(idx[5], std::uint32_t{0});  // edge_bot empty
    REQUIRE_EQ(idx[6], std::uint32_t{0});  // edge_left empty
    REQUIRE_EQ(idx[7], std::uint32_t{0});  // edge_right empty
    // diag_main : white(2) at pos 3 & 4 → 2*27 + 2*81 = 216
    REQUIRE_EQ(idx[8], std::uint32_t{216});
    // diag_anti : black(1) at pos 3 & 4 → 1*27 + 1*81 = 108
    REQUIRE_EQ(idx[9], std::uint32_t{108});
}

void test_pattern_color_flip() {
    // Flipping colors should map cell 1 -> 2 and vice versa.
    // We verify : extract_all_flipped(b) == extract_all(swap(b)).
    Board b = Board::start_position();
    // Add a few more pieces to make patterns non-trivial.
    b.black |= Bitboard{1} << 0;
    b.white |= Bitboard{1} << 63;

    std::array<std::uint32_t, NUM_PATTERNS> flipped{};
    extract_all_flipped(b, flipped);

    Board b2 = b;
    std::swap(b2.black, b2.white);
    std::array<std::uint32_t, NUM_PATTERNS> swapped{};
    extract_all(b2, swapped);

    for (std::size_t i = 0; i < NUM_PATTERNS; ++i) {
        REQUIRE_EQ(flipped[i], swapped[i]);
    }
}

// ---------------------------------------------------------------------------
// Eval tests
// ---------------------------------------------------------------------------

void test_eval_basic_start_zero() {
    // Start position is symmetric (2 black + 2 white centered, same
    // mobility). eval_basic should return 0.
    const Board b = Board::start_position();
    REQUIRE_EQ(eval_basic(b), 0);
}

void test_eval_basic_corner_bonus() {
    // Single black piece at corner 0. STM = black. eval should reward
    // black for owning a corner.
    Board b;
    b.black = Bitboard{1} << 0;
    b.stm = Color::Black;
    REQUIRE(eval_basic(b) > 0);

    // Same position but stm = white : eval should be opposite sign.
    b.stm = Color::White;
    REQUIRE(eval_basic(b) < 0);
}

void test_eval_basic_sign_symmetry() {
    // If we swap colors AND stm, eval_basic should return the SAME
    // value (the position is identical from the new stm's POV).
    Board b = Board::start_position();
    b.black |= Bitboard{1} << 0;   // black gets corner NW
    b.white |= Bitboard{1} << 7;   // white gets corner NE
    const int eb = eval_basic(b);

    Board b2 = b;
    std::swap(b2.black, b2.white);
    b2.stm = ~b2.stm;
    REQUIRE_EQ(eval_basic(b2), eb);
}

void test_eval_pattern_zero_weights() {
    // With all-zero weights, eval_pattern returns 0.
    std::vector<std::int32_t> w(total_pattern_buckets(), 0);
    const Board b = Board::start_position();
    REQUIRE_EQ(eval_pattern(b, w), 0);
}

void test_eval_pattern_one_hot() {
    // Set a single weight at the offset of corner_NW pattern, index 1
    // (= black piece at sq 0). Then place black at sq 0 and verify
    // eval_pattern returns that weight (or its negative for white stm).
    std::vector<std::int32_t> w(total_pattern_buckets(), 0);
    constexpr auto offsets = pattern_offsets();
    w[offsets[0] + 1] = 12345;

    Board b;
    b.black = Bitboard{1} << 0;
    b.stm = Color::Black;
    REQUIRE_EQ(eval_pattern(b, w), 12345);

    b.stm = Color::White;
    REQUIRE_EQ(eval_pattern(b, w), -12345);
}

// ---------------------------------------------------------------------------
// Search tests
// ---------------------------------------------------------------------------

void test_search_picks_move_start() {
    const Board b = Board::start_position();
    SearchConfig cfg;
    cfg.max_depth = 3;
    const SearchResult r = search(b, cfg);
    // Must return one of the 4 legal moves (19, 26, 37, 44).
    REQUIRE(r.best_move == 19 || r.best_move == 26
         || r.best_move == 37 || r.best_move == 44);
    REQUIRE(r.depth_reached >= 1);
    REQUIRE(r.nodes > 0);
}

void test_search_must_pass() {
    // Sparse board where stm has no legal moves but opp does.
    Board b;
    b.black = Bitboard{1} << 0;
    b.white = Bitboard{1} << 63;
    b.stm = Color::Black;
    SearchConfig cfg;
    cfg.max_depth = 1;
    const SearchResult r = search(b, cfg);
    REQUIRE(r.best_move == NO_SQUARE);
}

void test_gen_data_constants() {
    REQUIRE_EQ(GEN_DATA_MAGIC,       std::uint32_t{0x4F544843});
    REQUIRE_EQ(GEN_DATA_VERSION,     std::uint32_t{1});
    REQUIRE_EQ(GEN_DATA_RECORD_SIZE, std::size_t{18});
    REQUIRE_EQ(GEN_DATA_HEADER_SIZE, std::size_t{16});
}

void test_search_terminal() {
    // Fabricated terminal : both have passed already.
    Board b;
    b.black = Bitboard{1} << 0;
    b.white = Bitboard{1} << 63;
    b.passes = 2;
    REQUIRE(b.is_game_over());
    SearchConfig cfg;
    cfg.max_depth = 1;
    const SearchResult r = search(b, cfg);
    // Black and white have 1 piece each → DRAW_SCORE = 0.
    REQUIRE_EQ(r.score, 0);
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

    test_pattern_layout();
    test_pattern_empty_board();
    test_pattern_single_black_corner();
    test_pattern_single_white_corner();
    test_pattern_index_max_value();
    test_pattern_start_position();
    test_pattern_color_flip();

    test_eval_basic_start_zero();
    test_eval_basic_corner_bonus();
    test_eval_basic_sign_symmetry();
    test_eval_pattern_zero_weights();
    test_eval_pattern_one_hot();

    test_search_picks_move_start();
    test_search_must_pass();
    test_search_terminal();
    test_gen_data_constants();

    std::cerr << "passed: " << g_passed << "  failed: " << g_failed << '\n';
    return g_failed == 0 ? 0 : 1;
}
