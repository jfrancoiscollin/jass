// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "test_framework.hpp"

#include "bitboard.hpp"
#include "board.hpp"
#include "position.hpp"
#include "types.hpp"

#include <string>

using namespace jass;

namespace {

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

    JASS_CHECK(is_promotion_square(3,  Color::White));
    JASS_CHECK(is_promotion_square(48, Color::Black));
    JASS_CHECK(!is_promotion_square(28, Color::White));
    JASS_CHECK(!is_promotion_square(28, Color::Black));
}

// -----------------------------------------------------------------------------
// Diagonal neighbour table
// -----------------------------------------------------------------------------
void test_neighbours() {
    JASS_CHECK_EQ(neighbour(1, Dir::UpLeft),    NO_SQUARE);
    JASS_CHECK_EQ(neighbour(1, Dir::UpRight),   NO_SQUARE);
    JASS_CHECK_EQ(neighbour(1, Dir::DownLeft),  static_cast<Square>(6));
    JASS_CHECK_EQ(neighbour(1, Dir::DownRight), static_cast<Square>(7));

    JASS_CHECK_EQ(neighbour(5, Dir::UpLeft),    NO_SQUARE);
    JASS_CHECK_EQ(neighbour(5, Dir::UpRight),   NO_SQUARE);
    JASS_CHECK_EQ(neighbour(5, Dir::DownLeft),  static_cast<Square>(10));
    JASS_CHECK_EQ(neighbour(5, Dir::DownRight), NO_SQUARE);

    JASS_CHECK_EQ(neighbour(46, Dir::UpLeft),    NO_SQUARE);
    JASS_CHECK_EQ(neighbour(46, Dir::UpRight),   static_cast<Square>(41));
    JASS_CHECK_EQ(neighbour(46, Dir::DownLeft),  NO_SQUARE);
    JASS_CHECK_EQ(neighbour(46, Dir::DownRight), NO_SQUARE);

    JASS_CHECK_EQ(neighbour(28, Dir::UpLeft),    static_cast<Square>(22));
    JASS_CHECK_EQ(neighbour(28, Dir::UpRight),   static_cast<Square>(23));
    JASS_CHECK_EQ(neighbour(28, Dir::DownLeft),  static_cast<Square>(32));
    JASS_CHECK_EQ(neighbour(28, Dir::DownRight), static_cast<Square>(33));

    for (int s = 1; s <= NUM_SQUARES; ++s) {
        const Square sq = static_cast<Square>(s);
        for (Dir d : ALL_DIRS) {
            const Square n = neighbour(sq, d);
            if (n == NO_SQUARE) continue;
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
    const auto p = Position::from_fen("B:W31-50,K28:B1-15,K20");
    JASS_CHECK(p.has_value());
    JASS_CHECK(p->side_to_move() == Color::Black);
    JASS_CHECK_EQ(popcount(p->white_men()),   20);
    JASS_CHECK_EQ(popcount(p->white_kings()), 1);
    JASS_CHECK_EQ(popcount(p->black_men()),   15);
    JASS_CHECK_EQ(popcount(p->black_kings()), 1);
    JASS_CHECK(p->piece_at(28) == Piece::WhiteKing);
    JASS_CHECK(p->piece_at(20) == Piece::BlackKing);

    const auto reparsed = Position::from_fen(p->to_fen());
    JASS_CHECK(reparsed.has_value());
    JASS_CHECK(*reparsed == *p);
}

void test_fen_rejects_invalid() {
    JASS_CHECK(!Position::from_fen("").has_value());
    JASS_CHECK(!Position::from_fen("garbage").has_value());
    JASS_CHECK(!Position::from_fen("W:W31-35:W36-40").has_value());
    JASS_CHECK(!Position::from_fen("W:W51:B1").has_value());
    JASS_CHECK(!Position::from_fen("W:W31:B20-10").has_value());
    JASS_CHECK(!Position::from_fen("W:W31,31:B1").has_value());
    JASS_CHECK(!Position::from_fen("X:W31:B1").has_value());
}

}  // namespace

void run_position_tests() {
    test_geometry();
    test_neighbours();
    test_bitboards();
    test_start_position();
    test_fen_round_trip_start();
    test_fen_with_ranges_and_kings();
    test_fen_rejects_invalid();
}
