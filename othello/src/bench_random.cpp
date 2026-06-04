// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Bench : N games of (engine + alpha-beta) vs random player.
// Gate 1 of the Phase Pattern-1 POC : engine should win ≥95%.
//
// CLI :
//   othello_bench_random [games=100] [depth=4] [seed=42]
//                        [weights=basic]
//   weights : "basic" (default) → eval_basic
//             else path to OTHW weights file → eval_pattern
//
// Output : "engine=W wins  L losses  D draws   rate=X.XXX"

#include "board.hpp"
#include "eval.hpp"
#include "movegen.hpp"
#include "search.hpp"
#include "weights.hpp"

#include <cstdint>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <optional>
#include <random>
#include <string>

namespace {

using namespace othello;

using EvalFn = std::function<int(const Board&)>;

EvalFn make_eval(const std::string& spec, std::optional<Weights>& storage) {
    if (spec == "basic") {
        return [](const Board& b) { return eval_basic(b); };
    }
    std::string err;
    auto w = load_weights(spec, &err);
    if (!w) {
        std::cerr << "failed to load weights '" << spec << "' : " << err << "\n";
        std::exit(3);
    }
    storage = std::move(w);
    const std::int32_t* ptr = storage->w.data();
    return [ptr](const Board& b) { return eval_pattern(b, ptr); };
}

Square random_move(const Board& b, std::mt19937& rng) {
    MoveList ml;
    generate_legal_moves(b, ml);
    if (ml.empty()) return NO_SQUARE;
    std::uniform_int_distribution<std::size_t> dist(0, ml.size() - 1);
    return ml[dist(rng)];
}

int play_one(bool engine_is_black, int depth, const EvalFn& eval,
             std::mt19937& rng) {
    Board b = Board::start_position();
    SearchConfig cfg;
    cfg.max_depth = depth;
    cfg.evaluator = eval;

    while (!b.is_game_over()) {
        const bool engine_turn = (b.stm == Color::Black) == engine_is_black;
        Square mv = engine_turn ? search(b, cfg).best_move
                                : random_move(b, rng);
        apply_move(b, mv);
    }
    const int blk = b.black_count();
    const int wht = b.white_count();
    const int engine_pc = engine_is_black ? blk : wht;
    const int opp_pc    = engine_is_black ? wht : blk;
    if (engine_pc > opp_pc) return +1;
    if (engine_pc < opp_pc) return -1;
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    const int games = (argc > 1) ? std::atoi(argv[1]) : 100;
    const int depth = (argc > 2) ? std::atoi(argv[2]) : 4;
    const std::uint32_t seed = (argc > 3)
        ? static_cast<std::uint32_t>(std::atoi(argv[3])) : 42U;
    const std::string weights_spec = (argc > 4) ? argv[4] : "basic";

    std::optional<Weights> w_store;
    const auto eval = make_eval(weights_spec, w_store);

    std::mt19937 rng(seed);
    int wins = 0, losses = 0, draws = 0;
    for (int i = 0; i < games; ++i) {
        const bool engine_is_black = (i % 2 == 0);
        const int r = play_one(engine_is_black, depth, eval, rng);
        if      (r > 0) ++wins;
        else if (r < 0) ++losses;
        else            ++draws;
    }
    const double rate = (wins + 0.5 * draws) / games;

    std::cout << "engine=" << wins << " wins  "
              << losses << " losses  "
              << draws  << " draws   "
              << "rate=" << rate
              << " (engine=" << weights_spec
              << ", depth=" << depth
              << ", games=" << games
              << ", seed=" << seed << ")\n";

    return rate >= 0.95 ? 0 : 2;
}
