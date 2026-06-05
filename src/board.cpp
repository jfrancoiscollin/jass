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

// Build the king ray table : for each (from, dir), record the sequence
// of squares reached by chaining `neighbour()` calls until off-board.
// Constexpr-evaluated, reads from kNeighbourTable.
constexpr KingRayTable build_king_ray_table() {
    KingRayTable t{};
    for (int s = FIRST_SQUARE; s <= LAST_SQUARE; ++s) {
        const Square from = static_cast<Square>(s);
        const std::size_t from_idx = static_cast<std::size_t>(from);
        for (std::size_t di = 0; di < NUM_DIRS; ++di) {
            KingRay& ray = t.data[from_idx][di];
            Square cur = kNeighbourTable.data[from_idx][di];
            while (cur != NO_SQUARE && ray.length < MAX_RAY_LEN) {
                ray.squares[ray.length] = cur;
                ray.length = static_cast<std::uint8_t>(ray.length + 1);
                cur = kNeighbourTable.data[static_cast<std::size_t>(cur)][di];
            }
        }
    }
    return t;
}

constinit const KingRayTable kKingRayTable = build_king_ray_table();

}  // namespace

const NeighbourTable& neighbours() { return kNeighbourTable; }

const KingRayTable& king_rays() { return kKingRayTable; }

Square ray_step(Square s, Dir d, int n) noexcept {
    Square cur = s;
    for (int i = 0; i < n; ++i) {
        cur = neighbour(cur, d);
        if (cur == NO_SQUARE) return NO_SQUARE;
    }
    return cur;
}

}  // namespace jass
