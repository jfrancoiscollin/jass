// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Bench : N games of (eval_basic + alpha-beta) vs random player.
// Gate 1 of the Phase Pattern-1 POC : eval should win ≥95%.
//
// CLI :
//   othello_bench_random [games=100] [depth=4] [seed=42]
//
// Output : "engine=W wins  L losses  D draws   rate=X.XXX"

#include "board.hpp"
#include "eval.hpp"
#include "movegen.hpp"
#include "search.hpp"

#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <random>
#include <string>

namespace {

using namespace othello;

Square random_move(const Board& b, std::mt19937& rng) {
    MoveList ml;
    generate_legal_moves(b, ml);
    if (ml.empty()) return NO_SQUARE;
    std::uniform_int_distribution<std::size_t> dist(0, ml.size() - 1);
    return ml[dist(rng)];
}

// Play one game. engine_is_black = true → engine plays Black, else White.
// Returns +1 if engine wins, -1 if loses, 0 if draw.
int play_one(bool engine_is_black, int depth, std::mt19937& rng) {
    Board b = Board::start_position();
    SearchConfig cfg;
    cfg.max_depth = depth;

    while (!b.is_game_over()) {
        const bool engine_turn = (b.stm == Color::Black) == engine_is_black;
        Square mv = NO_SQUARE;
        if (engine_turn) {
            mv = search(b, cfg).best_move;
            // search() returns NO_SQUARE on a pass, but if there are
            // legal moves the result is always one of them.
        } else {
            mv = random_move(b, rng);
        }
        apply_move(b, mv);
    }
    const int blk = b.black_count();
    const int wht = b.white_count();
    int engine_pc = engine_is_black ? blk : wht;
    int opp_pc    = engine_is_black ? wht : blk;
    if (engine_pc > opp_pc) return +1;
    if (engine_pc < opp_pc) return -1;
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    int games = (argc > 1) ? std::atoi(argv[1]) : 100;
    int depth = (argc > 2) ? std::atoi(argv[2]) : 4;
    std::uint32_t seed = (argc > 3) ? static_cast<std::uint32_t>(std::atoi(argv[3])) : 42;

    std::mt19937 rng(seed);

    int wins = 0, losses = 0, draws = 0;
    // Alternate colours so the engine plays an equal number of Black
    // and White games — Othello has a small first-move advantage.
    for (int i = 0; i < games; ++i) {
        const bool engine_is_black = (i % 2 == 0);
        const int r = play_one(engine_is_black, depth, rng);
        if      (r > 0) ++wins;
        else if (r < 0) ++losses;
        else            ++draws;
    }
    const double rate = (wins + 0.5 * draws) / games;

    std::cout << "engine=" << wins << " wins  "
              << losses << " losses  "
              << draws  << " draws   "
              << "rate=" << rate
              << " (depth=" << depth
              << ", games=" << games
              << ", seed=" << seed << ")\n";

    // Gate 1 : rate >= 0.95 (≥95% wins/draws).
    return rate >= 0.95 ? 0 : 2;
}
