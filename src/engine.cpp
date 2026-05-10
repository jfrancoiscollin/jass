// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Jean-François Collin

#include "engine.hpp"

#include "movegen.hpp"
#include "zobrist.hpp"

namespace jass {

namespace {
constexpr std::size_t DEFAULT_TT_MB = 16;
}  // namespace

Engine::Engine() : pos_(Position::start_position()) {
    tt_.resize_mb(DEFAULT_TT_MB);
}

Engine::Engine(std::size_t tt_mb) : pos_(Position::start_position()) {
    tt_.resize_mb(tt_mb);
}

void Engine::new_game() {
    pos_ = Position::start_position();
    tt_.clear();
    hash_history_.clear();
}

void Engine::set_position(const Position& pos) noexcept {
    pos_ = pos;
    hash_history_.clear();
}

bool Engine::set_position_fen(std::string_view fen) {
    auto p = Position::from_fen(fen);
    if (!p) return false;
    pos_ = *p;
    hash_history_.clear();
    return true;
}

bool Engine::apply_move(const Move& m) {
    MoveList ml;
    generate_legal_moves(pos_, ml);
    for (const auto& legal : ml) {
        if (legal == m) {
            // Record the *predecessor* before the move so search() can spot
            // repetitions of any earlier game position.
            hash_history_.push_back(zobrist_hash(pos_));
            pos_ = pos_.after(m);
            return true;
        }
    }
    return false;
}

SearchResult Engine::search(int max_depth) {
    SearchLimits lim;
    lim.max_depth = max_depth;
    return ::jass::search(pos_, lim, tt_, hash_history_);
}

void Engine::clear_tt() noexcept {
    tt_.clear();
}

void Engine::resize_tt_mb(std::size_t mb) {
    tt_.resize_mb(mb);
}

}  // namespace jass
