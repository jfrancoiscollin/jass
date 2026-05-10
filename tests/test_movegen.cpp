// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Functional tests for `generate_legal_moves` and a perft validator. The
// hand-crafted scenarios cover the trickiest FMJD rules:
//   - mandatory capture
//   - majority-capture rule (longest chain wins)
//   - men capturing in all four directions (including backwards)
//   - kings landing on any empty square past the captured piece
//   - promotion only when the final landing square is on the promotion row
//   - a man passing through the promotion row mid-chain stays a man

#include "test_framework.hpp"

#include "bitboard.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "types.hpp"

#include <algorithm>
#include <cstdint>
#include <string_view>

using namespace jass;

namespace {

// Convenience: parse a FEN that we know is valid in our hand-crafted tests.
Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

bool contains_capture(const MoveList& ml, Square from, Square to,
                      std::initializer_list<Square> caps) {
    for (const auto& m : ml) {
        if (m.from != from || m.to != to) continue;
        if (m.num_captures != caps.size()) continue;
        bool ok = true;
        std::size_t i = 0;
        for (Square c : caps) {
            if (m.captures[i++] != c) { ok = false; break; }
        }
        if (ok) return true;
    }
    return false;
}

// -----------------------------------------------------------------------------
// Quiet generation
// -----------------------------------------------------------------------------
void test_quiet_start_position() {
    const Position p = Position::start_position();
    MoveList ml;
    generate_legal_moves(p, ml);
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(9));
    for (const auto& m : ml) {
        JASS_CHECK(m.is_quiet());
        JASS_CHECK(!m.promotes);
    }
}

void test_quiet_king_slide() {
    // White king alone in the centre; a lonely black king far away keeps the
    // FEN shape valid and avoids any capture interaction.
    const Position p = parse("W:WK28:BK1");
    MoveList ml;
    generate_legal_moves(p, ml);
    // Diagonals from 28: 4 (NW) + 5 (NE) + 4 (SW) + 4 (SE) = 17.
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(17));
    for (const auto& m : ml) {
        JASS_CHECK(m.is_quiet());
        JASS_CHECK_EQ(m.from, static_cast<Square>(28));
    }
}

// -----------------------------------------------------------------------------
// Captures — men
// -----------------------------------------------------------------------------
void test_man_captures_forward() {
    const Position p = parse("W:W28:B22");
    MoveList ml;
    generate_legal_moves(p, ml);
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(1));
    JASS_CHECK(contains_capture(ml, 28, 17, {22}));
    JASS_CHECK(!ml[0].promotes);
}

void test_man_captures_backward() {
    // White man at 22 has only quiet moves forward (NW/NE) but a black man on
    // 28 sits on its SE diagonal — so a *backward* capture is mandatory.
    const Position p = parse("W:W22:B28");
    MoveList ml;
    generate_legal_moves(p, ml);
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(1));
    JASS_CHECK(contains_capture(ml, 22, 33, {28}));
}

void test_majority_capture_rule() {
    // From 28, white can either:
    //   - capture 22 only (lands at 17, no continuation), 1 capture
    //   - capture 23 then 14 (lands at 10),               2 captures
    // Only the 2-capture chain is legal under FMJD rules.
    const Position p = parse("W:W28:B22,23,14");
    MoveList ml;
    generate_legal_moves(p, ml);
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(1));
    JASS_CHECK(contains_capture(ml, 28, 10, {23, 14}));
}

void test_man_through_promotion_no_promote() {
    // 11 captures 7 → lands at 2 (row 0, the promotion row), then captures 8
    // → lands at 13 (row 2). Final square is *not* the promotion row, so the
    // man does NOT promote, despite touching row 0 mid-chain.
    const Position p = parse("W:W11:B7,8");
    MoveList ml;
    generate_legal_moves(p, ml);
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(1));
    JASS_CHECK(contains_capture(ml, 11, 13, {7, 8}));
    JASS_CHECK(!ml[0].promotes);

    const Position next = p.after(ml[0]);
    JASS_CHECK(next.piece_at(13) == Piece::WhiteMan);
    JASS_CHECK(next.piece_at(7)  == Piece::None);
    JASS_CHECK(next.piece_at(8)  == Piece::None);
    JASS_CHECK(next.side_to_move() == Color::Black);
}

