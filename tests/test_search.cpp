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
// The exact PSQT values are implementation details, so the tests below check
// invariants (sign, ordering, dominance of material over positional terms)
// instead of pinning specific numbers.
void test_eval_start_is_near_zero() {
    const Position p = Position::start_position();
    // Material is identical and the PSQT is mirrored between the colours,
    // so the start-position eval is dominated by the small tempo bonus.
    const int e = evaluate(p);
    JASS_CHECK(e > -2 * MAN_VALUE / 5);  // |e| < 40
    JASS_CHECK(e <  2 * MAN_VALUE / 5);
}

void test_eval_material_dominates_positional() {
    // Removing one black man from the start position must improve white's
    // eval by clearly more than any positional swing in the PSQT.
    const Position p_full   = Position::start_position();
    const Position p_minus  = parse("W:W31-50:B1-19");  // black is missing 20

    const int e_full  = evaluate(p_full);
    const int e_minus = evaluate(p_minus);
    JASS_CHECK(e_minus - e_full > MAN_VALUE / 2);
    // And the magnitude shouldn't blow up to a king's value either.
    JASS_CHECK(e_minus - e_full < KING_VALUE);
}

void test_eval_stm_flips_sign() {
    // Identical board, only side-to-move differs: signs flip.
    const Position w = parse("W:W31-50:B1-15");
    const Position b = parse("B:W31-50:B1-15");
    JASS_CHECK(evaluate(w) > MAN_VALUE);
    JASS_CHECK(evaluate(b) < -MAN_VALUE);
}

void test_eval_king_more_valuable_than_man() {
    const Position pm = parse("W:W31:B1");
    const Position pk = parse("W:WK31:B1");
    // Replacing white's man with a king strictly improves white's eval by
    // at least KING_VALUE - MAN_VALUE minus a small PSQT slack.
    JASS_CHECK(evaluate(pk) - evaluate(pm) >= KING_VALUE - MAN_VALUE - 50);
}

void test_eval_advancement_bonus() {
    // Pushing a single white man one rank toward promotion should never
    // decrease its eval (in an otherwise identical context).
    const Position back = parse("W:W31:B1");   // row 6
    const Position fwd  = parse("W:W26:B1");   // row 5 — closer to promotion
    JASS_CHECK(evaluate(fwd) > evaluate(back));
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

void test_qsearch_avoids_horizon_effect() {
    // White man at 33 vs black man at 22. White's two quiet moves are
    //   - 33-28 (NW): leaves white *en prise* — black 22 must capture 28
    //                 (mandatory) and lands at 33, leaving white with no
    //                 pieces and therefore mated.
    //   - 33-29 (NE): perfectly safe, no capture available for black.
    // Without quiescence the depth-1 leaf eval scores both moves equally
    // and the engine picks 33-28 because of move-ordering. Quiescence
    // plays the forced black capture out at the horizon and exposes the
    // true value of 33-28, so the engine must pick 33-29.
    const Position p = parse("W:W33:B22");
    SearchLimits lim;
    lim.max_depth = 1;
    const SearchResult r = search(p, lim);
    JASS_CHECK_EQ(r.best_move.from, static_cast<Square>(33));
    JASS_CHECK_EQ(r.best_move.to,   static_cast<Square>(29));
}

void test_search_score_reflects_material_lead() {
    // White has a king + a man, black has only a king: white is ahead by
    // roughly one man. The score from white's POV must be clearly positive
    // and not absurdly larger than a man's value at this depth.
    const Position p = parse("W:WK28,31:BK1");

    SearchLimits lim;
    lim.max_depth = 3;
    const SearchResult r = search(p, lim);

    MoveList legal;
    generate_legal_moves(p, legal);
    JASS_CHECK(list_contains(legal, r.best_move));
    JASS_CHECK(r.score > MAN_VALUE / 2);
    JASS_CHECK(r.score < KING_VALUE);
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
    test_eval_start_is_near_zero();
    test_eval_material_dominates_positional();
    test_eval_stm_flips_sign();
    test_eval_king_more_valuable_than_man();
    test_eval_advancement_bonus();
    test_search_returns_legal_move_from_start();
    test_search_no_legal_moves_returns_mate();
    test_search_finds_forced_capture();
    test_qsearch_avoids_horizon_effect();
    test_search_score_reflects_material_lead();
    test_search_depth_increases();
}
