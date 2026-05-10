// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Unit tests for the high-level `Engine` facade. The contract under test:
//   - new_game() resets to the standard initial position
//   - apply_move accepts only legal moves and updates the held position
//   - search() returns a legal move and a sensible depth
//   - the persistent transposition table actually accelerates a repeated
//     search of the same position (fewer nodes on the second call)

#include "test_framework.hpp"

#include "engine.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"
#include "types.hpp"

using namespace jass;

namespace {

void test_engine_starts_at_initial_position() {
    Engine e;
    JASS_CHECK(e.position() == Position::start_position());
}

void test_engine_new_game_resets_position() {
    Engine e;
    JASS_CHECK(e.set_position_fen("B:W31-50:B1-20"));
    JASS_CHECK(e.position().side_to_move() == Color::Black);
    e.new_game();
    JASS_CHECK(e.position() == Position::start_position());
}

void test_engine_apply_legal_move() {
    Engine e;
    MoveList ml;
    generate_legal_moves(e.position(), ml);
    JASS_CHECK(!ml.empty());
    const Move first = ml[0];
    JASS_CHECK(e.apply_move(first));
    JASS_CHECK(e.position().side_to_move() == Color::Black);
}

void test_engine_apply_illegal_move() {
    Engine e;
    Move bogus;
    bogus.from = 1;
    bogus.to   = 2;  // 2 is not a legal destination from 1 in the start
    JASS_CHECK(!e.apply_move(bogus));
    JASS_CHECK(e.position() == Position::start_position());
}

void test_engine_search_returns_legal_move() {
    Engine e;
    e.use_book(false);  // exercise the search itself, not the book lookup
    const SearchResult r = e.search(/*max_depth=*/4);
    JASS_CHECK_EQ(r.depth, 4);
    MoveList ml;
    generate_legal_moves(e.position(), ml);
    bool found = false;
    for (const auto& m : ml) if (m == r.best_move) { found = true; break; }
    JASS_CHECK(found);
}

void test_engine_tt_persistence_speeds_up_repeated_search() {
    Engine e;
    e.use_book(false);
    e.resize_tt_mb(4);

    const SearchResult first  = e.search(5);
    const SearchResult second = e.search(5);

    // The first search filled the TT; the second one re-explores the same
    // tree and must visit strictly fewer nodes.
    JASS_CHECK_EQ(first.depth, 5);
    JASS_CHECK_EQ(second.depth, 5);
    JASS_CHECK(second.nodes <  first.nodes);
    JASS_CHECK(second.nodes <= first.nodes / 2);
}

void test_engine_clear_tt_undoes_warm_up() {
    Engine e;
    e.use_book(false);
    e.resize_tt_mb(4);

    const SearchResult warm = e.search(4);
    e.clear_tt();
    const SearchResult cold = e.search(4);

    JASS_CHECK(cold.nodes > warm.nodes / 2);  // back to roughly the cold cost
}

}  // namespace

void run_engine_tests() {
    test_engine_starts_at_initial_position();
    test_engine_new_game_resets_position();
    test_engine_apply_legal_move();
    test_engine_apply_illegal_move();
    test_engine_search_returns_legal_move();
    test_engine_tt_persistence_speeds_up_repeated_search();
    test_engine_clear_tt_undoes_warm_up();
}
