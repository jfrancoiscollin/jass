// SPDX-License-Identifier: AGPL-3.0-or-later
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

void test_probe_unknown_when_outside_tablebase() {
    // 4 kings vs 1 king is not in the bitbase (yet).
    JASS_CHECK(probe_endgame(parse("W:WK28,K33,K38,K42:BK1"))
               == EndgameResult::Unknown);
    // 2 kings vs 2 kings is not in the bitbase either.
    JASS_CHECK(probe_endgame(parse("W:WK28,K33:BK1,K6"))
               == EndgameResult::Unknown);
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

// -----------------------------------------------------------------------------
// 2-vs-1 bitbase
// -----------------------------------------------------------------------------
// Most KKvK positions in international draughts are actually drawn under
// pure FMJD rules (forced-capture defence by the lone king); the bitbase
// only marks WIN when the strong side has a concrete tactical sequence.
// Here we use a position where white can immediately capture: white king
// at 12 attacks black at 7 with empty landing at 1.
void test_probe_kkvk_immediate_capture_is_white_win() {
    const Position p = parse("W:WK12,K28:BK7");
    JASS_CHECK(probe_endgame(p) == EndgameResult::WhiteWin);
}

void test_probe_kvkk_immediate_capture_is_black_win() {
    // Mirror of the above: 2 black kings vs 1 white king with a one-move
    // capture for the black side.
    const Position p = parse("B:WK7:BK12,K28");
    JASS_CHECK(probe_endgame(p) == EndgameResult::BlackWin);
}

void test_search_kkvk_returns_winning_score() {
    const Position p = parse("W:WK12,K28:BK7");
    SearchLimits lim;
    lim.max_depth = 2;
    TranspositionTable tt;
    tt.resize_mb(1);
    const SearchResult r = search(p, lim, tt, {});
    // White's POV: positive, well above ordinary positional scores.
    JASS_CHECK(r.score >= MATE_SCORE - MAX_PLY - 5);
}

// -----------------------------------------------------------------------------
// 3-vs-1 bitbase
// -----------------------------------------------------------------------------
// Like KKvK, most KKKvK positions are technical draws under pure FMJD
// rules; we test on a position that is a forced WhiteWin (white's king
// at 12 captures black's king at 7 in one move, landing at 1 — black
// has no pieces left).
void test_probe_kkkvk_immediate_capture_is_white_win() {
    const Position p = parse("W:WK12,K28,K33:BK7");
    JASS_CHECK(probe_endgame(p) == EndgameResult::WhiteWin);
}

void test_probe_kvkkk_immediate_capture_is_black_win() {
    const Position p = parse("B:WK7:BK12,K28,K33");
    JASS_CHECK(probe_endgame(p) == EndgameResult::BlackWin);
}

void test_probe_3v1_unknown_when_men_present() {
    // A man on the board takes the position out of the kings-only tables.
    const Position p = parse("W:W31,K28,K33,K38:BK1");
    JASS_CHECK(probe_endgame(p) == EndgameResult::Unknown);
}

}  // namespace

void run_endgame_tests() {
    test_probe_kvk_draw_at_various_squares();
    test_probe_unknown_when_men_present();
    test_probe_unknown_when_outside_tablebase();
    test_search_returns_draw_in_kvk();
    test_probe_kkvk_immediate_capture_is_white_win();
    test_probe_kvkk_immediate_capture_is_black_win();
    test_search_kkvk_returns_winning_score();
    test_probe_kkkvk_immediate_capture_is_white_win();
    test_probe_kvkkk_immediate_capture_is_black_win();
    test_probe_3v1_unknown_when_men_present();
}
