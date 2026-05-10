// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Native entry point.
//
// Default: reads HUB-style commands from stdin and writes the responses
// to stdout — the form a draughts GUI expects when launching the engine.
// Pass `--smoke` to run the historical demo (start position, FEN
// round-trip, sample neighbours, depth-6 best-move and a 40-ply
// engine-vs-engine game) instead.

#include "board.hpp"
#include "engine.hpp"
#include "hub.hpp"
#include "movegen.hpp"
#include "nnue.hpp"
#include "position.hpp"
#include "search.hpp"
#include "tournament.hpp"

#include <charconv>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <random>
#include <string>
#include <string_view>

using namespace jass;

namespace {

const char* dir_name(Dir d) {
    switch (d) {
        case Dir::UpLeft:    return "NW";
        case Dir::UpRight:   return "NE";
        case Dir::DownLeft:  return "SW";
        case Dir::DownRight: return "SE";
    }
    return "??";
}

void show_neighbours(Square s) {
    std::cout << "Square " << static_cast<int>(s) << " neighbours:";
    for (Dir d : ALL_DIRS) {
        const Square n = neighbour(s, d);
        std::cout << ' ' << dir_name(d) << '=';
        if (n == NO_SQUARE) std::cout << '-';
        else                std::cout << static_cast<int>(n);
    }
    std::cout << '\n';
}

int run_smoke() {
    const Position start = Position::start_position();
    std::cout << "=== Jass — international draughts engine ===\n\n";
    std::cout << start.to_ascii() << '\n';
    std::cout << "Hub FEN: " << start.to_fen() << "\n\n";

    const auto round_trip = Position::from_fen(start.to_fen());
    std::cout << "FEN round-trip: "
              << (round_trip && *round_trip == start ? "OK" : "FAILED")
              << "\n\n";

    std::cout << "Sample diagonal neighbours:\n";
    for (Square s : {Square{1}, Square{6}, Square{28}, Square{45}, Square{50}}) {
        show_neighbours(s);
    }
    std::cout << '\n';

    Engine engine;
    const SearchResult sr = engine.search(6);
    std::cout << "Search at depth " << sr.depth
              << ": best move "    << format_move(sr.best_move)
              << " (score="        << sr.score
              << ", nodes="        << sr.nodes << ")\n\n";

    std::cout << "Engine-vs-engine smoke game (depth 4, cap 40 plies):\n";
    Engine game;
    for (int ply = 1; ply <= 40; ++ply) {
        MoveList legal;
        generate_legal_moves(game.position(), legal);
        if (legal.empty()) {
            std::cout << "  ply " << ply << ": "
                      << (game.position().side_to_move() == Color::White ? "White" : "Black")
                      << " has no legal move — game over.\n";
            break;
        }
        const SearchResult r = game.search(4);
        std::cout << "  ply " << ply << " ("
                  << (game.position().side_to_move() == Color::White ? 'W' : 'B') << "): "
                  << format_move(r.best_move)
                  << " score=" << r.score << '\n';
        game.apply_move(r.best_move);
    }
    return 0;
}

}  // namespace

int parse_int_or(std::string_view s, int fallback) {
    int v = fallback;
    auto [ptr, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
    return (ec == std::errc{}) ? v : fallback;
}

// -----------------------------------------------------------------------------
// --gen-data: write a binary dataset of (position, target-score) records for
// offline NNUE training.  See `tools/README.md` for the format.
// -----------------------------------------------------------------------------
int run_gen_data_mode(int argc, char** argv) {
    int          n         = 10000;
    const char*  out_path  = "selfplay.bin";
    int          play_depth = 4;       // depth used to advance games
    int          eval_depth = 8;       // depth used to label sampled positions
    int          random_open_plies = 4;

    if (argc > 2) {
        int parsed = parse_int_or(argv[2], -1);
        if (parsed > 0) n = parsed;
    }
    if (argc > 3) out_path = argv[3];

    std::ofstream f(out_path, std::ios::binary);
    if (!f) {
        std::cerr << "error: cannot open " << out_path << " for writing\n";
        return 1;
    }

    // Header: 4 bytes magic + 4 bytes record-count.  We backpatch the count
    // at the end of the run so the file is self-describing even if the
    // requested count is reduced (e.g. all reachable positions were sampled).
    const char magic[4] = {'J', 'N', 'N', 'T'};
    f.write(magic, 4);
    std::uint32_t count_placeholder = 0;
    f.write(reinterpret_cast<const char*>(&count_placeholder), 4);

    std::mt19937_64 rng(0x5eed5eed5eed5eedULL);
    Engine          e;
    e.use_book(false);

    int generated  = 0;
    int game_count = 0;

    while (generated < n) {
        ++game_count;
        e.new_game();

        // Random opening plies for diversity.  Pick uniformly among the legal
        // moves of the current position; this is enough to avoid identical
        // games across runs.
        for (int i = 0; i < random_open_plies; ++i) {
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) break;
            e.apply_move(ml[rng() % ml.size()]);
        }

        for (int ply = 0; ply < 100 && generated < n; ++ply) {
            MoveList ml;
            generate_legal_moves(e.position(), ml);
            if (ml.empty()) break;

            // Sample roughly every fourth ply.
            if ((rng() & 3) == 0) {
                SearchLimits lim;
                lim.max_depth = eval_depth;
                const SearchResult r = e.search(lim);
                const int score = r.score;

                const Position& pos = e.position();
                const std::uint64_t bbs[4] = {
                    pos.white_men(),   pos.white_kings(),
                    pos.black_men(),   pos.black_kings()};
                f.write(reinterpret_cast<const char*>(bbs), 32);
                const std::uint8_t stm = (pos.side_to_move() == Color::White) ? 0 : 1;
                f.write(reinterpret_cast<const char*>(&stm), 1);
                const std::int32_t s32 = static_cast<std::int32_t>(score);
                f.write(reinterpret_cast<const char*>(&s32), 4);

                ++generated;
            }

            // Advance the game with a low-depth move so positions stay diverse.
            SearchLimits lim;
            lim.max_depth = play_depth;
            const SearchResult r = e.search(lim);
            if (!e.apply_move(r.best_move)) break;
        }

        if ((game_count % 50) == 0) {
            std::cout << "  played " << game_count << " games, "
                      << generated << " / " << n << " positions\n";
        }
    }

    // Backpatch the count.
    f.seekp(4, std::ios::beg);
    const std::uint32_t count32 = static_cast<std::uint32_t>(generated);
    f.write(reinterpret_cast<const char*>(&count32), 4);
    f.close();

    std::cout << "wrote " << generated << " records to " << out_path << "\n";
    return 0;
}

