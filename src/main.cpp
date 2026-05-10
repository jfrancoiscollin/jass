// SPDX-License-Identifier: MIT
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

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) {
        const std::string_view a{argv[i]};
        if      (a == "--smoke")   return run_smoke();
        else if (a == "--version") { std::cout << "Jass 0.0.1\n"; return 0; }
        else if (a == "--help") {
            std::cout <<
                "Usage: jass [--smoke|--version|--help]\n"
                "Default: read HUB-style commands from stdin.\n"
                "  --smoke    run a self-contained demo\n"
                "  --version  print the engine version\n";
            return 0;
        }
    }

    HubFrontEnd hub(std::cin, std::cout);
    return hub.run();
}
