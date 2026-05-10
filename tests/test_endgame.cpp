// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Tests for the endgame-knowledge probe and its integration into the
// search.

#include "test_framework.hpp"

#include "endgame.hpp"
#include "position.hpp"
#include "search.hpp"
#include "tt.hpp"

#include <string_view>

using namespace jass;

namespace {

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

// -----------------------------------------------------------------------------
// probe_endgame
// -----------------------------------------------------------------------------
void test_probe_kvk_draw_at_various_squares() {
    // A handful of placements; all must be drawn under FMJD.
    JASS_CHECK(probe_endgame(parse("W:WK1:BK50"))  == EndgameResult::Draw);
    JASS_CHECK(probe_endgame(parse("W:WK28:BK1"))  == EndgameResult::Draw);
    JASS_CHECK(probe_endgame(parse("B:WK28:BK33")) == EndgameResult::Draw);
}

void test_probe_unknown_when_men_present() {
    // Even one man on either side disqualifies the kings-only probe.
    JASS_CHECK(probe_endgame(parse("W:WK28:B1"))   == EndgameResult::Unknown);
    JASS_CHECK(probe_endgame(parse("W:W31:BK1"))   == EndgameResult::Unknown);
    JASS_CHECK(probe_endgame(Position::start_position()) == EndgameResult::Unknown);
}

void test_probe_unknown_when_more_than_one_king_each_side() {
    JASS_CHECK(probe_endgame(parse("W:WK28,K33:BK1"))   == EndgameResult::Unknown);
    JASS_CHECK(probe_endgame(parse("W:WK28:BK1,K6"))    == EndgameResult::Unknown);
}

// -----------------------------------------------------------------------------
// Search × endgame
// -----------------------------------------------------------------------------
void test_search_returns_draw_in_kvk() {
    const Position p = parse("W:WK28:BK1");
    SearchLimits lim;
    lim.max_depth = 5;
    TranspositionTable tt;
    tt.resize_mb(1);
    const SearchResult r = search(p, lim, tt, {});
    JASS_CHECK_EQ(r.score, 0);
}

}  // namespace

void run_endgame_tests() {
    test_probe_kvk_draw_at_various_squares();
    test_probe_unknown_when_men_present();
    test_probe_unknown_when_more_than_one_king_each_side();
    test_search_returns_draw_in_kvk();
}
