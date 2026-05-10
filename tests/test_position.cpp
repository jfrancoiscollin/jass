// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Tiny self-contained test runner. No external framework: we accumulate
// failures and exit non-zero if anything fails, printing each failure with
// file/line info.

#include "bitboard.hpp"
#include "board.hpp"
#include "position.hpp"
#include "types.hpp"

#include <cstdio>
#include <cstdlib>
#include <string>

namespace {

int g_failures = 0;
int g_assertions = 0;

#define JASS_CHECK(cond)                                                       \
    do {                                                                       \
        ++g_assertions;                                                        \
        if (!(cond)) {                                                         \
            ++g_failures;                                                      \
            std::fprintf(stderr, "[FAIL] %s:%d: %s\n",                         \
                         __FILE__, __LINE__, #cond);                           \
        }                                                                      \
    } while (0)

#define JASS_CHECK_EQ(a, b)                                                    \
    do {                                                                       \
        ++g_assertions;                                                        \
        const auto _va = (a);                                                  \
        const auto _vb = (b);                                                  \
        if (!(_va == _vb)) {                                                   \
            ++g_failures;                                                      \
            std::fprintf(stderr,                                               \
                         "[FAIL] %s:%d: expected %s == %s\n",                  \
                         __FILE__, __LINE__, #a, #b);                          \
        }                                                                      \
    } while (0)

using namespace jass;

// -----------------------------------------------------------------------------
// Geometry
// -----------------------------------------------------------------------------
void test_geometry() {
    JASS_CHECK_EQ(row_of(1),  0);
    JASS_CHECK_EQ(col_of(1),  1);
    JASS_CHECK_EQ(row_of(5),  0);
    JASS_CHECK_EQ(col_of(5),  9);
    JASS_CHECK_EQ(row_of(6),  1);
    JASS_CHECK_EQ(col_of(6),  0);
    JASS_CHECK_EQ(row_of(28), 5);
    JASS_CHECK_EQ(col_of(28), 4);
    JASS_CHECK_EQ(row_of(46), 9);
    JASS_CHECK_EQ(col_of(46), 0);
    JASS_CHECK_EQ(row_of(50), 9);
    JASS_CHECK_EQ(col_of(50), 8);

    // Promotion rows
    JASS_CHECK(is_promotion_square(3,  Color::White));   // top row
    JASS_CHECK(is_promotion_square(48, Color::Black));   // bottom row
    JASS_CHECK(!is_promotion_square(28, Color::White));
    JASS_CHECK(!is_promotion_square(28, Color::Black));
}

// -----------------------------------------------------------------------------
// Diagonal neighbour table
// -----------------------------------------------------------------------------
void test_neighbours() {
    // Top-left corner (square 1).
    JASS_CHECK_EQ(neighbour(1, Dir::UpLeft),    NO_SQUARE);
    JASS_CHECK_EQ(neighbour(1, Dir::UpRight),   NO_SQUARE);
    JASS_CHECK_EQ(neighbour(1, Dir::DownLeft),  static_cast<Square>(6));
    JASS_CHECK_EQ(neighbour(1, Dir::DownRight), static_cast<Square>(7));

    // Top-right corner (square 5).
    JASS_CHECK_EQ(neighbour(5, Dir::UpLeft),    NO_SQUARE);
    JASS_CHECK_EQ(neighbour(5, Dir::UpRight),   NO_SQUARE);
    JASS_CHECK_EQ(neighbour(5, Dir::DownLeft),  static_cast<Square>(10));
    JASS_CHECK_EQ(neighbour(5, Dir::DownRight), NO_SQUARE);

    // Bottom-left corner (square 46).
    JASS_CHECK_EQ(neighbour(46, Dir::UpLeft),    NO_SQUARE);
    JASS_CHECK_EQ(neighbour(46, Dir::UpRight),   static_cast<Square>(41));
    JASS_CHECK_EQ(neighbour(46, Dir::DownLeft),  NO_SQUARE);
    JASS_CHECK_EQ(neighbour(46, Dir::DownRight), NO_SQUARE);

    // Central square (28).
    JASS_CHECK_EQ(neighbour(28, Dir::UpLeft),    static_cast<Square>(22));
    JASS_CHECK_EQ(neighbour(28, Dir::UpRight),   static_cast<Square>(23));
    JASS_CHECK_EQ(neighbour(28, Dir::DownLeft),  static_cast<Square>(32));
    JASS_CHECK_EQ(neighbour(28, Dir::DownRight), static_cast<Square>(33));

    // Diagonal symmetry: if A is the UpLeft of B, then B is the DownRight
    // of A; same for the other diagonal.
    for (int s = 1; s <= NUM_SQUARES; ++s) {
        const Square sq = static_cast<Square>(s);
        for (Dir d : ALL_DIRS) {
            const Square n = neighbour(sq, d);
            if (n == NO_SQUARE) continue;
            // Reverse direction: invert both bits.
            const Dir rev = static_cast<Dir>(static_cast<std::uint8_t>(d) ^ 3);
            JASS_CHECK_EQ(neighbour(n, rev), sq);
        }
    }
}

// -----------------------------------------------------------------------------
// Bitboard helpers
// -----------------------------------------------------------------------------
void test_bitboards() {
    Bitboard b = 0;
    set(b, 1);
    set(b, 28);
    set(b, 50);
    JASS_CHECK_EQ(popcount(b), 3);
    JASS_CHECK(test(b, 1));
    JASS_CHECK(test(b, 28));
    JASS_CHECK(test(b, 50));
    JASS_CHECK(!test(b, 2));

    Bitboard tmp = b;
    JASS_CHECK_EQ(pop_lsb(tmp), static_cast<Square>(1));
    JASS_CHECK_EQ(pop_lsb(tmp), static_cast<Square>(28));
    JASS_CHECK_EQ(pop_lsb(tmp), static_cast<Square>(50));
    JASS_CHECK_EQ(tmp, 0ULL);

    JASS_CHECK_EQ(popcount(PLAYABLE_BB), NUM_SQUARES);
}

// -----------------------------------------------------------------------------
// Position
// -----------------------------------------------------------------------------
void test_start_position() {
    const Position p = Position::start_position();
    JASS_CHECK_EQ(popcount(p.white_men()),   20);
    JASS_CHECK_EQ(popcount(p.black_men()),   20);
    JASS_CHECK_EQ(popcount(p.white_kings()), 0);
    JASS_CHECK_EQ(popcount(p.black_kings()), 0);
    JASS_CHECK_EQ(popcount(p.empties()),     10);
    JASS_CHECK(p.side_to_move() == Color::White);

    JASS_CHECK(p.piece_at(1)  == Piece::BlackMan);
    JASS_CHECK(p.piece_at(20) == Piece::BlackMan);
    JASS_CHECK(p.piece_at(21) == Piece::None);
    JASS_CHECK(p.piece_at(30) == Piece::None);
    JASS_CHECK(p.piece_at(31) == Piece::WhiteMan);
    JASS_CHECK(p.piece_at(50) == Piece::WhiteMan);
}

void test_fen_round_trip_start() {
    const Position p = Position::start_position();
    const std::string fen = p.to_fen();
    const auto parsed = Position::from_fen(fen);
    JASS_CHECK(parsed.has_value());
    JASS_CHECK(*parsed == p);
}

void test_fen_with_ranges_and_kings() {
    // A black-to-move position with a couple of kings on each side.
    const auto p = Position::from_fen("B:W31-50,K28:B1-15,K20");
    JASS_CHECK(p.has_value());
    JASS_CHECK(p->side_to_move() == Color::Black);
    JASS_CHECK_EQ(popcount(p->white_men()),   20);
    JASS_CHECK_EQ(popcount(p->white_kings()), 1);
    JASS_CHECK_EQ(popcount(p->black_men()),   15);
    JASS_CHECK_EQ(popcount(p->black_kings()), 1);
    JASS_CHECK(p->piece_at(28) == Piece::WhiteKing);
    JASS_CHECK(p->piece_at(20) == Piece::BlackKing);

    // Round-trip: serialise then parse again, expect equal position.
    const auto reparsed = Position::from_fen(p->to_fen());
    JASS_CHECK(reparsed.has_value());
    JASS_CHECK(*reparsed == *p);
}

void test_fen_rejects_invalid() {
    JASS_CHECK(!Position::from_fen("").has_value());
    JASS_CHECK(!Position::from_fen("garbage").has_value());
    // Same colour twice.
    JASS_CHECK(!Position::from_fen("W:W31-35:W36-40").has_value());
    // Out-of-range square.
    JASS_CHECK(!Position::from_fen("W:W51:B1").has_value());
    // Reversed range.
    JASS_CHECK(!Position::from_fen("W:W31:B20-10").has_value());
    // Two pieces on the same square.
    JASS_CHECK(!Position::from_fen("W:W31,31:B1").has_value());
    // Bad side-to-move.
    JASS_CHECK(!Position::from_fen("X:W31:B1").has_value());
}

}  // namespace

int main() {
    test_geometry();
    test_neighbours();
    test_bitboards();
    test_start_position();
    test_fen_round_trip_start();
    test_fen_with_ranges_and_kings();
    test_fen_rejects_invalid();

    if (g_failures == 0) {
        std::printf("All %d assertions passed.\n", g_assertions);
        return 0;
    }
    std::fprintf(stderr, "%d / %d assertions FAILED.\n",
                 g_failures, g_assertions);
    return 1;
}
