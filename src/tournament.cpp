// SPDX-License-Identifier: MIT
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

GameRecord play_game(const EngineConfig& white_cfg,
                     const EngineConfig& black_cfg,
                     int                 max_plies) {
    Engine w_engine;
    Engine b_engine;
    w_engine.use_book(white_cfg.use_book);
    b_engine.use_book(black_cfg.use_book);
    w_engine.new_game();
    b_engine.new_game();

    for (int ply = 0; ply < max_plies; ++ply) {
        const Position& pos = w_engine.position();

        // Terminal: no legal move → side to move loses.
        MoveList ml;
        generate_legal_moves(pos, ml);
        if (ml.empty()) {
            return {pos.side_to_move() == Color::White ? GameOutcome::BlackWin
                                                      : GameOutcome::WhiteWin,
                    ply, "no legal moves"};
        }

        // 25-move rule.
        if (pos.halfmove_clock() >= FIFTY_MOVE_PLIES) {
            return {GameOutcome::Draw, ply, "25-move rule"};
        }

        // 3-fold repetition over the actual game history.
        const ZobristHash h = zobrist_hash(pos);
        if (repetition_count(w_engine.hash_history(), h) >= 2) {
            return {GameOutcome::Draw, ply, "3-fold repetition"};
        }

        Engine&             cur = (pos.side_to_move() == Color::White) ? w_engine : b_engine;
        const EngineConfig& cfg = (pos.side_to_move() == Color::White) ? white_cfg : black_cfg;
        const SearchResult  r   = cur.search(make_limits(cfg));

        // Both engines must stay in lock-step to keep their game history
        // (used by the search for repetition detection) accurate.
        const bool ok_w = w_engine.apply_move(r.best_move);
        const bool ok_b = b_engine.apply_move(r.best_move);
        if (!ok_w || !ok_b) {
            // Should never happen — the search returns legal moves.
            return {pos.side_to_move() == Color::White ? GameOutcome::BlackWin
                                                      : GameOutcome::WhiteWin,
                    ply, "illegal engine move"};
        }
    }
    return {GameOutcome::Draw, max_plies, "ply cap"};
}

TournamentResult run_tournament(const EngineConfig& a,
                                const EngineConfig& b,
                                int                 pairs,
                                int                 max_plies) {
    TournamentResult tr;
    for (int i = 0; i < pairs; ++i) {
        // A as white, B as black.
        const GameRecord g1 = play_game(a, b, max_plies);
        if      (g1.outcome == GameOutcome::WhiteWin) ++tr.a_wins;
        else if (g1.outcome == GameOutcome::BlackWin) ++tr.b_wins;
        else                                          ++tr.draws;

        // B as white, A as black.
        const GameRecord g2 = play_game(b, a, max_plies);
        if      (g2.outcome == GameOutcome::BlackWin) ++tr.a_wins;
        else if (g2.outcome == GameOutcome::WhiteWin) ++tr.b_wins;
        else                                          ++tr.draws;
    }
    return tr;
}

}  // namespace jass
