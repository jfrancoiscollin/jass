// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Head-to-head between two evaluators (typically pattern vs basic).
//   othello_bench_eval_vs_eval <weights_A.bin or "basic">
//                              <weights_B.bin or "basic">
//                              [games=100] [depth=4] [seed=42] [random_plies=8]
//
// Both engines are deterministic per (board, depth, eval), so a
// random opening (`random_plies` of uniform-random play) is needed
// to diversify games. The same opening is played by both engines (A
// and B alternate colours), so outcomes only differ via the eval.
//
// Result : "A=W wins L losses D draws  rate=X.XXX (from A's POV)"
// Exit code 0 if rate_A >= 0.50 (A at least matches B), 2 otherwise.

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
#include <vector>

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
        std::cerr << "failed to load weights from '" << spec
                  << "' : " << err << "\n";
        std::exit(3);
    }
    storage = std::move(w);
    const std::int32_t* ptr = storage->w.data();
    return [ptr](const Board& b) { return eval_pattern(b, ptr); };
}

// Pre-roll a random opening : `n_plies` non-pass plies from start.
// Same opening can be re-used to play both colour-swap halves.
Board random_opening(int n_plies, std::mt19937& rng) {
    Board pos = Board::start_position();
    int done = 0;
    while (done < n_plies && !pos.is_game_over()) {
        MoveList ml;
        generate_legal_moves(pos, ml);
        if (ml.empty()) {
            apply_move(pos, NO_SQUARE);  // forced pass, not counted
            continue;
        }
        std::uniform_int_distribution<std::size_t> d(0, ml.size() - 1);
        apply_move(pos, ml[d(rng)]);
        ++done;
    }
    return pos;
}

// Play one game from `start`. Returns +1 if A wins (= side
// `a_is_black` wins), -1 if B wins, 0 draw.
int play_one(Board pos, bool a_is_black, int depth,
             const EvalFn& a, const EvalFn& b) {
    SearchConfig ca, cb;
    ca.max_depth = depth; ca.evaluator = a;
    cb.max_depth = depth; cb.evaluator = b;

    while (!pos.is_game_over()) {
        const bool a_turn = (pos.stm == Color::Black) == a_is_black;
        const Square mv = a_turn ? search(pos, ca).best_move
                                 : search(pos, cb).best_move;
        apply_move(pos, mv);
    }
    const int blk = pos.black_count();
    const int wht = pos.white_count();
    const int a_pc = a_is_black ? blk : wht;
    const int b_pc = a_is_black ? wht : blk;
    if (a_pc > b_pc) return +1;
    if (a_pc < b_pc) return -1;
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: othello_bench_eval_vs_eval "
                     "<weights_A or \"basic\"> <weights_B or \"basic\"> "
                     "[games=100] [depth=4] [seed=42]\n";
        return 1;
    }
    const std::string spec_a = argv[1];
    const std::string spec_b = argv[2];
    const int games = (argc > 3) ? std::atoi(argv[3]) : 100;
    const int depth = (argc > 4) ? std::atoi(argv[4]) : 4;
    const std::uint32_t seed = (argc > 5)
        ? static_cast<std::uint32_t>(std::atoi(argv[5])) : 42U;
    const int random_plies = (argc > 6) ? std::atoi(argv[6]) : 8;

    std::optional<Weights> wa_store, wb_store;
    auto a_eval = make_eval(spec_a, wa_store);
    auto b_eval = make_eval(spec_b, wb_store);

    std::mt19937 rng(seed);
    int wins = 0, losses = 0, draws = 0;
    // Play in pairs : each random opening is used twice with A/B
    // colour swapped. This minimises opening-luck bias.
    for (int g = 0; g < games; ++g) {
        const bool start_new_pair = (g % 2 == 0);
        static Board last_opening;
        if (start_new_pair) {
            last_opening = random_opening(random_plies, rng);
        }
        const bool a_is_black = start_new_pair;  // A=Black on odd-indexed pair start
        const int r = play_one(last_opening, a_is_black, depth, a_eval, b_eval);
        if      (r > 0) ++wins;
        else if (r < 0) ++losses;
        else            ++draws;
    }
    const double rate = (wins + 0.5 * draws) / games;
    std::cout << "A=" << wins << " wins  "
              << losses << " losses  "
              << draws << " draws  "
              << "rate=" << rate
              << " (A=" << spec_a << " vs B=" << spec_b
              << ", depth=" << depth << ", games=" << games << ")\n";

    return rate >= 0.5 ? 0 : 2;
}
