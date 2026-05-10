// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Smoke-test entry point. The HUB front-end and the WASM bindings will land
// in their own translation units; for now this binary serves as a
// hand-runnable demo:
//   1. prints the starting position and validates a FEN round-trip
//   2. shows a few diagonal-neighbour samples
//   3. runs the search at a fixed depth from the initial position
//   4. plays a short engine-vs-engine game to prove that the move
//      generator, applier and search are wired together end-to-end.

#include "board.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "search.hpp"

#include <iostream>
#include <string>

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

std::string move_string(const Move& m) {
    const char sep = m.is_capture() ? 'x' : '-';
    return std::to_string(static_cast<int>(m.from)) + sep +
           std::to_string(static_cast<int>(m.to));
}

}  // namespace

int main() {
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

    SearchLimits limits;
    limits.max_depth = 6;
    const SearchResult sr = search(start, limits);
    std::cout << "Search at depth " << sr.depth
              << ": best move " << move_string(sr.best_move)
              << " (score=" << sr.score
              << ", nodes=" << sr.nodes << ")\n\n";

    // Engine-vs-engine smoke game: each side plays the search's best move
    // until somebody runs out of legal replies (or we reach the cap).
    std::cout << "Engine-vs-engine smoke game (depth 4, cap 40 plies):\n";
    Position pos = start;
    for (int ply = 1; ply <= 40; ++ply) {
        SearchLimits sl;
        sl.max_depth = 4;
        const SearchResult r = search(pos, sl);
        MoveList legal;
        generate_legal_moves(pos, legal);
        if (legal.empty()) {
            std::cout << "  ply " << ply << ": "
                      << (pos.side_to_move() == Color::White ? "White" : "Black")
                      << " has no legal move — game over.\n";
            break;
        }
        std::cout << "  ply " << ply << " ("
                  << (pos.side_to_move() == Color::White ? 'W' : 'B') << "): "
                  << move_string(r.best_move)
                  << " score=" << r.score << '\n';
        pos = pos.after(r.best_move);
    }

    return 0;
}
