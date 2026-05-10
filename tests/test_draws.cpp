// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Tests for FMJD draw rules: the half-move clock and 25-move (50-ply)
// draw, and 2-fold repetition detection in the search.

#include "test_framework.hpp"

#include "engine.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"
#include "tt.hpp"
#include "types.hpp"
#include "zobrist.hpp"

#include <string_view>
#include <vector>

using namespace jass;

namespace {

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

// -----------------------------------------------------------------------------
// Half-move clock semantics on Position::after
// -----------------------------------------------------------------------------
void test_clock_resets_on_capture() {
    Position p = parse("W:W28:B22");
    p.set_halfmove_clock(40);

    MoveList ml;
    generate_legal_moves(p, ml);
    JASS_CHECK_EQ(ml.size(), static_cast<std::size_t>(1));
    JASS_CHECK(ml[0].is_capture());

    const Position next = p.after(ml[0]);
    JASS_CHECK_EQ(next.halfmove_clock(), 0);
}

void test_clock_resets_on_man_move() {
    Position p = Position::start_position();
    p.set_halfmove_clock(40);

    MoveList ml;
    generate_legal_moves(p, ml);
    // Pick a quiet man move (the start position has nine of them).
    const Move m = ml[0];
    JASS_CHECK(m.is_quiet());

    const Position next = p.after(m);
    JASS_CHECK_EQ(next.halfmove_clock(), 0);
}

void test_clock_increments_on_king_quiet_move() {
    Position p = parse("W:WK28:BK1");
    p.set_halfmove_clock(5);

    MoveList ml;
    generate_legal_moves(p, ml);
    const Move m = ml[0];
    JASS_CHECK(m.is_quiet());

    const Position next = p.after(m);
    JASS_CHECK_EQ(next.halfmove_clock(), 6);
}

// -----------------------------------------------------------------------------
// 25-move rule (50-ply) detected by the search
// -----------------------------------------------------------------------------
void test_search_returns_draw_when_clock_at_threshold() {
    // 2 kings + 1 man vs 1 king — material lead worth ≈ 500 cp via the
    // normal eval (we deliberately put a man on the board so the
    // position does not fall into the kings-only bitbase). With the
    // 25-move clock at the threshold the search must report a draw at
    // the root.
    Position p = parse("W:WK28,K33,41:BK1");
    p.set_halfmove_clock(FIFTY_MOVE_PLIES);

    SearchLimits lim;
    lim.max_depth = 3;
    TranspositionTable tt;
    tt.resize_mb(1);

    const SearchResult r = search(p, lim, tt, {});
    JASS_CHECK_EQ(r.score, 0);
}

void test_search_normal_when_clock_below_threshold() {
    Position p = parse("W:WK28,K33,41:BK1");
    p.set_halfmove_clock(10);

    SearchLimits lim;
    lim.max_depth = 3;
    TranspositionTable tt;
    tt.resize_mb(1);

    const SearchResult r = search(p, lim, tt, {});
    JASS_CHECK(r.score > 100);  // material lead must shine through
}

// -----------------------------------------------------------------------------
// Repetition detected by the search
// -----------------------------------------------------------------------------
void test_search_returns_draw_on_repetition_in_history() {
    const Position p = parse("W:WK28,K33,41:BK1");
    const ZobristHash h = zobrist_hash(p);

    SearchLimits lim;
    lim.max_depth = 3;
    TranspositionTable tt;
    tt.resize_mb(1);

    const std::vector<ZobristHash> with_repetition{h};
    const SearchResult with    = search(p, lim, tt, with_repetition);
    tt.clear();
    const SearchResult without = search(p, lim, tt, {});

    JASS_CHECK_EQ(with.score,   0);
    JASS_CHECK(without.score > 100);
}

// -----------------------------------------------------------------------------
// Engine flow: applying moves accumulates the hash history
// -----------------------------------------------------------------------------
void test_engine_apply_move_records_predecessor() {
    Engine e;
    JASS_CHECK(e.set_position_fen("W:WK28:BK1"));
    JASS_CHECK_EQ(e.hash_history().size(), static_cast<std::size_t>(0));

    MoveList ml;
    generate_legal_moves(e.position(), ml);
    JASS_CHECK(!ml.empty());

    const ZobristHash before = zobrist_hash(e.position());
    JASS_CHECK(e.apply_move(ml[0]));
    JASS_CHECK_EQ(e.hash_history().size(), static_cast<std::size_t>(1));
    JASS_CHECK_EQ(e.hash_history().front(), before);
}

void test_engine_new_game_clears_history() {
    Engine e;
    JASS_CHECK(e.set_position_fen("W:WK28:BK1"));
    MoveList ml;
    generate_legal_moves(e.position(), ml);
    JASS_CHECK(e.apply_move(ml[0]));
    JASS_CHECK(!e.hash_history().empty());

    e.new_game();
    JASS_CHECK(e.hash_history().empty());
    JASS_CHECK(e.position() == Position::start_position());
}

}  // namespace

void run_draw_tests() {
    test_clock_resets_on_capture();
    test_clock_resets_on_man_move();
    test_clock_increments_on_king_quiet_move();

    test_search_returns_draw_when_clock_at_threshold();
    test_search_normal_when_clock_below_threshold();

    test_search_returns_draw_on_repetition_in_history();

    test_engine_apply_move_records_predecessor();
    test_engine_new_game_clears_history();
}
