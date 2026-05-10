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
#include "position.hpp"
#include "search.hpp"
#include "tournament.hpp"

#include <charconv>
#include <iostream>
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

int run_tournament_mode(int argc, char** argv) {
    // Usage: --tournament [depth_a] [depth_b] [pairs]
    // Defaults: depth_a=4, depth_b=6, pairs=1 (so 2 games total).
    int depth_a = 4, depth_b = 6, pairs = 1;
    if (argc > 2) depth_a = parse_int_or(argv[2], depth_a);
    if (argc > 3) depth_b = parse_int_or(argv[3], depth_b);
    if (argc > 4) pairs   = parse_int_or(argv[4], pairs);

    EngineConfig a; a.max_depth = depth_a;
    EngineConfig b; b.max_depth = depth_b;

    std::cout << "Tournament: A(depth=" << depth_a
              << ") vs B(depth=" << depth_b
              << "), " << (pairs * 2) << " games\n";

    const TournamentResult r = run_tournament(a, b, pairs);
    std::cout << "Result: A=" << r.a_wins
              << " B="        << r.b_wins
              << " Draws="    << r.draws << '\n';
    return 0;
}

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        const std::string_view a{argv[i]};
        if      (a == "--smoke")      return run_smoke();
        else if (a == "--tournament") return run_tournament_mode(argc, argv);
        else if (a == "--version") { std::cout << "Jass 0.0.1\n"; return 0; }
        else if (a == "--help") {
            std::cout <<
                "Usage: jass [--smoke|--tournament [a b pairs]|--version|--help]\n"
                "Default: read HUB-style commands from stdin.\n"
                "  --smoke                          run a self-contained demo\n"
                "  --tournament [da db pairs]       play a colour-swap match\n"
                "                                   between depth-da and depth-db\n"
                "                                   engines (default 4 vs 6, 2 games)\n"
                "  --version                        print the engine version\n";
            return 0;
        }
    }

    HubFrontEnd hub(std::cin, std::cout);
    return hub.run();
}
