"""Paired, deterministic candidate-versus-parent arena."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from .game_graph import GameGraph
from .model import MiniJassMLP
from .search import InferenceCache, SearchConfig, bounded_negamax


@dataclass(frozen=True)
class ArenaConfig:
    pairs: int = 8
    max_plies: int = 128
    search_depth: int = 3
    node_budget: int = 8
    epsilon: float = 0.0
    confidence_z: float = 1.96


def _play_game(
    graph: GameGraph,
    candidate: MiniJassMLP,
    parent: MiniJassMLP,
    candidate_starts: bool,
    config: ArenaConfig,
    seed: int,
) -> float:
    rng = np.random.default_rng(seed)
    candidate_cache = InferenceCache()
    parent_cache = InferenceCache()
    state_id = 0
    plies = 0
    terminal: float | None = None
    for plies in range(config.max_plies):
        terminal = graph.terminal_value(state_id)
        if terminal is not None:
            break
        candidate_turn = (plies % 2 == 0) == candidate_starts
        model = candidate if candidate_turn else parent
        cache = candidate_cache if candidate_turn else parent_cache
        legal = graph.legal_actions(state_id)
        if config.epsilon > 0 and rng.random() < config.epsilon:
            action = int(rng.choice(legal))
        else:
            result = bounded_negamax(
                graph,
                model,
                state_id,
                SearchConfig(config.search_depth, config.node_budget),
                cache,
            )
            action = result.selected_action
        state_id = graph.child(state_id, action)
    else:
        terminal = 0.0

    if terminal is None:
        raise RuntimeError("arena game ended without an outcome")
    starting_side_outcome = terminal if plies % 2 == 0 else -terminal
    return starting_side_outcome if candidate_starts else -starting_side_outcome


def run_arena(
    graph: GameGraph,
    candidate: MiniJassMLP,
    parent: MiniJassMLP,
    config: ArenaConfig,
    seed: int,
) -> dict[str, Any]:
    if config.pairs < 1:
        raise ValueError("arena requires at least one pair")
    outcomes: list[float] = []
    paired_seeds: list[int] = []
    for pair in range(config.pairs):
        pair_seed = seed + pair
        paired_seeds.append(pair_seed)
        outcomes.append(_play_game(graph, candidate, parent, True, config, pair_seed))
        outcomes.append(_play_game(graph, candidate, parent, False, config, pair_seed))
    wins = sum(outcome > 0 for outcome in outcomes)
    draws = sum(outcome == 0 for outcome in outcomes)
    losses = sum(outcome < 0 for outcome in outcomes)
    games = len(outcomes)
    score = (wins + 0.5 * draws) / games
    standard_error = math.sqrt(max(score * (1.0 - score), 0.0) / games)
    lower_bound = max(0.0, score - config.confidence_z * standard_error)
    return {
        "games": games,
        "pairs": config.pairs,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score": score,
        "score_lower_confidence_bound": lower_bound,
        "confidence_z": config.confidence_z,
        "paired_seeds": paired_seeds,
    }