// -----------------------------------------------------------------------------
// --benchmark-nnue: pit the trained `LinearNetwork` (loaded from a binary
// weights file) against the handcrafted eval. Both engines are otherwise
// identical (same depth, same threads). Plays a colour-swap match across
// the default opening pool so we get diverse games.
// -----------------------------------------------------------------------------
int run_benchmark_nnue_mode(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: jass --benchmark-nnue <weights.bin> [depth=6] "
                     "[pairs=1]\n";
        return 1;
    }
    const char* weights_path = argv[2];
    const int   depth = (argc > 3) ? parse_int_or(argv[3], 6) : 6;
    const int   pairs = (argc > 4) ? parse_int_or(argv[4], 1) : 1;

    LinearNetwork trained;
    if (!trained.load(weights_path)) {
        std::cerr << "error: cannot load weights from " << weights_path << "\n";
        return 1;
    }

    EngineConfig handcrafted;
    handcrafted.max_depth = depth;
    handcrafted.nnue      = nullptr;

    EngineConfig nnue_cfg;
    nnue_cfg.max_depth = depth;
    nnue_cfg.nnue      = &trained;

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());

    std::cout << "Benchmark: NNUE (" << weights_path
              << ") vs handcrafted, depth " << depth
              << ", " << total_games << " games "
              << "(" << pool.size() << " openings × " << pairs
              << " pairs × 2 colours)\n";

    // A = NNUE, B = handcrafted
    const TournamentResult r = run_tournament(nnue_cfg, handcrafted, pairs);

    std::cout << "Result: NNUE=" << r.a_wins
              << " Handcrafted=" << r.b_wins
              << " Draws="       << r.draws
              << " (total "      << r.games << ")\n";

    // A simple verdict line.  Wins are worth 1 point, draws 0.5.
    const double nnue_score = r.a_wins + 0.5 * r.draws;
    const double rate       = nnue_score / r.games;
    std::cout << "NNUE score rate: " << rate
              << " (" << nnue_score << " / " << r.games << ")\n";
    return 0;
}

int run_tournament_mode(int argc, char** argv) {
    // Usage: --tournament [depth_a] [depth_b] [pairs]
    // Defaults: depth_a=4, depth_b=6, pairs=1 (so 2 games total).
    int depth_a = 4, depth_b = 6, pairs = 1;
    if (argc > 2) depth_a = parse_int_or(argv[2], depth_a);
    if (argc > 3) depth_b = parse_int_or(argv[3], depth_b);
    if (argc > 4) pairs   = parse_int_or(argv[4], pairs);

    EngineConfig a; a.max_depth = depth_a;
    EngineConfig b; b.max_depth = depth_b;

    const auto pool = default_opening_pool();
    const int  total_games = pairs * 2 * static_cast<int>(pool.size());
    std::cout << "Tournament: A(depth=" << depth_a
              << ") vs B(depth=" << depth_b
              << "), " << total_games << " games "
              << "(" << pool.size() << " openings × " << pairs
              << " pairs × 2 colours)\n";

    const TournamentResult r = run_tournament(a, b, pairs);
    std::cout << "Result: A=" << r.a_wins
              << " B="        << r.b_wins
              << " Draws="    << r.draws
              << " (total "   << r.games << ")\n";
    return 0;
}

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        const std::string_view a{argv[i]};
        if      (a == "--smoke")           return run_smoke();
        else if (a == "--tournament")      return run_tournament_mode(argc, argv);
        else if (a == "--gen-data")        return run_gen_data_mode(argc, argv);
        else if (a == "--benchmark-nnue")  return run_benchmark_nnue_mode(argc, argv);
        else if (a == "--version") { std::cout << "Jass 0.0.1\n"; return 0; }
        else if (a == "--help") {
            std::cout <<
                "Usage: jass [--smoke|--tournament [a b pairs]|"
                            "--gen-data [N path]|--benchmark-nnue weights [d p]|"
                            "--version|--help]\n"
                "Default: read HUB-style commands from stdin.\n"
                "  --smoke                          run a self-contained demo\n"
                "  --tournament [da db pairs]       play a colour-swap match\n"
                "                                   between depth-da and depth-db\n"
                "                                   engines (default 4 vs 6, 2 games)\n"
                "  --gen-data [N path]              write N self-play training\n"
                "                                   records to <path> (default\n"
                "                                   10000 to selfplay.bin)\n"
                "  --benchmark-nnue <weights.bin> [depth=6] [pairs=1]\n"
                "                                   pit a trained NNUE (loaded\n"
                "                                   from <weights.bin>) against\n"
                "                                   the handcrafted eval. Plays\n"
                "                                   2*pairs games per opening\n"
                "                                   from the default opening pool.\n"
                "  --version                        print the engine version\n";
            return 0;
        }
    }

    HubFrontEnd hub(std::cin, std::cout);
    return hub.run();
}