void test_man_promotes_at_end_of_capture() {
    // 11 captures 7 → lands at 2 (row 0). Chain ends there → man promotes.
    const Position p = parse("W:W11:B7");
    MoveList ml;
    generate_legal_moves(p, ml);
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(1));
    JASS_CHECK(contains_capture(ml, 11, 2, {7}));
    JASS_CHECK(ml[0].promotes);

    const Position next = p.after(ml[0]);
    JASS_CHECK(next.piece_at(2) == Piece::WhiteKing);
    JASS_CHECK(next.piece_at(7) == Piece::None);
}

// -----------------------------------------------------------------------------
// Captures — kings
// -----------------------------------------------------------------------------
void test_king_capture_multiple_landings() {
    // White king at 33, black man at 28 on the NW diagonal. The king may
    // land on any empty square strictly past the captured piece — i.e. one
    // of {22, 17, 11, 6} — which yields four distinct legal moves of length
    // one capture each.
    const Position p = parse("W:WK33:B28");
    MoveList ml;
    generate_legal_moves(p, ml);
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(4));

    int found = 0;
    for (Square land : {Square{22}, Square{17}, Square{11}, Square{6}}) {
        for (const auto& m : ml) {
            if (m.from == 33 && m.to == land &&
                m.num_captures == 1 && m.captures[0] == 28) {
                ++found;
            }
        }
    }
    JASS_CHECK_EQ(found, 4);
}

// -----------------------------------------------------------------------------
// Position::after — sanity checks against captures
// -----------------------------------------------------------------------------
void test_after_clears_captures_and_flips_stm() {
    const Position p = parse("W:W28:B22,23,14");
    MoveList ml;
    generate_legal_moves(p, ml);
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(1));

    const Position q = p.after(ml[0]);
    JASS_CHECK(q.piece_at(28) == Piece::None);
    JASS_CHECK(q.piece_at(23) == Piece::None);
    JASS_CHECK(q.piece_at(14) == Piece::None);
    JASS_CHECK(q.piece_at(22) == Piece::BlackMan);  // not part of the chain
    JASS_CHECK(q.piece_at(10) == Piece::WhiteMan);
    JASS_CHECK(q.side_to_move() == Color::Black);
}

// -----------------------------------------------------------------------------
// Perft
// -----------------------------------------------------------------------------
std::uint64_t perft(const Position& pos, int depth) {
    if (depth == 0) return 1;
    MoveList ml;
    generate_legal_moves(pos, ml);
    if (depth == 1) return ml.size();
    std::uint64_t total = 0;
    for (const auto& m : ml) {
        total += perft(pos.after(m), depth - 1);
    }
    return total;
}

void test_perft_start() {
    const Position p = Position::start_position();
    // FMJD international draughts perft from the standard initial position.
    // The depths 1..5 values are well-known and stable.
    JASS_CHECK_EQ(perft(p, 1), static_cast<std::uint64_t>(9));
    JASS_CHECK_EQ(perft(p, 2), static_cast<std::uint64_t>(81));
    JASS_CHECK_EQ(perft(p, 3), static_cast<std::uint64_t>(658));
    JASS_CHECK_EQ(perft(p, 4), static_cast<std::uint64_t>(4265));
    JASS_CHECK_EQ(perft(p, 5), static_cast<std::uint64_t>(27117));
}

}  // namespace

void run_movegen_tests() {
    test_quiet_start_position();
    test_quiet_king_slide();
    test_man_captures_forward();
    test_man_captures_backward();
    test_majority_capture_rule();
    test_man_through_promotion_no_promote();
    test_man_promotes_at_end_of_capture();
    test_king_capture_multiple_landings();
    test_after_clears_captures_and_flips_stm();
    test_perft_start();
}
