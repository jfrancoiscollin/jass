// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin

#include "tournament.hpp"

#include "engine.hpp"
#include "movegen.hpp"
#include "position.hpp"
#include "zobrist.hpp"

namespace jass {

namespace {

SearchLimits make_limits(const EngineConfig& cfg) {
    SearchLimits l;
    l.max_depth   = cfg.max_depth;
    l.threads     = cfg.threads;
    l.movetime_ms = cfg.movetime_ms;
    return l;
}

int repetition_count(const std::vector<ZobristHash>& history,
                     ZobristHash                     current) noexcept {
    int n = 0;
    for (auto h : history) if (h == current) ++n;
    return n;
}

}  // namespace

std::vector<Position> default_opening_pool() {
    const Position start = Position::start_position();
    MoveList ml;
    generate_legal_moves(start, ml);
    std::vector<Position> pool;
    pool.reserve(ml.size());
    for (const auto& m : ml) pool.push_back(start.after(m));
    return pool;
}

GameRecord play_game(const EngineConfig& white_cfg,
                     const EngineConfig& black_cfg,
                     int                 max_plies,
                     const Position*     start) {
    Engine w_engine;
    Engine b_engine;
    w_engine.use_book(white_cfg.use_book);
    b_engine.use_book(black_cfg.use_book);

    // Both engines need to share the *same* starting state. `new_game`
    // resets to the standard initial position and clears the TT and
    // hash history; `set_position` then replaces the position when an
    // opening was specified, leaving the TT clear and the history
    // empty so the search starts from a clean slate.
    w_engine.new_game();
    b_engine.new_game();
    if (start) {
        w_engine.set_position(*start);
        b_engine.set_position(*start);
    }

    for (int ply = 0; ply < max_plies; ++ply) {
        const Position& pos = w_engine.position();

        MoveList ml;
        generate_legal_moves(pos, ml);
        if (ml.empty()) {
            return {pos.side_to_move() == Color::White ? GameOutcome::BlackWin
                                                      : GameOutcome::WhiteWin,
                    ply, "no legal moves"};
        }
        if (pos.halfmove_clock() >= FIFTY_MOVE_PLIES) {
            return {GameOutcome::Draw, ply, "25-move rule"};
        }
        const ZobristHash h = zobrist_hash(pos);
        if (repetition_count(w_engine.hash_history(), h) >= 2) {
            return {GameOutcome::Draw, ply, "3-fold repetition"};
        }

        Engine&             cur = (pos.side_to_move() == Color::White) ? w_engine : b_engine;
        const EngineConfig& cfg = (pos.side_to_move() == Color::White) ? white_cfg : black_cfg;
        const SearchResult  r   = cur.search(make_limits(cfg));

        const bool ok_w = w_engine.apply_move(r.best_move);
        const bool ok_b = b_engine.apply_move(r.best_move);
        if (!ok_w || !ok_b) {
            return {pos.side_to_move() == Color::White ? GameOutcome::BlackWin
                                                      : GameOutcome::WhiteWin,
                    ply, "illegal engine move"};
        }
    }
    return {GameOutcome::Draw, max_plies, "ply cap"};
}

TournamentResult run_tournament(const EngineConfig&          a,
                                const EngineConfig&          b,
                                int                          pairs,
                                int                          max_plies,
                                const std::vector<Position>* openings) {
    TournamentResult tr;

    // If the caller didn't supply an opening pool, build the default one.
    // We materialise it locally so the rest of the loop has a single
    // pointer to iterate against.
    const std::vector<Position> default_pool = openings ? std::vector<Position>{}
                                                       : default_opening_pool();
    const std::vector<Position>& pool = openings ? *openings : default_pool;

    auto record = [&](const GameRecord& g, bool a_is_white) {
        ++tr.games;
        const bool a_won = (g.outcome == GameOutcome::WhiteWin &&  a_is_white)
                       ||  (g.outcome == GameOutcome::BlackWin && !a_is_white);
        const bool b_won = (g.outcome == GameOutcome::WhiteWin && !a_is_white)
                       ||  (g.outcome == GameOutcome::BlackWin &&  a_is_white);
        if      (a_won) ++tr.a_wins;
        else if (b_won) ++tr.b_wins;
        else            ++tr.draws;
    };

    if (pool.empty()) {
        // Nothing to iterate; play from the start position only.
        for (int i = 0; i < pairs; ++i) {
            record(play_game(a, b, max_plies, /*start=*/nullptr), /*a_is_white=*/true);
            record(play_game(b, a, max_plies, /*start=*/nullptr), /*a_is_white=*/false);
        }
        return tr;
    }

    for (int i = 0; i < pairs; ++i) {
        for (const Position& opening : pool) {
            record(play_game(a, b, max_plies, &opening), /*a_is_white=*/true);
            record(play_game(b, a, max_plies, &opening), /*a_is_white=*/false);
        }
    }
    return tr;
}

}  // namespace jass
