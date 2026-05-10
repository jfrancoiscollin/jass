// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// Move generation interface.
//
// Skeleton: the public API is fixed but the implementation is intentionally
// minimal so the rest of the engine (and the test scaffolding) can compile
// and link. Filling in the legal-move logic — including the FMJD
// "majority capture" rule — is the next milestone.

#pragma once

#include "position.hpp"
#include "types.hpp"

#include <vector>

namespace jass {

class MoveList {
public:
    void clear() noexcept { moves_.clear(); }
    void push(const Move& m) { moves_.push_back(m); }

    std::size_t size() const noexcept { return moves_.size(); }
    bool empty() const noexcept { return moves_.empty(); }

    Move&       operator[](std::size_t i)       noexcept { return moves_[i]; }
    const Move& operator[](std::size_t i) const noexcept { return moves_[i]; }

    auto begin()       noexcept { return moves_.begin(); }
    auto end()         noexcept { return moves_.end();   }
    auto begin() const noexcept { return moves_.begin(); }
    auto end()   const noexcept { return moves_.end();   }

private:
    std::vector<Move> moves_;
};

// Generate all *legal* moves for the side to move in `pos`. In international
// draughts this means: if any capture is available, only the capture sequences
// of maximum length are returned (the FMJD majority rule); otherwise quiet
// moves are returned. The current build returns an empty list — the full
// implementation lands in the next milestone.
void generate_legal_moves(const Position& pos, MoveList& out);

}  // namespace jass
