// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin
//
// `Engine` — a long-lived facade around `Position`, the move generator and
// the search. It owns a transposition table that survives across `search()`
// calls so iterative deepening reuses prior work and successive moves of a
// game share their lookup data.
//
// This is the type intended to back the HUB front-end and the WASM bindings.

#pragma once

#include "position.hpp"
#include "search.hpp"
#include "tt.hpp"
#include "types.hpp"

#include <cstddef>
#include <string_view>

namespace jass {

class Engine {
public:
    Engine();
    explicit Engine(std::size_t tt_mb);

    // Reset to the standard initial position and clear the TT. Use at the
    // start of a new game.
    void new_game();

    // Replace the current position. The TT is *not* cleared — entries
    // produced by previous searches remain available if their hash keys
    // happen to apply to the new tree.
    void set_position(const Position& pos) noexcept;
    bool set_position_fen(std::string_view fen);

    const Position& position() const noexcept { return pos_; }

    // Apply a move to the current position. Returns false (and leaves the
    // position unchanged) if `m` is not in the current legal-move list.
    bool apply_move(const Move& m);

    // Search the current position with iterative deepening up to the given
    // depth. The persistent TT is reused.
    SearchResult search(int max_depth);

    // Direct TT control for callers that want fine-grained behaviour.
    void clear_tt() noexcept;
    void resize_tt_mb(std::size_t mb);

    std::size_t tt_size() const noexcept { return tt_.size(); }

private:
    Position           pos_;
    TranspositionTable tt_;
};

}  // namespace jass
