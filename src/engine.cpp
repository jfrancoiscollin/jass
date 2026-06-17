// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "engine.hpp"

#include "movegen.hpp"
#include "zobrist.hpp"

#include <optional>

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
    return search(lim);
}

SearchResult Engine::search(const SearchLimits& limits) {
    if (use_book_) {
        std::optional<Move> bm = scan_book_active_ ? scan_book_.probe(pos_)
                                                   : book_.probe(pos_);
        if (bm) {
            SearchResult r;
            r.best_move = *bm;
            r.score     = 0;
            r.depth     = 0;
            r.nodes     = 0;
            r.from_book = true;
            r.pv.push_back(*bm);
            return r;
        }
    }
    // Propagate the engine-level NNUE pointer when the caller didn't
    // pin one explicitly. An explicit `limits.nnue` (including null on
    // purpose) always wins, which lets tournaments override the
    // default per game.
    if (limits.nnue == nullptr && nnue_ != nullptr) {
        SearchLimits effective = limits;
        effective.nnue = nnue_;
        return ::jass::search(pos_, effective, tt_, hash_history_);
    }
    return ::jass::search(pos_, limits, tt_, hash_history_);
}

bool Engine::load_book(std::string_view path) {
    // Auto-detect the format: a JBK2 file is accepted only by the Scan-style
    // loader and a JBOK file only by the classic loader, so trying the Scan
    // loader first cleanly routes each format to the right table.
    if (scan_book_.load(path)) {
        scan_book_active_ = true;
        return true;
    }
    scan_book_active_ = false;
    return book_.load(path);
}

std::size_t Engine::book_size() const noexcept {
    return scan_book_active_ ? scan_book_.size() : book_.size();
}

void Engine::clear_tt() noexcept {
    tt_.clear();
}

void Engine::resize_tt_mb(std::size_t mb) {
    tt_.resize_mb(mb);
}

}  // namespace jass
