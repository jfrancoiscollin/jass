// SPDX-License-Identifier: MIT
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
    // Must be one of the three possible outcomes.
    JASS_CHECK(g.outcome == GameOutcome::WhiteWin
            || g.outcome == GameOutcome::BlackWin
            || g.outcome == GameOutcome::Draw);
}

void test_run_tournament_counts_add_up() {
    EngineConfig a, b;
    a.max_depth = 2;
    b.max_depth = 2;
    const int pairs = 1;  // 2 games total
    const TournamentResult r = run_tournament(a, b, pairs, /*max_plies=*/80);
    JASS_CHECK_EQ(r.a_wins + r.b_wins + r.draws, pairs * 2);
}

}  // namespace

void run_tournament_tests() {
    test_play_game_terminates_with_known_outcome();
    test_run_tournament_counts_add_up();
}
