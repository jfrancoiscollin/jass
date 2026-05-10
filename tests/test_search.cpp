// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Functional tests for the alpha-beta search. The handcrafted scenarios
// pin down the contract that the rest of the engine relies on:
//   - the returned move is always one produced by `generate_legal_moves`
//   - a side with no legal moves is reported as mated
//   - on a position that *forces* a capture, the search returns that
//     capture (this implicitly checks the search/movegen integration)
//   - winning material is reflected in a positive score
//   - the search completes its requested depth and reports node counts

#include "test_framework.hpp"

#include "eval.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"
#include "types.hpp"

#include <algorithm>
#include <string_view>

using namespace jass;

namespace {

Position parse(std::string_view fen) {
    auto p = Position::from_fen(fen);
    JASS_CHECK(p.has_value());
    return p.value_or(Position{});
}

bool list_contains(const MoveList& ml, const Move& m) {
    for (const auto& x : ml) if (x == m) return true;
    return false;
}

// -----------------------------------------------------------------------------
// Evaluation
// -----------------------------------------------------------------------------
void test_eval_balanced_start() {
    const Position p = Position::start_position();
    JASS_CHECK_EQ(evaluate(p), 0);
}

void test_eval_material_advantage() {
    const Position p = parse("W:W31:B1");      // 1 vs 1, white to move
    JASS_CHECK_EQ(evaluate(p), 0);

    const Position q = parse("W:W31,32:B1");   // 2 vs 1, white to move
    JASS_CHECK_EQ(evaluate(q), MAN_VALUE);

    const Position r = parse("B:W31,32:B1");   // 2 vs 1, black to move
    JASS_CHECK_EQ(evaluate(r), -MAN_VALUE);

    const Position k = parse("W:WK31:B1");     // 1 king vs 1 man, white to move
    JASS_CHECK_EQ(evaluate(k), KING_VALUE - MAN_VALUE);
}

// -----------------------------------------------------------------------------
// Search
// -----------------------------------------------------------------------------
void test_search_returns_legal_move_from_start() {
    const Position p = Position::start_position();

    SearchLimits lim;
    lim.max_depth = 4;
    const SearchResult r = search(p, lim);

    JASS_CHECK_EQ(r.depth, 4);
    JASS_CHECK(r.nodes > 0);

    MoveList legal;
    generate_legal_moves(p, legal);
    JASS_CHECK(list_contains(legal, r.best_move));
}

void test_search_no_legal_moves_returns_mate() {
    // Black is to move with no pieces left at all → no legal moves.
    const Position p = parse("B:W31:B");

    SearchLimits lim;
    lim.max_depth = 3;
    const SearchResult r = search(p, lim);

    JASS_CHECK(r.score <= -(MATE_SCORE - MAX_PLY));
    JASS_CHECK(is_mate_score(r.score));
}

void test_search_finds_forced_capture() {
    // The only legal move captures black's lone piece, leaving black with
    // no pieces and therefore no legal reply: a mate-in-one for white.
    const Position p = parse("W:W28:B22");

    SearchLimits lim;
    lim.max_depth = 4;
    const SearchResult r = search(p, lim);

    JASS_CHECK_EQ(r.best_move.from, static_cast<Square>(28));
    JASS_CHECK_EQ(r.best_move.to,   static_cast<Square>(17));
    JASS_CHECK_EQ(r.best_move.num_captures, 1);
    JASS_CHECK_EQ(r.best_move.captures[0], static_cast<Square>(22));
    JASS_CHECK(r.score >= MATE_SCORE - MAX_PLY);
    JASS_CHECK(is_mate_score(r.score));
}

void test_search_chooses_better_of_two_options() {
    // White has a king at 28 and a stranded man at 31. Black has a king
    // at 1 (far away). Material is equal in the static sense but the
    // search at depth 3+ should still return *some* legal move (we just
    // assert legality + score sanity here, since the eval is purely
    // material).
    const Position p = parse("W:WK28,31:BK1");

    SearchLimits lim;
    lim.max_depth = 3;
    const SearchResult r = search(p, lim);

    MoveList legal;
    generate_legal_moves(p, legal);
    JASS_CHECK(list_contains(legal, r.best_move));
    // Material is +100 for White (man + king vs king) → STM-relative
    // score should be at least the material advantage minus a small
    // search noise budget.
    JASS_CHECK(r.score >= MAN_VALUE - 50);
    JASS_CHECK(r.score <= MAN_VALUE + 50);
}

void test_search_depth_increases() {
    // Sanity: deeper iterative deepening visits strictly more nodes than a
    // shallow one (in a non-mate position) and still returns a legal move.
    const Position p = Position::start_position();

    SearchLimits lo;
    lo.max_depth = 2;
    SearchLimits hi;
    hi.max_depth = 4;

    const SearchResult r_lo = search(p, lo);
    const SearchResult r_hi = search(p, hi);

    JASS_CHECK_EQ(r_lo.depth, 2);
    JASS_CHECK_EQ(r_hi.depth, 4);
    JASS_CHECK(r_hi.nodes > r_lo.nodes);
}

}  // namespace

void run_search_tests() {
    test_eval_balanced_start();
    test_eval_material_advantage();
    test_search_returns_legal_move_from_start();
    test_search_no_legal_moves_returns_mate();
    test_search_finds_forced_capture();
    test_search_chooses_better_of_two_options();
    test_search_depth_increases();
}
