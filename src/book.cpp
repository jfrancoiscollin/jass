// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "book.hpp"

#include "movegen.hpp"

#include <utility>
#include <vector>

namespace jass {

namespace {

// Each opening line is a flat list of (from, to) pairs starting from the
// initial position; intermediate stops are not needed because the book
// only needs the (from, to) endpoints to disambiguate a legal move.
//
// The lines were chosen from elementary international-draughts opening
// theory — the kind of moves a beginner would play almost reflexively.
// They are not copied from any opening database.
struct Step { int from; int to; };

const std::vector<std::vector<Step>> OPENING_LINES = {
    // Centre opening (32-28) and a few black replies + replies-to-replies.
    {{32, 28}, {19, 23}, {28, 19}, {14, 23}},
    {{32, 28}, {18, 22}, {37, 32}},
    {{32, 28}, {18, 23}, {38, 32}},
    {{32, 28}, {17, 22}, {28, 19}, {14, 23}},

    // Roozenburg-style 33-29.
    {{33, 28}, {18, 22}, {39, 33}},
    {{33, 29}, {19, 23}, {35, 30}},
    {{33, 29}, {18, 22}, {39, 33}},

    // 31-26 lateral push.
    {{31, 26}, {17, 22}, {37, 31}},
    {{31, 26}, {17, 21}, {26, 22}},
    {{31, 26}, {18, 22}, {37, 31}},

    // 34-30 wing.
    {{34, 30}, {20, 25}, {30, 24}},
    {{34, 30}, {19, 24}, {30, 19}},

    // 35-30.
    {{35, 30}, {20, 25}, {40, 35}},
};

}  // namespace

Book::Book() {
    populate();
}

void Book::populate() {
    for (const auto& line : OPENING_LINES) {
        Position pos = Position::start_position();

        for (const Step& s : line) {
            // Find the legal move whose (from, to) match this step.
            MoveList ml;
            generate_legal_moves(pos, ml);
            const Move* found = nullptr;
            for (const auto& m : ml) {
                if (static_cast<int>(m.from) == s.from
                 && static_cast<int>(m.to)   == s.to) {
                    found = &m;
                    break;
                }
            }
            if (!found) break;  // line invalid, skip the rest

            // First entry seen for this position wins; subsequent lines
            // sharing the same prefix don't overwrite.
            entries_.emplace(zobrist_hash(pos), *found);
            pos = pos.after(*found);
        }
    }
}

std::optional<Move> Book::probe(const Position& pos) const {
    const auto it = entries_.find(zobrist_hash(pos));
    if (it == entries_.end()) return std::nullopt;

    // Defensive: confirm the stored move is legal in this position. A
    // hash collision (or tampered table) could otherwise have us emit
    // an illegal move.
    MoveList ml;
    generate_legal_moves(pos, ml);
    for (const auto& m : ml) {
        if (m == it->second) return m;
    }
    return std::nullopt;
}

}  // namespace jass
