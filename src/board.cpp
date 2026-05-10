// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "board.hpp"

namespace jass {

namespace {

// Build the 4-direction neighbour table from the FMJD geometry.
constexpr NeighbourTable build_neighbour_table() {
    NeighbourTable t{};
    for (auto& row : t.data) row.fill(NO_SQUARE);

    for (int s = FIRST_SQUARE; s <= LAST_SQUARE; ++s) {
        const Square sq  = static_cast<Square>(s);
        const int    r   = row_of(sq);
        const int    c   = col_of(sq);

        struct Step { Dir d; int dr; int dc; };
        constexpr std::array<Step, NUM_DIRS> steps = {{
            {Dir::UpLeft,    -1, -1},
            {Dir::UpRight,   -1, +1},
            {Dir::DownLeft,  +1, -1},
            {Dir::DownRight, +1, +1},
        }};

        for (const auto& [dir, dr, dc] : steps) {
            const int nr = r + dr;
            const int nc = c + dc;
            if (nr < 0 || nr >= BOARD_SIDE || nc < 0 || nc >= BOARD_SIDE) {
                continue;
            }
            // Recover the FMJD square number for (nr, nc).
            // On even rows the dark squares sit at odd columns and on odd
            // rows at even columns; the column index inside the row is
            // therefore (nc - 1) / 2 or nc / 2 respectively.
            const int col_in_row = (nr % 2 == 0) ? (nc - 1) / 2 : nc / 2;
            const Square nsq = static_cast<Square>(nr * 5 + col_in_row + 1);
            t.data[static_cast<std::size_t>(sq)]
                  [static_cast<std::size_t>(dir)] = nsq;
        }
    }
    return t;
}

constinit const NeighbourTable kNeighbourTable = build_neighbour_table();

}  // namespace

const NeighbourTable& neighbours() { return kNeighbourTable; }

Square ray_step(Square s, Dir d, int n) noexcept {
    Square cur = s;
    for (int i = 0; i < n; ++i) {
        cur = neighbour(cur, d);
        if (cur == NO_SQUARE) return NO_SQUARE;
    }
    return cur;
}

}  // namespace jass
