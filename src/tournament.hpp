// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (c) 2026 Jean-François Collin
//
// Self-play tournament harness.
//
// Pits two `Engine` configurations against each other, drives the games
// to a definite result (no legal moves, 25-move rule, 3-fold repetition
// or a hard ply cap) and counts wins / losses / draws. Useful for
// regression testing a new heuristic against the previous build.

#pragma once

#include "search.hpp"

namespace jass {

struct EngineConfig {
    int  max_depth = 6;
    int  threads   = 1;
    int  movetime_ms = 0;   // 0 → use depth only
    bool use_book   = false;
};

enum class GameOutcome : std::uint8_t {
    WhiteWin,
    BlackWin,
    Draw,
};

struct GameRecord {
    GameOutcome outcome;
    int         plies;
    const char* reason;  // "no legal moves", "25-move rule", "3-fold repetition", "ply cap"
};

// Play one game from the standard initial position. White plays per
// `white_cfg`, Black per `black_cfg`. Stops at `max_plies` and reports
// a draw with reason "ply cap" if the game hasn't terminated by then.
GameRecord play_game(const EngineConfig& white_cfg,
                     const EngineConfig& black_cfg,
                     int                 max_plies = 300);

struct TournamentResult {
    int a_wins = 0;
    int b_wins = 0;
    int draws  = 0;
};

// Run a colour-swap pair of games: A as white vs B as black, then B as
// white vs A as black, repeated `pairs` times. With `pairs = 1` the
// result is a 2-game match.
TournamentResult run_tournament(const EngineConfig& a,
                                const EngineConfig& b,
                                int                 pairs = 1,
                                int                 max_plies = 300);

}  // namespace jass
