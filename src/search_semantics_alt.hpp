// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once

#include "search.hpp"
#include "tt.hpp"

#include <cstddef>
#include <vector>

namespace jass {

// HOME-only search entry point. Its implementation is the frozen Attribution
// V1 search semantics compiled under distinct public symbols so production
// jass_lib keeps the current develop/V4 search byte-for-byte.
SearchResult attribution_search_internal(
    const Position& pos,
    const SearchLimits& limits,
    TranspositionTable& tt,
    const std::vector<ZobristHash>& game_history);

class AttributionEngine {
public:
    AttributionEngine() { tt_.resize_mb(16); }
    explicit AttributionEngine(std::size_t tt_mb) { tt_.resize_mb(tt_mb); }

    void new_game() {
        pos_ = Position::start_position();
        history_.clear();
        tt_.clear();
    }
    void set_position(const Position& pos) noexcept {
        pos_ = pos;
        history_.clear();
    }
    const Position& position() const noexcept { return pos_; }
    void clear_tt() noexcept { tt_.clear(); }
    void resize_tt_mb(std::size_t mb) { tt_.resize_mb(mb); }
    void use_book(bool yes) noexcept { use_book_ = yes; }
    bool book_enabled() const noexcept { return use_book_; }

    SearchResult search(const SearchLimits& limits) {
        // Attribution V1 preregisters book-off. Refuse to silently introduce a
        // book path into this HOME-only facade.
        if (use_book_) {
            SearchResult out{};
            out.stop_reason = SearchStopReason::External;
            return out;
        }
        return attribution_search_internal(pos_, limits, tt_, history_);
    }

private:
    Position pos_{};
    TranspositionTable tt_{};
    std::vector<ZobristHash> history_{};
    bool use_book_{false};
};

}  // namespace jass
