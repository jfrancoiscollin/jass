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

#include "position.hpp"
#include "search.hpp"

#include <vector>

namespace jass {

// Forward declaration so an NNUE pointer can travel through tournament
// configs without dragging in nnue.hpp.
class INetwork;

struct EngineConfig {
    int                  max_depth   = 6;
    int                  threads     = 1;
    int                  movetime_ms = 0;       // 0 → use depth only
    bool                 use_book    = false;
    // Optional NNUE-style network — when non-null, the engine uses
    // `INetwork::evaluate()` instead of the handcrafted eval at every
    // leaf in the search. Any concrete network (Linear, MLP, …) works.
    const INetwork*      nnue        = nullptr;
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

// Play one game from `start` (or the standard initial position when
// `start` is null). White plays per `white_cfg`, Black per `black_cfg`.
// Stops at `max_plies` and reports a draw with reason "ply cap" if the
// game hasn't terminated by then.
GameRecord play_game(const EngineConfig& white_cfg,
                     const EngineConfig& black_cfg,
                     int                 max_plies = 300,
                     const Position*     start     = nullptr);

// The 9 reachable positions after one half-move from the start — used
// as the default opening pool when the tournament caller doesn't
// provide its own. Same engine playing the same configuration can no
// longer trivially mirror itself; each game starts from a different
// first move.
std::vector<Position> default_opening_pool();

struct TournamentResult {
    int a_wins = 0;
    int b_wins = 0;
    int draws  = 0;
    int games  = 0;   // total = a_wins + b_wins + draws
};

// Run a colour-swap match. For each opening in `openings` (or the
// `default_opening_pool()` if empty), and for each of `pairs`
// repetitions, play A as white then B as white. Total games:
// `2 × pairs × openings.size()`.
TournamentResult run_tournament(const EngineConfig&         a,
                                const EngineConfig&         b,
                                int                         pairs        = 1,
                                int                         max_plies    = 300,
                                const std::vector<Position>* openings    = nullptr);

}  // namespace jass
