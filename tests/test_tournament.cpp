// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Tests for the self-play tournament harness. We deliberately use very
// small depths so the tests stay fast.

#include "test_framework.hpp"

#include "tournament.hpp"

using namespace jass;

namespace {

void test_play_game_terminates_with_known_outcome() {
    EngineConfig a, b;
    a.max_depth = 2;
    b.max_depth = 2;
    const GameRecord g = play_game(a, b, /*max_plies=*/100);
    JASS_CHECK(g.plies > 0);
    JASS_CHECK(g.reason != nullptr);
    JASS_CHECK(g.outcome == GameOutcome::WhiteWin
            || g.outcome == GameOutcome::BlackWin
            || g.outcome == GameOutcome::Draw);
}

void test_default_opening_pool_has_nine_openings() {
    const auto pool = default_opening_pool();
    JASS_CHECK_EQ(pool.size(), static_cast<std::size_t>(9));
    // Each opening must be a black-to-move position (white played one ply).
    for (const auto& p : pool) {
        JASS_CHECK(p.side_to_move() == Color::Black);
    }
}

void test_run_tournament_counts_add_up() {
    EngineConfig a, b;
    a.max_depth = 2;
    b.max_depth = 2;
    // 1 pair × 9 openings × 2 colours = 18 games.
    const int pairs = 1;
    const TournamentResult r = run_tournament(a, b, pairs, /*max_plies=*/60);
    JASS_CHECK_EQ(r.games, 9 * 2 * pairs);
    JASS_CHECK_EQ(r.a_wins + r.b_wins + r.draws, r.games);
}

void test_run_tournament_with_explicit_pool() {
    EngineConfig a, b;
    a.max_depth = 2;
    b.max_depth = 2;
    // Use just two custom openings so the test stays fast.
    auto pool = default_opening_pool();
    pool.resize(2);
    const TournamentResult r = run_tournament(a, b, /*pairs=*/1,
                                              /*max_plies=*/60, &pool);
    JASS_CHECK_EQ(r.games, 4);  // 2 openings × 2 colours
    JASS_CHECK_EQ(r.a_wins + r.b_wins + r.draws, r.games);
}

}  // namespace

void run_tournament_tests() {
    test_play_game_terminates_with_known_outcome();
    test_default_opening_pool_has_nine_openings();
    test_run_tournament_counts_add_up();
    test_run_tournament_with_explicit_pool();
}
