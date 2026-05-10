// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Smoke-test entry point. Prints the starting position, exercises the
// FEN round-trip and verifies the diagonal-neighbour table on a few
// reference squares. Eventually this will be replaced by the HUB protocol
// front-end.

#include "board.hpp"
#include "movegen.hpp"
#include "position.hpp"

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

    MoveList moves;
    generate_legal_moves(start, moves);
    std::cout << "Legal moves from the starting position: "
              << moves.size()
              << " (movegen is still a skeleton — expect 0)\n";

    return 0;
}
