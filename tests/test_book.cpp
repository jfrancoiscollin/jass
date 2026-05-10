// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Tests for the opening book and its Engine integration.

#include "test_framework.hpp"

#include "book.hpp"
#include "engine.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"

using namespace jass;

namespace {

bool legal_move(const Position& pos, const Move& m) {
    MoveList ml;
    generate_legal_moves(pos, ml);
    for (const auto& lm : ml) if (lm == m) return true;
    return false;
}

// -----------------------------------------------------------------------------
// Book itself
// -----------------------------------------------------------------------------
void test_book_has_entries() {
    Book b;
    JASS_CHECK(b.size() > 0);
}

void test_book_probes_start_position() {
    Book b;
    const auto m = b.probe(Position::start_position());
    JASS_CHECK(m.has_value());
    if (m) JASS_CHECK(legal_move(Position::start_position(), *m));
}

void test_book_misses_after_off_book_move() {
    Book b;
    Position p = Position::start_position();

    // Play an arbitrary off-book move (the book lines all start with
    // 31-26 / 32-28 / 33-28 / 33-29 / 34-30 / 35-30; pick something
    // else: 35-30 IS in the book, but 34-29 is not).
    MoveList ml;
    generate_legal_moves(p, ml);
    for (const auto& m : ml) {
        if (m.from == 34 && m.to == 29) { p = p.after(m); break; }
    }
    JASS_CHECK(p.side_to_move() == Color::Black);

    JASS_CHECK(!b.probe(p).has_value());
}

// -----------------------------------------------------------------------------
// Engine integration
// -----------------------------------------------------------------------------
void test_engine_search_uses_book_in_opening() {
    Engine e;
    const SearchResult r = e.search(/*max_depth=*/1);
    JASS_CHECK(r.from_book);
    JASS_CHECK_EQ(r.depth, 0);
    JASS_CHECK_EQ(r.nodes, static_cast<std::uint64_t>(0));
    JASS_CHECK(legal_move(e.position(), r.best_move));
}

void test_engine_disabled_book_falls_back_to_search() {
    Engine e;
    e.use_book(false);
    const SearchResult r = e.search(/*max_depth=*/2);
    JASS_CHECK(!r.from_book);
    JASS_CHECK_EQ(r.depth, 2);
    JASS_CHECK(r.nodes > 0);
}

}  // namespace

void run_book_tests() {
    test_book_has_entries();
    test_book_probes_start_position();
    test_book_misses_after_off_book_move();
    test_engine_search_uses_book_in_opening();
    test_engine_disabled_book_falls_back_to_search();
}
